"""
LangGraph-powered conversational agent that keeps track of structured lead data.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TypedDict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from src.voca.config import Config

logger = logging.getLogger("voca.langgraph")


class LeadData(BaseModel):
    """Structured representation of the key booking/lead fields."""

    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    service_type: Optional[str] = None
    preferred_date: Optional[str] = None
    preferred_time: Optional[str] = None
    number_of_people: Optional[str] = None
    room_type: Optional[str] = None
    notes: Optional[str] = None
    custom_fields: Dict[str, Optional[str]] = Field(default_factory=dict)


class LeadUpdate(BaseModel):
    """LLM-extracted update for the conversation state."""

    lead: LeadData = Field(default_factory=LeadData)
    lead_status: Optional[str] = Field(
        default=None,
        description="Lead status classification such as hot/warm/cold.",
    )
    summary_requested: bool = Field(
        default=False,
        description="True when the host app wants a structured summary response.",
    )


class GraphState(TypedDict, total=False):
    organization_id: Optional[str]
    system_prompt: str
    messages: List[BaseMessage]
    collected_data: Dict[str, Any]
    lead_status: Optional[str]
    transcript: List[Dict[str, Any]]
    summary_requested: bool
    last_reply: Optional[str]


@dataclass
class LangGraphAgentResult:
    reply: str
    messages: List[BaseMessage]
    collected_data: Dict[str, Any]
    lead_status: Optional[str]
    transcript: List[Dict[str, Any]]
    summary_requested: bool


class LangGraphAgent:
    """Wrapper around LangGraph to manage conversation + structured state."""

    def __init__(self, model_name: Optional[str] = None, temperature: Optional[float] = None):
        self.logger = logger
        if not Config.gemini_api_key:
            self.logger.warning("GEMINI_API_KEY missing; LangGraph agent will fail on first call.")

        self.model_name = model_name or "gemini-2.5-flash"
        self.temperature = temperature if temperature is not None else Config.llm_temperature
        self.chat_llm = ChatGoogleGenerativeAI(
            model=self.model_name,
            temperature=self.temperature,
            max_output_tokens=Config.llm_max_tokens,
            convert_system_message_to_human=True,
            google_api_key=Config.gemini_api_key or None,
        )
        self.state_parser = self.chat_llm.with_structured_output(LeadUpdate)
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(GraphState)
        graph.add_node("assistant", self._assistant_node)
        graph.add_node("state_tracker", self._state_tracker_node)
        graph.add_edge("assistant", "state_tracker")
        graph.add_edge("state_tracker", END)
        graph.set_entry_point("assistant")
        return graph.compile()

    def generate_reply(
        self,
        *,
        organization_id: Optional[str],
        system_prompt: str,
        messages: List[BaseMessage],
        collected_data: Dict[str, Any],
        lead_status: Optional[str],
        transcript: List[Dict[str, Any]],
        summary_requested: bool = False,
    ) -> LangGraphAgentResult:
        """Invoke the LangGraph flow and return updated conversation state."""
        state: GraphState = {
            "organization_id": organization_id,
            "system_prompt": system_prompt,
            "messages": messages,
            "collected_data": collected_data.copy(),
            "lead_status": lead_status,
            "transcript": transcript.copy(),
            "summary_requested": summary_requested,
        }
        result: GraphState = self.graph.invoke(state)
        reply = result.get("last_reply") or ""
        return LangGraphAgentResult(
            reply=reply,
            messages=result.get("messages", messages),
            collected_data=result.get("collected_data", collected_data),
            lead_status=result.get("lead_status", lead_status),
            transcript=result.get("transcript", transcript),
            summary_requested=result.get("summary_requested", summary_requested),
        )

    # Graph nodes -----------------------------------------------------------------
    def _assistant_node(self, state: GraphState) -> GraphState:
        conversation: List[BaseMessage] = [SystemMessage(content=state["system_prompt"])]
        conversation.extend(state.get("messages", []))

        response = self.chat_llm.invoke(conversation)
        if isinstance(response, AIMessage):
            reply_text = response.content
        else:
            # Fallback in unexpected cases
            reply_text = getattr(response, "content", str(response))
            response = AIMessage(content=reply_text)

        updated_messages = state.get("messages", []).copy()
        updated_messages.append(response)

        updated_transcript = state.get("transcript", []).copy()
        updated_transcript.append({"role": "assistant", "content": reply_text})

        new_state = state.copy()
        new_state["messages"] = updated_messages
        new_state["transcript"] = updated_transcript
        new_state["last_reply"] = reply_text
        return new_state

    def _state_tracker_node(self, state: GraphState) -> GraphState:
        tracker_instructions = (
            "You are a CRM state tracker. "
            "Given the full conversation, extract any newly provided values for the lead fields "
            "(name, phone, email, service_type, preferred_date, preferred_time, number_of_people, "
            "room_type, notes) and store them in JSON. "
            "Only include fields that are explicitly mentioned. "
            "Classify the lead as hot, warm, or cold depending on intent and readiness. "
            "Set summary_requested to true only if the user explicitly requests a summary."
        )
        tracker_messages: List[BaseMessage] = [SystemMessage(content=tracker_instructions)]
        tracker_messages.extend(state.get("messages", []))

        try:
            update = self.state_parser.invoke(tracker_messages)
        except Exception as exc:
            self.logger.warning("Lead state extraction failed: %s", exc)
            return state

        merged_fields = state.get("collected_data", {}).copy()
        lead_dict = update.lead.model_dump()
        custom_fields = lead_dict.pop("custom_fields", {}) or {}

        for key, value in lead_dict.items():
            if value:
                merged_fields[key] = value

        for key, value in custom_fields.items():
            if value:
                merged_fields[key] = value

        new_state = state.copy()
        new_state["collected_data"] = merged_fields
        if update.lead_status:
            new_state["lead_status"] = update.lead_status
        if update.summary_requested:
            new_state["summary_requested"] = True
        return new_state

