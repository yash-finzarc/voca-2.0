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
    """Return a loaded STT engine, preferring Coqui STT, falling back to Vosk."""
    # Force backend via env: VOCA_STT_BACKEND=vosk|coqui
    backend = os.getenv("VOCA_STT_BACKEND", "auto").lower()
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


