from typing import Dict, Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/server/info", response_model=Dict[str, Any])
async def get_server_info():
    """Get server information."""
    import socket
    hostname = socket.gethostname()
    return {"status": "success", "hostname": hostname}


@router.get("/api/models/info", response_model=Dict[str, Any])
async def get_models_info():
    """
    Get real-time model information from active services.
    Model info functionality has been removed.
    """
    return {
        "status": "success",
        "models": {
            "message": "Model info feature has been removed"
        },
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }

