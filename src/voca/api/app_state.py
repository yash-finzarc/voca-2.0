"""
Application state management for VOCA API.
"""
import logging
import threading
from datetime import datetime
from queue import Queue
from typing import Optional, Dict, Any

from src.voca.orchestrator import VocaOrchestrator
from src.voca.twilio_voice import TwilioCallManager
from src.voca.twilio_config import get_twilio_config

logger = logging.getLogger(__name__)


class AppState:
    """Global application state manager."""
    
    def __init__(self):
        self.orchestrator: Optional[VocaOrchestrator] = None
        self.twilio_manager: Optional[TwilioCallManager] = None
        self.log_queue: Queue = Queue()
        self.is_twilio_server_running: bool = False
        self.is_continuous_call_running: bool = False
        self.continuous_call_thread: Optional[threading.Thread] = None
        # Store demo contexts for medical demo calls (demo_id -> context_dict)
        self.demo_contexts: Dict[str, Dict[str, Any]] = {}
        # In-memory audio cache for pre-generated audio (audio_id -> bytes)
        self.audio_cache: Dict[str, bytes] = {}
        
    def get_orchestrator(self) -> VocaOrchestrator:
        """Get or create orchestrator instance."""
        if self.orchestrator is None:
            self.orchestrator = VocaOrchestrator(on_log=self._log_callback)
        return self.orchestrator
    
    def get_twilio_manager(self) -> Optional[TwilioCallManager]:
        """Get or create Twilio manager instance."""
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


# Global app state instance
app_state = AppState()

