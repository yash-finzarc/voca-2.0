"""
Logs endpoints for retrieving and streaming logs.
"""
import asyncio
from queue import Queue, Empty
from typing import List

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.routing import APIRouter

from src.voca.api.app_state import app_state
from src.voca.api.models import LogEntry

router = APIRouter(prefix="/api/logs", tags=["logs"])

# Active WebSocket connections for log streaming
# Export this for use in main.py
active_websockets: List[WebSocket] = []


async def broadcast_log(log_entry: dict):
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


@router.get("", response_model=List[LogEntry])
async def get_logs(limit: int = 100):
    """Get recent logs."""
    logs = []
    temp_queue = Queue()
    
    # Drain the log queue
    while not app_state.log_queue.empty():
        try:
            log = app_state.log_queue.get_nowait()
            temp_queue.put(log)
            logs.append(LogEntry(**log))
        except Empty:
            break
    
    # Put logs back in original queue
    while not temp_queue.empty():
        app_state.log_queue.put(temp_queue.get())
    
    # Return most recent logs
    return logs[-limit:]


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for real-time log streaming."""
    await websocket.accept()
    active_websockets.append(websocket)
    
    try:
        while True:
            # Keep connection alive and wait for client messages
            data = await websocket.receive_text()
            # Echo back or handle client messages if needed
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        active_websockets.remove(websocket)
    except Exception as e:
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
        except Empty:
            pass
        except Exception as e:
            await asyncio.sleep(0.5)

