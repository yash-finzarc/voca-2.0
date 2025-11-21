"""
FastAPI application for VOCA frontend backend integration.
Provides REST API endpoints for the web frontend.
"""
import asyncio
import logging
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime
from queue import Queue, Empty

import os
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from twilio.twiml.voice_response import VoiceResponse
import time

# Ngrok removed - using Linode server
NGROK_AVAILABLE = False

from src.voca.orchestrator import VocaOrchestrator
from src.voca.twilio_voice import TwilioCallManager
from src.voca.twilio_config import get_twilio_config
from src.voca.config import Config
from src.voca.system_prompt import (
    get_prompt,
    get_prompt_with_name,
    update_prompt,
    reset_prompt,
    get_default_prompt,
    DEFAULT_SYSTEM_PROMPT,
)
from src.voca.conversation_logger import log_user, log_ai


# Request/Response Models
class MakeCallRequest(BaseModel):
    phone_number: str


class CountryCode(BaseModel):
    name: str
    code: str


class CallInfo(BaseModel):
    call_sid: str
    status: str
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    start_time: Optional[float] = None


class CallStatusResponse(BaseModel):
    active_calls: int
    models_ready: bool
    calls: Dict[str, Dict[str, Any]]


class StatusResponse(BaseModel):
    status: str
    message: str


class LogEntry(BaseModel):
    timestamp: str
    message: str


class NgrokUrlRequest(BaseModel):
    url: str


class CallRecord(BaseModel):
    call_sid: str
    status: str
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    direction: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: Optional[int] = None
    duration_human: Optional[str] = None


class CallStatusSummary(BaseModel):
    ongoing: List[CallRecord] = Field(default_factory=list)
    declined: List[CallRecord] = Field(default_factory=list)
    completed: List[CallRecord] = Field(default_factory=list)
    others: List[CallRecord] = Field(default_factory=list)


class SystemPromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="The system prompt text")
    name: Optional[str] = Field(None, description="The name of the system prompt")
    welcome_message: Optional[str] = Field(None, description="Custom welcome message for calls. If not provided, will be generated from system prompt.")
    organization_id: Optional[str] = Field(
        None,
        description="Organization ID this prompt belongs to",
    )


class SystemPromptResponse(BaseModel):
    prompt: str
    name: Optional[str] = None
    welcome_message: Optional[str] = None


class SystemPromptListItem(BaseModel):
    id: Optional[str] = None
    key: Optional[str] = None
    name: Optional[str] = None
    prompt: str
    welcome_message: Optional[str] = None
    is_default: Optional[bool] = None
    organization_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class OrganizationRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Organization name")
    domain: Optional[str] = Field(None, description="Organization domain")
    api_key: Optional[str] = Field(None, description="API key for authentication")


class OrganizationResponse(BaseModel):
    id: str
    name: str
    domain: Optional[str] = None
    api_key: Optional[str] = None
    created_at: Optional[str] = None


def _resolve_org_id(
    body_value: Optional[str] = None,
    query_value: Optional[str] = None,
    header_value: Optional[str] = None,
) -> Optional[str]:
    """Determine the organization ID from request components."""
    return body_value or query_value or header_value or Config.default_organization_id or None


