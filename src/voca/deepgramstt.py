"""
Deepgram Speech-to-Text (STT) implementation using Deepgram's streaming API.
Adapted to work with PCM16 audio chunks as expected by the VOCA orchestrator.
"""
import threading
import queue
import logging
from typing import Optional
import numpy as np

from deepgram import DeepgramClient
from deepgram.core.events import EventType

from src.voca.config import Config


class DeepgramSTT:
    """
    Deepgram STT implementation that uses streaming API for real-time transcription.
    Handles PCM16 audio chunks and returns transcriptions.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "nova-3", language: str = "en-IN", auto_load: bool = False):
        """
        Initialize Deepgram STT.
        
        Args:
            api_key: Deepgram API key (defaults to Config.deepgram_api_key)
            model: Deepgram model to use (default: "nova-3")
            language: Language code (default: "en-IN")
            auto_load: If True, establish connection immediately. If False, call load() separately.
        """
        self.api_key = api_key or Config.deepgram_api_key
        if not self.api_key:
            raise ValueError("Deepgram API key not provided. Set DEEPGRAM_API_KEY environment variable.")
        
        self.model = model
        self.language = language
        self.client = DeepgramClient(api_key=self.api_key)
        self.connection = None
        self._connection_obj = None  # Store original connection object for cleanup
        self.ready = threading.Event()
        self.transcript_queue = queue.Queue()
        self.current_transcript = ""
        self.is_connected = False
        self.log = logging.getLogger("voca.deepgram_stt")
        
        # Thread for managing connection
        self._connection_thread = None
        self._lock = threading.Lock()
        self._actual_model_info = None  # Store actual model info from API responses
        
        # Auto-load client if requested (doesn't establish connection, just verifies client)
        if auto_load:
            self.load()  # This just verifies client, doesn't establish connection
        
    def _setup_connection(self):
        """Set up Deepgram streaming connection."""
        if self.connection is not None and self.is_connected:
            return  # Connection already established
        
        try:
            # Create connection - enter context manager if needed
            connection_obj = self.client.listen.v1.connect(
                model=self.model,
                language=self.language,
            )
            # Store the original object for cleanup
            self._connection_obj = connection_obj
            # If it's a context manager, enter it but don't exit until close()
            if hasattr(connection_obj, '__enter__'):
                self.connection = connection_obj.__enter__()
            else:
                self.connection = connection_obj
            
            def on_message(result):
                """Handle transcription messages from Deepgram."""
                event_type = getattr(result, "type", None)
                channel = getattr(result, "channel", None)
                
                # Capture model info from result metadata if available
                with self._lock:
                    try:
                        if hasattr(result, "metadata"):
                            metadata = result.metadata
                            if metadata and hasattr(metadata, "model_info"):
                                # Store actual model info from API
                                self._actual_model_info = {
                                    "model": getattr(metadata.model_info, "name", self.model) if hasattr(metadata, "model_info") else self.model,
                                    "language": getattr(metadata, "language", self.language),
                                }
                    except Exception:
                        pass
                
                if channel and hasattr(channel, "alternatives"):
                    transcript = channel.alternatives[0].transcript
                    is_final = getattr(result, "is_final", True)
                    if transcript:
                        with self._lock:
                            if is_final:
                                self.current_transcript = transcript
                                self.transcript_queue.put(transcript)
                                self.log.debug(f"Final transcript: {transcript}")
                            else:
                                # Update current transcript with interim result
                                self.current_transcript = transcript
                                self.log.debug(f"Interim transcript: {transcript}")
            
            def on_open(_):
                """Handle connection open event."""
                self.ready.set()
                self.is_connected = True
                self.log.info("Deepgram connection opened")
            
            def on_error(error):
                """Handle connection errors."""
                self.log.error(f"Deepgram connection error: {error}")
                self.is_connected = False
            
            def on_close(_):
                """Handle connection close event."""
                self.log.info("Deepgram connection closed")
                self.is_connected = False
            
            self.connection.on(EventType.OPEN, on_open)
            self.connection.on(EventType.MESSAGE, on_message)
            self.connection.on(EventType.ERROR, on_error)
            self.connection.on(EventType.CLOSE, on_close)
            
            # Start listening in a separate thread
            def start_listening():
                try:
                    self.connection.start_listening()
                except Exception as e:
                    self.log.error(f"Error in Deepgram listening thread: {e}")
                    self.is_connected = False
            
            self._connection_thread = threading.Thread(target=start_listening, daemon=True)
            self._connection_thread.start()
            
            # Wait for connection to be ready (with timeout)
            if not self.ready.wait(timeout=5.0):
                raise TimeoutError("Deepgram connection not ready within timeout")
                
        except Exception as e:
            self.log.error(f"Failed to set up Deepgram connection: {e}")
            self.is_connected = False
            if self.connection:
                try:
                    self.connection.finish()
                except:
                    pass
                self.connection = None
            raise
    
    def load(self):
        """
        Load/initialize the STT client (lightweight).
        Note: Connection is established lazily when first audio arrives to avoid Deepgram timeout.
        The client is ready, but connection will be created on first use.
        """
        # Just verify client is initialized - don't establish connection yet
        # Connection will be created lazily in transcribe_pcm16() to avoid timeout
        if not self.client:
            raise RuntimeError("Deepgram client not initialized")
        self.log.info(f"Deepgram STT client initialized (model: {self.model}, connection will be established on first use)")
    
    def is_ready(self) -> bool:
        """
        Check if STT is ready to transcribe.
        Returns True if client is initialized (connection will be created on first use).
        """
        # Client must be initialized - connection is created lazily
        return self.api_key is not None and self.client is not None
    
    def get_model_info(self) -> dict:
        """
        Get real-time model information from the active connection.
        Uses actual model info from API responses when available.
        
        Returns:
            Dictionary with model information including model name, language, and connection status
        """
        # Use actual model info from API if available, otherwise use configured values
        with self._lock:
            actual_info = self._actual_model_info or {}
        
        info = {
            "model": actual_info.get("model", self.model),
            "language": actual_info.get("language", self.language),
            "is_connected": self.is_connected,
            "is_ready": self.is_ready(),
            "configured_model": self.model,  # Keep configured value for reference
            "configured_language": self.language,
        }
        
        # Try to get additional info from connection if available
        if self.connection:
            try:
                # Check if connection has metadata
                if hasattr(self.connection, 'metadata'):
                    metadata = self.connection.metadata
                    if metadata:
                        info["connection_metadata"] = str(metadata)
            except Exception:
                pass
        
        return info
    
    def transcribe_pcm16(self, pcm16: np.ndarray) -> Optional[str]:
        """
        Transcribe PCM16 audio chunk.
        Connection is created lazily on first use to avoid Deepgram timeout.
        
        Args:
            pcm16: NumPy array of PCM16 audio data (int16)
            
        Returns:
            Transcribed text if available, None otherwise
        """
        # Lazy connection setup - create connection when first audio arrives
        # This avoids Deepgram timeout (connections timeout if no audio is sent)
        if not self.is_connected or self.connection is None:
            try:
                self._setup_connection()
                self.log.debug("Deepgram STT connection established on first audio")
            except Exception as e:
                self.log.error(f"Failed to establish Deepgram connection: {e}")
                return None
        
        try:
            # Convert numpy array to bytes
            audio_bytes = pcm16.tobytes()
            
            # Send audio chunk to Deepgram
            self.connection.send_media(audio_bytes)
            
            # Try to get latest transcript from queue (non-blocking)
            transcript = None
            try:
                while True:
                    transcript = self.transcript_queue.get_nowait()
            except queue.Empty:
                # Use current transcript if available
                with self._lock:
                    transcript = self.current_transcript if self.current_transcript else None
            
            return transcript
            
        except Exception as e:
            self.log.error(f"Error transcribing audio: {e}")
            return None
    
    def close(self):
        """Close the Deepgram connection."""
        if self.connection:
            try:
                # Try to finish the connection properly
                if hasattr(self.connection, 'finish'):
                    self.connection.finish()
            except Exception as e:
                self.log.error(f"Error finishing Deepgram connection: {e}")
            finally:
                # If we stored the original connection object, exit the context manager
                if hasattr(self, '_connection_obj') and hasattr(self._connection_obj, '__exit__'):
                    try:
                        self._connection_obj.__exit__(None, None, None)
                    except Exception as e:
                        self.log.error(f"Error exiting Deepgram context manager: {e}")
                
                self.connection = None
                self._connection_obj = None
                self.is_connected = False
                self.ready.clear()
                self.current_transcript = ""
                # Clear the queue
                while not self.transcript_queue.empty():
                    try:
                        self.transcript_queue.get_nowait()
                    except queue.Empty:
                        break


def build_stt(load_connection: bool = False):
    """
    Build and return a Deepgram STT instance.
    By default, only initializes client (connection created lazily on first audio).
    This avoids Deepgram timeout - connections timeout if no audio is sent.
    This function is expected by the orchestrator.
    
    Args:
        load_connection: If True, call load() (still won't establish connection, just verify client).
    
    Returns:
        DeepgramSTT instance
    """
    try:
        stt = DeepgramSTT(auto_load=load_connection)
        return stt
    except Exception as e:
        logging.getLogger("voca.deepgram_stt").error(f"Failed to build Deepgram STT: {e}")
        raise

