from __future__ import annotations

import asyncio
import json
import logging
import base64
import websocket
import threading
import time
from typing import Optional, Callable, Dict, Any, List
from queue import Queue

import av
import numpy as np
import requests
from aiortc import RTCPeerConnection, MediaStreamTrack, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaPlayer, MediaRecorder

from src.voca.config import Config


class AudioSinkTrack(MediaStreamTrack):
    """Audio track that captures incoming audio and converts to PCM16."""
    kind = "audio"

    def __init__(self, track: MediaStreamTrack, on_pcm16: Callable[[np.ndarray], None], sample_rate: int = 16000):
        super().__init__()
        self._track = track
        self._on_pcm16 = on_pcm16
        self._sample_rate = sample_rate

    async def recv(self):
        frame = await self._track.recv()
        # Convert to mono 16k int16
        pcm = frame.to_ndarray(format="s16")
        # pcm shape: (samples, channels). Mix to mono if needed
        if pcm.ndim == 2 and pcm.shape[1] > 1:
            pcm = pcm.mean(axis=1).astype(pcm.dtype)
        # Callback out
        self._on_pcm16(pcm)
        return frame


class AudioSourceTrack(MediaStreamTrack):
    """Audio track that sends audio data to Twilio (for TTS output)."""
    kind = "audio"

    def __init__(self, sample_rate: int = 8000, channels: int = 1):
        super().__init__()
        self._sample_rate = sample_rate
        self._channels = channels
        self._audio_queue: Queue = Queue()
        self._timestamp = 0

    async def recv(self):
        # Wait for audio data from queue
        if self._audio_queue.empty():
            # Return silence if no audio available
            samples = int(self._sample_rate * 0.02)  # 20ms of silence
            audio_data = np.zeros((samples, self._channels), dtype=np.int16)
        else:
            audio_data = self._audio_queue.get()

        # Create audio frame
        frame = av.AudioFrame.from_ndarray(audio_data, format="s16", layout="mono" if self._channels == 1 else "stereo")
        frame.sample_rate = self._sample_rate
        frame.pts = self._timestamp
        self._timestamp += len(audio_data)
        
        return frame

    def add_audio(self, audio_data: np.ndarray):
        """Add audio data to the queue for sending."""
        self._audio_queue.put(audio_data)


