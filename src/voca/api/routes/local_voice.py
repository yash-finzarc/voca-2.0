import threading

from fastapi import APIRouter, HTTPException

from src.voca.api.models import StatusResponse
from src.voca.api.state import app_state

router = APIRouter(prefix="/api/local-voice")


@router.post("/start-continuous", response_model=StatusResponse)
async def start_continuous_call():
    """Start continuous voice interaction."""
    raise HTTPException(
        status_code=501,
        detail="Local voice interaction is not available. This application uses Deepgram Voice Agent for Twilio calls only."
    )


@router.post("/stop-continuous", response_model=StatusResponse)
async def stop_continuous_call():
    """Stop continuous voice interaction."""
    raise HTTPException(
        status_code=501,
        detail="Local voice interaction is not available. This application uses Deepgram Voice Agent for Twilio calls only."
    )


@router.post("/one-minute-test", response_model=StatusResponse)
async def start_one_minute_test():
    """Run one minute test interaction."""
    raise HTTPException(
        status_code=501,
        detail="Local voice interaction is not available. This application uses Deepgram Voice Agent for Twilio calls only."
    )


@router.get("/status", response_model=StatusResponse)
async def get_local_voice_status():
    """Get local voice status."""
    return StatusResponse(
        status="unavailable",
        message="Local voice interaction is not available. This application uses Deepgram Voice Agent for Twilio calls only."
    )


