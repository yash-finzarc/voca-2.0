from __future__ import annotations

import threading
from typing import Callable, Optional

import numpy as np

from src.voca.stt import build_stt
from src.voca.tts import CoquiTTS
from src.voca.llm_client import GeminiClient
from src.voca.config import Config

try:
    import sounddevice as sd
except Exception:  # pragma: no cover
    sd = None  # type: ignore
try:
    import webrtcvad
except Exception:
    webrtcvad = None  # type: ignore


class VocaOrchestrator:
    def __init__(self, on_log: Optional[Callable[[str], None]] = None):
        self.on_log = on_log or (lambda m: None)
        self.stt = None
        self.tts = CoquiTTS()
        self.llm = GeminiClient()
        self._lock = threading.Lock()

    def log(self, msg: str):
        self.on_log(msg)

    def load_models(self):
        self.log("Loading STT...")
        self.stt = build_stt()
        self.log("Loading TTS...")
        self.tts.load()
        self.log("Models ready.")

    def models_ready(self) -> bool:
        stt_ready = (self.stt is not None) and getattr(self.stt, "is_ready", lambda: False)()
        tts_ready = self.tts is not None and self.tts.is_ready()
        return stt_ready and tts_ready

    def ensure_models_loaded(self):
        if not self.models_ready():
            self.load_models()

    def handle_audio_chunk(self, pcm16: np.ndarray):
        # naive: do full utterance on each chunk; in practice, use VAD/segmenter
        if self.stt is None or not getattr(self.stt, "is_ready", lambda: False)():
            return
        try:
            text = self.stt.transcribe_pcm16(pcm16)
            if text:
                self.log(f"USER: {text}")
                reply = self.generate_reply(text)
                if reply:
                    self.log(f"ASSISTANT: {reply}")
                    self.tts.speak(reply)
        except Exception as e:
            self.log(f"Error processing audio: {e}")

    def generate_reply(self, user_text: str) -> str:
        system_prompt = (
            "You are Voca, a helpful voice assistant. "
            "Respond concisely and naturally. "
            "If asked how you can help, say: 'I can assist you with the information that is available to me.' "
            "Keep responses brief and conversational."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
        return self.llm.complete_chat(messages)

    def run_one_minute_interaction(self, duration_sec: int = 30):
        """Record mic audio for duration, transcribe once, query LLM, then speak reply."""
        # Auto-load if needed
        try:
            self.ensure_models_loaded()
        except Exception as e:
            self.log(f"Model load failed: {e}")
            return
        if sd is None:
            self.log("sounddevice not available. Cannot record microphone.")
            return

        sr = Config.sample_rate
        self.log(f"Recording microphone for {duration_sec}s at {sr} Hz...")
        try:
            audio = sd.rec(int(duration_sec * sr), samplerate=sr, channels=1, dtype='int16')
            sd.wait()
        except Exception as e:
            self.log(f"Audio capture failed: {e}")
            return

        pcm16 = np.squeeze(audio)  # shape (N,)
        self.log("Transcribing...")
        try:
            text = self.stt.transcribe_pcm16(pcm16)
        except Exception as e:
            self.log(f"Transcription failed: {e}")
            return

        if not text:
            self.log("No speech detected.")
            return

        self.log(f"USER: {text}")
        self.log("Generating reply...")
        try:
            reply = self.generate_reply(text)
        except Exception as e:
            self.log(f"LLM error: {e}")
            return

        if not reply:
            self.log("Empty reply.")
            return
        self.log(f"ASSISTANT: {reply}")
        try:
            self.tts.speak(reply)
        except Exception as e:
            self.log(f"TTS error: {e}")

    def run_continuous_vad_loop(self, max_silence_ms: int = 2000, frame_ms: int = 30):
        """Continuously listen with VAD; when user stops, process utterance and keep the call up."""
        if sd is None:
            self.log("sounddevice not available.")
            return
        try:
            self.ensure_models_loaded()
        except Exception as e:
            self.log(f"Model load failed: {e}")
            return
        sr = Config.sample_rate
        use_webrtc = webrtcvad is not None
        vad = webrtcvad.Vad(1) if use_webrtc else None  # 0-3; 1 is more sensitive
        if not use_webrtc:
            self.log("Using energy-based VAD (no webrtcvad wheel found)")
        bytes_per_sample = 2
        frame_samples = int(sr * frame_ms / 1000)
        silence_limit_frames = int(max_silence_ms / frame_ms)
        min_utterance_frames = int(300 / frame_ms)  # Minimum 300ms of speech before processing

        self._vad_stop = False
        self.log("VAD loop started. Speak to interact.")

        def stream_callback(indata, frames, time_info, status):
            pass

        buffer = []
        silence_count = 0
        speech_count = 0
        consecutive_silence = 0

        with sd.RawInputStream(samplerate=sr, blocksize=frame_samples, channels=1, dtype='int16') as stream:
            while not getattr(self, "_vad_stop", False):
                chunk = stream.read(frame_samples)[0]
                if use_webrtc:
                    is_speech = vad.is_speech(chunk, sr)
                else:
                    # Energy-based VAD: compute RMS and compare to adaptive threshold
                    arr = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
                    rms = float(np.sqrt(np.mean(arr * arr)) + 1e-6)
                    # Initialize adaptive threshold using first 50 frames (~1.5s)
                    if not hasattr(self, "_rms_noise_floor"):
                        self._rms_noise_floor = rms
                        self._rms_thresh = max(200.0, self._rms_noise_floor * 2.0)  # Even lower threshold
                    else:
                        # Slowly adapt noise floor when detected as silence
                        if rms < getattr(self, "_rms_thresh", 500.0) * 0.6:  # More lenient
                            self._rms_noise_floor = 0.995 * self._rms_noise_floor + 0.005 * rms
                            self._rms_thresh = max(200.0, self._rms_noise_floor * 2.0)
                    is_speech = rms >= getattr(self, "_rms_thresh", 500.0)
                buffer.append(chunk)
                if is_speech:
                    silence_count = 0
                    speech_count += 1
                    consecutive_silence = 0
                else:
                    silence_count += 1
                    consecutive_silence += 1
                # If we've observed speech and then enough silence, finalize utterance
                if silence_count >= silence_limit_frames and buffer and speech_count >= min_utterance_frames:
                    pcm = np.frombuffer(b"".join(buffer), dtype=np.int16)
                    buffer.clear()
                    silence_count = 0
                    speech_count = 0
                    consecutive_silence = 0
                    try:
                        # Apply simple noise reduction and normalization
                        pcm_float = pcm.astype(np.float32) / 32768.0
                        # Simple high-pass filter to remove low-frequency noise
                        pcm_float = np.diff(pcm_float, prepend=pcm_float[0])
                        # Normalize
                        if np.max(np.abs(pcm_float)) > 0:
                            pcm_float = pcm_float / np.max(np.abs(pcm_float)) * 0.95
                        pcm_clean = (pcm_float * 32768.0).astype(np.int16)
                        text = self.stt.transcribe_pcm16(pcm_clean)
                        if text and len(text.strip()) > 2:  # Only process if meaningful text
                            self.log(f"USER: {text}")
                            reply = self.generate_reply(text)
                            if reply:
                                self.log(f"ASSISTANT: {reply}")
                                self.tts.speak(reply)
                    except Exception as e:
                        self.log(f"Pipeline error: {e}")
                elif silence_count >= silence_limit_frames and buffer:
                    # Reset if we had audio but not enough speech
                    buffer.clear()
                    silence_count = 0
                    speech_count = 0
                    consecutive_silence = 0
        self.log("VAD loop stopped.")


