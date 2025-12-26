"""
SarvamAI Speech-to-Text (STT) service with HTTP streaming support.
SarvamAI STT uses HTTP streaming (NOT WebSocket) - this is a key difference from Deepgram.

Handles real-time audio transcription with partial and final transcript support via HTTP chunked streaming.
"""
import asyncio
import json
import logging
import httpx
from typing import Callable, Optional, AsyncIterator

logger = logging.getLogger(__name__)


class SarvamSTTClient:
    """
    SarvamAI STT client for streaming speech-to-text transcription via HTTP.
    
    IMPORTANT: SarvamAI STT does NOT support WebSocket connections.
    It requires HTTP POST with chunked transfer encoding for streaming audio.
    """
    
    def __init__(self, api_key: str, language: str = "en-IN", sample_rate: int = 8000):
        """
        Initialize SarvamAI STT client.
        
        Args:
            api_key: SarvamAI API key
            language: Language code (default: en-IN)
            sample_rate: Audio sample rate in Hz (default: 8000 for Twilio)
        """
        self.api_key = api_key
        self.language = language
        self.sample_rate = sample_rate
        self.client: Optional[httpx.AsyncClient] = None
        self.is_connected = False
        self.transcript_callback: Optional[Callable[[str, bool], None]] = None
        self._audio_queue: Optional[asyncio.Queue] = None
        self._stream_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        
    async def connect(self):
        """Initialize HTTP client for SarvamAI STT streaming."""
        try:
            logger.info("Initializing SarvamAI STT HTTP streaming client")
            logger.debug(f"Language: {self.language}, Sample rate: {self.sample_rate}")
            logger.debug(f"API key present: {bool(self.api_key)}, length: {len(self.api_key) if self.api_key else 0}")
            
            # Create HTTP client with no timeout for streaming
            self.client = httpx.AsyncClient(timeout=None)
            self._audio_queue = asyncio.Queue()
            self._stop_event.clear()
            self.is_connected = True
            
            # Start streaming task
            self._stream_task = asyncio.create_task(self._stream_transcription())
            
            logger.info("SarvamAI STT HTTP streaming client initialized")
            
        except Exception as e:
            logger.error(f"Error initializing SarvamAI STT client: {e}")
            self.is_connected = False
            raise
    
    async def _audio_generator(self) -> AsyncIterator[bytes]:
        """
        Generator that yields PCM audio chunks from the queue.
        Stops when None is received (sentinel value).
        """
        while True:
            try:
                # Wait for audio chunk with timeout to allow checking stop event
                chunk = await asyncio.wait_for(self._audio_queue.get(), timeout=0.1)
                if chunk is None:  # Sentinel value to stop
                    break
                yield chunk
            except asyncio.TimeoutError:
                # Check if we should stop
                if self._stop_event.is_set():
                    break
                continue
    
    async def _stream_transcription(self):
        """
        Stream audio to SarvamAI STT via HTTP POST with chunked transfer encoding.
        Receives transcription responses and calls the callback.
        """
        if not self.client or not self._audio_queue:
            logger.error("STT client not properly initialized")
            return
        
        try:
            # SarvamAI STT HTTP endpoint (NOT WebSocket)
            url = "https://api.sarvam.ai/speech-to-text"
            
            # CRITICAL: Use x-api-key header (NOT Authorization: Bearer)
            # SarvamAI requires x-api-key for all requests
            # Transfer-Encoding is handled automatically by httpx for streaming
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "audio/raw"
            }
            
            logger.info(f"Starting HTTP streaming to SarvamAI STT: {url}")
            
            # Stream audio chunks to SarvamAI
            async with self.client.stream(
                "POST",
                url,
                headers=headers,
                content=self._audio_generator()
            ) as response:
                logger.info(f"STT HTTP response status: {response.status_code}")
                
                if response.status_code != 200:
                    # Read full error response for debugging
                    try:
                        error_text = await response.aread()
                        error_message = error_text.decode('utf-8', errors='ignore')
                        logger.error(f"STT HTTP error {response.status_code}")
                        logger.error(f"Error response: {error_message}")
                        logger.error(f"Response headers: {dict(response.headers)}")
                    except Exception as e:
                        logger.error(f"Failed to read error response: {e}")
                    self.is_connected = False
                    return
                
                # Read transcription responses line by line
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    
                    try:
                        data = json.loads(line)
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
                        logger.warning(f"Failed to parse STT message: {e}, line: {line[:200]}")
                    except Exception as e:
                        logger.error(f"Error processing STT message: {e}", exc_info=True)
                        
        except Exception as e:
            logger.error(f"Error in STT HTTP streaming: {e}", exc_info=True)
            self.is_connected = False
    
    async def send_audio(self, pcm_audio: bytes):
        """
        Send PCM audio frame to SarvamAI STT via HTTP streaming.
        
        Args:
            pcm_audio: Raw PCM audio bytes (16-bit, little-endian)
        """
        if not self.is_connected or not self._audio_queue:
            logger.warning("STT not connected, cannot send audio")
            return
        
        try:
            # Queue audio chunk for streaming
            await self._audio_queue.put(pcm_audio)
        except Exception as e:
            logger.error(f"Error queuing audio for STT: {e}", exc_info=True)
            self.is_connected = False
    
    def set_transcript_callback(self, callback: Callable[[str, bool], None]):
        """
        Set callback function for receiving transcripts.
        
        Args:
            callback: Async function that receives (transcript: str, is_final: bool)
        """
        self.transcript_callback = callback
    
    async def stop(self):
        """Close HTTP connection and cleanup."""
        try:
            self._stop_event.set()
            
            # Send sentinel value to stop audio generator
            if self._audio_queue:
                await self._audio_queue.put(None)
            
            # Wait for stream task to complete
            if self._stream_task:
                try:
                    await asyncio.wait_for(self._stream_task, timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("STT stream task did not complete in time, cancelling")
                    self._stream_task.cancel()
                    try:
                        await self._stream_task
                    except asyncio.CancelledError:
                        pass
            
            # Close HTTP client
            if self.client:
                await self.client.aclose()
                self.client = None
            
            self.is_connected = False
            logger.info("SarvamAI STT HTTP streaming client closed")
        except Exception as e:
            logger.error(f"Error stopping STT client: {e}")