# Global state management
class AppState:
    def __init__(self):
        self.orchestrator: Optional[VocaOrchestrator] = None
        self.twilio_manager: Optional[TwilioCallManager] = None
        self.log_queue: Queue = Queue()
        self.is_twilio_server_running: bool = False
        self.is_continuous_call_running: bool = False
        self.continuous_call_thread: Optional[threading.Thread] = None
        self.ngrok_tunnel = None  # pyngrok tunnel object
        self.ngrok_url: Optional[str] = None
        self.ngrok_port: int = 8000  # API server port
        
    def get_orchestrator(self) -> VocaOrchestrator:
        if self.orchestrator is None:
            self.orchestrator = VocaOrchestrator(on_log=self._log_callback)
        return self.orchestrator
    
    def get_twilio_manager(self) -> Optional[TwilioCallManager]:
        if self.twilio_manager is None:
            config = get_twilio_config()
            if config.validate():
                self.twilio_manager = TwilioCallManager(self.get_orchestrator())
            else:
                return None
        return self.twilio_manager
    
    def _log_callback(self, message: str):
        """Callback for log messages."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "message": message
        }
        self.log_queue.put(log_entry)
        # WebSocket broadcast will happen via background task


# Global app state
app_state = AppState()

# Initialize FastAPI app
app = FastAPI(
    title="VOCA API",
    description="API for VOCA AI Voice Assistant",
    version="1.0.0"
)

# Add CORS middleware for frontend
# Allow specific origins for production and development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://voca-frontend-self.vercel.app",  # Vercel production deployment
        "http://localhost:3000",  # Local development
        "http://localhost:3001",  # Alternative local port
    ],
    allow_credentials=True,  # Can be True when using specific origins
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# WebSocket connections for real-time logs
active_websockets: List[WebSocket] = []


async def broadcast_log(log_entry: Dict[str, str]):
    """Broadcast log entry to all connected WebSocket clients."""
    if active_websockets:
        disconnected = []
        for ws in active_websockets:
            try:
                await ws.send_json(log_entry)
            except Exception:
                disconnected.append(ws)
        
        # Remove disconnected clients
        for ws in disconnected:
            active_websockets.remove(ws)


@app.on_event("startup")
async def startup_event():
    """Initialize components on startup."""
    logger = logging.getLogger(__name__)
    logger.info("VOCA API server starting up...")
    # Start log broadcaster task
    asyncio.create_task(log_broadcaster())
    
    # Ngrok removed - using Linode server (172.105.50.83:8000)
    # Old ngrok startup code commented out:
    # # Automatically start ngrok tunnel when API server starts
    run_main = os.getenv("RUN_MAIN")
    if (
        NGROK_AVAILABLE
        and app_state.ngrok_tunnel is None
        and (run_main is None or run_main == "true")  # Run when not using reloader or in main process
    ):
        loop = asyncio.get_running_loop()

        async def start_ngrok():
            def _connect():
                try:
                    tunnel = ngrok.connect(app_state.ngrok_port)
                    app_state.ngrok_tunnel = tunnel
                    app_state.ngrok_url = tunnel.public_url
                    logger.info(f"Ngrok tunnel started automatically: {app_state.ngrok_url}")
                    app_state._log_callback(f"Ngrok tunnel started automatically: {app_state.ngrok_url}")
                except Exception as exc:
                    logger.error(f"Failed to start ngrok tunnel automatically: {exc}")
                    app_state._log_callback(f"Failed to start ngrok tunnel automatically: {exc}")

            await loop.run_in_executor(None, _connect)

        await start_ngrok()
    
    logger.info("Server running on Linode: http://172.105.50.83:8000")
    app_state._log_callback("Server running on Linode: http://172.105.50.83:8000")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger = logging.getLogger(__name__)
    logger.info("VOCA API server shutting down...")
    
    # Stop ngrok tunnel if running
    if app_state.ngrok_tunnel is not None and NGROK_AVAILABLE:
        try:
            ngrok.disconnect(app_state.ngrok_tunnel.public_url)
            logger.info("Ngrok tunnel stopped")
            app_state._log_callback("Ngrok tunnel stopped")
        except Exception as e:
            logger.error(f"Error stopping ngrok tunnel: {e}")
        finally:
            app_state.ngrok_tunnel = None
            app_state.ngrok_url = None


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "VOCA API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# OPTIONS handler - FastAPI CORS middleware should handle this automatically
# But we add explicit handler as fallback for ngrok compatibility
@app.options("/{full_path:path}")
async def options_handler(full_path: str, request: Request):
    """Handle OPTIONS requests for CORS preflight."""
    origin = request.headers.get("origin", "*")
    
    response = Response(
        content="",
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": origin if origin else "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept, Origin, X-Requested-With",
            "Access-Control-Max-Age": "3600",
        }
    )
    return response


# ==================== Local Voice Endpoints ====================

@app.post("/api/local-voice/start-continuous", response_model=StatusResponse)
async def start_continuous_call():
    """Start continuous voice interaction."""
    if app_state.is_continuous_call_running:
        raise HTTPException(status_code=400, detail="Continuous call is already running")
    
    orchestrator = app_state.get_orchestrator()
    
    def _worker():
        try:
            app_state.is_continuous_call_running = True
            orchestrator.run_continuous_vad_loop()
        except Exception as e:
            app_state._log_callback(f"Continuous call error: {e}")
        finally:
            app_state.is_continuous_call_running = False
    
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    app_state.continuous_call_thread = thread
    
    app_state._log_callback("Continuous call started")
    return StatusResponse(status="success", message="Continuous call started")


@app.post("/api/local-voice/stop-continuous", response_model=StatusResponse)
async def stop_continuous_call():
    """Stop continuous voice interaction."""
    if not app_state.is_continuous_call_running:
        raise HTTPException(status_code=400, detail="Continuous call is not running")
    
    orchestrator = app_state.get_orchestrator()
    setattr(orchestrator, "_vad_stop", True)
    app_state.is_continuous_call_running = False
    
    app_state._log_callback("Continuous call stopped")
    return StatusResponse(status="success", message="Continuous call stopped")


@app.post("/api/local-voice/one-minute-test", response_model=StatusResponse)
async def start_one_minute_test():
    """Run one minute test interaction."""
    orchestrator = app_state.get_orchestrator()
    
    def _worker():
        try:
            orchestrator.run_one_minute_interaction(duration_sec=30)
        except Exception as e:
            app_state._log_callback(f"One minute test error: {e}")
    
    threading.Thread(target=_worker, daemon=True).start()
    app_state._log_callback("One minute test started")
    return StatusResponse(status="success", message="One minute test started")


@app.get("/api/local-voice/status", response_model=StatusResponse)
async def get_local_voice_status():
    """Get local voice status."""
    orchestrator = app_state.get_orchestrator()
    models_ready = orchestrator.models_ready()
    
    status = "running" if app_state.is_continuous_call_running else "ready"
    message = f"Models ready: {models_ready}, Continuous call: {app_state.is_continuous_call_running}"
    
    return StatusResponse(status=status, message=message)


# ==================== Twilio Endpoints ====================

@app.get("/api/twilio/country-codes", response_model=List[CountryCode])
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


@app.post("/api/twilio/start-server", response_model=StatusResponse)
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


@app.post("/api/twilio/make-call", response_model=Dict[str, Any])
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


@app.post("/api/twilio/hangup-all", response_model=StatusResponse)
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


@app.get("/api/twilio/status", response_model=CallStatusResponse)
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


@app.get("/api/twilio/call-status/summary", response_model=CallStatusSummary)
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


@app.get("/api/twilio/configured", response_model=Dict[str, bool])
async def check_twilio_configured():
    """Check if Twilio is configured."""
    config = get_twilio_config()
    is_configured = config.validate()
    return {"configured": is_configured}


@app.get("/api/twilio/webhook-urls", response_model=Dict[str, str])
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


# ==================== Ngrok Endpoints ====================

@app.post("/api/ngrok/start", response_model=Dict[str, Any])
async def start_ngrok_tunnel():
    """Start ngrok tunnel for the API server."""
    if not NGROK_AVAILABLE:
        raise HTTPException(
            status_code=400,
            detail="pyngrok not installed. Install it with: pip install pyngrok"
        )
    
    if app_state.ngrok_tunnel is not None:
        return {
            "status": "already_running",
            "url": app_state.ngrok_url,
            "message": "Ngrok tunnel is already running"
        }
    
    try:
        # Start ngrok tunnel on API server port (8000)
        app_state.ngrok_tunnel = ngrok.connect(app_state.ngrok_port)
        app_state.ngrok_url = app_state.ngrok_tunnel.public_url
        
        app_state._log_callback(f"Ngrok tunnel started: {app_state.ngrok_url}")
        
        return {
            "status": "success",
            "url": app_state.ngrok_url,
            "message": f"Ngrok tunnel started successfully. Frontend can connect to: {app_state.ngrok_url}"
        }
    except Exception as e:
        app_state._log_callback(f"Failed to start ngrok tunnel: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start ngrok tunnel: {str(e)}")


@app.post("/api/ngrok/stop", response_model=StatusResponse)
async def stop_ngrok_tunnel():
    """Stop ngrok tunnel."""
    if not NGROK_AVAILABLE:
        raise HTTPException(
            status_code=400,
            detail="pyngrok not installed"
        )
    
    if app_state.ngrok_tunnel is None:
        raise HTTPException(status_code=400, detail="Ngrok tunnel is not running")
    
    try:
        ngrok.disconnect(app_state.ngrok_tunnel.public_url)
        app_state._log_callback(f"Ngrok tunnel stopped: {app_state.ngrok_url}")
        
        old_url = app_state.ngrok_url
        app_state.ngrok_tunnel = None
        app_state.ngrok_url = None
        
        return StatusResponse(
            status="success",
            message=f"Ngrok tunnel stopped. Previous URL was: {old_url}"
        )
    except Exception as e:
        app_state._log_callback(f"Failed to stop ngrok tunnel: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop ngrok tunnel: {str(e)}")


@app.get("/api/ngrok/status", response_model=Dict[str, Any])
async def get_ngrok_status():
    """Get ngrok tunnel status and URL."""
    if not NGROK_AVAILABLE:
        return {
            "available": False,
            "running": False,
            "url": None,
            "message": "pyngrok not installed"
        }
    
    if app_state.ngrok_tunnel is None:
        return {
            "available": True,
            "running": False,
            "url": None,
            "message": "Ngrok tunnel is not running"
        }
    
    return {
        "available": True,
        "running": True,
        "url": app_state.ngrok_url,
        "port": app_state.ngrok_port,
        "message": f"Ngrok tunnel is active. Frontend URL: {app_state.ngrok_url}"
    }


@app.post("/api/ngrok/set-url", response_model=StatusResponse)
async def set_ngrok_url(request: Dict[str, str]):
    """Manually set ngrok URL if you're running ngrok separately."""
    url = request.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    # Ensure URL has https:// prefix
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    
    app_state.ngrok_url = url
    app_state._log_callback(f"Ngrok URL set manually: {url}")
    
    return StatusResponse(
        status="success",
        message=f"Ngrok URL set to: {url}"
    )


