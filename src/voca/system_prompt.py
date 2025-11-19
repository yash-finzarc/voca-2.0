"""
System prompt management using Supabase.
Handles fetching, updating, and resetting the system prompt.
"""
import logging
import time
from datetime import datetime
from typing import Dict, Optional

from src.voca.supabase_client import get_supabase_client, is_supabase_configured

logger = logging.getLogger("voca.system_prompt")

# Default system prompt (fallback)
DEFAULT_SYSTEM_PROMPT = (
    "You are Voca, a helpful voice assistant. "
    "Respond concisely and naturally. "
    "If asked how you can help, say: 'I can assist you with the information that is available to me.' "
    "Keep responses brief and conversational."
)

# In-memory cache to reduce DB calls (keyed by organization ID or '__default__')
_cached_prompts: Dict[str, Optional[str]] = {}
_cached_names: Dict[str, Optional[str]] = {}
_cached_welcome_messages: Dict[str, Optional[str]] = {}
_cache_timestamps: Dict[str, float] = {}
CACHE_TTL_SECONDS = 60  # Cache for 60 seconds


def _cache_key(organization_id: Optional[str]) -> str:
    return organization_id or "__default__"


def _read_cache(cache_key: str) -> Optional[dict]:
    prompt = _cached_prompts.get(cache_key)
    timestamp = _cache_timestamps.get(cache_key)
    if prompt is None or timestamp is None:
        return None
    if time.time() - timestamp > CACHE_TTL_SECONDS:
        return None
    return {
        "prompt": prompt,
        "name": _cached_names.get(cache_key) or "Default",
        "welcome_message": _cached_welcome_messages.get(cache_key)
    }


def _write_cache(cache_key: str, prompt: Optional[str], name: Optional[str], welcome_message: Optional[str] = None):
    _cached_prompts[cache_key] = prompt
    _cached_names[cache_key] = name
    _cached_welcome_messages[cache_key] = welcome_message
    _cache_timestamps[cache_key] = time.time()


def get_default_prompt() -> str:
    """Get the default system prompt."""
    return DEFAULT_SYSTEM_PROMPT


def get_prompt(organization_id: Optional[str] = None) -> str:
    """
    Get the current system prompt from Supabase.
    Falls back to default if Supabase is unavailable.
    """
    prompt_data = get_prompt_with_name(organization_id=organization_id)
    return prompt_data["prompt"]


def get_prompt_with_name(organization_id: Optional[str] = None) -> dict:
    """
    Get the current system prompt and name from Supabase.
    Returns dict with 'prompt' and 'name' keys.
    Falls back to default if Supabase is unavailable.
    """
    cache_key = _cache_key(organization_id)
    cached = _read_cache(cache_key)
    if cached:
        return cached

    if not is_supabase_configured():
        logger.debug("Supabase not configured, using default prompt")
        return {"prompt": DEFAULT_SYSTEM_PROMPT, "name": "Default", "welcome_message": None}

    client = get_supabase_client()
    if client is None:
        logger.warning("Supabase client unavailable, using default prompt")
        return {"prompt": DEFAULT_SYSTEM_PROMPT, "name": "Default", "welcome_message": None}

    try:
        prompt_data = _fetch_prompt_for_organization(client, organization_id)
        _write_cache(
            cache_key,
            prompt_data["prompt"],
            prompt_data.get("name"),
            prompt_data.get("welcome_message")
        )
        return prompt_data
    except Exception as e:
        logger.error(f"Error fetching system prompt from Supabase: {e}")
        return {"prompt": DEFAULT_SYSTEM_PROMPT, "name": "Default", "welcome_message": None}


