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

