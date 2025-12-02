from __future__ import annotations

import queue
from typing import Optional

import numpy as np
# import sounddevice as sd  # Commented out - not needed for Twilio calls
sd = None  # type: ignore
import logging

from src.voca.config import Config

try:
    from TTS.api import TTS  # Coqui TTS
except Exception:  # pragma: no cover
    TTS = None  # type: ignore

try:
    from deepgram import DeepgramClient
    # Deepgram SDK v5.x uses different API structure
    # Options are passed as dictionaries, not separate classes
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DeepgramClient = None  # type: ignore
    DEEPGRAM_AVAILABLE = False


class CoquiTTS:
    def __init__(self, model_name: Optional[str] = None, sample_rate: int = 22050, device: Optional[str] = None):
        self.model_name = model_name or Config.tts_model_name
        self.sample_rate = sample_rate
        self.device = device or Config.device
        self._tts = None
        self.log = logging.getLogger("voca.tts")

    def load(self):
        if TTS is None:
            raise RuntimeError("Coqui TTS not installed. Install 'coqui-tts'.")
        self.log.info(f"Loading TTS model {self.model_name}")
        self._tts = TTS(self.model_name)

    def is_ready(self) -> bool:
        return self._tts is not None

    def speak(self, text: str):
        if not text:
            return
        if self._tts is None:
            raise RuntimeError("TTS model not loaded")
        if sd is None:
            # Sounddevice not available - this is expected for Twilio calls
            # Twilio uses its own TTS via TwiML response.say()
            self.log.warning("sounddevice not available. Audio playback skipped (this is normal for Twilio calls).")
            return
        # Generate waveform
        self.log.info(f"Synthesizing {len(text)} characters")
        wav = self._tts.tts(text=text)
        wav = np.asarray(wav, dtype=np.float32)
        self.log.info(f"Playing audio: {len(wav)} samples @ {self.sample_rate} Hz")
        sd.play(wav, samplerate=self.sample_rate, blocking=True)


class DeepgramTTS:
    """Deepgram Text-to-Speech implementation for generating audio from text."""
    
    def __init__(self, api_key: Optional[str] = None, voice: str = "aura-asteria-en", sample_rate: int = 24000):
        self.api_key = api_key or Config.deepgram_api_key
        self.voice = voice
        self.sample_rate = sample_rate
        self._client = None
        self.log = logging.getLogger("voca.tts.deepgram")
        
    def load(self):
        """Initialize Deepgram client."""
        if not DEEPGRAM_AVAILABLE or DeepgramClient is None:
            raise RuntimeError("Deepgram SDK not installed. Install 'deepgram-sdk'.")
        if not self.api_key:
            raise RuntimeError("Deepgram API key not configured. Set DEEPGRAM_API_KEY environment variable.")
        self.log.info("Initializing Deepgram TTS client")
        # Deepgram SDK v5.x uses api_key as a keyword argument
        try:
            self._client = DeepgramClient(api_key=self.api_key)
        except TypeError:
            # Fallback for older versions that might use positional argument
            try:
                self._client = DeepgramClient(self.api_key)
            except Exception as e:
                raise RuntimeError(f"Failed to initialize Deepgram client: {e}")
        
    def is_ready(self) -> bool:
        """Check if Deepgram client is ready."""
        return self._client is not None
    
    def speak(self, text: str) -> Optional[bytes]:
        """
        Generate audio from text using Deepgram TTS.
        Returns audio bytes (PCM16 format) or None if error.
        """
        if not text:
            return None
        if self._client is None:
            raise RuntimeError("Deepgram TTS client not loaded")
        
        try:
            # Deepgram SDK v5.x uses dictionary for options
            options_dict = {
                "model": self.voice,
                "encoding": "linear16",
                "container": "none",
                "sample_rate": self.sample_rate,
            }
            
            # Deepgram SDK v5.x API structure - use v1 instead of v("1")
            response = self._client.speak.v1.save(
                {"text": text},
                options=options_dict
            )
            
            # Read audio data from response
            # In v5.x, the response structure may be different
            if hasattr(response, 'stream'):
                audio_data = response.stream.read()
            elif hasattr(response, 'read'):
                audio_data = response.read()
            elif hasattr(response, 'content'):
                audio_data = response.content
            else:
                # Try to get bytes directly
                audio_data = bytes(response) if response else None
            
            return audio_data
            
        except Exception as e:
            self.log.error(f"Deepgram TTS error: {e}")
            return None
    
    def speak_to_numpy(self, text: str) -> Optional[np.ndarray]:
        """
        Generate audio from text and return as numpy array (int16 PCM).
        Returns numpy array or None if error.
        """
        audio_bytes = self.speak(text)
        if audio_bytes is None:
            return None
        
        # Convert bytes to numpy array (int16 PCM)
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
        return audio_array