def update_prompt(
    prompt: str,
    name: Optional[str] = None,
    welcome_message: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> bool:
    """
    Update the system prompt in Supabase.
    Optionally update the name as well.
    
    If organization_id is provided, saves to organization_system_prompts table.
    If organization_id is None, saves to system_prompts table as default.
    
    Returns True if successful, False otherwise.
    """
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
        if organization_id:
            logger.info(f"Updating prompt for organization: {organization_id}")
            success = _upsert_organization_prompt(client, organization_id, prompt.strip(), name, welcome_message)
            if success:
                # Refresh cache with latest data including welcome_message
                prompt_data = _fetch_prompt_for_organization(client, organization_id)
                _write_cache(
                    _cache_key(organization_id),
                    prompt_data["prompt"],
                    prompt_data.get("name"),
                    prompt_data.get("welcome_message")
                )
            return success
        else:
            logger.info("Updating default system prompt (no organization_id provided)")
            success = _update_default_prompt(client, prompt.strip(), name, welcome_message)
            if success:
                # Refresh cache with latest data including welcome_message
                prompt_data = _fetch_prompt_for_organization(client, None)
                _write_cache(
                    _cache_key(None),
                    prompt_data["prompt"],
                    prompt_data.get("name"),
                    prompt_data.get("welcome_message")
                )
            return success
    except Exception as e:
        logger.error(f"Error updating system prompt from Supabase: {e}", exc_info=True)
        return False


def reset_prompt(organization_id: Optional[str] = None) -> bool:
    """
    Reset the system prompt to default in Supabase.
    Returns True if successful, False otherwise.
    """
    return update_prompt(DEFAULT_SYSTEM_PROMPT, name="Default", organization_id=organization_id)


def _fetch_prompt_for_organization(client, organization_id: Optional[str]) -> dict:
    """
    Fetch prompt for a specific organization.
    Falls back to default prompt if org prompt not found.
    Returns dict with 'prompt', 'name', and 'welcome_message' keys.
    """
    if organization_id:
        response = (
            client.table("organization_system_prompts")
            .select("prompt, name, welcome_message")
            .eq("organization_id", organization_id)
            .eq("is_active", True)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if response.data:
            data = response.data[0]
            prompt = data.get("prompt", DEFAULT_SYSTEM_PROMPT)
            name = data.get("name", "Custom")
            welcome_message = data.get("welcome_message")
            logger.debug("Organization prompt fetched from Supabase")
            return {"prompt": prompt, "name": name, "welcome_message": welcome_message}
        logger.info(
            "No active prompt found for organization %s, falling back to default",
            organization_id,
        )

    # Default prompt fallback
    response = (
        client.table("system_prompts")
        .select("prompt, name, welcome_message")
        .eq("key", "default")
        .limit(1)
        .execute()
    )

    if response.data:
        data = response.data[0]
        prompt = data.get("prompt", DEFAULT_SYSTEM_PROMPT)
        name = data.get("name", "Default")
        welcome_message = data.get("welcome_message")
        logger.debug("System prompt fetched from Supabase")
        return {"prompt": prompt, "name": name, "welcome_message": welcome_message}

    logger.info("No system prompt rows found, initializing with default")
    _initialize_default_prompt(client)
    return {"prompt": DEFAULT_SYSTEM_PROMPT, "name": "Default", "welcome_message": None}


def _update_default_prompt(client, prompt: str, name: Optional[str], welcome_message: Optional[str] = None) -> bool:
    update_data = {
        "prompt": prompt,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if name is not None:
        update_data["name"] = name.strip() if name.strip() else None
    if welcome_message is not None:
        update_data["welcome_message"] = welcome_message.strip() if welcome_message.strip() else None

    response = (
        client.table("system_prompts")
        .update(update_data)
        .eq("key", "default")
        .execute()
    )

    cache_key = _cache_key(None)
    if response.data:
        _write_cache(cache_key, prompt, update_data.get("name"))
        logger.info("Default system prompt updated in Supabase")
        return True

    logger.info("Default prompt row missing, creating new row")
    created = _initialize_prompt(client, prompt, name)
    if created:
        _write_cache(cache_key, prompt, name)
    return created


def _initialize_default_prompt(client) -> bool:
    """Initialize the system_prompts table with default prompt."""
    return _initialize_prompt(client, DEFAULT_SYSTEM_PROMPT, "Default")


def _initialize_prompt(client, prompt: str, name: Optional[str] = None) -> bool:
    """Initialize the system_prompts table with given prompt and optional name."""
    try:
        insert_data = {
            "key": "default",
            "prompt": prompt,
            "is_default": True,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if name is not None:
            insert_data["name"] = name.strip() if name.strip() else None

        response = client.table("system_prompts").insert(insert_data).execute()

        if response.data and len(response.data) > 0:
            cache_key = _cache_key(None)
            _write_cache(cache_key, prompt, name.strip() if name and name.strip() else None)
            logger.info("System prompt initialized in Supabase")
            return True

        logger.error("Failed to initialize system prompt in Supabase")
        return False
    except Exception as e:
        logger.warning(f"Insert failed, trying update: {e}")
        try:
            update_data = {
                "prompt": prompt,
                "updated_at": datetime.utcnow().isoformat(),
            }
            if name is not None:
                update_data["name"] = name.strip() if name.strip() else None

            response = (
                client.table("system_prompts")
                .update(update_data)
                .eq("key", "default")
                .execute()
            )

            if response.data and len(response.data) > 0:
                cache_key = _cache_key(None)
                _write_cache(cache_key, prompt, name.strip() if name and name.strip() else None)
                logger.info("System prompt initialized via update in Supabase")
                return True
        except Exception as e2:
            logger.error(f"Failed to initialize system prompt: {e2}")

        return False


def _upsert_organization_prompt(client, organization_id: str, prompt: str, name: Optional[str], welcome_message: Optional[str] = None) -> bool:
    """Insert a new prompt row for the organization and deactivate previous prompts."""
    # First, verify the organization exists
    try:
        org_check = client.table("organizations").select("id").eq("id", organization_id).limit(1).execute()
        if not org_check.data or len(org_check.data) == 0:
            logger.error("Organization %s does not exist. Please create the organization first.", organization_id)
            return False
    except Exception as e:
        logger.error("Failed to verify organization existence: %s", e)
        return False
    
    # Deactivate previous prompts
    try:
        client.table("organization_system_prompts").update({"is_active": False}).eq("organization_id", organization_id).eq("is_active", True).execute()
    except Exception as e:
        logger.warning("Failed to deactivate previous prompts for org %s: %s", organization_id, e)

    insert_data = {
        "organization_id": organization_id,
        "prompt": prompt,
        "name": name.strip() if name and name.strip() else None,
        "welcome_message": welcome_message.strip() if welcome_message and welcome_message.strip() else None,
        "is_active": True,
        "updated_at": datetime.utcnow().isoformat(),
    }

    try:
        response = client.table("organization_system_prompts").insert(insert_data).execute()
        if response.data and len(response.data) > 0:
            logger.info("Organization %s prompt updated", organization_id)
            return True
    except Exception as e:
        logger.error("Failed to insert organization prompt for %s: %s", organization_id, e)
        return False

    logger.error("Failed to insert organization prompt for %s", organization_id)
    return False


def get_welcome_message(organization_id: Optional[str] = None) -> Optional[str]:
    """
    Get the welcome message from Supabase for the given organization.
    Returns None if no welcome message is set (should generate from prompt).
    """
    prompt_data = get_prompt_with_name(organization_id=organization_id)
    return prompt_data.get("welcome_message")


def clear_cache():
    """Clear the in-memory cache (useful for testing or forced refresh)."""
    _cached_prompts.clear()
    _cached_names.clear()
    _cached_welcome_messages.clear()
    _cache_timestamps.clear()
    logger.debug("System prompt cache cleared")

