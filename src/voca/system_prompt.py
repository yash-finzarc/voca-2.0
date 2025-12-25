"""
System prompt utilities for VOCA.
"""
from typing import Optional


def get_state_tracker_prompt(organization_id: Optional[str] = None) -> str:
    """
    Get the state tracker prompt for LangGraph agent.
    
    Args:
        organization_id: Optional organization ID (not currently used)
    
    Returns:
        State tracker prompt string
    """
    return """You are a state tracker that extracts structured information from conversations.
Your job is to:
1. Identify key information mentioned by the user (name, phone, email, service type, etc.)
2. Update the collected_data dictionary with any new information
3. Determine if the lead is ready (all required fields collected)
4. Set lead_status to "qualified" when ready, "pending" otherwise

Be precise and only extract information that was explicitly mentioned or clearly implied.
Do not make up information."""

