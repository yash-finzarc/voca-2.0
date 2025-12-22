from typing import Dict, Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/server/info", response_model=Dict[str, Any])
async def get_server_info():
    """Get server information (Linode server URL)."""
    linode_url = "http://172.105.50.83:8000"
    return {"status": "success", "server_url": linode_url, "port": 8000, "message": f"Server running on Linode: {linode_url}"}

