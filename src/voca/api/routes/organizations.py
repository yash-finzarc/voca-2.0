import logging
from typing import List

from fastapi import APIRouter, HTTPException

from src.voca.api.models import OrganizationRequest, OrganizationResponse

router = APIRouter(prefix="/api/organizations")
logger = logging.getLogger(__name__)


@router.post("", response_model=OrganizationResponse)
async def create_organization(request: OrganizationRequest):
    """Create a new organization."""
    from src.voca.supabase_client import get_supabase_client, is_supabase_configured

    if not is_supabase_configured():
        raise HTTPException(status_code=400, detail="Supabase not configured")

    client = get_supabase_client()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client unavailable")

    try:
        insert_data = {
            "name": request.name.strip(),
            "domain": request.domain.strip() if request.domain else None,
            "api_key": request.api_key.strip() if request.api_key else None,
        }

        response = client.table("organizations").insert(insert_data).execute()

        if response.data and len(response.data) > 0:
            org_data = response.data[0]
            return OrganizationResponse(
                id=org_data["id"],
                name=org_data["name"],
                domain=org_data.get("domain"),
                api_key=org_data.get("api_key"),
                created_at=org_data.get("created_at"),
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to create organization")
    except Exception as e:
        logger.error(f"Error creating organization: {e}")
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=400, detail="Organization with this name or API key already exists")
        raise HTTPException(status_code=500, detail=f"Failed to create organization: {str(e)}")


@router.get("", response_model=List[OrganizationResponse])
async def list_organizations():
    """List all organizations."""
    from src.voca.supabase_client import get_supabase_client, is_supabase_configured

    if not is_supabase_configured():
        raise HTTPException(status_code=400, detail="Supabase not configured")

    client = get_supabase_client()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client unavailable")

    try:
        response = client.table("organizations").select("*").order("created_at", desc=True).execute()

        if response.data:
            return [
                OrganizationResponse(
                    id=org["id"],
                    name=org["name"],
                    domain=org.get("domain"),
                    api_key=org.get("api_key"),
                    created_at=org.get("created_at"),
                )
                for org in response.data
            ]
        return []
    except Exception as e:
        logger.error(f"Error listing organizations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list organizations: {str(e)}")


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(organization_id: str):
    """Get a specific organization by ID."""
    from src.voca.supabase_client import get_supabase_client, is_supabase_configured

    if not is_supabase_configured():
        raise HTTPException(status_code=400, detail="Supabase not configured")

    client = get_supabase_client()
    if client is None:
        raise HTTPException(status_code=500, detail="Supabase client unavailable")

    try:
        response = client.table("organizations").select("*").eq("id", organization_id).limit(1).execute()

        if response.data and len(response.data) > 0:
            org_data = response.data[0]
            return OrganizationResponse(
                id=org_data["id"],
                name=org_data["name"],
                domain=org_data.get("domain"),
                api_key=org_data.get("api_key"),
                created_at=org_data.get("created_at"),
            )
        else:
            raise HTTPException(status_code=404, detail="Organization not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting organization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get organization: {str(e)}")

