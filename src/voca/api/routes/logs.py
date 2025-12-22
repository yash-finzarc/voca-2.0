import asyncio
from queue import Queue, Empty
from typing import List

from fastapi import APIRouter, WebSocket

from src.voca.api.models import LogEntry
from src.voca.api.state import app_state, active_websockets

router = APIRouter()


@router.get("/api/logs", response_model=List[LogEntry])
async def get_logs(limit: int = 100):
    """Get recent logs."""
    logs: List[LogEntry] = []
    temp_queue: Queue = Queue()

    while True:
        try:
            log_entry = app_state.log_queue.get_nowait()
            temp_queue.put(log_entry)
        except Empty:
            break

    while len(logs) < limit:
        try:
            log_entry = temp_queue.get_nowait()
            logs.append(LogEntry(**log_entry))
        except Empty:
            break

    return logs


@router.get("/ws/test")
async def websocket_test_get():
    """HTTP GET endpoint to test if the /ws/test route is accessible."""
    return {
        "status": "ok",
        "message": "WebSocket endpoint is registered. Use wscat or a WebSocket client to connect.",
        "websocket_url": "wss://voca2.duckdns.org/ws/test",
        "note": "If you see 405, Nginx may not be configured for WebSocket upgrades"
    }


@router.websocket("/ws/test")
async def websocket_test(websocket: WebSocket):
    """Simple test WebSocket endpoint for debugging."""
    import logging
    logger = logging.getLogger(__name__)
    
    client_info = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
    logger.info(f"[WS_TEST] WebSocket connection attempt from {client_info}")
    logger.info(f"[WS_TEST] WebSocket URL: {websocket.url}")
    logger.info(f"[WS_TEST] WebSocket headers: {dict(websocket.headers)}")
    
    try:
        await websocket.accept()
        logger.info("[WS_TEST] WebSocket connected successfully")
        
        # Send a welcome message
        await websocket.send_json({"type": "welcome", "message": "WebSocket connection successful!"})
        
        try:
            while True:
                # Wait for messages from client
                try:
                    data = await websocket.receive_json()
                    logger.info(f"[WS_TEST] Received: {data}")
                    
                    # Echo back the message
                    await websocket.send_json({"type": "echo", "received": data})
                except ValueError as e:
                    logger.warning(f"[WS_TEST] Invalid JSON received: {e}")
                    await websocket.send_json({"type": "error", "message": "Invalid JSON"})
        except Exception as e:
            logger.info(f"[WS_TEST] WebSocket closed: {e}")
    except Exception as e:
        logger.error(f"[WS_TEST] Error in WebSocket: {e}", exc_info=True)
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for real-time logs."""
    await websocket.accept()
    active_websockets.append(websocket)

    try:
        while True:
            await asyncio.sleep(1)
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break
    except Exception:
        if websocket in active_websockets:
            active_websockets.remove(websocket)

