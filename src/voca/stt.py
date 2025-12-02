from __future__ import annotations

import os
from typing import Optional, Callable, List

import numpy as np
import logging

from src.voca.config import Config

try:
    from stt import Model  # Coqui STT
except Exception as e:  # pragma: no cover
    Model = None  # type: ignore

try:
    import vosk
except Exception:  # pragma: no cover
    vosk = None  # type: ignore

try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None  # type: ignore

try:
    from deepgram import DeepgramClient
    # Deepgram SDK v5.x uses different API structure
    # The new API doesn't require separate imports for LiveOptions/Events
    # They're accessed through the client instance
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DeepgramClient = None  # type: ignore
    DEEPGRAM_AVAILABLE = False


class CoquiSTT:
    def __init__(self, model_path: Optional[str] = None, scorer_path: Optional[str] = None, sample_rate: int = 16000):
        self.model_path = model_path or Config.stt_model_path
        self.scorer_path = scorer_path or Config.stt_scorer_path
        self.sample_rate = sample_rate
        self._model = None
        self.log = logging.getLogger("voca.stt.coqui")

    def load(self):
        if Model is None:
            raise RuntimeError("Coqui STT not installed. Install 'coqui-stt'.")
        self.log.info(f"Loading Coqui STT model from {self.model_path}")
        self._model = Model(self.model_path)
        if self.scorer_path and os.path.exists(self.scorer_path):
            try:
                self.log.info(f"Enabling external scorer {self.scorer_path}")
                self._model.enableExternalScorer(self.scorer_path)
            except Exception:
                self.log.warning("Failed to enable external scorer", exc_info=True)

    def is_ready(self) -> bool:
        return self._model is not None

    def transcribe_pcm16(self, audio: np.ndarray) -> str:
        """
        audio: int16 mono numpy array at self.sample_rate
        """
        if self._model is None:
            raise RuntimeError("STT model not loaded")
        if audio.dtype != np.int16:
            raise ValueError("audio must be int16 mono PCM")
        self.log.info(f"Transcribing {len(audio)} samples @ {self.sample_rate} Hz")
        return self._model.stt(audio.tobytes())


class VoskSTT:
    def __init__(self, model_dir: Optional[str] = None, sample_rate: int = 16000):
        self.model_dir = model_dir or os.getenv("VOCA_VOSK_MODEL_DIR", "models/vosk/en-us")
        self.sample_rate = sample_rate
        self._model = None
        self._recognizer = None
        self.log = logging.getLogger("voca.stt.vosk")

    def load(self):
        if vosk is None:
            raise RuntimeError("Vosk not installed. Install 'vosk'.")
        self.log.info(f"Loading Vosk model from {self.model_dir}")
        self._model = vosk.Model(self.model_dir)
        self._recognizer = vosk.KaldiRecognizer(self._model, self.sample_rate)

    def is_ready(self) -> bool:
        return self._recognizer is not None

    def transcribe_pcm16(self, audio: np.ndarray) -> str:
        if self._recognizer is None:
            raise RuntimeError("Vosk recognizer not loaded")
        if audio.dtype != np.int16:
            raise ValueError("audio must be int16 mono PCM")
        self.log.info(f"Transcribing {len(audio)} samples @ {self.sample_rate} Hz")
        self._recognizer.AcceptWaveform(audio.tobytes())
        res = self._recognizer.Result()
        # result is a JSON string like {"text": "..."}
        try:
            import json as _json
            return _json.loads(res).get("text", "").strip()
        except Exception:
            return ""


def build_stt() -> "object":
    """Return a loaded STT engine, preferring Deepgram, falling back to others."""
    # Force backend via env: VOCA_STT_BACKEND=deepgram|vosk|coqui|whisper
    backend = os.getenv("VOCA_STT_BACKEND", "auto").lower()
    if backend == "deepgram":
        dgstt = DeepgramSTT()
        dgstt.load()
        return dgstt
    if backend == "vosk":
        vstt = VoskSTT()
        vstt.load()
        return vstt
    if backend == "whisper":
        w = FasterWhisperSTT()
        w.load()
        return w
    if backend == "coqui":
        stt_engine = CoquiSTT()
        stt_engine.load()
        return stt_engine
    # Try Deepgram first (if API key is set)
    if Config.deepgram_api_key:
        try:
            dgstt = DeepgramSTT()
            dgstt.load()
            return dgstt
        except Exception:
            pass
    # Try Coqui
    try:
        stt_engine = CoquiSTT()
        stt_engine.load()
        return stt_engine
    except Exception:
        # Fallback to Vosk
        vstt = VoskSTT()
        vstt.load()
        return vstt


