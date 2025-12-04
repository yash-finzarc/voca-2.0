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

    # Default prompt fallback - get the most recent active/default prompt
    try:
        # Try to get the most recent active prompt first
        try:
            response = (
                client.table("system_prompts")
                .select("prompt, name, welcome_message")
                .eq("is_active", True)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
        except Exception:
            # If is_active column doesn't exist, try is_default
            response = (
                client.table("system_prompts")
                .select("prompt, name, welcome_message")
                .eq("is_default", True)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
    except Exception as e:
        logger.warning("Error fetching default prompt: %s", e)
        response = type('obj', (object,), {'data': None})()

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
    """
    Insert a new default prompt row and deactivate previous ones.
    This preserves history of all prompts instead of overwriting.
    """
    # First, deactivate all previous default prompts
    try:
        try:
            client.table("system_prompts").update({"is_active": False}).eq("is_default", True).eq("is_active", True).execute()
        except Exception:
            client.table("system_prompts").update({"is_default": False}).eq("is_default", True).execute()
    except Exception as e:
        logger.warning("Failed to deactivate previous default prompts: %s", e)
    
    insert_data = {
        "prompt": prompt,
        "name": name.strip() if name and name.strip() else None,
        "is_default": True,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if welcome_message is not None:
        insert_data["welcome_message"] = welcome_message.strip() if welcome_message.strip() else None
    
    try:
        insert_data["is_active"] = True
    except Exception:
        pass

    try:
        response = client.table("system_prompts").insert(insert_data).execute()
        if response.data and len(response.data) > 0:
            cache_key = _cache_key(None)
            _write_cache(cache_key, prompt, name.strip() if name and name.strip() else None, welcome_message)
            logger.info("New default system prompt created in Supabase (preserving history)")
            return True
        else:
            logger.error("Insert succeeded but no data returned")
            return False
    except Exception as e:
        logger.error("Failed to insert new default prompt: %s", e, exc_info=True)
        logger.warning("All insert methods failed, attempting initialization")
        created = _initialize_prompt(client, prompt, name, welcome_message)
        if created:
            cache_key = _cache_key(None)
            _write_cache(cache_key, prompt, name, welcome_message)
        return created

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
    return _initialize_prompt(client, DEFAULT_SYSTEM_PROMPT, "Default", None)


def _initialize_prompt(client, prompt: str, name: Optional[str] = None, welcome_message: Optional[str] = None) -> bool:
    """Initialize the system_prompts table with given prompt and optional name."""
    try:
        insert_data = {
            "prompt": prompt,
            "is_default": True,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if name is not None:
            insert_data["name"] = name.strip() if name.strip() else None
        if welcome_message is not None:
            insert_data["welcome_message"] = welcome_message.strip() if welcome_message.strip() else None
        
        try:
            insert_data["is_active"] = True
        except Exception:
            pass

        response = client.table("system_prompts").insert(insert_data).execute()

        if response.data and len(response.data) > 0:
            cache_key = _cache_key(None)
            _write_cache(cache_key, prompt, name.strip() if name and name.strip() else None, welcome_message)
            logger.info("System prompt initialized in Supabase")
            return True

        logger.error("Failed to initialize system prompt in Supabase")
        return False
    except Exception as e:
        logger.error(f"Insert failed in _initialize_prompt: {e}", exc_info=True)
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


def create_prompt_with_id(
    prompt_id: str,
    prompt: str,
    name: Optional[str] = None,
    welcome_message: Optional[str] = None,
) -> bool:
    """
    Create a new system prompt with a specific UUID (from frontend).
    This deactivates all previous default prompts and creates a new one.
    
    Args:
        prompt_id: UUID generated by frontend (crypto.randomUUID())
        prompt: The prompt text
        name: Optional name for the prompt
        welcome_message: Optional welcome message
    
    Returns:
        True if successful, False otherwise
    
    This function aligns with frontend behavior where:
    - Frontend generates UUID using crypto.randomUUID()
    - Frontend calls create() with the UUID
    - New prompt is created and all others are deactivated
    """
    if not prompt or not prompt.strip():
        logger.error("Cannot create prompt with empty text")
        return False

    if not is_supabase_configured():
        logger.error("Supabase not configured, cannot create prompt")
        return False

    client = get_supabase_client()
    if client is None:
        logger.error("Supabase client unavailable, cannot create prompt")
        return False

    try:
        # Deactivate all previous default prompts (aligns with frontend auto-activation)
        try:
            client.table("system_prompts").update({"is_active": False}).eq("is_default", True).execute()
            logger.debug("Deactivated all previous default prompts")
        except Exception as e:
            logger.warning(f"Failed to deactivate previous prompts: {e}")

        # Create the new prompt with the UUID provided by frontend
        insert_data = {
            "id": prompt_id,  # Use the UUID from frontend as the id
            "prompt": prompt.strip(),
            "is_default": True,
            "is_active": True,  # New prompt is automatically active
        }

        # Add optional fields - explicitly set to None if empty (consistent with update_prompt_by_id)
        if name is not None:
            insert_data["name"] = name.strip() if name.strip() else None

        if welcome_message is not None:
            insert_data["welcome_message"] = welcome_message.strip() if welcome_message.strip() else None

        # Note: created_at has a default, updated_at we'll set explicitly
        insert_data["updated_at"] = datetime.utcnow().isoformat()

        logger.info(f"Creating prompt with UUID: {prompt_id}, name: {name}, prompt length: {len(prompt.strip())}")
        logger.debug(f"Insert data: {insert_data}")

        try:
            response = client.table("system_prompts").insert(insert_data).execute()

            if response.data and len(response.data) > 0:
                # Clear cache to force refresh
                clear_cache()
                logger.info(f"New prompt created with UUID {prompt_id} (preserving all previous prompts)")
                return True
            else:
                error_msg = f"Failed to create prompt - no data returned. Response: {response}"
                logger.error(error_msg)
                raise ValueError(error_msg)

        except Exception as insert_error:
            error_msg = f"Supabase insert error: {str(insert_error)}"
            logger.error(error_msg)
            logger.error(f"Insert data that failed: {insert_data}")
            logger.error(f"Error type: {type(insert_error).__name__}")
            raise RuntimeError(f"Failed to insert prompt into database: {str(insert_error)}") from insert_error

    except ValueError as ve:
        raise
    except RuntimeError as re:
        raise
    except Exception as e:
        error_msg = f"Unexpected error creating prompt with UUID {prompt_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise RuntimeError(error_msg) from e


def update_prompt_by_id(
    prompt_id: str,
    prompt: str,
    name: Optional[str] = None,
    welcome_message: Optional[str] = None,
) -> bool:
    """
    Update an existing prompt by its UUID.
    
    Args:
        prompt_id: UUID of the prompt to update
        prompt: New prompt text
        name: Optional new name
        welcome_message: Optional new welcome message
    
    Returns:
        True if successful, False otherwise
    
    This function aligns with frontend behavior where:
    - Frontend calls update() with UUID and new data
    - Only the specified prompt is updated
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
        update_data = {
            "prompt": prompt.strip(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        if name is not None:
            update_data["name"] = name.strip() if name.strip() else None
        if welcome_message is not None:
            update_data["welcome_message"] = welcome_message.strip() if welcome_message.strip() else None

        response = (
            client.table("system_prompts")
            .update(update_data)
            .eq("id", prompt_id)
            .execute()
        )

        if response.data and len(response.data) > 0:
            # Clear cache to force refresh
            clear_cache()
            logger.info(f"Prompt {prompt_id} updated successfully")
            return True
        else:
            logger.warning(f"Prompt {prompt_id} not found")
            return False
    except Exception as e:
        logger.error(f"Error updating prompt {prompt_id}: {e}", exc_info=True)
        return False


def activate_prompt_by_id(prompt_id: str) -> bool:
    """
    Activate a prompt by UUID and deactivate all other default prompts.
    
    Args:
        prompt_id: UUID of the prompt to activate
    
    Returns:
        True if successful, False otherwise
    
    Raises:
        RuntimeError: If there's an error that should be propagated to the caller
    
    This function aligns with frontend behavior where:
    - Frontend calls activate() when a prompt is selected
    - Selected prompt becomes active (is_active: true)
    - All other prompts are deactivated (is_active: false)
    - This happens automatically when user selects a prompt in dropdown
    """
    if not is_supabase_configured():
        error_msg = "Supabase not configured, cannot activate prompt"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    client = get_supabase_client()
    if client is None:
        error_msg = "Supabase client unavailable, cannot activate prompt"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    try:
        # First, verify the prompt exists
        logger.info(f"Checking if prompt {prompt_id} exists...")
        check_response = (
            client.table("system_prompts")
            .select("id, is_default, is_active")
            .eq("id", prompt_id)
            .limit(1)
            .execute()
        )

        if not check_response.data or len(check_response.data) == 0:
            error_msg = f"Prompt {prompt_id} not found in database"
            logger.error(error_msg)
            raise ValueError(error_msg)

        prompt_data = check_response.data[0]
        is_default = prompt_data.get("is_default", False)
        current_is_active = prompt_data.get("is_active", False)

        logger.info(f"Prompt {prompt_id} found. is_default={is_default}, current is_active={current_is_active}")

        # Deactivate all other prompts (both default and non-default) to ensure only one is active
        # This aligns with frontend behavior where selecting one deactivates all others
        try:
            deactivate_response = client.table("system_prompts").update({"is_active": False}).neq("id", prompt_id).execute()
            logger.debug(f"Deactivated all other prompts (keeping {prompt_id} active). Updated {len(deactivate_response.data) if deactivate_response.data else 0} prompts")
        except Exception as e:
            logger.warning(f"Failed to deactivate other prompts (non-critical): {e}")

        # Activate the specified prompt
        logger.info(f"Activating prompt {prompt_id}...")
        response = (
            client.table("system_prompts")
            .update({"is_active": True, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", prompt_id)
            .execute()
        )

        if response.data and len(response.data) > 0:
            # Clear cache to force refresh
            clear_cache()
            logger.info(f"Prompt {prompt_id} activated successfully (all others deactivated)")
            return True
        else:
            error_msg = f"Failed to activate prompt {prompt_id} - update returned no data. Response: {response}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
    except ValueError as ve:
        # Re-raise ValueError (prompt not found)
        raise
    except RuntimeError as re:
        # Re-raise RuntimeError
        raise
    except Exception as e:
        error_msg = f"Unexpected error activating prompt {prompt_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e


def clear_cache():
    """Clear the in-memory cache (useful for testing or forced refresh)."""
    _cached_prompts.clear()
    _cached_names.clear()
    _cached_welcome_messages.clear()
    _cache_timestamps.clear()
    logger.debug("System prompt cache cleared")
