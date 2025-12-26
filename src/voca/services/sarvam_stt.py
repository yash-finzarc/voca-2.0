"""
SarvamAI Speech-to-Text (STT) service with WebSocket streaming support.
Handles real-time audio transcription with partial and final transcript support.
"""
import asyncio
import json
import logging
import websockets
from websockets.legacy.client import connect
from typing import Callable, Optional
import base64

logger = logging.getLogger(__name__)


class SarvamSTTClient:
    """
    SarvamAI STT client for streaming speech-to-text transcription.
    
    Handles WebSocket connection to SarvamAI STT service, sends PCM audio frames,
    and receives partial and final transcripts.
    """
    
    def __init__(self, api_key: str, language: str = "en-IN", sample_rate: int = 8000):
        """
        Initialize SarvamAI STT client.
        
        Args:
            api_key: SarvamAI API subscription key
            language: Language code (default: en-IN)
            sample_rate: Audio sample rate in Hz (default: 8000 for Twilio)
        """
        self.api_key = api_key
        self.language = language
        self.sample_rate = sample_rate
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.transcript_callback: Optional[Callable[[str, bool], None]] = None
        self._receive_task: Optional[asyncio.Task] = None
        
    async def connect(self):
        """Establish WebSocket connection to SarvamAI STT service."""
        try:
            # SarvamAI STT WebSocket endpoint
            # Based on SarvamAI documentation: wss://api.sarvam.ai/speech-to-text/ws
            uri = "wss://api.sarvam.ai/speech-to-text/ws"
            # Use lowercase header name as per SarvamAI documentation
            headers = {
                "api-subscription-key": self.api_key
            }
            
            logger.info(f"Connecting to SarvamAI STT: {uri}")
            logger.debug(f"Language: {self.language}, Sample rate: {self.sample_rate}")
            logger.debug(f"API key present: {bool(self.api_key)}, length: {len(self.api_key) if self.api_key else 0}")
            
            # Use legacy client for websockets 15.0.1 compatibility
            try:
                self.websocket = await connect(uri, extra_headers=headers)
                self.is_connected = True
            except websockets.exceptions.InvalidStatusCode as e:
                logger.error(f"STT connection failed with HTTP {e.status_code}")
                if hasattr(e, 'headers'):
                    logger.error(f"Response headers: {e.headers}")
                raise
            
            # Note: SarvamAI may not require initial config message
            # If config is needed, it might be sent as query params or first message
            # Try sending config as first message (adjust format based on actual API)
            try:
                config = {
                    "language": self.language,
                    "sample_rate": self.sample_rate,
                    "encoding": "pcm",
                    "format": "raw"
                }
                await self.websocket.send(json.dumps(config))
                logger.info("Connected to SarvamAI STT and sent configuration")
            except Exception as e:
                logger.warning(f"Could not send initial config (may not be required): {e}")
                logger.info("Connected to SarvamAI STT (no config sent)")
            
            # Start receiving transcripts
            self._receive_task = asyncio.create_task(self._receive_transcripts())
            
        except Exception as e:
            logger.error(f"Error connecting to SarvamAI STT: {e}")
            self.is_connected = False
            raise
    
    async def _receive_transcripts(self):
        """Receive and process transcript messages from SarvamAI STT."""
        try:
            async for message in self.websocket:
                try:
                    if isinstance(message, str):
                        data = json.loads(message)
                        
                        # Log full message for debugging
                        logger.debug(f"STT received message: {data}")
                        
                        # Handle different response types
                        if data.get("type") == "transcript":
                            transcript = data.get("transcript", "")
                            is_final = data.get("is_final", False)
                            
                            if transcript and self.transcript_callback:
                                await self.transcript_callback(transcript, is_final)
                                
                        elif data.get("type") == "error":
                            error_msg = data.get("error", data.get("message", "Unknown error"))
                            logger.error(f"SarvamAI STT error: {error_msg}, full response: {data}")
                            self.is_connected = False
                            break
                            
                        elif data.get("type") == "partial":
                            # Partial transcript
                            transcript = data.get("transcript", "")
                            if transcript and self.transcript_callback:
                                await self.transcript_callback(transcript, False)
                                
                        elif data.get("type") == "final":
                            # Final transcript
                            transcript = data.get("transcript", "")
                            if transcript and self.transcript_callback:
                                await self.transcript_callback(transcript, True)
                        else:
                            # Log unknown message types for debugging
                            logger.debug(f"STT unknown message type: {data.get('type')}, full: {data}")
                                
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse STT message: {e}, message: {message[:200]}")
                except Exception as e:
                    logger.error(f"Error processing STT message: {e}", exc_info=True)
                    
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"SarvamAI STT WebSocket connection closed: {e.code} - {e.reason}")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Error in STT receive loop: {e}", exc_info=True)
            self.is_connected = False
    
    async def send_audio(self, pcm_audio: bytes):
        """
        Send PCM audio frame to SarvamAI STT.
        
        Args:
            pcm_audio: Raw PCM audio bytes (16-bit, little-endian)
        
        Note: SarvamAI may accept raw binary or JSON format. Trying both approaches.
        """
        if not self.is_connected or not self.websocket:
            logger.warning("STT not connected, cannot send audio")
            return
        
        try:
            # Check if connection is still open
            if self.websocket.closed:
                logger.warning("STT WebSocket is closed, cannot send audio")
                self.is_connected = False
                return
            
            # Try sending as JSON with base64-encoded audio (common format)
            audio_b64 = base64.b64encode(pcm_audio).decode("ascii")
            message = {
                "type": "audio",
                "data": audio_b64,
                "sample_rate": self.sample_rate,
                "encoding": "pcm"
            }
            await self.websocket.send(json.dumps(message))
            
            # Alternative: If above doesn't work, try raw binary:
            # await self.websocket.send(pcm_audio)
            
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"STT connection closed while sending: {e.code} - {e.reason}")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Error sending audio to STT: {e}", exc_info=True)
            self.is_connected = False
    
    def set_transcript_callback(self, callback: Callable[[str, bool], None]):
        """
        Set callback function for receiving transcripts.
        
        Args:
            callback: Async function that receives (transcript: str, is_final: bool)
        """
        self.transcript_callback = callback
    
    async def stop(self):
        """Close WebSocket connection and cleanup."""
        try:
            if self._receive_task:
                self._receive_task.cancel()
                try:
                    await self._receive_task
                except asyncio.CancelledError:
                    pass
            
            if self.websocket:
                await self.websocket.close()
                self.is_connected = False
                logger.info("SarvamAI STT connection closed")
        except Exception as e:
            logger.error(f"Error stopping STT client: {e}")