class DeepgramSTTClient:
    """Deepgram STT WebSocket client for real-time transcription."""
    
    def __init__(self, on_transcript: Callable[[str, bool], None], api_key: str):
        self.on_transcript = on_transcript
        self.api_key = api_key
        self.logger = logging.getLogger(__name__)
        self.ws: Optional[websocket.WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.is_connected = False
        
    def start(self):
        """Start Deepgram STT WebSocket connection."""
        try:
            # Deepgram WebSocket URL
            url = f"wss://api.deepgram.com/v1/listen?model=nova-2&language=en-US&punctuate=true&interim_results=true"
            headers = {
                "Authorization": f"Token {self.api_key}"
            }
            
            self.ws = websocket.WebSocketApp(
                url,
                header=headers,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            # Start WebSocket in a separate thread
            self.ws_thread = threading.Thread(target=self._run_websocket, daemon=True)
            self.ws_thread.start()
            self.logger.info("[DEEPGRAM_STT] Started WebSocket connection")
            
        except Exception as e:
            self.logger.error(f"[DEEPGRAM_STT] Error starting WebSocket: {e}", exc_info=True)
    
    def _run_websocket(self):
        """Run WebSocket in a thread."""
        self.ws.run_forever()
    
    def _on_open(self, ws):
        """Handle WebSocket open."""
        self.is_connected = True
        self.logger.info("[DEEPGRAM_STT] WebSocket connected")
    
    def _on_message(self, ws, message):
        """Handle WebSocket message (transcription)."""
        try:
            data = json.loads(message)
            transcript = data.get("channel", {}).get("alternatives", [{}])[0].get("transcript", "")
            is_final = data.get("is_final", False)
            
            if transcript:
                self.on_transcript(transcript, is_final)
        except Exception as e:
            self.logger.error(f"[DEEPGRAM_STT] Error processing message: {e}")
    
    def _on_error(self, ws, error):
        """Handle WebSocket error."""
        self.logger.error(f"[DEEPGRAM_STT] WebSocket error: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close."""
        self.is_connected = False
        self.logger.info(f"[DEEPGRAM_STT] WebSocket closed: {close_status_code}")
    
    def send_audio(self, audio_data: bytes):
        """Send audio data to Deepgram for transcription."""
        if self.is_connected and self.ws:
            try:
                self.ws.send(audio_data, websocket.ABNF.OPCODE_BINARY)
            except Exception as e:
                self.logger.error(f"[DEEPGRAM_STT] Error sending audio: {e}")
    
    def stop(self):
        """Stop Deepgram STT connection."""
        if self.ws:
            self.ws.close()
        self.is_connected = False
        self.logger.info("[DEEPGRAM_STT] Stopped")


class WebRTCSession:
    """Complete WebRTC session for a call with STT/TTS integration."""
    
    def __init__(
        self,
        call_sid: str,
        on_transcript: Callable[[str, bool], None],
        on_audio_input: Optional[Callable[[np.ndarray], None]] = None
    ):
        self.call_sid = call_sid
        self.on_transcript = on_transcript
        self.on_audio_input = on_audio_input or (lambda x: None)
        self.logger = logging.getLogger(__name__)
        
        # WebRTC peer connection
        self.pc: Optional[RTCPeerConnection] = None
        self.audio_sink: Optional[AudioSinkTrack] = None
        self.audio_source: Optional[AudioSourceTrack] = None
        
        # Deepgram STT
        self.deepgram_stt: Optional[DeepgramSTTClient] = None
        
        # Audio buffer for STT
        self.audio_buffer: List[np.ndarray] = []
        self.buffer_lock = threading.Lock()
        
        # State
        self.is_connected = False
        self.is_closed = False
        
    async def initialize(self, sdp_offer: str) -> Optional[str]:
        """Initialize WebRTC session with SDP offer and return answer."""
        try:
            self.pc = RTCPeerConnection()
            
            # Create audio source track for TTS output
            self.audio_source = AudioSourceTrack(sample_rate=8000, channels=1)
            self.pc.addTrack(self.audio_source)
            
            # Handle incoming audio tracks
            @self.pc.on("track")
            def on_track(track):
                self.logger.info(f"[WebRTC] Received track: {track.kind} for call {self.call_sid}")
                if track.kind == "audio":
                    # Create audio sink to capture incoming audio
                    self.audio_sink = AudioSinkTrack(
                        track=track,
                        on_pcm16=self._handle_audio_input,
                        sample_rate=16000
                    )
                    # Start processing audio
                    asyncio.create_task(self._process_audio_loop())
            
            # Handle ICE candidates
            @self.pc.on("icecandidate")
            def on_icecandidate(candidate):
                if candidate:
                    self.logger.debug(f"[WebRTC] ICE candidate: {candidate.candidate}")
            
            # Handle connection state changes
            @self.pc.on("connectionstatechange")
            def on_connectionstatechange():
                state = self.pc.connectionState
                self.logger.info(f"[WebRTC] Connection state: {state} for call {self.call_sid}")
                self.is_connected = (state == "connected")
                if state in ["closed", "failed", "disconnected"]:
                    self.is_closed = True
            
            # Process SDP offer
            offer = RTCSessionDescription(sdp=sdp_offer, type="offer")
            await self.pc.setRemoteDescription(offer)
            
            # Create and set local description (answer)
            answer = await self.pc.createAnswer()
            await self.pc.setLocalDescription(answer)
            
            # Start Deepgram STT
            if Config.deepgram_api_key:
                self.deepgram_stt = DeepgramSTTClient(
                    on_transcript=self._handle_transcript,
                    api_key=Config.deepgram_api_key
                )
                self.deepgram_stt.start()
            
            self.logger.info(f"[WebRTC] Session initialized for call {self.call_sid}")
            return self.pc.localDescription.sdp
            
        except Exception as e:
            self.logger.error(f"[WebRTC] Error initializing session: {e}", exc_info=True)
            return None
    
    def _handle_audio_input(self, pcm16: np.ndarray):
        """Handle incoming audio from WebRTC."""
        try:
            # Call user callback
            self.on_audio_input(pcm16)
            
            # Buffer audio for Deepgram STT
            if self.deepgram_stt and self.deepgram_stt.is_connected:
                # Convert to bytes (16-bit PCM, mono)
                audio_bytes = pcm16.astype(np.int16).tobytes()
                self.deepgram_stt.send_audio(audio_bytes)
                
        except Exception as e:
            self.logger.error(f"[WebRTC] Error handling audio input: {e}")
    
    async def _process_audio_loop(self):
        """Process audio in a loop."""
        while not self.is_closed and self.audio_sink:
            try:
                await self.audio_sink.recv()
            except Exception as e:
                if not self.is_closed:
                    self.logger.error(f"[WebRTC] Error in audio loop: {e}")
                break
    
    def _handle_transcript(self, transcript: str, is_final: bool):
        """Handle transcription from Deepgram."""
        try:
            self.on_transcript(transcript, is_final)
        except Exception as e:
            self.logger.error(f"[WebRTC] Error handling transcript: {e}")
    
    async def send_audio(self, audio_data: np.ndarray):
        """Send audio data to Twilio via WebRTC (for TTS)."""
        if self.audio_source and not self.is_closed:
            try:
                # Ensure audio is in correct format (mono, int16)
                if audio_data.ndim == 2:
                    audio_data = audio_data.mean(axis=1).astype(np.int16)
                else:
                    audio_data = audio_data.astype(np.int16)
                
                # Reshape for audio frame
                audio_data = audio_data.reshape(-1, 1)
                
                self.audio_source.add_audio(audio_data)
            except Exception as e:
                self.logger.error(f"[WebRTC] Error sending audio: {e}")
    
    async def stream_tts(self, text: str, model: str = "aura-2-odysseus-en"):
        """Stream TTS audio to WebRTC using Deepgram."""
        try:
            # Use Deepgram REST API to get audio
            api_url = f"https://api.deepgram.com/v1/speak?model={model}&encoding=linear16&sample_rate=8000&container=none"
            headers = {
                "Authorization": f"Token {Config.deepgram_api_key}",
                "Content-Type": "application/json",
            }
            
            text_data = {"text": text}
            resp = requests.post(api_url, headers=headers, json=text_data, timeout=30, stream=True)
            resp.raise_for_status()
            
            # Stream audio chunks to WebRTC
            chunk_size = 1600  # ~200ms of audio at 8kHz
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk and not self.is_closed:
                    # Convert bytes to numpy array
                    audio_array = np.frombuffer(chunk, dtype=np.int16)
                    await self.send_audio(audio_array)
            
            self.logger.info(f"[WebRTC] Streamed TTS for call {self.call_sid}: {text[:50]}...")
            
        except Exception as e:
            self.logger.error(f"[WebRTC] Error streaming TTS: {e}", exc_info=True)
    
    async def close(self):
        """Close WebRTC session and cleanup."""
        try:
            self.is_closed = True
            
            # Stop Deepgram STT
            if self.deepgram_stt:
                self.deepgram_stt.stop()
                self.deepgram_stt = None
            
            # Close WebRTC connection
            if self.pc:
                await self.pc.close()
                self.pc = None
            
            self.logger.info(f"[WebRTC] Session closed for call {self.call_sid}")
            
        except Exception as e:
            self.logger.error(f"[WebRTC] Error closing session: {e}")


class TwilioWebRTCClient:
    """WebRTC client specifically designed for Twilio Voice integration."""
    
    def __init__(self, on_audio: Optional[Callable[[np.ndarray], None]] = None):
        self.pc: Optional[RTCPeerConnection] = None
        self.on_audio = on_audio or (lambda x: None)
        self.logger = logging.getLogger(__name__)
        self._audio_track: Optional[AudioSinkTrack] = None
        
    async def connect(self, sdp_offer: str = None) -> Optional[str]:
        """Connect to Twilio Voice and return SDP answer."""
        try:
            self.pc = RTCPeerConnection()
            
            # Add audio track for receiving audio from Twilio
            if self.pc:
                # Create audio sink track
                self._audio_track = AudioSinkTrack(
                    track=None,  # Will be set when remote track is received
                    on_pcm16=self.on_audio,
                    sample_rate=16000
                )
                
                # Handle incoming tracks
                @self.pc.on("track")
                def on_track(track):
                    self.logger.info(f"Received track: {track.kind}")
                    if track.kind == "audio":
                        # Replace the track in our sink
                        self._audio_track._track = track
                
                # Handle ICE candidates
                @self.pc.on("icecandidate")
                def on_icecandidate(candidate):
                    self.logger.info(f"ICE candidate: {candidate}")
                
                # Handle connection state changes
                @self.pc.on("connectionstatechange")
                def on_connectionstatechange():
                    self.logger.info(f"Connection state: {self.pc.connectionState}")
                
                # If we have an SDP offer, process it
                if sdp_offer:
                    offer = RTCSessionDescription(sdp=sdp_offer, type="offer")
                    await self.pc.setRemoteDescription(offer)
                    
                    # Create answer
                    answer = await self.pc.createAnswer()
                    await self.pc.setLocalDescription(answer)
                    
                    return self.pc.localDescription.sdp
                    
        except Exception as e:
            self.logger.error(f"WebRTC connection failed: {e}")
            return None
    
    async def send_audio(self, audio_data: np.ndarray):
        """Send audio data to Twilio (for TTS output)."""
        # This would typically involve creating an audio track and sending it
        # For now, this is a placeholder as Twilio handles TTS differently
        pass
    
    async def close(self):
        """Close the WebRTC connection."""
        if self.pc:
            await self.pc.close()
            self.pc = None
            self.logger.info("WebRTC connection closed")


class WebRTCClient:
    """Legacy WebRTC client for backward compatibility."""
    
    def __init__(self):
        self.pc: Optional[RTCPeerConnection] = None

    async def connect(self):
        self.pc = RTCPeerConnection()
        # In a real integration, you'd negotiate SDP with a gateway and attach remote tracks

    async def close(self):
        if self.pc:
            await self.pc.close()
            self.pc = None


