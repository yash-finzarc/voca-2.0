from typing import Dict, Any

from fastapi import APIRouter

from src.voca.api.state import app_state

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
    Fetches actual model data from streaming APIs instead of hardcoded values.
    """
    model_info = app_state.get_model_info()
    return {
        "status": "success",
        "models": model_info,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }

