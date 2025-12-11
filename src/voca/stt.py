from __future__ import annotations

import os
from typing import Optional

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
    from deepgram import DeepgramClient, PrerecordedOptions, FileSource
except Exception:
    DeepgramClient = None  # type: ignore


class CoquiSTT:
    def __init__(self, model_path: Optional[str] = None, scorer_path: Optional[str] = None, sample_rate: int = 16000):
        self.model_path = model_path or Config.stt_model_path
        self.scorer_path = scorer_path or Config.stt_scorer_path
        self.sample_rate = sample_rate
        self._model = None
        self.log = logging.getLogger("voca.stt.coqui")
        self.model_name = "CoquiSTT"

    def load(self):
        if Model is None:
            raise RuntimeError("Coqui STT not installed. Install 'coqui-stt'.")
        self.log.info(f"[STT] Loading Coqui STT model from {self.model_path}")
        self._model = Model(self.model_path)
        if self.scorer_path and os.path.exists(self.scorer_path):
            try:
                self.log.info(f"[STT] Enabling external scorer {self.scorer_path}")
                self._model.enableExternalScorer(self.scorer_path)
            except Exception:
                self.log.warning("[STT] Failed to enable external scorer", exc_info=True)
        self.log.info(f"[STT] Active STT Model: {self.model_name}")

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
        self.log.info(f"[STT] Transcribing with {self.model_name}: {len(audio)} samples @ {self.sample_rate} Hz")
        result = self._model.stt(audio.tobytes())
        self.log.info(f"[STT] {self.model_name} transcription result: {result}")
        return result


class VoskSTT:
    def __init__(self, model_dir: Optional[str] = None, sample_rate: int = 16000):
        self.model_dir = model_dir or os.getenv("VOCA_VOSK_MODEL_DIR", "models/vosk/en-us")
        self.sample_rate = sample_rate
        self._model = None
        self._recognizer = None
        self.log = logging.getLogger("voca.stt.vosk")
        self.model_name = "VoskSTT"

    def load(self):
        if vosk is None:
            raise RuntimeError("Vosk not installed. Install 'vosk'.")
        self.log.info(f"[STT] Loading Vosk model from {self.model_dir}")
        self._model = vosk.Model(self.model_dir)
        self._recognizer = vosk.KaldiRecognizer(self._model, self.sample_rate)
        self.log.info(f"[STT] Active STT Model: {self.model_name}")

    def is_ready(self) -> bool:
        return self._recognizer is not None

    def transcribe_pcm16(self, audio: np.ndarray) -> str:
        if self._recognizer is None:
            raise RuntimeError("Vosk recognizer not loaded")
        if audio.dtype != np.int16:
            raise ValueError("audio must be int16 mono PCM")
        self.log.info(f"[STT] Transcribing with {self.model_name}: {len(audio)} samples @ {self.sample_rate} Hz")
        self._recognizer.AcceptWaveform(audio.tobytes())
        res = self._recognizer.Result()
        # result is a JSON string like {"text": "..."}
        try:
            import json as _json
            result = _json.loads(res).get("text", "").strip()
            self.log.info(f"[STT] {self.model_name} transcription result: {result}")
            return result
        except Exception:
            return ""


def build_stt() -> "object":
    """Return a loaded STT engine, preferring Deepgram, then Coqui STT, falling back to Vosk."""
    logger = logging.getLogger("voca.stt")
    
    # Force backend via env: VOCA_STT_BACKEND=deepgram|vosk|coqui|whisper
    backend = os.getenv("VOCA_STT_BACKEND", "auto").lower()
    
    logger.info(f"[STT] Building STT engine with backend preference: {backend}")
    
    if backend == "deepgram":
        logger.info("[STT] Attempting to load Deepgram STT...")
        try:
            dg = DeepgramSTT()
            dg.load()
            logger.info(f"[STT] Successfully loaded Deepgram STT model: {dg.model_name}")
            return dg
        except Exception as e:
            logger.error(f"[STT] Failed to load Deepgram STT: {e}", exc_info=True)
            raise
    
    if backend == "vosk":
        logger.info("[STT] Attempting to load Vosk STT...")
        vstt = VoskSTT()
        vstt.load()
        logger.info(f"[STT] Successfully loaded Vosk STT model: {vstt.model_name}")
        return vstt
    
    if backend == "whisper":
        logger.info("[STT] Attempting to load FasterWhisper STT...")
        w = FasterWhisperSTT()
        w.load()
        logger.info(f"[STT] Successfully loaded FasterWhisper STT model: {w.model_name}")
        return w
    
    if backend == "coqui":
        logger.info("[STT] Attempting to load Coqui STT...")
        stt_engine = CoquiSTT()
        stt_engine.load()
        logger.info(f"[STT] Successfully loaded Coqui STT model: {stt_engine.model_name}")
        return stt_engine
    
    # Auto mode: Try Deepgram first, then Coqui, then Vosk
    if backend == "auto":
        # Try Deepgram first
        if DeepgramClient is not None and os.getenv("DEEPGRAM_API_KEY"):
            logger.info("[STT] Auto mode: Attempting to load Deepgram STT...")
            try:
                dg = DeepgramSTT()
                dg.load()
                logger.info(f"[STT] Auto mode: Successfully loaded Deepgram STT model: {dg.model_name}")
                return dg
            except Exception as e:
                logger.warning(f"[STT] Auto mode: Failed to load Deepgram STT: {e}, trying Coqui...")
        
        # Try Coqui
        logger.info("[STT] Auto mode: Attempting to load Coqui STT...")
        try:
            stt_engine = CoquiSTT()
            stt_engine.load()
            logger.info(f"[STT] Auto mode: Successfully loaded Coqui STT model: {stt_engine.model_name}")
            return stt_engine
        except Exception as e:
            logger.warning(f"[STT] Auto mode: Failed to load Coqui STT: {e}, trying Vosk...")
        
        # Fallback to Vosk
        logger.info("[STT] Auto mode: Attempting to load Vosk STT...")
        vstt = VoskSTT()
        vstt.load()
        logger.info(f"[STT] Auto mode: Successfully loaded Vosk STT model: {vstt.model_name}")
        return vstt
    
    # Default: Try Coqui, fallback to Vosk
    logger.info("[STT] Default mode: Attempting to load Coqui STT...")
    try:
        stt_engine = CoquiSTT()
        stt_engine.load()
        logger.info(f"[STT] Default mode: Successfully loaded Coqui STT model: {stt_engine.model_name}")
        return stt_engine
    except Exception:
        logger.warning("[STT] Default mode: Failed to load Coqui STT, falling back to Vosk...")
        vstt = VoskSTT()
        vstt.load()
        logger.info(f"[STT] Default mode: Successfully loaded Vosk STT model: {vstt.model_name}")
        return vstt


