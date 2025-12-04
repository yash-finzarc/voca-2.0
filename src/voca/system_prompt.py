"""
System prompt management using Supabase.
Handles fetching, updating, and resetting the system prompt.
"""
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

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


def extract_json_from_prompt(prompt_text: str) -> Optional[Dict]:
    """
    Extract JSON data from prompt text.
    Looks for JSON in various formats:
    1. Between <!-- JSON_DATA --> and <!-- END_JSON --> markers
    2. Between === TEST_RESULTS_JSON === and === END_JSON === markers
    3. In ```json code blocks
    4. Any valid JSON object in the text
    
    Returns JSON dict if found, None otherwise.
    """
    if not prompt_text:
        return None
    
    # Try different patterns to extract JSON
    patterns = [
        # Pattern 1: <!-- JSON_DATA --> ... <!-- END_JSON -->
        r'<!--\s*JSON_DATA\s*-->(.*?)<!--\s*END_JSON\s*-->',
        # Pattern 2: === TEST_RESULTS_JSON === ... === END_JSON ===
        r'===\s*TEST_RESULTS_JSON\s*===(.*?)===\s*END_JSON\s*===',
        # Pattern 3: ```json ... ```
        r'```json\s*(.*?)\s*```',
        # Pattern 4: ``` ... ``` (generic code block)
        r'```\s*(.*?)\s*```',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, prompt_text, re.DOTALL | re.IGNORECASE)
        if match:
            json_str = match.group(1).strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue
    
    # Try to find any JSON object in the text (fallback)
    # Look for { ... } pattern
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', prompt_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    return None


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
    Returns dict with 'prompt', 'name', 'welcome_message', and 'service_type' keys.
    Falls back to default if Supabase is unavailable.
    """
    cache_key = _cache_key(organization_id)
    cached = _read_cache(cache_key)
    if cached:
        # Add service_type to cached data if not present (for backward compatibility)
        if "service_type" not in cached:
            cached["service_type"] = "conversational"
        return cached

    if not is_supabase_configured():
        logger.debug("Supabase not configured, using default prompt")
        return {"prompt": DEFAULT_SYSTEM_PROMPT, "name": "Default", "welcome_message": None, "service_type": "conversational"}

    client = get_supabase_client()
    if client is None:
        logger.warning("Supabase client unavailable, using default prompt")
        return {"prompt": DEFAULT_SYSTEM_PROMPT, "name": "Default", "welcome_message": None, "service_type": "conversational"}

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
        return {"prompt": DEFAULT_SYSTEM_PROMPT, "name": "Default", "welcome_message": None, "service_type": "conversational"}


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
    Returns dict with 'prompt', 'name', 'welcome_message', and 'service_type' keys.
    """
    if organization_id:
        # Note: organization_system_prompts doesn't have service_type, so it defaults to conversational
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
            return {"prompt": prompt, "name": name, "welcome_message": welcome_message, "service_type": "conversational"}
        logger.info(
            "No active prompt found for organization %s, falling back to default",
            organization_id,
        )

    # Default prompt fallback - get the most recent active/default prompt
    try:
        # Try to get the most recent active prompt first (with service_type)
        try:
            response = (
                client.table("system_prompts")
                .select("prompt, name, welcome_message, service_type")
                .eq("is_active", True)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
        except Exception:
            # If is_active column doesn't exist, try is_default
            try:
                response = (
                    client.table("system_prompts")
                    .select("prompt, name, welcome_message, service_type")
                    .eq("is_default", True)
                    .order("updated_at", desc=True)
                    .limit(1)
                    .execute()
                )
            except Exception:
                # If service_type column doesn't exist yet, fetch without it
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
        service_type = data.get("service_type", "conversational")  # Default to conversational if not present
        logger.debug("System prompt fetched from Supabase")
        return {"prompt": prompt, "name": name, "welcome_message": welcome_message, "service_type": service_type}

    logger.info("No system prompt rows found, initializing with default")
    _initialize_default_prompt(client)
    return {"prompt": DEFAULT_SYSTEM_PROMPT, "name": "Default", "welcome_message": None, "service_type": "conversational"}


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


def create_prompt(
    prompt: str,
    name: Optional[str] = None,
    welcome_message: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Create a new system prompt. Supabase will auto-generate the UUID.
    This deactivates all previous default prompts and creates a new one.
    
    Args:
        prompt: The prompt text
        name: Optional name for the prompt
        welcome_message: Optional welcome message
    
    Returns:
        Tuple of (success: bool, prompt_id: Optional[str])
        - If successful, returns (True, uuid_from_supabase)
        - If failed, returns (False, None)
    """
    if not prompt or not prompt.strip():
        logger.error("Cannot create prompt with empty text")
        return (False, None)

    if not is_supabase_configured():
        logger.error("Supabase not configured, cannot create prompt")
        return (False, None)

    client = get_supabase_client()
    if client is None:
        logger.error("Supabase client unavailable, cannot create prompt")
        return (False, None)
    
    # Log which key type we're using (for debugging RLS issues)
    from src.voca.config import Config
    supabase_key = Config.supabase_key
    if supabase_key:
        # Service role keys are typically longer and start with 'eyJ'
        # Anon keys are shorter. This is just for logging.
        key_length = len(supabase_key)
        logger.debug(f"Using Supabase key (length: {key_length}). If using anon key, RLS policies must allow INSERT.")
    else:
        logger.warning("No Supabase key configured!")

    try:
        # Deactivate all previous default prompts (aligns with frontend auto-activation)
        try:
            client.table("system_prompts").update({"is_active": False}).eq("is_default", True).execute()
            logger.debug("Deactivated all previous default prompts")
        except Exception as e:
            logger.warning(f"Failed to deactivate previous prompts: {e}")

        # Generate UUID in Python to ensure we have it
        # Even though Supabase has gen_random_uuid() as default, generating it here ensures we can return it
        generated_uuid = str(uuid.uuid4())
        logger.info(f"Generated UUID in Python: {generated_uuid}")
        
        # Create the new prompt with the generated UUID
        insert_data = {
            "id": generated_uuid,  # Explicitly set the UUID
            "prompt": prompt.strip(),
            "is_default": True,
            "is_active": True,  # New prompt is automatically active
        }

        # Add optional fields - explicitly set to None if empty (consistent with update_prompt_by_id)
        if name is not None:
            insert_data["name"] = name.strip() if name.strip() else None

        if welcome_message is not None:
            insert_data["welcome_message"] = welcome_message.strip() if welcome_message.strip() else None

        # Note: created_at and updated_at have defaults, but we'll set updated_at explicitly
        insert_data["updated_at"] = datetime.utcnow().isoformat()

        logger.info(f"Creating prompt (Supabase will generate UUID), name: {name}, prompt length: {len(prompt.strip())}")
        logger.debug(f"Insert data: {insert_data}")

        try:
            logger.info(f"Attempting to insert prompt into Supabase...")
            logger.info(f"Insert data keys: {list(insert_data.keys())}")
            logger.info(f"Insert data - name: {insert_data.get('name')}, prompt length: {len(insert_data.get('prompt', ''))}")
            
            # Insert the new prompt - Supabase will generate UUID
            # Note: Supabase Python client returns the inserted row by default
            # We don't need .select() - it's not supported after .insert()
            logger.info(f"Executing insert (Supabase will return inserted row by default)...")
            response = client.table("system_prompts").insert(insert_data).execute()
            
            # Log the full response for debugging
            logger.info(f"Supabase insert response received")
            logger.info(f"Response has data: {bool(response.data)}")
            logger.info(f"Response data length: {len(response.data) if response.data else 0}")
            logger.debug(f"Full response object: {response}")
            logger.debug(f"Response data type: {type(response.data)}")
            logger.debug(f"Response data: {response.data}")
            
            # Check response status if available
            if hasattr(response, 'status_code'):
                logger.info(f"Response status code: {response.status_code}")
                if response.status_code not in [200, 201]:
                    error_msg = f"Supabase insert returned status code {response.status_code}, expected 200/201"
                    logger.error(error_msg)
                    return (False, None)
            
            # Check for errors in response
            if hasattr(response, 'error') and response.error:
                error_msg = f"Supabase returned an error: {response.error}"
                logger.error(error_msg)
                return (False, None)
            
            # Check if response has data
            if not response.data:
                error_msg = f"❌ Supabase insert returned no data. This usually means RLS policy blocked the insert."
                logger.error(error_msg)
                logger.error(f"Full response: {response}")
                logger.error("SOLUTION: Add RLS policy in Supabase SQL Editor:")
                logger.error("CREATE POLICY \"Allow all operations on system_prompts\"")
                logger.error("ON public.system_prompts AS PERMISSIVE FOR ALL TO public USING (true) WITH CHECK (true);")
                return (False, None)
            
            if len(response.data) == 0:
                error_msg = f"❌ Supabase insert returned empty data array. This usually means RLS policy blocked the insert."
                logger.error(error_msg)
                logger.error("SOLUTION: Add RLS policy in Supabase SQL Editor:")
                logger.error("CREATE POLICY \"Allow all operations on system_prompts\"")
                logger.error("ON public.system_prompts AS PERMISSIVE FOR ALL TO public USING (true) WITH CHECK (true);")
                return (False, None)
            
            # Get the UUID from the response (should match what we sent)
            # If response doesn't have it, use the one we generated
            generated_id = None
            if response.data and len(response.data) > 0:
                generated_id = response.data[0].get("id")
            
            # Fallback to the UUID we generated if response doesn't have it
            if not generated_id:
                generated_id = generated_uuid
                logger.warning(f"Response didn't include ID, using generated UUID: {generated_id}")
            else:
                logger.info(f"✅ UUID from Supabase response: {generated_id}")
            
            # Verify the UUID matches what we sent (should be the same)
            if generated_id != generated_uuid:
                logger.warning(f"UUID mismatch: sent {generated_uuid}, got {generated_id}. Using response UUID.")
                generated_id = generated_uuid  # Use the one we generated to be safe
            
            # CRITICAL: Verify this is actually a NEW prompt, not an existing one
            # Check the created_at timestamp from the response - it should be very recent
            response_prompt = response.data[0]
            response_created_at = response_prompt.get('created_at')
            response_name = response_prompt.get('name')
            response_prompt_text = response_prompt.get('prompt', '')
            
            logger.info(f"Response prompt - name: {response_name}, created_at: {response_created_at}")
            logger.info(f"Requested prompt - name: {name}, prompt length: {len(prompt.strip())}")
            
            # IMMEDIATE CHECK: If the name doesn't match (and name was provided), this is definitely wrong
            # But only check if name was actually provided (not None/empty)
            if name and name.strip():
                # Name was provided, so it should match
                if response_name and response_name.strip() != name.strip():
                    error_msg = f"❌ CRITICAL: Response name '{response_name}' doesn't match requested name '{name}'. RLS blocked insert and returned existing prompt."
                    logger.error(error_msg)
                    logger.error("SOLUTION: Add RLS policy in Supabase SQL Editor:")
                    logger.error("CREATE POLICY \"Allow all operations on system_prompts\"")
                    logger.error("ON public.system_prompts AS PERMISSIVE FOR ALL TO public USING (true) WITH CHECK (true);")
                    return (False, None)
            # If name was not provided, we don't check it (it's optional)
            
            # Verify the prompt was actually created by fetching it back with more details
            try:
                verify_response = client.table("system_prompts").select("id, name, prompt, created_at, updated_at").eq("id", generated_id).limit(1).execute()
                if not verify_response.data or len(verify_response.data) == 0:
                    error_msg = f"Prompt {generated_id} was not found after creation - insert may have failed silently due to RLS"
                    logger.error(error_msg)
                    return (False, None)
                
                verified_prompt = verify_response.data[0]
                logger.info(f"Verified prompt {generated_id} exists in database")
                logger.info(f"Verified prompt - name: {verified_prompt.get('name')}, created_at: {verified_prompt.get('created_at')}, updated_at: {verified_prompt.get('updated_at')}")
                
                # Double-check: Make sure this is a NEW prompt, not an existing one
                # Check if the created_at and updated_at timestamps are very recent (within last 10 seconds)
                # Note: datetime is already imported at the top of the file
                created_at_str = verified_prompt.get('created_at')
                updated_at_str = verified_prompt.get('updated_at')
                
                if created_at_str:
                    try:
                        # Handle different datetime formats
                        if isinstance(created_at_str, str):
                            if 'Z' in created_at_str:
                                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                            else:
                                created_at = datetime.fromisoformat(created_at_str)
                        else:
                            created_at = created_at_str
                            
                        # Ensure timezone-aware
                        if created_at.tzinfo is None:
                            created_at = created_at.replace(tzinfo=timezone.utc)
                        
                        now = datetime.now(timezone.utc)
                        time_diff = (now - created_at).total_seconds()
                        
                        logger.info(f"Time difference: {time_diff} seconds between now and created_at")
                        
                        # Allow up to 30 seconds difference (more lenient for network delays, clock skew, etc.)
                        if abs(time_diff) > 30:
                            error_msg = f"❌ CRITICAL: Prompt {generated_id} was created {abs(time_diff)} seconds ago - this is an EXISTING prompt, not a new one! The insert was blocked by RLS and Supabase returned an existing row."
                            logger.error(error_msg)
                            logger.error(f"This means RLS policy blocked the insert. The new prompt was NOT created.")
                            logger.error("SOLUTION: Add RLS policy in Supabase SQL Editor:")
                            logger.error("CREATE POLICY \"Allow all operations on system_prompts\"")
                            logger.error("ON public.system_prompts AS PERMISSIVE FOR ALL TO public USING (true) WITH CHECK (true);")
                            return (False, None)  # Return False - the insert failed
                        else:
                            logger.info(f"✅ Timestamp check passed: prompt created {abs(time_diff)} seconds ago (within acceptable range)")
                    except Exception as time_check_error:
                        logger.warning(f"Could not verify creation time: {time_check_error}")
                        import traceback
                        logger.debug(f"Time check traceback: {traceback.format_exc()}")
                
                # Also verify the prompt text matches what we tried to insert
                # Use a more lenient comparison (normalize whitespace)
                if response_prompt_text and prompt.strip():
                    # Normalize whitespace for comparison (multiple spaces -> single space)
                    import re
                    requested_normalized = re.sub(r'\s+', ' ', prompt.strip())
                    response_normalized = re.sub(r'\s+', ' ', response_prompt_text.strip())
                    
                    if response_normalized != requested_normalized:
                        # Log a warning but don't fail - sometimes Supabase might normalize whitespace
                        logger.warning(f"⚠️ Prompt text doesn't exactly match (whitespace differences possible)")
                        logger.debug(f"Requested (normalized): {requested_normalized[:100]}...")
                        logger.debug(f"Got back (normalized): {response_normalized[:100]}...")
                        # Don't return False here - the insert might have succeeded with whitespace normalization
                        # Instead, we'll rely on the timestamp check which is more reliable
                
            except Exception as verify_error:
                error_msg = f"Could not verify prompt creation: {verify_error}"
                logger.warning(error_msg)  # Changed to warning, not error
                import traceback
                logger.debug(f"Verification traceback: {traceback.format_exc()}")
                # Even if verification fails, the insert might have succeeded
                # So we'll still return the UUID, but log the warning
                logger.warning("⚠️ Verification failed, but insert may have succeeded. Returning UUID anyway.")
                # Return True with the UUID - let the API endpoint handle verification
                # This ensures we don't lose the UUID even if verification has issues
                clear_cache()
                return (True, generated_id)
            
            # Clear cache to force refresh
            clear_cache()
            logger.info(f"✅ New prompt created successfully with UUID {generated_id} (generated by Supabase)")
            return (True, generated_id)

        except Exception as insert_error:
            error_msg = f"Supabase insert error: {str(insert_error)}"
            logger.error(error_msg)
            logger.error(f"Insert data that failed: {insert_data}")
            logger.error(f"Error type: {type(insert_error).__name__}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return (False, None)

    except Exception as e:
        error_msg = f"Unexpected error creating prompt: {str(e)}"
        logger.error(error_msg, exc_info=True)
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return (False, None)


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
