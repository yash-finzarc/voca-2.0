import asyncio
import logging
import os
import threading
from datetime import datetime
from queue import Queue, Empty
from typing import Optional, List, Dict, Any

from fastapi import WebSocket

from src.voca.config import Config
from src.voca.Twilio.twilio_config import get_twilio_config


class AppState:
    def __init__(self):
        # Using custom LLM pipeline with orchestrator
        self.log_queue: Queue = Queue()
        self.is_twilio_server_running: bool = False
        self.is_continuous_call_running: bool = False
        self.continuous_call_thread: Optional[threading.Thread] = None

    def get_twilio_manager(self):
        """
        Get Twilio configuration.
        Note: Twilio calls now use custom LLM pipeline via WebSocket endpoints.
        This method is kept for compatibility but returns None since TwilioCallManager is not needed.
        """
        # Verify Twilio is configured
        config = get_twilio_config()
        if not config.validate():
            return None
        
        # Custom LLM pipeline handles everything via WebSocket - just return config
        return config

    def _log_callback(self, message: str):
        """Callback for log messages."""
        log_entry = {"timestamp": datetime.now().isoformat(), "message": message}
        self.log_queue.put(log_entry)


app_state = AppState()

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


async def log_broadcaster():
    """Background task to broadcast logs to WebSocket clients."""
    while True:
        try:
            await asyncio.sleep(0.1)
            if not app_state.log_queue.empty():
                log_entry = app_state.log_queue.get_nowait()
                await broadcast_log(log_entry)
        except Exception as e:
            logging.getLogger(__name__).error(f"Log broadcaster error: {e}")
            await asyncio.sleep(0.5)