class FasterWhisperSTT:
    def __init__(self, model_size: Optional[str] = None, device: Optional[str] = None, sample_rate: int = 16000):
        self.model_size = model_size or os.getenv("VOCA_WHISPER_MODEL", "base")
        self.device = device or os.getenv("VOCA_WHISPER_DEVICE", "cpu")
        self.sample_rate = sample_rate
        self._model = None
        self.log = logging.getLogger("voca.stt.whisper")

    def load(self):
        if WhisperModel is None:
            raise RuntimeError("faster-whisper not installed. Install 'faster-whisper'.")
        self.log.info(f"Loading Faster-Whisper model {self.model_size} on {self.device}")
        self._model = WhisperModel(self.model_size, device=self.device)

    def is_ready(self) -> bool:
        return self._model is not None

    def transcribe_pcm16(self, audio: np.ndarray) -> str:
        if self._model is None:
            raise RuntimeError("Whisper model not loaded")
        if audio.dtype != np.int16:
            raise ValueError("audio must be int16 mono PCM")
        self.log.info(f"Transcribing {len(audio)} samples @ {self.sample_rate} Hz")
        # Convert int16 PCM to float32 in [-1,1]
        audio_f32 = audio.astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(audio_f32, language="en")
        text = " ".join(seg.text for seg in segments).strip()
        return text


