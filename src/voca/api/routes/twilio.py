import asyncio
import json
import logging
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Request, Query

from src.voca.api.models import (
    CountryCode,
    StatusResponse,
    CallStatusResponse,
    CallStatusSummary,
    CallRecord,
)
from src.voca.api.state import app_state
from src.voca.config import Config
from src.voca.twilio_config import get_twilio_config

router = APIRouter(prefix="/api/twilio")
logger = logging.getLogger(__name__)


@router.get("/country-codes", response_model=List[CountryCode])
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
        "Venezuela (+58)": "+58",
    }

    return [CountryCode(name=name, code=code) for name, code in country_codes.items()]


@router.post("/start-server", response_model=StatusResponse)
async def start_twilio_server():
    """Start the Twilio webhook server."""
    if app_state.is_twilio_server_running:
        return StatusResponse(status="success", message="Twilio server is already running")

    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        raise HTTPException(status_code=400, detail="Twilio not configured. Please set up environment variables.")

    def _worker():
        try:
            twilio_manager.start(host="0.0.0.0", port=5000)
            app_state.is_twilio_server_running = True
            app_state._log_callback("Twilio server started")
        except Exception as e:
            app_state._log_callback(f"Failed to start Twilio server: {e}")
            app_state.is_twilio_server_running = False

    threading.Thread(target=_worker, daemon=True).start()

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
async def make_twilio_call(request: Request):
    """Make an outbound call using Twilio."""
    body = None
    try:
        body = await request.json()
    except Exception:
        try:
            body_bytes = await request.body()
            body_str = body_bytes.decode("utf-8") if body_bytes else ""

            if body_str.startswith('"') and body_str.endswith('"'):
                body_str = body_str[1:-1]
                body_str = body_str.replace('\\"', '"').replace("\\n", "\n")

            if body_str:
                body = json.loads(body_str)
            else:
                body = {}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse request body as JSON: {e}, body: {body_str[:100] if 'body_str' in locals() else 'N/A'}")
            raise HTTPException(
                status_code=422,
                detail='Invalid JSON format in request body. Expected: {"phone_number": "+1234567890"}',
            )
        except Exception as e:
            logger.error(f"Failed to read request body: {e}")
            raise HTTPException(status_code=422, detail=f"Failed to parse request body: {str(e)}")

    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="Invalid JSON format in request body")

    phone_number = body.get("phone_number") if isinstance(body, dict) else None

    if not phone_number:
        raise HTTPException(
            status_code=400,
            detail='Phone number is required. Expected format: {"phone_number": "+1234567890"}',
        )

    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        raise HTTPException(status_code=400, detail="Twilio not configured. Please set up environment variables.")

    def _worker():
        try:
            call_sid = twilio_manager.make_call(phone_number)
            if call_sid:
                app_state._log_callback(f"Call initiated to {phone_number}, SID: {call_sid}")
            else:
                app_state._log_callback(f"Failed to initiate call to {phone_number}")
        except Exception as e:
            app_state._log_callback(f"Call error: {e}")

    threading.Thread(target=_worker, daemon=True).start()

    return {"status": "initiated", "message": f"Call to {phone_number} is being initiated"}


@router.post("/hangup-all", response_model=StatusResponse)
async def hangup_all_calls():
    """Hang up all active calls."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        raise HTTPException(status_code=400, detail="Twilio not configured. Please set up environment variables.")

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
        return CallStatusResponse(active_calls=0, models_ready=False, calls={})

    try:
        status = twilio_manager.get_call_status()
        return CallStatusResponse(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {e}")


@router.get("/call-status/summary", response_model=CallStatusSummary)
async def get_twilio_call_status_summary(
    limit: int = Query(20, ge=1, le=100),
    start_time_after: Optional[str] = Query(None, description="ISO 8601 timestamp. Only calls starting after this time are returned."),
    start_time_before: Optional[str] = Query(None, description="ISO 8601 timestamp. Only calls starting before this time are returned."),
):
    """Fetch categorized Twilio call records for the dashboard."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        config = get_twilio_config()
        if not config.validate():
            raise HTTPException(
                status_code=400,
                detail="Twilio not configured. Please set up environment variables (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER).",
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Twilio configuration is valid but manager failed to initialize. Check server logs for details.",
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
            raise HTTPException(status_code=400, detail=f"Invalid {field_name} value. Expected ISO 8601 format.") from exc

    parsed_after = _parse_iso8601(start_time_after, "start_time_after")
    parsed_before = _parse_iso8601(start_time_before, "start_time_before")

    try:
        summary = twilio_manager.fetch_call_history(limit=limit, start_time_after=parsed_after, start_time_before=parsed_before)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch call history: {exc}") from exc

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

    make_call_url = f"{webhook_url.replace('/webhook/voice', '')}/outbound"

    return {
        "incoming_call_webhook": webhook_url,
        "make_call_webhook": make_call_url,
        "call_status_webhook": f"{webhook_url.replace('/webhook/voice', '')}/call/status",
        "process_speech_webhook": f"{webhook_url.replace('/webhook/voice', '')}/process_speech/{{call_sid}}",
    }