# ==================== Logs Endpoints ====================

@app.get("/api/logs", response_model=List[LogEntry])
async def get_logs(limit: int = 100):
    """Get recent logs."""
    logs = []
    temp_queue = Queue()
    
    # Drain the queue
    while True:
        try:
            log_entry = app_state.log_queue.get_nowait()
            temp_queue.put(log_entry)
        except Empty:
            break
    
    # Get items from temp queue and limit
    while len(logs) < limit:
        try:
            log_entry = temp_queue.get_nowait()
            logs.append(LogEntry(**log_entry))
        except Empty:
            break
    
    return logs


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for real-time logs."""
    await websocket.accept()
    active_websockets.append(websocket)
    
    try:
        # Keep connection alive and wait for messages from broadcaster
        # The log_broadcaster task will send messages via broadcast_log()
        while True:
            # Just keep the connection alive
            await asyncio.sleep(1)
            # Send a ping to keep connection alive
            try:
                await websocket.send_json({"type": "ping"})
            except:
                break
                
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
    except Exception as e:
        logging.getLogger(__name__).error(f"WebSocket error: {e}")
        if websocket in active_websockets:
            active_websockets.remove(websocket)


# Background task to broadcast logs
async def log_broadcaster():
    """Background task to broadcast logs to WebSocket clients."""
    while True:
        try:
            # Use asyncio-compatible queue checking
            await asyncio.sleep(0.1)
            if not app_state.log_queue.empty():
                log_entry = app_state.log_queue.get_nowait()
                await broadcast_log(log_entry)
        except Exception as e:
            logging.getLogger(__name__).error(f"Log broadcaster error: {e}")
            await asyncio.sleep(0.5)


# ==================== Twilio Webhook Endpoints ====================
# These endpoints are needed for Twilio to handle calls through ngrok

@app.post("/outbound")
async def handle_outbound_call(request: Request):
    """Handle outbound call TwiML - forwarded from Twilio webhook server."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        # Return basic TwiML if Twilio not configured
        response = VoiceResponse()
        response.say("Service temporarily unavailable")
        return Response(content=str(response), media_type='text/xml')
    
    # Get the voice handler from the manager
    voice_handler = twilio_manager.voice_handler
    
    form_data = await request.form()
    call_sid = form_data.get('CallSid')
    
    # Store call information
    if call_sid:
        voice_handler.active_calls[call_sid] = {
            'to_number': 'outbound',
            'status': 'ringing',
            'start_time': time.time(),
            'audio_buffer': []
        }
    
    response = VoiceResponse()
    
    # Generate greeting from system prompt
    try:
        org_id = form_data.get('organization_id') or app_state.get_orchestrator().default_organization_id
        greeting = app_state.get_orchestrator().generate_greeting(
            conversation_id=call_sid,
            organization_id=org_id
        )
    except Exception as e:
        logger.error(f"Error generating greeting: {e}")
        greeting = "Hello! This is VOCA calling. How can I help you today?"
    
    response.say(greeting)
    
    # Gather user input
    if call_sid:
        gather = response.gather(
            input='speech',
            timeout=10,
            speech_timeout='auto',
            action=f'/process_speech/{call_sid}',
            method='POST'
        )
        gather.say("I'm listening...")
        response.redirect(f'/process_speech/{call_sid}')
    
    return Response(content=str(response), media_type='text/xml')


