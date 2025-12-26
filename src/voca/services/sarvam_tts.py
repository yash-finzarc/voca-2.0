"""
SarvamAI Text-to-Speech (TTS) service with WebSocket streaming support.
Handles real-time text-to-speech conversion with streaming audio output.
"""
import asyncio
import json
import logging
import websockets
from websockets.legacy.client import connect
from typing import Callable, Optional
import base64

logger = logging.getLogger(__name__)


class SarvamTTSClient:
    """
    SarvamAI TTS client for streaming text-to-speech conversion.
    
    Handles WebSocket connection to SarvamAI TTS service, sends text in chunks,
    and streams PCM audio frames back immediately.
    """
    
    def __init__(self, api_key: str, language: str = "en-IN", voice: str = "anushka", sample_rate: int = 8000):
        """
        Initialize SarvamAI TTS client.
        
        Args:
            api_key: SarvamAI API subscription key
            language: Language code (default: en-IN)
            voice: Voice name (default: anushka)
            sample_rate: Audio sample rate in Hz (default: 8000 for Twilio)
        """
        self.api_key = api_key
        self.language = language
        self.voice = voice
        self.sample_rate = sample_rate
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.audio_callback: Optional[Callable[[bytes], None]] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._is_cancelled = False
        
    async def connect(self):
        """Establish WebSocket connection to SarvamAI TTS service."""
        try:
            # SarvamAI TTS WebSocket endpoint
            # NOTE: Adjust endpoint URL based on actual SarvamAI API documentation
            uri = "wss://api.sarvam.ai/text-to-speech/ws"
            headers = {
                "Api-Subscription-Key": self.api_key
            }
            
            logger.info(f"Connecting to SarvamAI TTS: {uri}")
            logger.debug(f"Language: {self.language}, Voice: {self.voice}, Sample rate: {self.sample_rate}")
            
            # Use legacy client for websockets 15.0.1 compatibility
            self.websocket = await connect(uri, extra_headers=headers)
            self.is_connected = True
            self._is_cancelled = False
            
            # Send initial configuration
            config = {
                "language": self.language,
                "voice": self.voice,
                "sample_rate": self.sample_rate,
                "encoding": "pcm",
                "format": "raw"
            }
            await self.websocket.send(json.dumps(config))
            logger.info("Connected to SarvamAI TTS and sent configuration")
            
            # Start receiving audio
            self._receive_task = asyncio.create_task(self._receive_audio())
            
        except Exception as e:
            logger.error(f"Error connecting to SarvamAI TTS: {e}")
            self.is_connected = False
            raise
    
    async def _receive_audio(self):
        """Receive and process audio messages from SarvamAI TTS."""
        try:
            async for message in self.websocket:
                if self._is_cancelled:
                    logger.info("TTS cancelled, stopping audio reception")
                    break
                    
                try:
                    if isinstance(message, bytes):
                        # Raw PCM audio bytes
                        if self.audio_callback and not self._is_cancelled:
                            await self.audio_callback(message)
                    elif isinstance(message, str):
                        data = json.loads(message)
                        
                        if data.get("type") == "audio":
                            # Base64-encoded audio
                            audio_b64 = data.get("data", "")
                            if audio_b64:
                                audio_bytes = base64.b64decode(audio_b64)
                                if self.audio_callback and not self._is_cancelled:
                                    await self.audio_callback(audio_bytes)
                                    
                        elif data.get("type") == "error":
                            error_msg = data.get("error", "Unknown error")
                            logger.error(f"SarvamAI TTS error: {error_msg}")
                            
                        elif data.get("type") == "done":
                            logger.debug("TTS generation completed")
                            
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse TTS message: {e}, message: {message[:100] if isinstance(message, str) else 'binary'}")
                except Exception as e:
                    logger.error(f"Error processing TTS message: {e}", exc_info=True)
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("SarvamAI TTS WebSocket connection closed")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Error in TTS receive loop: {e}", exc_info=True)
            self.is_connected = False
    
    async def send_text(self, text: str, is_final: bool = True):
        """
        Send text to SarvamAI TTS for conversion.
        
        Args:
            text: Text to convert to speech
            is_final: Whether this is the final chunk (default: True)
        """
        if not self.is_connected or not self.websocket:
            logger.warning("TTS not connected, cannot send text")
            return
        
        if self._is_cancelled:
            logger.debug("TTS cancelled, ignoring text")
            return
        
        try:
            message = {
                "type": "text",
                "text": text,
                "is_final": is_final
            }
            await self.websocket.send(json.dumps(message))
            logger.debug(f"Sent text to TTS (length: {len(text)}, final: {is_final})")
        except Exception as e:
            logger.error(f"Error sending text to TTS: {e}", exc_info=True)
    
    async def send_text_chunks(self, text: str, chunk_size: int = 50):
        """
        Send text in sentence-level chunks for streaming TTS.
        
        Args:
            text: Full text to convert
            chunk_size: Approximate characters per chunk (default: 50)
        """
        # Split by sentences (period, exclamation, question mark)
        import re
        sentences = re.split(r'([.!?]\s+)', text)
        
        # Recombine sentences into chunks
        chunks = []
        current_chunk = ""
        for part in sentences:
            if len(current_chunk) + len(part) <= chunk_size:
                current_chunk += part
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = part
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        # Send chunks sequentially
        for i, chunk in enumerate(chunks):
            if self._is_cancelled:
                break
            is_final = (i == len(chunks) - 1)
            await self.send_text(chunk, is_final=is_final)
            # Small delay between chunks for better streaming
            if not is_final:
                await asyncio.sleep(0.05)
    
    def set_audio_callback(self, callback: Callable[[bytes], None]):
        """
        Set callback function for receiving audio.
        
        Args:
            callback: Async function that receives PCM audio bytes
        """
        self.audio_callback = callback
    
    async def cancel(self):
        """Cancel current TTS generation (for barge-in)."""
        self._is_cancelled = True
        logger.info("TTS cancelled (barge-in detected)")
    
    async def stop(self):
        """Close WebSocket connection and cleanup."""
        try:
            self._is_cancelled = True
            
            if self._receive_task:
                self._receive_task.cancel()
                try:
                    await self._receive_task
                except asyncio.CancelledError:
                    pass
            
            if self.websocket:
                await self.websocket.close()
                self.is_connected = False
                logger.info("SarvamAI TTS connection closed")
        except Exception as e:
            logger.error(f"Error stopping TTS client: {e}")

