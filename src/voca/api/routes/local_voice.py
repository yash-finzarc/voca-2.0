import threading

from fastapi import APIRouter, HTTPException

from src.voca.api.models import StatusResponse
from src.voca.api.state import app_state

router = APIRouter(prefix="/api/local-voice")


@router.post("/start-continuous", response_model=StatusResponse)
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


@router.post("/stop-continuous", response_model=StatusResponse)
async def stop_continuous_call():
    """Stop continuous voice interaction."""
    if not app_state.is_continuous_call_running:
        raise HTTPException(status_code=400, detail="Continuous call is not running")

    orchestrator = app_state.get_orchestrator()
    setattr(orchestrator, "_vad_stop", True)
    app_state.is_continuous_call_running = False

    app_state._log_callback("Continuous call stopped")
    return StatusResponse(status="success", message="Continuous call stopped")


@router.post("/one-minute-test", response_model=StatusResponse)
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


@router.get("/status", response_model=StatusResponse)
async def get_local_voice_status():
    """Get local voice status."""
    orchestrator = app_state.get_orchestrator()
    models_ready = orchestrator.models_ready()

    status = "running" if app_state.is_continuous_call_running else "ready"
    message = f"Models ready: {models_ready}, Continuous call: {app_state.is_continuous_call_running}"

    return StatusResponse(status=status, message=message)


