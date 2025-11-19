from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np
from langchain_core.messages import BaseMessage, HumanMessage

from src.voca.config import Config
from src.voca.conversation_store import save_conversation_snapshot
from src.voca.langgraph_agent import LangGraphAgent, LangGraphAgentResult
from src.voca.stt import build_stt
from src.voca.system_prompt import get_prompt, get_welcome_message
from src.voca.tts import CoquiTTS
from src.voca.conversation_logger import log_user, log_ai

try:
    import sounddevice as sd
except Exception:  # pragma: no cover
    sd = None  # type: ignore
try:
    import webrtcvad
except Exception:
    webrtcvad = None  # type: ignore


@dataclass
class ConversationSession:
    organization_id: Optional[str]
    messages: List[BaseMessage] = field(default_factory=list)
    collected_data: Dict[str, Any] = field(default_factory=dict)
    lead_status: Optional[str] = None
    transcript: List[Dict[str, Any]] = field(default_factory=list)
    summary_requested: bool = False
    greeting_sent: bool = False  # Track if greeting has been sent


class VocaOrchestrator:
    def __init__(
        self,
        on_log: Optional[Callable[[str], None]] = None,
        organization_id: Optional[str] = None,
    ):
        self.on_log = on_log or (lambda m: None)
        self.stt = None
        self.tts = CoquiTTS()
        self.llm = LangGraphAgent()
        self._lock = threading.Lock()
        self._sessions: Dict[str, ConversationSession] = {}
        self.default_organization_id = organization_id or Config.default_organization_id or None

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
                log_user(text)
                reply = self.generate_reply(text, conversation_id="local_audio")
                if reply:
                    self.log(f"ASSISTANT: {reply}")
                    log_ai(reply)
                    self.tts.speak(reply)
        except Exception as e:
            self.log(f"Error processing audio: {e}")

    def _get_session(self, conversation_id: Optional[str], organization_id: Optional[str]) -> ConversationSession:
        key = conversation_id or "default"
        session = self._sessions.get(key)
        if session is None:
            session = ConversationSession(organization_id=organization_id or self.default_organization_id)
            self._sessions[key] = session
        elif organization_id and organization_id != session.organization_id:
            session.organization_id = organization_id
        return session

    def generate_reply(
        self,
        user_text: str,
        *,
        conversation_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        call_sid: Optional[str] = None,
    ) -> str:
        session = self._get_session(conversation_id, organization_id)
        session.transcript.append({"role": "user", "content": user_text})
        session.messages.append(HumanMessage(content=user_text))
        
        # Log user message
        log_user(user_text)

        org_id = session.organization_id or self.default_organization_id
        system_prompt = get_prompt(organization_id=org_id)
        
        # If greeting has already been sent, modify the system prompt to prevent re-greeting
        if session.greeting_sent:
            # Add instruction to not greet again
            system_prompt = (
                system_prompt + 
                "\n\nIMPORTANT: A greeting has already been given at the start of this call. "
                "Do NOT greet the user again. If they say 'hi', 'hello', or similar greetings, "
                "simply acknowledge them naturally and continue the conversation. "
                "For example, respond with 'Hi! How can I help you?' or 'Hello! What can I do for you?' "
                "instead of repeating the full greeting."
            )

        try:
            result: LangGraphAgentResult = self.llm.generate_reply(
                organization_id=org_id,
                system_prompt=system_prompt,
                messages=session.messages,
                collected_data=session.collected_data,
                lead_status=session.lead_status,
                transcript=session.transcript,
                summary_requested=session.summary_requested,
            )

            session.messages = result.messages
            session.collected_data = result.collected_data
            session.lead_status = result.lead_status
            session.transcript = result.transcript
            session.summary_requested = result.summary_requested

            if org_id:
                save_conversation_snapshot(
                    organization_id=org_id,
                    call_sid=call_sid or conversation_id,
                    transcript=session.transcript,
                    lead_data=session.collected_data,
                    lead_status=session.lead_status,
                )

            # Ensure we have a valid reply
            reply = result.reply.strip() if result.reply else ""
            if not reply:
                # If no reply, provide a graceful response
                if 'name' in user_text.lower() or session.collected_data.get('name'):
                    reply = "I'm sorry, I couldn't quite catch that. Could you please spell your name for me? First, tell me your first name, and then your last name."
                else:
                    reply = "I'm sorry, I couldn't quite understand what you're saying. Could you please repeat that?"
            
            # Log AI response
            if reply:
                log_ai(reply)
            
            return reply
            
        except Exception as e:
            self.log(f"Error generating reply: {e}")
            # Return a graceful error message instead of raising
            # Check if we're collecting a name
            if 'name' in user_text.lower() or session.collected_data.get('name'):
                reply = "I'm sorry, I couldn't quite catch that. Could you please spell your name for me? First, tell me your first name, and then your last name."
            else:
                reply = "I'm sorry, I couldn't quite understand what you're saying. Could you please repeat that?"
            
            # Log AI response even on error
            if reply:
                log_ai(reply)
            
            return reply

    def generate_greeting(
        self,
        *,
        conversation_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> str:
        """
        Generate an initial greeting message.
        First checks for a welcome_message in the database.
        If not found, generates one based on the system prompt.
        This is used when a call first connects.
        """
        org_id = organization_id or self.default_organization_id
        
        # Mark that greeting will be sent (get session to set the flag)
        session = self._get_session(conversation_id, organization_id)
        session.greeting_sent = True
        
        # First, try to get welcome_message from database
        welcome_message = get_welcome_message(organization_id=org_id)
        if welcome_message and welcome_message.strip():
            # Use the welcome_message from database
            greeting = welcome_message.strip()
            # Limit length for TwiML
            if len(greeting) > 300:
                greeting = greeting[:300] + "..."
            self.log(f"Using welcome_message from database: {greeting}")
            log_ai(greeting)
            return greeting
        
        # If no welcome_message in database, generate one from system prompt
        system_prompt = get_prompt(organization_id=org_id)
        
        try:
            # Use the LLM to generate a greeting based on the system prompt
            from langchain_core.messages import HumanMessage, SystemMessage
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content="Generate a brief, natural greeting (1-2 sentences) that you would say when answering a phone call. Keep it warm, professional, and aligned with your role.")
            ]
            
            result: LangGraphAgentResult = self.llm.generate_reply(
                organization_id=org_id,
                system_prompt=system_prompt,
                messages=messages,
                collected_data={},
                lead_status=None,
                transcript=[],
                summary_requested=False,
            )
            
            greeting = result.reply.strip()
            if greeting and len(greeting) > 0:
                # Limit length for TwiML
                if len(greeting) > 300:
                    greeting = greeting[:300] + "..."
                self.log(f"Generated greeting from system prompt: {greeting}")
                log_ai(greeting)
                return greeting
        except Exception as e:
            self.log(f"Error generating greeting: {e}")
        
        # Fallback to a simple greeting if LLM fails
        fallback_greeting = "Hello! How can I help you today?"
        log_ai(fallback_greeting)
        return fallback_greeting

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
        log_user(text)
        self.log("Generating reply...")
        try:
            reply = self.generate_reply(text, conversation_id="one_minute_test")
        except Exception as e:
            self.log(f"LLM error: {e}")
            return

        if not reply:
            self.log("Empty reply.")
            return
        self.log(f"ASSISTANT: {reply}")
        log_ai(reply)
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
                            log_user(text)
                            reply = self.generate_reply(text, conversation_id="continuous_vad")
                            if reply:
                                self.log(f"ASSISTANT: {reply}")
                                log_ai(reply)
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


