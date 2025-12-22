import logging
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response

from src.voca.api.models import (
    StatusResponse,
    SystemPromptResponse,
    SystemPromptListItem,
    SystemPromptRequest,
    WelcomeMessageRequest,
)
from src.voca.api.utils import resolve_org_id
from src.voca.config import Config
from src.voca.system_prompt import (
    activate_prompt_by_id,
    create_prompt,
    create_prompt_with_id,
    get_default_prompt,
    get_prompt,
    get_prompt_with_name,
    reset_prompt,
    update_prompt,
    update_prompt_by_id,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/system-prompt", response_model=SystemPromptResponse)
async def get_system_prompt(organization_id: Optional[str] = Query(None), x_organization_id: Optional[str] = Header(None)):
    """Get the current system prompt and name."""
    try:
        resolved_org = resolve_org_id(query_value=organization_id, header_value=x_organization_id)
        prompt_data = get_prompt_with_name(resolved_org)
        return SystemPromptResponse(
            prompt=prompt_data["prompt"],
            name=prompt_data.get("name"),
            welcome_message=prompt_data.get("welcome_message"),
        )
    except Exception as e:
        logger.error(f"Error fetching system prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch system prompt: {str(e)}")


@router.get("/api/system-prompt/list", response_model=List[SystemPromptListItem])
async def list_system_prompts(
    organization_id: Optional[str] = Query(None),
    x_organization_id: Optional[str] = Header(None),
    include_default: bool = Query(True, description="Include default prompts"),
):
    """List all system prompts (default and organization-specific)."""
    from src.voca.supabase_client import get_supabase_client, is_supabase_configured

    results: List[SystemPromptListItem] = []

    if not is_supabase_configured():
        logger.error("Supabase not configured. System prompts must be stored in Supabase.")
        raise HTTPException(status_code=500, detail="Supabase is not configured. Please configure Supabase to manage system prompts.")

    client = get_supabase_client()
    if client is None:
        logger.error("Supabase client unavailable. System prompts must be stored in Supabase.")
        raise HTTPException(status_code=500, detail="Supabase client is unavailable. Please check your Supabase configuration.")

    try:
        resolved_org = resolve_org_id(query_value=organization_id, header_value=x_organization_id)

        if include_default:
            try:
                default_response = client.table("system_prompts").select("*").order("updated_at", desc=True).execute()
                if default_response.data:
                    for item in default_response.data:
                        is_default = item.get("is_default", False)
                        if is_default:
                            results.append(
                                SystemPromptListItem(
                                    id=item.get("id"),
                                    name=item.get("name") or "Default",
                                    prompt=item.get("prompt", ""),
                                    welcome_message=item.get("welcome_message"),
                                    is_default=is_default,
                                    is_active=item.get("is_active", False),
                                    created_at=item.get("created_at"),
                                    updated_at=item.get("updated_at"),
                                )
                            )
            except Exception as e:
                logger.warning(f"Error fetching default prompts: {e}")

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
            try:
                all_org_response = (
                    client.table("organization_system_prompts").select("*").eq("is_active", True).order("updated_at", desc=True).execute()
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


@router.post("/api/system-prompt", response_model=StatusResponse)
@router.put("/api/system-prompt", response_model=StatusResponse)
@router.patch("/api/system-prompt", response_model=StatusResponse)
async def update_system_prompt(request: SystemPromptRequest, x_organization_id: Optional[str] = Header(None)):
    """
    DEPRECATED: Frontend should manage system prompts directly via Supabase.
    This endpoint is kept for backward compatibility but returns a message.
    """
    logger.warning("System prompt create/update endpoint called - frontend should use Supabase directly")
    return StatusResponse(
        status="info",
        message="System prompts are now managed directly from the frontend via Supabase. Please use the Supabase client in your Next.js frontend to create/update prompts.",
        prompt_id=None,
    )


@router.put("/api/system-prompt/welcome-message", response_model=StatusResponse)
@router.patch("/api/system-prompt/welcome-message", response_model=StatusResponse)
@router.post("/api/system-prompt/welcome-message", response_model=StatusResponse)
async def update_welcome_message(
    request: Optional[WelcomeMessageRequest] = None,
    welcome_message: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    x_organization_id: Optional[str] = Header(None),
):
    """
    DEPRECATED: Frontend should manage welcome messages directly via Supabase.
    """
    logger.warning("Welcome message update endpoint called - frontend should use Supabase directly")
    return StatusResponse(
        status="info",
        message="Welcome messages are now managed directly from the frontend via Supabase. Please use the Supabase client in your Next.js frontend to update welcome messages.",
        prompt_id=None,
    )


@router.options("/api/system-prompt/activate")
async def activate_system_prompt_options(request: Request):
    """Handle CORS preflight for activate endpoint."""
    return Response(
        content="",
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
            "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept, Origin, X-Requested-With",
            "Access-Control-Max-Age": "3600",
        },
    )


@router.post("/api/system-prompt/activate", response_model=StatusResponse)
@router.put("/api/system-prompt/activate", response_model=StatusResponse)
@router.patch("/api/system-prompt/activate", response_model=StatusResponse)
@router.get("/api/system-prompt/activate", response_model=StatusResponse)
async def activate_system_prompt(request: Request, prompt_id: Optional[str] = Query(None, description="UUID of the prompt to activate (query parameter)")):
    """
    DEPRECATED: Frontend should manage prompt activation directly via Supabase.
    """
    logger.warning("System prompt activate endpoint called - frontend should use Supabase directly")
    return StatusResponse(
        status="info",
        message="System prompt activation is now managed directly from the frontend via Supabase. Please use the Supabase client in your Next.js frontend to activate/deactivate prompts.",
        prompt_id=None,
    )


@router.post("/api/system-prompt/reset", response_model=StatusResponse)
async def reset_system_prompt(organization_id: Optional[str] = Query(None), x_organization_id: Optional[str] = Header(None)):
    """
    DEPRECATED: Frontend should manage prompt resets directly via Supabase.
    """
    logger.warning("System prompt reset endpoint called - frontend should use Supabase directly")
    return StatusResponse(
        status="info",
        message="System prompt reset is now managed directly from the frontend via Supabase. Please use the Supabase client in your Next.js frontend to manage prompts.",
        prompt_id=None,
    )