@app.post("/webhook/voice")
async def handle_incoming_call_webhook(request: Request):
    """Handle incoming Twilio call webhook - forwarded from Twilio webhook server."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        response.say("Service temporarily unavailable")
        return Response(content=str(response), media_type='text/xml')
    
    voice_handler = twilio_manager.voice_handler
    
    form_data = await request.form()
    call_sid = form_data.get('CallSid')
    from_number = form_data.get('From')
    
    if call_sid:
        voice_handler.active_calls[call_sid] = {
            'from_number': from_number,
            'status': 'ringing',
            'start_time': time.time(),
            'audio_buffer': []
        }
    
    response = VoiceResponse()
    
    # Generate greeting from system prompt
    try:
        org_id = form_data.get('organization_id') or app_state.get_orchestrator().default_organization_id
        greeting = app_state.get_orchestrator().generate_greeting(
            conversation_id=call_sid,
            organization_id=org_id
        )
    except Exception as e:
        logger.error(f"Error generating greeting: {e}")
        greeting = "Hello! You've reached VOCA, your AI voice assistant. Please speak after the tone."
    
    response.say(greeting)
    
    if call_sid:
        gather = response.gather(
            input='speech',
            timeout=10,
            speech_timeout='auto',
            action=f'/process_speech/{call_sid}',
            method='POST'
        )
        gather.say("I'm listening...")
        response.redirect(f'/process_speech/{call_sid}')
    
    return Response(content=str(response), media_type='text/xml')


@app.post("/process_speech/{call_sid}")
async def handle_speech_webhook(call_sid: str, request: Request):
    """Handle speech input from Twilio - forwarded from Twilio webhook server."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        response.say("Service temporarily unavailable")
        return Response(content=str(response), media_type='text/xml')
    
    voice_handler = twilio_manager.voice_handler
    
    if call_sid not in voice_handler.active_calls:
        raise HTTPException(status_code=404, detail="Call not found")
    
    form_data = await request.form()
    speech_result = form_data.get('SpeechResult', '')
    confidence = form_data.get('Confidence', '0')
    
    app_state._log_callback(f"Speech received for call {call_sid}: {speech_result} (confidence: {confidence})")
    
    if speech_result and float(confidence) > 0.5:
        try:
            # User message and AI response are logged in orchestrator.generate_reply
            ai_response = voice_handler.orchestrator.generate_reply(
                speech_result,
                conversation_id=call_sid,
                call_sid=call_sid,
            )
            app_state._log_callback(f"AI Response: {ai_response}")
            
            if not ai_response or len(ai_response.strip()) == 0:
                ai_response = "I understand. Can you tell me more about that?"
            
            if len(ai_response) > 500:
                ai_response = ai_response[:500] + "..."
            
            response = VoiceResponse()
            response.say(ai_response)
            
            # Check if user declined further assistance and AI responded with closing message
            speech_lower = speech_result.lower()
            ai_response_lower = ai_response.lower()
            
            # Check if user said "no thank you" or similar declining phrases
            decline_phrases = [
                "no thank you", "no thanks", "no, thank you", "no, thanks",
                "that's all", "nothing else", "i'm good", "i'm fine",
                "not really", "no more", "no, that's all", "no that's all"
            ]
            
            user_declined = any(phrase in speech_lower for phrase in decline_phrases)
            
            # Check if AI responded with closing message
            closing_phrases = [
                "thank you for calling. have a great day",
                "thank you for calling, have a great day",
                "have a great day"
            ]
            
            ai_closing = any(phrase in ai_response_lower for phrase in closing_phrases)
            
            # If user declined and AI gave closing message, end the call
            if user_declined and ai_closing:
                response.hangup()
                app_state._log_callback(f"Call {call_sid} ended - user declined further assistance")
                return Response(content=str(response), media_type='text/xml')
            
            if call_sid:
                gather = response.gather(
                    input='speech',
                    timeout=10,
                    speech_timeout='auto',
                    action=f'/process_speech/{call_sid}',
                    method='POST'
                )
                gather.say("I'm listening...")
                response.redirect(f'/process_speech/{call_sid}')
            
            return Response(content=str(response), media_type='text/xml')
            
        except Exception as e:
            app_state._log_callback(f"Error processing speech: {e}")
            response = VoiceResponse()
            response.say("I'm sorry, I had trouble processing that. Please try again.")
            if call_sid:
                response.redirect(f'/process_speech/{call_sid}')
            return Response(content=str(response), media_type='text/xml')
    else:
        response = VoiceResponse()
        response.say("I didn't catch that. Please speak clearly.")
        if call_sid:
            response.redirect(f'/process_speech/{call_sid}')
        return Response(content=str(response), media_type='text/xml')


