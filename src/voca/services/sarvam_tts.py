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
            # NOTE: SarvamAI TTS supports WebSocket (unlike STT which requires HTTP)
            uri = "wss://api.sarvam.ai/text-to-speech/ws"
            # CRITICAL: Verify API key is not empty
            if not self.api_key or not self.api_key.strip():
                raise ValueError("SarvamAI API key is empty or not set")
            
            # SarvamAI TTS WebSocket authentication
            # According to SarvamAI official docs: WebSocket TTS requires "api-subscription-key" header (lowercase)
            # Reference: https://docs.sarvam.ai/api-reference-docs/authentication
            api_key_clean = self.api_key.strip()
            
            headers = {
                "api-subscription-key": api_key_clean
            }
            
            logger.info(f"Connecting to SarvamAI TTS: {uri}")
            logger.info(f"API key present: {bool(self.api_key)}, length: {len(self.api_key) if self.api_key else 0}")
            logger.info(f"API key starts with: {self.api_key[:10] if self.api_key and len(self.api_key) >= 10 else 'N/A'}")
            logger.info(f"Headers being sent: {dict(headers)}")  # Log actual headers (without value for security)
            logger.info(f"Header keys: {list(headers.keys())}")
            logger.debug(f"Language: {self.language}, Voice: {self.voice}, Sample rate: {self.sample_rate}")
            
            # Use legacy client for websockets 15.0.1 compatibility
            try:
                logger.info(f"Attempting WebSocket connection with headers: {list(headers.keys())}")
                self.websocket = await connect(uri, extra_headers=headers)
                self.is_connected = True
                self._is_cancelled = False
            except websockets.exceptions.InvalidStatusCode as e:
                logger.error(f"TTS connection failed with HTTP {e.status_code}")
                logger.error(f"API key length: {len(self.api_key) if self.api_key else 0}")
                logger.error(f"API key format check: starts with 'sk_' = {self.api_key.startswith('sk_') if self.api_key else False}")
                if hasattr(e, 'headers'):
                    logger.error(f"Response headers: {e.headers}")
                # Try to read response body if available
                if hasattr(e, 'response') and hasattr(e.response, 'read'):
                    try:
                        error_body = e.response.read().decode('utf-8')
                        logger.error(f"Error response body: {error_body}")
                    except:
                        pass
                raise
            
            # CRITICAL: SarvamAI TTS requires a config message FIRST before any text messages
            # This initializes the TTS session on Sarvam's side
            logger.info("Connected to SarvamAI TTS, sending config...")
            await self._send_config()
            
            # Start receiving audio
            self._receive_task = asyncio.create_task(self._receive_audio())
            
        except Exception as e:
            logger.error(f"Error connecting to SarvamAI TTS: {e}")
            self.is_connected = False
            raise
    
    async def _send_config(self):
        """
        Send configuration message to SarvamAI TTS.
        This MUST be sent immediately after WebSocket connection, before any text messages.
        """
        if not self.websocket or not self.is_connected:
            logger.warning("Cannot send TTS config: WebSocket not connected")
            return
        
        try:
            config_payload = {
                "type": "config",
                "data": {
                    "audio_format": "pcm",
                    "sample_rate": self.sample_rate,
                    "language": self.language,
                    "voice": "default"
                }
            }
            
            config_json = json.dumps(config_payload)
            await self.websocket.send(config_json)
            logger.info(f"✓ TTS config sent: {config_payload}")
        except Exception as e:
            logger.error(f"Error sending TTS config: {e}", exc_info=True)
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
                        
                        # Log full message for debugging
                        logger.debug(f"TTS received message: {data}")
                        
                        if data.get("type") == "audio":
                            # Base64-encoded audio
                            # Defensive parsing: data["data"] must be a string (base64), not a dict
                            audio_data = data.get("data", "")
                            if isinstance(audio_data, str) and audio_data:
                                try:
                                    audio_bytes = base64.b64decode(audio_data)
                                    if self.audio_callback and not self._is_cancelled:
                                        await self.audio_callback(audio_bytes)
                                except Exception as e:
                                    logger.error(f"Error decoding TTS audio: {e}")
                            elif isinstance(audio_data, dict):
                                # If data["data"] is a dict, it might be an error or different format
                                logger.warning(f"TTS audio message has dict data instead of base64 string: {audio_data}")
                            else:
                                logger.debug(f"TTS audio message with empty or invalid data: {type(audio_data)}")
                                    
                        elif data.get("type") == "error":
                            error_data = data.get("data", {})
                            error_msg = error_data.get("message", data.get("error", "Unknown error"))
                            error_code = error_data.get("code", "unknown")
                            logger.error(f"SarvamAI TTS error (code {error_code}): {error_msg}, full response: {data}")
                            # Don't disconnect on 422 errors (invalid parameters) - connection is still valid
                            # The error is about message format, not authentication
                            if error_code == 422:
                                logger.warning("TTS parameter error (422) - connection remains open, check message format")
                            else:
                                # Only disconnect on critical errors (auth, server errors, etc.)
                                logger.error(f"TTS critical error (code {error_code}) - disconnecting")
                                self.is_connected = False
                                break
                            
                        elif data.get("type") == "done":
                            logger.debug("TTS generation completed")
                        else:
                            # Log unknown message types for debugging
                            logger.debug(f"TTS unknown message type: {data.get('type')}, full: {data}")
                            
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse TTS message: {e}, message: {message[:200] if isinstance(message, str) else 'binary'}")
                except Exception as e:
                    logger.error(f"Error processing TTS message: {e}", exc_info=True)
                    
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"SarvamAI TTS WebSocket connection closed: {e.code} - {e.reason}")
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
            # Check if connection is still open
            if not self.websocket or self.websocket.closed:
                logger.warning(f"TTS WebSocket is closed (is_connected={self.is_connected}, websocket={self.websocket is not None}), cannot send text")
                self.is_connected = False
                return
            
            # SarvamAI TTS WebSocket message format: {"type": "text", "data": {...}}
            # Format per SarvamAI documentation
            payload = {
                "type": "text",
                "data": {
                    "text": text,
                    "voice": "default",
                    "language": self.language
                }
            }
            
            message_json = json.dumps(payload)
            # Log payload structure but not full content (to avoid cluttering logs)
            logger.debug(f"TTS payload structure: type={payload.get('type')}, text_length={len(text)}, voice={payload.get('data', {}).get('voice')}, language={payload.get('data', {}).get('language')}")
            logger.info(f"TTS sending text (length: {len(text)} chars, voice: default, language: {self.language})")
            
            await self.websocket.send(message_json)
            logger.debug(f"✓ TTS message sent successfully")
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"TTS connection closed while sending: {e.code} - {e.reason}")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Error sending text to TTS: {e}", exc_info=True)
            self.is_connected = False
    
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

