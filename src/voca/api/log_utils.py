import asyncio
from typing import Dict, List

from fastapi import WebSocket


# Track active WebSocket connections for log streaming
active_websockets: List[WebSocket] = []


async def broadcast_log(log_entry: Dict[str, str]):
    """Broadcast a single log entry to all connected WebSocket clients."""
    if not active_websockets:
        return

    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(log_entry)
        except Exception:
            disconnected.append(ws)

    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)


async def log_broadcaster(app_state):
    """Background task to stream queued logs to WebSocket clients."""
    import logging

    logger = logging.getLogger(__name__)
    while True:
        try:
            await asyncio.sleep(0.1)
            if not app_state.log_queue.empty():
                log_entry = app_state.log_queue.get_nowait()
                await broadcast_log(log_entry)
        except Exception as exc:
            logger.error(f"Log broadcaster error: {exc}")
            await asyncio.sleep(0.5)


__all__ = ["active_websockets", "broadcast_log", "log_broadcaster"]

