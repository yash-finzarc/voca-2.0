"""
System prompt utilities for VOCA.
"""
from typing import Optional
from src.voca.supabase_client import get_supabase_client, is_supabase_configured
from src.voca.config import Config


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


def get_prompt(organization_id: Optional[str] = None) -> str:
    """
    Get system prompt from Supabase.
    Uses default prompt (is_default=True) since organization_id filtering may not be in schema.
    
    Args:
        organization_id: Optional organization ID (currently not used in query, kept for API compatibility)
    
    Returns:
        System prompt string
    """
    if not is_supabase_configured():
        # Fallback to a default prompt if Supabase is not configured
        return "You are a helpful assistant."
    
    client = get_supabase_client()
    if not client:
        return "You are a helpful assistant."
    
    try:
        # Get default active prompt (matching server.py pattern)
        response = (
            client.table("system_prompts")
            .select("prompt")
            .eq("is_default", True)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        
        if response.data and response.data[0].get("prompt"):
            return response.data[0]["prompt"]
        
        # Fallback
        return "You are a helpful assistant."
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error fetching system prompt: {e}")
        return "You are a helpful assistant."


def get_welcome_message(organization_id: Optional[str] = None) -> Optional[str]:
    """
    Get welcome message from Supabase.
    Uses default prompt (is_default=True) since organization_id filtering may not be in schema.
    
    Args:
        organization_id: Optional organization ID (currently not used in query, kept for API compatibility)
    
    Returns:
        Welcome message string or None if not found
    """
    if not is_supabase_configured():
        return None
    
    client = get_supabase_client()
    if not client:
        return None
    
    try:
        # Get default active welcome message (matching server.py pattern)
        response = (
            client.table("system_prompts")
            .select("welcome_message")
            .eq("is_default", True)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        
        if response.data and response.data[0].get("welcome_message"):
            return response.data[0]["welcome_message"]
        
        return None
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error fetching welcome message: {e}")
        return None