# ==================== System Prompt Endpoints ====================

@app.get("/api/system-prompt", response_model=SystemPromptResponse)
async def get_system_prompt(
    organization_id: Optional[str] = Query(None),
    x_organization_id: Optional[str] = Header(None),
):
    """Get the current system prompt and name."""
    try:
        resolved_org = _resolve_org_id(query_value=organization_id, header_value=x_organization_id)
        prompt_data = get_prompt_with_name(resolved_org)
        return SystemPromptResponse(
            prompt=prompt_data["prompt"],
            name=prompt_data.get("name"),
            welcome_message=prompt_data.get("welcome_message")
        )
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching system prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch system prompt: {str(e)}")


@app.get("/api/system-prompt/list", response_model=List[SystemPromptListItem])
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
        resolved_org = _resolve_org_id(query_value=organization_id, header_value=x_organization_id)
        
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
                logger = logging.getLogger(__name__)
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
                logger = logging.getLogger(__name__)
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
                logger = logging.getLogger(__name__)
                logger.warning(f"Error fetching all organization prompts: {e}")
        
        return results
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error listing system prompts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list system prompts: {str(e)}")


@app.post("/api/system-prompt", response_model=StatusResponse)
@app.put("/api/system-prompt", response_model=StatusResponse)
@app.patch("/api/system-prompt", response_model=StatusResponse)
async def update_system_prompt(
    request: SystemPromptRequest,
    x_organization_id: Optional[str] = Header(None),
):
    """Update the system prompt and optionally the name.
    
    If organization_id is not provided, the prompt will be saved as the default prompt.
    This allows the system to work without multi-tenant setup initially.
    """
    try:
        resolved_org = _resolve_org_id(
            body_value=request.organization_id,
            header_value=x_organization_id,
        )
        
        # Allow None organization_id - will save as default prompt
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
                        logger = logging.getLogger(__name__)
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
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating system prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update system prompt: {str(e)}")


