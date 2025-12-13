"""
System prompt management endpoints.
"""
import logging
from typing import Optional, List

from fastapi import HTTPException, Query, Header
from fastapi.routing import APIRouter

from src.voca.api.app_state import app_state
from src.voca.api.models import (
    StatusResponse,
    SystemPromptResponse,
    SystemPromptRequest,
    SystemPromptListItem,
    WelcomeMessageRequest,
)
from src.voca.api.utils import resolve_org_id
from src.voca.system_prompt import (
    get_prompt_with_name,
    update_prompt,
    reset_prompt,
    DEFAULT_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system-prompt", tags=["system-prompt"])


@router.get("", response_model=SystemPromptResponse)
async def get_system_prompt(
    organization_id: Optional[str] = Query(None),
    x_organization_id: Optional[str] = Header(None),
):
    """Get the current system prompt and name."""
    try:
        resolved_org = resolve_org_id(query_value=organization_id, header_value=x_organization_id)
        prompt_data = get_prompt_with_name(resolved_org)
        return SystemPromptResponse(
            prompt=prompt_data["prompt"],
            name=prompt_data.get("name"),
            welcome_message=prompt_data.get("welcome_message")
        )
    except Exception as e:
        logger.error(f"Error fetching system prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch system prompt: {str(e)}")


@router.get("/list", response_model=List[SystemPromptListItem])
async def list_system_prompts(
    organization_id: Optional[str] = Query(None),
    x_organization_id: Optional[str] = Header(None),
    include_default: bool = Query(True, description="Include default prompts"),
):
    """List all system prompts (default and organization-specific)."""
    from src.voca.supabase_client import get_supabase_client, is_supabase_configured
    
    results = []
    
    if not is_supabase_configured():
        # Return default prompt if Supabase not configured
        return [
            SystemPromptListItem(
                name="Default",
                prompt=DEFAULT_SYSTEM_PROMPT,
                is_default=True,
            )
        ]
    
    client = get_supabase_client()
    if client is None:
        return results
    
    try:
        resolved_org = resolve_org_id(query_value=organization_id, header_value=x_organization_id)
        
        # Get default prompts
        if include_default:
            try:
                default_response = client.table("system_prompts").select("*").order("updated_at", desc=True).execute()
                if default_response.data:
                    for item in default_response.data:
                        results.append(
                            SystemPromptListItem(
                                id=item.get("id"),
                                key=item.get("key"),
                                name=item.get("name") or "Default",
                                prompt=item.get("prompt", ""),
                                welcome_message=item.get("welcome_message"),
                                is_default=item.get("is_default", False),
                                created_at=item.get("created_at"),
                                updated_at=item.get("updated_at"),
                            )
                        )
            except Exception as e:
                logger.warning(f"Error fetching default prompts: {e}")
        
        # Get organization-specific prompts
        if resolved_org:
            try:
                org_response = (
                    client.table("organization_system_prompts")
                    .select("*")
                    .eq("organization_id", resolved_org)
                    .eq("is_active", True)
                    .order("updated_at", desc=True)
                    .execute()
                )
                if org_response.data:
                    for item in org_response.data:
                        results.append(
                            SystemPromptListItem(
                                id=item.get("id"),
                                name=item.get("name") or "Custom Prompt",
                                prompt=item.get("prompt", ""),
                                welcome_message=item.get("welcome_message"),
                                organization_id=item.get("organization_id"),
                                is_default=False,
                                created_at=item.get("created_at"),
                                updated_at=item.get("updated_at"),
                            )
                        )
            except Exception as e:
                logger.warning(f"Error fetching organization prompts: {e}")
        else:
            # If no org specified, get all organization prompts
            try:
                all_org_response = (
                    client.table("organization_system_prompts")
                    .select("*")
                    .eq("is_active", True)
                    .order("updated_at", desc=True)
                    .execute()
                )
                if all_org_response.data:
                    for item in all_org_response.data:
                        results.append(
                            SystemPromptListItem(
                                id=item.get("id"),
                                name=item.get("name") or "Custom Prompt",
                                prompt=item.get("prompt", ""),
                                welcome_message=item.get("welcome_message"),
                                organization_id=item.get("organization_id"),
                                is_default=False,
                                created_at=item.get("created_at"),
                                updated_at=item.get("updated_at"),
                            )
                        )
            except Exception as e:
                logger.warning(f"Error fetching all organization prompts: {e}")
        
        return results
    except Exception as e:
        logger.error(f"Error listing system prompts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list system prompts: {str(e)}")


@router.post("", response_model=StatusResponse)
@router.put("", response_model=StatusResponse)
@router.patch("", response_model=StatusResponse)
async def update_system_prompt(
    request: SystemPromptRequest,
    x_organization_id: Optional[str] = Header(None),
):
    """Update the system prompt and optionally the name."""
    try:
        resolved_org = resolve_org_id(
            body_value=request.organization_id,
            header_value=x_organization_id,
        )
        
        if not request.prompt or not request.prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt text is required")
        
        # If organization_id is provided, verify it exists
        if resolved_org:
            from src.voca.supabase_client import get_supabase_client, is_supabase_configured
            if is_supabase_configured():
                client = get_supabase_client()
                if client:
                    try:
                        org_check = client.table("organizations").select("id").eq("id", resolved_org).limit(1).execute()
                        if not org_check.data or len(org_check.data) == 0:
                            raise HTTPException(
                                status_code=404,
                                detail=f"Organization '{resolved_org}' not found. Please create the organization first using POST /api/organizations"
                            )
                    except HTTPException:
                        raise
                    except Exception as e:
                        logger.warning(f"Could not verify organization existence: {e}")
        
        success = update_prompt(request.prompt, request.name, request.welcome_message, organization_id=resolved_org)
        if success:
            name_msg = f" with name '{request.name}'" if request.name else ""
            org_msg = f" for organization {resolved_org}" if resolved_org else " as default prompt"
            app_state._log_callback(
                f"System prompt updated via API{name_msg}{org_msg}"
            )
            message = f"System prompt updated successfully{org_msg}"
            return StatusResponse(status="success", message=message)
        else:
            raise HTTPException(status_code=500, detail="Failed to update system prompt. Check backend logs for details.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating system prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update system prompt: {str(e)}")


@router.put("/welcome-message", response_model=StatusResponse)
@router.patch("/welcome-message", response_model=StatusResponse)
@router.post("/welcome-message", response_model=StatusResponse)
async def update_welcome_message(
    request: Optional[WelcomeMessageRequest] = None,
    welcome_message: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    x_organization_id: Optional[str] = Header(None),
):
    """Update only the welcome message for the system prompt."""
    try:
        # Get welcome_message from request body or query parameter
        msg = None
        if request and request.welcome_message is not None:
            msg = request.welcome_message
        elif welcome_message is not None:
            msg = welcome_message
        
        resolved_org = resolve_org_id(
            body_value=request.organization_id if request else None,
            query_value=organization_id,
            header_value=x_organization_id,
        )
        
        # Get current prompt to preserve it
        prompt_data = get_prompt_with_name(resolved_org)
        current_prompt = prompt_data.get("prompt", "")
        current_name = prompt_data.get("name")
        
        # Update with same prompt but new welcome_message
        success = update_prompt(
            current_prompt,
            current_name,
            msg,
            organization_id=resolved_org
        )
        
        if success:
            org_msg = f" for organization {resolved_org}" if resolved_org else " as default prompt"
            message = f"Welcome message updated successfully{org_msg}"
            return StatusResponse(status="success", message=message)
        else:
            raise HTTPException(status_code=500, detail="Failed to update welcome message. Check backend logs for details.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating welcome message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update welcome message: {str(e)}")


@router.post("/reset", response_model=StatusResponse)
async def reset_system_prompt(
    organization_id: Optional[str] = Query(None),
    x_organization_id: Optional[str] = Header(None),
):
    """Reset the system prompt to default."""
    try:
        resolved_org = resolve_org_id(query_value=organization_id, header_value=x_organization_id)
        success = reset_prompt(resolved_org)
        if success:
            app_state._log_callback(
                f"System prompt reset to default via API (org={resolved_org or 'default'})"
            )
            return StatusResponse(status="success", message="System prompt reset to default successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to reset system prompt")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting system prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset system prompt: {str(e)}")

