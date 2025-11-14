"""
System prompt management using Supabase.
Handles fetching, updating, and resetting the system prompt.
"""
import logging
from typing import Optional
from datetime import datetime

from src.voca.supabase_client import get_supabase_client, is_supabase_configured

logger = logging.getLogger("voca.system_prompt")

# Default system prompt (fallback)
DEFAULT_SYSTEM_PROMPT = (
    "You are Voca, a helpful voice assistant. "
    "Respond concisely and naturally. "
    "If asked how you can help, say: 'I can assist you with the information that is available to me.' "
    "Keep responses brief and conversational."
)

# In-memory cache to reduce DB calls
_cached_prompt: Optional[str] = None
_cached_name: Optional[str] = None
_cache_timestamp: Optional[float] = None
CACHE_TTL_SECONDS = 60  # Cache for 60 seconds


def get_default_prompt() -> str:
    """Get the default system prompt."""
    return DEFAULT_SYSTEM_PROMPT


def get_prompt() -> str:
    """
    Get the current system prompt from Supabase.
    Falls back to default if Supabase is unavailable.
    """
    prompt_data = get_prompt_with_name()
    return prompt_data["prompt"]


def get_prompt_with_name() -> dict:
    """
    Get the current system prompt and name from Supabase.
    Returns dict with 'prompt' and 'name' keys.
    Falls back to default if Supabase is unavailable.
    """
    global _cached_prompt, _cached_name, _cache_timestamp
    
    # Return cached data if still valid
    if _cached_prompt is not None and _cache_timestamp is not None:
        import time
        if time.time() - _cache_timestamp < CACHE_TTL_SECONDS:
            return {
                "prompt": _cached_prompt,
                "name": _cached_name or "Default"
            }
    
    # Check if Supabase is configured
    if not is_supabase_configured():
        logger.debug("Supabase not configured, using default prompt")
        return {
            "prompt": DEFAULT_SYSTEM_PROMPT,
            "name": "Default"
        }
    
    client = get_supabase_client()
    if client is None:
        logger.warning("Supabase client unavailable, using default prompt")
        return {
            "prompt": DEFAULT_SYSTEM_PROMPT,
            "name": "Default"
        }
    
    try:
        # Fetch from Supabase - query by key='default', include name
        response = client.table("system_prompts").select("prompt, name").eq("key", "default").limit(1).execute()
        
        if response.data and len(response.data) > 0:
            data = response.data[0]
            prompt = data.get("prompt", DEFAULT_SYSTEM_PROMPT)
            name = data.get("name", "Default")
            # Update cache
            import time
            _cached_prompt = prompt
            _cached_name = name
            _cache_timestamp = time.time()
            logger.debug("System prompt fetched from Supabase")
            return {
                "prompt": prompt,
                "name": name
            }
        else:
            # No row found, initialize with default
            logger.info("No system prompt found in Supabase, initializing with default")
            _initialize_default_prompt(client)
            return {
                "prompt": DEFAULT_SYSTEM_PROMPT,
                "name": "Default"
            }
            
    except Exception as e:
        logger.error(f"Error fetching system prompt from Supabase: {e}")
        return {
            "prompt": DEFAULT_SYSTEM_PROMPT,
            "name": "Default"
        }


def update_prompt(prompt: str, name: Optional[str] = None) -> bool:
    """
    Update the system prompt in Supabase.
    Optionally update the name as well.
    Returns True if successful, False otherwise.
    """
    global _cached_prompt, _cached_name, _cache_timestamp
    
    if not prompt or not prompt.strip():
        logger.error("Cannot update with empty prompt")
        return False
    
    if not is_supabase_configured():
        logger.error("Supabase not configured, cannot update prompt")
        return False
    
    client = get_supabase_client()
    if client is None:
        logger.error("Supabase client unavailable, cannot update prompt")
        return False
    
    try:
        # Prepare update data
        update_data = {
            "prompt": prompt.strip(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Include name if provided
        if name is not None:
            update_data["name"] = name.strip() if name.strip() else None
        
        # Try to update existing row by key='default'
        response = client.table("system_prompts").update(update_data).eq("key", "default").execute()
        
        if response.data and len(response.data) > 0:
            # Update cache
            import time
            _cached_prompt = prompt.strip()
            if name is not None:
                _cached_name = name.strip() if name.strip() else None
            _cache_timestamp = time.time()
            logger.info("System prompt updated in Supabase")
            return True
        else:
            # Row doesn't exist, insert it
            logger.info("System prompt row not found, creating new row")
            return _initialize_prompt(client, prompt.strip(), name)
            
    except Exception as e:
        logger.error(f"Error updating system prompt from Supabase: {e}")
        return False


def reset_prompt() -> bool:
    """
    Reset the system prompt to default in Supabase.
    Returns True if successful, False otherwise.
    """
    return update_prompt(DEFAULT_SYSTEM_PROMPT)


def _initialize_default_prompt(client) -> bool:
    """Initialize the system_prompts table with default prompt."""
    return _initialize_prompt(client, DEFAULT_SYSTEM_PROMPT, "Default")


def _initialize_prompt(client, prompt: str, name: Optional[str] = None) -> bool:
    """Initialize the system_prompts table with given prompt and optional name."""
    global _cached_prompt, _cached_name, _cache_timestamp
    try:
        # Prepare insert data
        insert_data = {
            "key": "default",
            "prompt": prompt,
            "is_default": True,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Include name if provided
        if name is not None:
            insert_data["name"] = name.strip() if name.strip() else None
        
        # Insert new row with key='default' (UUID will auto-generate)
        response = client.table("system_prompts").insert(insert_data).execute()
        
        if response.data and len(response.data) > 0:
            # Update cache
            import time
            _cached_prompt = prompt
            _cached_name = name.strip() if name and name.strip() else None
            _cache_timestamp = time.time()
            logger.info("System prompt initialized in Supabase")
            return True
        else:
            logger.error("Failed to initialize system prompt in Supabase")
            return False
            
    except Exception as e:
        # If insert fails (e.g., row already exists), try update
        logger.warning(f"Insert failed, trying update: {e}")
        try:
            update_data = {
                "prompt": prompt,
                "updated_at": datetime.utcnow().isoformat()
            }
            if name is not None:
                update_data["name"] = name.strip() if name.strip() else None
            
            response = client.table("system_prompts").update(update_data).eq("key", "default").execute()
            
            if response.data and len(response.data) > 0:
                import time
                _cached_prompt = prompt
                _cached_name = name.strip() if name and name.strip() else None
                _cache_timestamp = time.time()
                logger.info("System prompt initialized via update in Supabase")
                return True
        except Exception as e2:
            logger.error(f"Failed to initialize system prompt: {e2}")
        
        return False


def clear_cache():
    """Clear the in-memory cache (useful for testing or forced refresh)."""
    global _cached_prompt, _cached_name, _cache_timestamp
    _cached_prompt = None
    _cached_name = None
    _cache_timestamp = None
    logger.debug("System prompt cache cleared")