class FasterWhisperSTT:
    def __init__(self, model_size: Optional[str] = None, device: Optional[str] = None, sample_rate: int = 16000):
        self.model_size = model_size or os.getenv("VOCA_WHISPER_MODEL", "base")
        self.device = device or os.getenv("VOCA_WHISPER_DEVICE", "cpu")
        self.sample_rate = sample_rate
        self._model = None
        self.log = logging.getLogger("voca.stt.whisper")
        self.model_name = f"FasterWhisper-{self.model_size}"

    def load(self):
        if WhisperModel is None:
            raise RuntimeError("faster-whisper not installed. Install 'faster-whisper'.")
        self.log.info(f"[STT] Loading Faster-Whisper model {self.model_size} on {self.device}")
        self._model = WhisperModel(self.model_size, device=self.device)
        self.log.info(f"[STT] Active STT Model: {self.model_name}")

    def is_ready(self) -> bool:
        return self._model is not None

    def transcribe_pcm16(self, audio: np.ndarray) -> str:
        if self._model is None:
            raise RuntimeError("Whisper model not loaded")
        if audio.dtype != np.int16:
            raise ValueError("audio must be int16 mono PCM")
        self.log.info(f"[STT] Transcribing with {self.model_name}: {len(audio)} samples @ {self.sample_rate} Hz")
        # Convert int16 PCM to float32 in [-1,1]
        audio_f32 = audio.astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(audio_f32, language="en")
        text = " ".join(seg.text for seg in segments).strip()
        return text


class DeepgramSTT:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, sample_rate: int = 16000):
        self.api_key = api_key or os.getenv("DEEPGRAM_API_KEY", "")
        self.model = model or os.getenv("DEEPGRAM_MODEL", "nova-2")
        self.sample_rate = sample_rate
        self._client = None
        self.log = logging.getLogger("voca.stt.deepgram")
        self.model_name = f"Deepgram-{self.model}"

    def load(self):
        if DeepgramClient is None:
            raise RuntimeError("deepgram-sdk not installed. Install 'deepgram-sdk'.")
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY not set. Set DEEPGRAM_API_KEY environment variable.")
        self.log.info(f"[STT] Initializing Deepgram client with model {self.model}")
        self._client = DeepgramClient(self.api_key)
        self.log.info(f"[STT] Active STT Model: {self.model_name}")

    def is_ready(self) -> bool:
        return self._client is not None

    def transcribe_pcm16(self, audio: np.ndarray) -> str:
        if self._client is None:
            raise RuntimeError("Deepgram client not loaded")
        if audio.dtype != np.int16:
            raise ValueError("audio must be int16 mono PCM")
        
        self.log.info(f"[STT] Transcribing with {self.model_name}: {len(audio)} samples @ {self.sample_rate} Hz")
        
        # Convert numpy array to bytes
        audio_bytes = audio.tobytes()
        
        # Create file source from audio bytes
        payload: FileSource = {
            "buffer": audio_bytes,
        }
        
        # Configure options
        options = PrerecordedOptions(
            model=self.model,
            language="en-US",
            smart_format=True,
        )
        
        try:
            response = self._client.listen.rest.v("1").transcribe_file(payload, options)
            # Extract transcript from response
            transcript = response.results.channels[0].alternatives[0].transcript
            self.log.info(f"[STT] {self.model_name} transcription result: {transcript}")
            return transcript.strip()
        except Exception as e:
            self.log.error(f"[STT] Deepgram transcription error: {e}", exc_info=True)
            return ""


