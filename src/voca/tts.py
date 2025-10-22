from __future__ import annotations

import queue
from typing import Optional

import numpy as np
import sounddevice as sd
import logging

from src.voca.config import Config

try:
    from TTS.api import TTS  # Coqui TTS
except Exception:  # pragma: no cover
    TTS = None  # type: ignore


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
        # Generate waveform
        self.log.info(f"Synthesizing {len(text)} characters")
        wav = self._tts.tts(text=text)
        wav = np.asarray(wav, dtype=np.float32)
        self.log.info(f"Playing audio: {len(wav)} samples @ {self.sample_rate} Hz")
        sd.play(wav, samplerate=self.sample_rate, blocking=True)


