"""
Twilio API endpoints.
"""
import asyncio
import threading
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import HTTPException, Query
from fastapi.routing import APIRouter

from src.voca.api.app_state import app_state
from src.voca.api.models import (
    StatusResponse,
    CountryCode,
    CallStatusResponse,
    CallStatusSummary,
    CallRecord,
    MakeCallRequest,
)
from src.voca.twilio_config import get_twilio_config

router = APIRouter(prefix="/api/twilio", tags=["twilio"])


@router.get("/country-codes", response_model=list[CountryCode])
async def get_country_codes():
    """Get list of supported country codes."""
    country_codes = {
        "United States (+1)": "+1",
        "Canada (+1)": "+1",
        "United Kingdom (+44)": "+44",
        "India (+91)": "+91",
        "Australia (+61)": "+61",
        "Germany (+49)": "+49",
        "France (+33)": "+33",
        "Japan (+81)": "+81",
        "China (+86)": "+86",
        "Brazil (+55)": "+55",
        "Mexico (+52)": "+52",
        "Russia (+7)": "+7",
        "South Korea (+82)": "+82",
        "Italy (+39)": "+39",
        "Spain (+34)": "+34",
        "Netherlands (+31)": "+31",
        "Sweden (+46)": "+46",
        "Norway (+47)": "+47",
        "Denmark (+45)": "+45",
        "Finland (+358)": "+358",
        "Poland (+48)": "+48",
        "Turkey (+90)": "+90",
        "South Africa (+27)": "+27",
        "Egypt (+20)": "+20",
        "Nigeria (+234)": "+234",
        "Kenya (+254)": "+254",
        "Israel (+972)": "+972",
        "Saudi Arabia (+966)": "+966",
        "UAE (+971)": "+971",
        "Singapore (+65)": "+65",
        "Malaysia (+60)": "+60",
        "Thailand (+66)": "+66",
        "Philippines (+63)": "+63",
        "Indonesia (+62)": "+62",
        "Vietnam (+84)": "+84",
        "Argentina (+54)": "+54",
        "Chile (+56)": "+56",
        "Colombia (+57)": "+57",
        "Peru (+51)": "+51",
        "Venezuela (+58)": "+58"
    }
    
    return [CountryCode(name=name, code=code) for name, code in country_codes.items()]


@router.post("/start-server", response_model=StatusResponse)
async def start_twilio_server():
    """Start the Twilio webhook server."""
    if app_state.is_twilio_server_running:
        return StatusResponse(status="success", message="Twilio server is already running")
    
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        raise HTTPException(
            status_code=400,
            detail="Twilio not configured. Please set up environment variables."
        )
    
    def _worker():
        try:
            twilio_manager.start(host='0.0.0.0', port=5000)
            app_state.is_twilio_server_running = True
            app_state._log_callback("Twilio server started successfully")
        except Exception as e:
            app_state._log_callback(f"Failed to start Twilio server: {e}")
            app_state.is_twilio_server_running = False
    
    threading.Thread(target=_worker, daemon=True).start()
    
    # Poll for server readiness with a timeout to avoid returning false errors
    timeout_seconds = 30
    poll_interval = 0.5
    elapsed = 0.0

    while elapsed < timeout_seconds:
        if app_state.is_twilio_server_running:
            return StatusResponse(status="success", message="Twilio server started")
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    
    raise HTTPException(status_code=500, detail="Failed to start Twilio server")


@router.post("/make-call", response_model=Dict[str, Any])
async def make_twilio_call(request: MakeCallRequest):
    """Make an outbound call using Twilio."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        raise HTTPException(
            status_code=400,
            detail="Twilio not configured. Please set up environment variables."
        )
    
    if not request.phone_number:
        raise HTTPException(status_code=400, detail="Phone number is required")
    
    def _worker():
        try:
            call_sid = twilio_manager.make_call(request.phone_number)
            if call_sid:
                app_state._log_callback(f"Call initiated to {request.phone_number}, SID: {call_sid}")
            else:
                app_state._log_callback(f"Failed to initiate call to {request.phone_number}")
        except Exception as e:
            app_state._log_callback(f"Call error: {e}")
    
    threading.Thread(target=_worker, daemon=True).start()
    
    return {
        "status": "initiated",
        "message": f"Call to {request.phone_number} is being initiated"
    }


@router.post("/hangup-all", response_model=StatusResponse)
async def hangup_all_calls():
    """Hang up all active calls."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        raise HTTPException(
            status_code=400,
            detail="Twilio not configured. Please set up environment variables."
        )
    
    try:
        twilio_manager.hangup_all_calls()
        app_state._log_callback("All calls hung up")
        return StatusResponse(status="success", message="All calls hung up")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to hang up calls: {e}")


@router.get("/status", response_model=CallStatusResponse)
async def get_twilio_status():
    """Get Twilio call status."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        return CallStatusResponse(
            active_calls=0,
            models_ready=False,
            calls={}
        )
    
    try:
        status = twilio_manager.get_call_status()
        return CallStatusResponse(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {e}")


@router.get("/call-status/summary", response_model=CallStatusSummary)
async def get_twilio_call_status_summary(
    limit: int = Query(20, ge=1, le=100),
    start_time_after: Optional[str] = Query(
        None,
        description="ISO 8601 timestamp. Only calls starting after this time are returned.",
    ),
    start_time_before: Optional[str] = Query(
        None,
        description="ISO 8601 timestamp. Only calls starting before this time are returned.",
    ),
):
    """Fetch categorized Twilio call records for the dashboard."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        raise HTTPException(
            status_code=400,
            detail="Twilio not configured. Please set up environment variables.",
        )

    def _parse_iso8601(value: Optional[str], field_name: str) -> Optional[datetime]:
        if value is None:
            return None
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid {field_name} value. Expected ISO 8601 format.",
            ) from exc

    parsed_after = _parse_iso8601(start_time_after, "start_time_after")
    parsed_before = _parse_iso8601(start_time_before, "start_time_before")

    try:
        summary = twilio_manager.fetch_call_history(
            limit=limit,
            start_time_after=parsed_after,
            start_time_before=parsed_before,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch call history: {exc}",
        ) from exc

    return CallStatusSummary(
        ongoing=[CallRecord(**record) for record in summary.get("ongoing", [])],
        declined=[CallRecord(**record) for record in summary.get("declined", [])],
        completed=[CallRecord(**record) for record in summary.get("completed", [])],
        others=[CallRecord(**record) for record in summary.get("others", [])],
    )


@router.get("/configured", response_model=Dict[str, bool])
async def check_twilio_configured():
    """Check if Twilio is configured."""
    config = get_twilio_config()
    is_configured = config.validate()
    return {"configured": is_configured}


@router.get("/webhook-urls", response_model=Dict[str, str])
async def get_twilio_webhook_urls():
    """Get all Twilio webhook URLs being used."""
    config = get_twilio_config()
    webhook_url = config.get_webhook_url()
    
    # Calculate make_call URL (same logic as in twilio_voice.py)
    make_call_url = f"{webhook_url.replace('/webhook/voice', '')}/outbound"
    
    return {
        "incoming_call_webhook": webhook_url,
        "make_call_webhook": make_call_url,
        "call_status_webhook": f"{webhook_url.replace('/webhook/voice', '')}/call/status",
        "process_speech_webhook": f"{webhook_url.replace('/webhook/voice', '')}/process_speech/{{call_sid}}"
    }

