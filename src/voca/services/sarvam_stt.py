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
            # NOTE: Adjust endpoint URL based on actual SarvamAI API documentation
            uri = "wss://api.sarvam.ai/speech-to-text-translate/ws"
            headers = {
                "Api-Subscription-Key": self.api_key
            }
            
            logger.info(f"Connecting to SarvamAI STT: {uri}")
            logger.debug(f"Language: {self.language}, Sample rate: {self.sample_rate}")
            
            # Use legacy client for websockets 15.0.1 compatibility
            self.websocket = await connect(uri, extra_headers=headers)
            self.is_connected = True
            
            # Send initial configuration
            config = {
                "language": self.language,
                "sample_rate": self.sample_rate,
                "encoding": "pcm",
                "format": "raw"
            }
            await self.websocket.send(json.dumps(config))
            logger.info("Connected to SarvamAI STT and sent configuration")
            
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
                        
                        # Handle different response types
                        if data.get("type") == "transcript":
                            transcript = data.get("transcript", "")
                            is_final = data.get("is_final", False)
                            
                            if transcript and self.transcript_callback:
                                await self.transcript_callback(transcript, is_final)
                                
                        elif data.get("type") == "error":
                            error_msg = data.get("error", "Unknown error")
                            logger.error(f"SarvamAI STT error: {error_msg}")
                            
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
                                
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse STT message: {e}, message: {message[:100]}")
                except Exception as e:
                    logger.error(f"Error processing STT message: {e}", exc_info=True)
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("SarvamAI STT WebSocket connection closed")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Error in STT receive loop: {e}", exc_info=True)
            self.is_connected = False
    
    async def send_audio(self, pcm_audio: bytes):
        """
        Send PCM audio frame to SarvamAI STT.
        
        Args:
            pcm_audio: Raw PCM audio bytes (16-bit, little-endian)
        
        Note: This implementation sends raw binary audio, which is common for streaming STT.
        If SarvamAI requires JSON/base64 format, adjust the message format accordingly.
        """
        if not self.is_connected or not self.websocket:
            logger.warning("STT not connected, cannot send audio")
            return
        
        try:
            # Send raw binary PCM audio (most common for streaming STT)
            # If SarvamAI requires JSON format, uncomment the alternative below:
            # audio_b64 = base64.b64encode(pcm_audio).decode("ascii")
            # message = {
            #     "type": "audio",
            #     "data": audio_b64,
            #     "sample_rate": self.sample_rate,
            #     "encoding": "pcm"
            # }
            # await self.websocket.send(json.dumps(message))
            
            await self.websocket.send(pcm_audio)
        except Exception as e:
            logger.error(f"Error sending audio to STT: {e}", exc_info=True)
    
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