class DeepgramSTT:
    """Deepgram Speech-to-Text implementation for real-time transcription."""
    
    def __init__(self, api_key: Optional[str] = None, sample_rate: int = 8000, keyterms: Optional[List[str]] = None):
        self.api_key = api_key or Config.deepgram_api_key
        self.sample_rate = sample_rate
        self._client = None
        self._connection = None
        self.log = logging.getLogger("voca.stt.deepgram")
        self._transcription_buffer = []
        self._is_connected = False
        
        # Parse keyterms from config or provided list
        if keyterms is not None:
            self.keyterms = keyterms
        elif Config.deepgram_keyterms:
            # Parse comma-separated keyterms from config
            self.keyterms = [term.strip() for term in Config.deepgram_keyterms.split(',') if term.strip()]
        else:
            self.keyterms = []
        
        if self.keyterms:
            self.log.info(f"🔑 Using Deepgram keyterms for better accuracy: {self.keyterms}")
        
    def load(self):
        """Initialize Deepgram client."""
        if not DEEPGRAM_AVAILABLE or DeepgramClient is None:
            raise RuntimeError("Deepgram SDK not installed. Install 'deepgram-sdk'.")
        if not self.api_key:
            raise RuntimeError("Deepgram API key not configured. Set DEEPGRAM_API_KEY environment variable.")
        self.log.info("Initializing Deepgram STT client with Nova-3 multilingual model (English India + Hindi)")
        # Deepgram SDK v5.x uses api_key as a keyword argument
        try:
            self._client = DeepgramClient(api_key=self.api_key)
        except TypeError:
            # Fallback for older versions that might use positional argument
            try:
                self._client = DeepgramClient(self.api_key)
            except Exception as e:
                raise RuntimeError(f"Failed to initialize Deepgram client: {e}")
        self._is_connected = True
        
    def is_ready(self) -> bool:
        """Check if Deepgram client is ready."""
        return self._client is not None and self._is_connected
    
    def transcribe_pcm16(self, audio: np.ndarray) -> str:
        """
        Transcribe audio using Deepgram prerecorded API.
        audio: int16 mono numpy array at self.sample_rate
        """
        if self._client is None:
            raise RuntimeError("Deepgram client not loaded")
        if audio.dtype != np.int16:
            raise ValueError("audio must be int16 mono PCM")
        
        try:
            # Convert numpy array to bytes
            audio_bytes = audio.tobytes()
            
            # Deepgram SDK v5.x uses buffer directly
            # Create file source from audio bytes
            payload = {
                "buffer": audio_bytes,
            }
            
            # Configure options for Deepgram SDK v5.x
            # Using nova-3 multilingual model with English (India) and Hindi support
            options_dict = {
                "model": "nova-3",
                "language": "en-IN",  # English (India) as primary language
                "detect_language": True,  # Enable automatic detection for Hindi and code-switching
                "smart_format": True,
                "encoding": "linear16",
                "sample_rate": self.sample_rate,
                "channels": 1,
            }
            
            # Add keyterms if configured (v5.x uses "keywords" parameter)
            if self.keyterms:
                options_dict["keywords"] = self.keyterms
            
            # Deepgram SDK v5.x uses different API - use v1 instead of rest.v("1")
            # Transcribe using the new API
            response = self._client.listen.v1.transcribe_file(
                payload,
                options=options_dict
            )
            
            # Extract transcript
            if response.results and response.results.channels:
                transcript = response.results.channels[0].alternatives[0].transcript
                return transcript.strip() if transcript else ""
            return ""
        except Exception as e:
            self.log.error(f"Deepgram transcription error: {e}")
            return ""
    
    def create_live_connection(self, on_transcript: Optional[Callable[[str], None]] = None):
        """
        Create a live transcription connection for streaming audio.
        Returns a connection object that can be used to send audio chunks.
        """
        if self._client is None:
            raise RuntimeError("Deepgram client not loaded")
        
        # Configure options for Deepgram SDK v5.x
        # Using nova-3 multilingual model with English (India) and Hindi support
        options_dict = {
            "model": "nova-3",
            "language": "en-IN",  # English (India) as primary language
            "detect_language": True,  # Enable automatic detection for Hindi and code-switching
            "smart_format": True,
            "encoding": "linear16",
            "sample_rate": self.sample_rate,
            "channels": 1,
            "interim_results": True,
        }
        
        # Add keyterms if configured (v5.x uses "keywords" parameter)
        if self.keyterms:
            options_dict["keywords"] = self.keyterms
        
        # Deepgram SDK v5.x uses connect() method for live transcription
        # Import EventType for event handling
        try:
            from deepgram.core.events import EventType
        except ImportError:
            # Fallback if EventType is in a different location
            try:
                from deepgram import LiveTranscriptionEvents as EventType
            except ImportError:
                # Use string-based event names as fallback
                EventType = type('EventType', (), {
                    'TRANSCRIPT': 'transcript',
                    'ERROR': 'error',
                    'OPEN': 'open'
                })()
        
        def on_message(result, **kwargs):
            """Handle transcript messages from Deepgram."""
            try:
                # Check if this is a final result (not interim)
                is_final = True
                if hasattr(result, 'is_final'):
                    is_final = result.is_final
                elif hasattr(result, 'channel') and hasattr(result.channel, 'alternatives'):
                    # Check if any alternative has is_final flag
                    if result.channel.alternatives:
                        is_final = getattr(result.channel.alternatives[0], 'is_final', True)
                
                # Only process final transcripts to avoid duplicate LLM calls
                if not is_final:
                    return
                
                # Deepgram SDK v5.x response structure
                if hasattr(result, 'channel') and result.channel:
                    if hasattr(result.channel, 'alternatives') and result.channel.alternatives:
                        sentence = result.channel.alternatives[0].transcript
                        if sentence and on_transcript:
                            on_transcript(sentence)
                elif hasattr(result, 'results') and result.results:
                    # Alternative response structure
                    if hasattr(result.results, 'channels') and result.results.channels:
                        if result.results.channels[0].alternatives:
                            sentence = result.results.channels[0].alternatives[0].transcript
                            if sentence and on_transcript:
                                on_transcript(sentence)
            except Exception as e:
                self.log.error(f"Error processing Deepgram transcript: {e}")
        
        def on_error(error, **kwargs):
            """Handle errors from Deepgram."""
            self.log.error(f"Deepgram live transcription error: {error}")
        
        # Deepgram SDK v5.x uses connect() method
        # Note: This returns a context manager, but we need to return the connection
        # We'll use connect() and return the connection object
        try:
            connection = self._client.listen.v1.connect(**options_dict)
            
            # Set up event handlers using EventType
            connection.on(EventType.TRANSCRIPT, on_message)
            connection.on(EventType.ERROR, on_error)
            
            # Start the connection
            connection.start()
            
            return connection
        except Exception as e:
            raise RuntimeError(f"Failed to start Deepgram live connection: {e}")
    
    def send_audio_chunk(self, connection, audio: np.ndarray):
        """Send an audio chunk to the live connection."""
        if audio.dtype != np.int16:
            raise ValueError("audio must be int16 mono PCM")
        audio_bytes = audio.tobytes()
        connection.send(audio_bytes)


