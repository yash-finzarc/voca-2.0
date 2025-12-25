import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from src.voca.api.models import (
    SystemPromptRequest,
    SystemPromptResponse,
    SystemPromptListItem,
)

router = APIRouter(prefix="/api/system-prompt")
logger = logging.getLogger(__name__)


@router.post("", response_model=SystemPromptResponse)
async def create_system_prompt(request: SystemPromptRequest):
    """Create or update a system prompt."""
    from src.voca.supabase_client import get_supabase_client, is_supabase_configured

    if not is_supabase_configured():
        raise HTTPException(status_code=400, detail="Supabase not configured")

    client = get_supabase_client()

    try:
        # Upsert system prompt
        result = (
            client.table("system_prompts")
            .upsert(
                {
                    "name": request.name,
                    "system_prompt": request.prompt,
                    "welcome_message": request.welcome_message,
                },
                on_conflict="name",
            )
            .execute()
        )

        return SystemPromptResponse(
            name=request.name,
            prompt=request.prompt,
            welcome_message=request.welcome_message,
        )
    except Exception as e:
        logger.error(f"Error creating system prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create system prompt: {str(e)}")


@router.get("", response_model=List[SystemPromptListItem])
async def list_system_prompts():
    """List all system prompts."""
    from src.voca.supabase_client import get_supabase_client, is_supabase_configured

    if not is_supabase_configured():
        raise HTTPException(status_code=400, detail="Supabase not configured")

    client = get_supabase_client()

    try:
        result = client.table("system_prompts").select("name").execute()

        return [SystemPromptListItem(name=item["name"]) for item in result.data]
    except Exception as e:
        logger.error(f"Error listing system prompts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list system prompts: {str(e)}")


@router.get("/{name}", response_model=SystemPromptResponse)
async def get_system_prompt(name: str):
    """Get a system prompt by name."""
    from src.voca.supabase_client import get_supabase_client, is_supabase_configured

    if not is_supabase_configured():
        raise HTTPException(status_code=400, detail="Supabase not configured")

    client = get_supabase_client()

    try:
        result = (
            client.table("system_prompts")
            .select("name, system_prompt, welcome_message")
            .eq("name", name)
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail=f"System prompt '{name}' not found")

        return SystemPromptResponse(
            name=result.data["name"],
            prompt=result.data["system_prompt"],
            welcome_message=result.data.get("welcome_message", ""),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting system prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get system prompt: {str(e)}")


@router.delete("/{name}")
async def delete_system_prompt(name: str):
    """Delete a system prompt by name."""
    from src.voca.supabase_client import get_supabase_client, is_supabase_configured

    if not is_supabase_configured():
        raise HTTPException(status_code=400, detail="Supabase not configured")

    client = get_supabase_client()

    try:
        result = client.table("system_prompts").delete().eq("name", name).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail=f"System prompt '{name}' not found")

        return {"message": f"System prompt '{name}' deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting system prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete system prompt: {str(e)}")

