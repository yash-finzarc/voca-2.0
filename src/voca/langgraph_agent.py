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
from src.voca.system_prompt import get_state_tracker_prompt

logger = logging.getLogger("voca.langgraph")


# Function implementations for voice AI agent
async def book_appointment(
    customer_name: str,
    appointment_date: str,
    appointment_time: str,
    service_type: str = None,
    notes: str = None,
) -> dict:
    """
    Book an appointment for a customer.
    
    Args:
        customer_name: The name of the customer booking the appointment
        appointment_date: The date of the appointment in YYYY-MM-DD format
        appointment_time: The time of the appointment in HH:MM format (24-hour format)
        service_type: The type of service or appointment (optional)
        notes: Any additional notes or special requests (optional)
    
    Returns:
        Dictionary with booking confirmation details
    """
    logger.info(f"Booking appointment for {customer_name} on {appointment_date} at {appointment_time}")
    
    # TODO: Implement actual booking logic (e.g., save to database)
    # For now, return a confirmation message
    
    result = {
        "status": "success",
        "message": f"Appointment booked successfully for {customer_name}",
        "appointment_date": appointment_date,
        "appointment_time": appointment_time,
        "service_type": service_type,
        "notes": notes,
    }
    
    return result


async def book_room(
    customer_name: str,
    check_in_date: str,
    room_type: str,
    check_out_date: str = None,
    number_of_guests: int = None,
    special_requests: str = None,
) -> dict:
    """
    Book a room or venue for a customer.
    
    Args:
        customer_name: The name of the customer booking the room
        check_in_date: The check-in date in YYYY-MM-DD format
        room_type: The type of room requested
        check_out_date: The check-out date in YYYY-MM-DD format (optional, for multi-day bookings)
        number_of_guests: The number of guests or people for the room booking (optional)
        special_requests: Any special requests or requirements (optional)
    
    Returns:
        Dictionary with room booking confirmation details
    """
    logger.info(f"Booking {room_type} room for {customer_name} from {check_in_date}")
    
    # TODO: Implement actual booking logic (e.g., save to database)
    # For now, return a confirmation message
    
    result = {
        "status": "success",
        "message": f"Room booked successfully for {customer_name}",
        "room_type": room_type,
        "check_in_date": check_in_date,
        "check_out_date": check_out_date,
        "number_of_guests": number_of_guests,
        "special_requests": special_requests,
    }
    
    return result


# Map function names to their implementations
FUNCTION_MAP = {
    "book_appointment": book_appointment,
    "book_room": book_room,
}


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
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get real-time model information.
        
        Returns:
            Dictionary with model information including model name and temperature
        """
        return {
            "model": self.model_name,
            "temperature": self.temperature,
            "type": "ChatGoogleGenerativeAI",
        }

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
        # Get state tracker prompt from Supabase
        organization_id = state.get("organization_id")
        try:
            tracker_instructions = get_state_tracker_prompt(organization_id=organization_id)
        except Exception as e:
            self.logger.error(f"Failed to fetch state tracker prompt from Supabase: {e}")
            # Fallback: return state without updating (don't use hardcoded prompt)
            self.logger.warning("State tracker node skipped - no prompt available from Supabase")
            return state
        
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