class WelcomeMessageRequest(BaseModel):
    welcome_message: Optional[str] = Field(None, description="Custom welcome message for calls")
    organization_id: Optional[str] = Field(None, description="Organization ID")


@app.put("/api/system-prompt/welcome-message", response_model=StatusResponse)
@app.patch("/api/system-prompt/welcome-message", response_model=StatusResponse)
@app.post("/api/system-prompt/welcome-message", response_model=StatusResponse)
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
        
        resolved_org = _resolve_org_id(
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
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating welcome message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update welcome message: {str(e)}")


@app.post("/api/system-prompt/reset", response_model=StatusResponse)
async def reset_system_prompt(
    organization_id: Optional[str] = Query(None),
    x_organization_id: Optional[str] = Header(None),
):
    """Reset the system prompt to default."""
    try:
        resolved_org = _resolve_org_id(query_value=organization_id, header_value=x_organization_id)
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
        logger = logging.getLogger(__name__)
        logger.error(f"Error resetting system prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset system prompt: {str(e)}")


# ==================== Organization Management Endpoints ====================

@app.post("/api/organizations", response_model=OrganizationResponse)
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
            app_state._log_callback(f"Organization created: {request.name} (ID: {org_data['id']})")
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
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating organization: {e}")
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=400, detail="Organization with this name or API key already exists")
        raise HTTPException(status_code=500, detail=f"Failed to create organization: {str(e)}")


@app.get("/api/organizations", response_model=List[OrganizationResponse])
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
        logger = logging.getLogger(__name__)
        logger.error(f"Error listing organizations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list organizations: {str(e)}")


@app.get("/api/organizations/{organization_id}", response_model=OrganizationResponse)
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
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting organization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get organization: {str(e)}")
