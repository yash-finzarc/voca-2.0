"""
SarvamAI Text-to-Speech (TTS) service with WebSocket streaming support.
Handles real-time text-to-speech conversion with streaming audio output.

CRITICAL: Twilio Media Streams requires μ-law encoded audio at 8000Hz, mono.
This service requests raw PCM from Sarvam and converts it to μ-law.

IMPORTANT: According to Sarvam documentation, output_audio_codec MUST be set
to "pcm" in the config message. If not specified, Sarvam defaults to MP3
(audio/mpeg), which cannot be converted to μ-law and will cause white noise.

Config format (per Sarvam docs - EXACT format, no extra fields):
{
  "type": "config",
  "data": {
    "speaker": "anushka",
    "language": "en-IN",
    "output_audio_codec": "pcm"  # CRITICAL: Prevents MP3 default
  }
}

If Sarvam returns MP3 instead of PCM (despite config), the system will raise
RuntimeError to prevent white noise/distortion. MP3 bytes cannot be directly
converted to μ-law - they must be decoded to PCM first.

Alternative Solution (if Sarvam cannot provide PCM):
- Install: pip install pydub
- Decode MP3 → PCM → μ-law using pydub.AudioSegment
- See code comments for implementation details
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
            # CRITICAL: According to Sarvam documentation, output_audio_codec MUST be set to "pcm"
            # If not specified, Sarvam defaults to MP3 (audio/mpeg), which cannot be converted to μ-law
            # Official format per Sarvam docs (EXACT format - no extra fields):
            # {
            #   "type": "config",
            #   "data": {
            #     "speaker": "anushka",
            #     "language": "en-IN",
            #     "output_audio_codec": "pcm"
            #   }
            # }
            config_payload = {
                "type": "config",
                "data": {
                    "speaker": self.voice,  # Voice name (e.g., "anushka" or "default")
                    "language": self.language,  # Language code (e.g., "en-IN") - NOT target_language_code
                    "output_audio_codec": "pcm"  # CRITICAL: Must be "pcm" to avoid MP3 default
                }
            }
            
            config_json = json.dumps(config_payload)
            await self.websocket.send(config_json)
            logger.info(f"✓ TTS config sent (requesting PCM): speaker={self.voice}, language={self.language}, output_audio_codec=pcm")
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
                        
                        # Log message type only (NEVER log audio data - it's too large and not human-readable)
                        msg_type = data.get("type", "unknown")
                        if msg_type == "audio":
                            # For audio messages, only log metadata, never the actual audio data
                            audio_data = data.get("data", "")
                            audio_size = len(audio_data) if isinstance(audio_data, str) else 0
                            logger.debug(f"TTS received audio message (size: {audio_size} base64 chars)")
                        else:
                            # For non-audio messages, log structure but not full content
                            logger.debug(f"TTS received message type: {msg_type}")
                        
                        if data.get("type") == "audio":
                            # Sarvam TTS sends audio in nested structure:
                            # {
                            #   "type": "audio",
                            #   "data": {
                            #     "request_id": "...",
                            #     "content_type": "audio/pcm",
                            #     "audio": "<base64_string>"
                            #   }
                            # }
                            payload = data.get("data", {})
                            
                            if isinstance(payload, dict) and "audio" in payload:
                                # Correct format: nested dict with "audio" key
                                audio_b64 = payload["audio"]
                                content_type = payload.get("content_type", "unknown")
                                
                                # CRITICAL: Twilio REQUIRES PCM, not MP3
                                # If Sarvam sends MP3, we cannot convert it to μ-law correctly
                                # MP3 bytes ≠ PCM samples, converting MP3 to μ-law produces white noise
                                valid_pcm_types = ("audio/pcm", "audio/pcm;rate=8000", "audio/raw", "audio/x-raw")
                                if content_type not in valid_pcm_types:
                                    error_msg = (
                                        f"Sarvam TTS returned {content_type} instead of PCM. "
                                        f"Cannot stream to Twilio (requires PCM → μ-law conversion). "
                                        f"Expected one of: {valid_pcm_types}. "
                                        f"This will cause white noise/distortion. "
                                        f"Check TTS config: output_audio_codec must be set to 'pcm' in config message. "
                                        f"Without output_audio_codec='pcm', Sarvam defaults to MP3."
                                    )
                                    logger.error(error_msg)
                                    # Hard fail: MP3 cannot be converted to μ-law for Twilio
                                    raise RuntimeError(error_msg)
                                
                                try:
                                    audio_bytes = base64.b64decode(audio_b64)
                                    
                                    # Verify PCM length is even (16-bit = 2 bytes per sample)
                                    if len(audio_bytes) % 2 != 0:
                                        logger.warning(f"PCM audio length ({len(audio_bytes)}) is not even (not 16-bit aligned), truncating")
                                        audio_bytes = audio_bytes[:-1]
                                    
                                    if self.audio_callback and not self._is_cancelled:
                                        await self.audio_callback(audio_bytes)
                                    logger.debug(f"TTS audio decoded: {len(audio_bytes)} bytes PCM (content_type: {content_type})")
                                except RuntimeError:
                                    # Re-raise our hard failure for MP3
                                    raise
                                except Exception as e:
                                    logger.error(f"Error decoding TTS audio: {e}", exc_info=True)
                            elif isinstance(payload, str) and payload:
                                # Fallback: if data["data"] is directly a base64 string (legacy format)
                                try:
                                    audio_bytes = base64.b64decode(payload)
                                    if self.audio_callback and not self._is_cancelled:
                                        await self.audio_callback(audio_bytes)
                                    logger.debug(f"TTS audio decoded (legacy format) and sent to callback ({len(audio_bytes)} bytes PCM)")
                                except Exception as e:
                                    logger.error(f"Error decoding TTS audio (legacy format): {e}")
                            else:
                                # Unexpected format
                                logger.warning(f"Unexpected audio payload format: keys={list(payload.keys()) if isinstance(payload, dict) else type(payload)}")
                                    
                        elif data.get("type") == "error":
                            error_data = data.get("data", {})
                            error_msg = error_data.get("message", data.get("error", "Unknown error"))
                            error_code = error_data.get("code", "unknown")
                            # Log error details but NEVER log audio data
                            logger.error(f"SarvamAI TTS error (code {error_code}): {error_msg}")
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
                            # Log unknown message types for debugging (but never log audio data)
                            msg_type = data.get("type", "unknown")
                            if msg_type == "audio":
                                logger.debug(f"TTS unknown audio message format")
                            else:
                                # For non-audio, log structure only
                                logger.debug(f"TTS unknown message type: {msg_type}, keys: {list(data.keys())}")
                            
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
            
            # CRITICAL: Sarvam TTS text message format - ONLY "text" field allowed
            # Voice and language are bound from config, NOT per message
            # Valid format: {"type": "text", "data": {"text": "..."}}
            # Invalid: {"type": "text", "data": {"text": "...", "voice": "...", "language": "..."}}
            payload = {
                "type": "text",
                "data": {
                    "text": text
                }
            }
            
            message_json = json.dumps(payload)
            # Log payload structure but not full content (to avoid cluttering logs)
            logger.debug(f"TTS payload structure: type={payload.get('type')}, text_length={len(text)}")
            logger.info(f"TTS sending text (length: {len(text)} chars)")
            
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

