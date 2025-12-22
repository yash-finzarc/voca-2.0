from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional, Callable, Dict, Any

import av
import numpy as np
from aiortc import RTCPeerConnection, MediaStreamTrack, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaPlayer, MediaRecorder


class AudioSinkTrack(MediaStreamTrack):
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
        if isinstance(frame, av.AudioFrame):
            pass
        # Callback out
        self._on_pcm16(pcm)
        return frame


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


