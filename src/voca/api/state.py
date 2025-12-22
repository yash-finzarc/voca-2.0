import asyncio
import logging
import os
import threading
from datetime import datetime
from queue import Queue, Empty
from typing import Optional, List, Dict, Any

from fastapi import WebSocket

from src.voca.config import Config
from src.voca.orchestrator import VocaOrchestrator
from src.voca.twilio_config import get_twilio_config
from src.voca.twilio_voice import TwilioCallManager


class AppState:
    def __init__(self):
        self.orchestrator: Optional[VocaOrchestrator] = None
        self.twilio_manager: Optional[TwilioCallManager] = None
        self.log_queue: Queue = Queue()
        self.is_twilio_server_running: bool = False
        self.is_continuous_call_running: bool = False
        self.continuous_call_thread: Optional[threading.Thread] = None

    def get_orchestrator(self) -> VocaOrchestrator:
        if self.orchestrator is None:
            self.orchestrator = VocaOrchestrator(on_log=self._log_callback)
        return self.orchestrator

    def get_twilio_manager(self):
        """Get Twilio call manager. STT and TTS are handled by TwiML with Deepgram."""
        if self.twilio_manager is None:
            config = get_twilio_config()
            if not config.validate():
                return None

            logger = logging.getLogger(__name__)

            # Note: Deepgram STT/TTS are handled by TwiML - no API key needed
            # The Deepgram API key check is kept for backward compatibility but not required
            deepgram_key_env = os.getenv("DEEPGRAM_API_KEY", "")
            deepgram_key_config = Config.deepgram_api_key
            deepgram_key = deepgram_key_config or deepgram_key_env

            if deepgram_key and deepgram_key.strip():
                # Update Config if we found it in environment but not in Config
                if not Config.deepgram_api_key and deepgram_key_env:
                    Config.deepgram_api_key = deepgram_key_env
                    logger.debug("Loaded DEEPGRAM_API_KEY from environment (not required for TwiML)")

            try:
                self.twilio_manager = TwilioCallManager(self.get_orchestrator())
            except Exception as e:
                logger.error(f"Failed to create TwilioCallManager: {e}")
                return None

        return self.twilio_manager

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get real-time model information from the orchestrator.
        
        Returns:
            Dictionary with current model information from active services
        """
        try:
            orchestrator = self.get_orchestrator()
            return orchestrator.get_model_info()
        except Exception as e:
            logging.getLogger(__name__).error(f"Error getting model info: {e}")
            return {"error": str(e)}
    
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

