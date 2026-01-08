"""
Application state management for VOCA API.
"""
from queue import Queue
from typing import Optional

from src.voca.Twilio.twilio_config import TwilioConfig, get_twilio_config
from src.voca.api.log_utils import active_websockets, log_broadcaster as _log_broadcaster


class AppState:
    """Application state manager."""
    
    def __init__(self):
        self.log_queue: Queue = Queue()
        self.is_twilio_server_running: bool = False
        self._twilio_config: Optional[TwilioConfig] = None
    
    def get_twilio_manager(self) -> Optional[TwilioConfig]:
        """Get the Twilio configuration manager."""
        if self._twilio_config is None:
            config = get_twilio_config()
            if config and config.validate():
                self._twilio_config = config
            else:
                return None
        return self._twilio_config
    
    def _log_callback(self, message: str):
        """Add a log entry to the queue."""
        from datetime import datetime
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "level": "info"
        }
        self.log_queue.put(log_entry)


# Global application state instance
app_state = AppState()


# Re-export log_broadcaster with app_state bound
async def log_broadcaster():
    """Background task to stream queued logs to WebSocket clients."""
    await _log_broadcaster(app_state)


__all__ = ["app_state", "log_broadcaster", "active_websockets"]

