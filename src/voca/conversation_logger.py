"""
Conversation logger for tracking user and AI interactions in terminal.
Formats messages as:
  user: <message>
  ai: <message>
"""
import sys
from typing import Optional
from datetime import datetime


class ConversationLogger:
    """Logs user and AI interactions in a clean, formatted way to terminal."""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._lock = None
        try:
            import threading
            self._lock = threading.Lock()
        except ImportError:
            pass
    
    def _safe_print(self, message: str):
        """Thread-safe print to stdout."""
        if not self.enabled:
            return
        
        if self._lock:
            with self._lock:
                print(message, flush=True)
        else:
            print(message, flush=True)
    
    def log_user(self, message: str):
        """Log a user message."""
        if not message or not message.strip():
            return
        
        # Clean up the message - remove common prefixes
        cleaned = message.strip()
        prefixes_to_remove = [
            "USER:",
            "Speech received for call",
            "Speech:",
        ]
        
        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                # Extract the actual message after the prefix
                cleaned = cleaned[len(prefix):].strip()
                # Remove call SID and confidence info if present
                if "(confidence:" in cleaned:
                    cleaned = cleaned.split("(confidence:")[0].strip()
                break
        
        # Format as "user: <message>"
        formatted = f"user: {cleaned}"
        self._safe_print(formatted)
    
    def log_ai(self, message: str):
        """Log an AI message."""
        if not message or not message.strip():
            return
        
        # Clean up the message - remove common prefixes
        cleaned = message.strip()
        prefixes_to_remove = [
            "ASSISTANT:",
            "AI Response:",
            "Generated greeting",
            "Using welcome_message",
        ]
        
        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                # Extract the actual message after the prefix
                cleaned = cleaned[len(prefix):].strip()
                # Remove "from database:" or "from system prompt:" suffixes
                if ":" in cleaned:
                    parts = cleaned.split(":", 1)
                    if len(parts) > 1:
                        cleaned = parts[1].strip()
                break
        
        # Format as "ai: <message>"
        formatted = f"ai: {cleaned}"
        self._safe_print(formatted)
    
    def log_message(self, message: str):
        """Automatically detect and log user or AI messages."""
        if not message or not message.strip():
            return
        
        message_lower = message.lower()
        
        # Check if it's a user message
        user_indicators = [
            "user:",
            "speech received",
            "speech:",
        ]
        
        # Check if it's an AI message
        ai_indicators = [
            "assistant:",
            "ai response:",
            "generated greeting",
            "using welcome_message",
        ]
        
        is_user = any(indicator in message_lower for indicator in user_indicators)
        is_ai = any(indicator in message_lower for indicator in ai_indicators)
        
        if is_user and not is_ai:
            self.log_user(message)
        elif is_ai:
            self.log_ai(message)
        # If neither, don't log (to avoid cluttering with system messages)
    
    def log_system(self, message: str):
        """Log a system message (not user or AI)."""
        if not message or not message.strip():
            return
        # System messages can be logged differently if needed
        # For now, we'll skip them to keep the conversation log clean


# Global conversation logger instance
_conversation_logger = ConversationLogger(enabled=True)


def log_user(message: str):
    """Log a user message."""
    _conversation_logger.log_user(message)


def log_ai(message: str):
    """Log an AI message."""
    _conversation_logger.log_ai(message)


def log_message(message: str):
    """Automatically detect and log user or AI messages."""
    _conversation_logger.log_message(message)


def enable_logging():
    """Enable conversation logging."""
    _conversation_logger.enabled = True


def disable_logging():
    """Disable conversation logging."""
    _conversation_logger.enabled = False

