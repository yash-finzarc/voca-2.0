"""
WebSocket handler for real-time audio streaming with Twilio.
Handles bidirectional audio streaming for real-time voice AI calls.
"""
import asyncio
import json
import logging
import threading
import time
import base64
import numpy as np
from typing import Dict, Optional, Callable
import websocket
from flask import Flask, request, Response
from flask_socketio import SocketIO, emit, join_room, leave_room

from .orchestrator import VocaOrchestrator


class TwilioWebSocketHandler:
    """Handles WebSocket connections for real-time audio streaming with Twilio."""
    
    def __init__(self, orchestrator: VocaOrchestrator):
        self.orchestrator = orchestrator
        self.logger = logging.getLogger(__name__)
        self.active_connections: Dict[str, Dict] = {}
        self.audio_buffers: Dict[str, list] = {}
        
    def create_socketio_app(self, host='0.0.0.0', port=5000):
        """Create Flask-SocketIO app for WebSocket handling."""
        app = Flask(__name__)
        app.config['SECRET_KEY'] = 'voca_twilio_secret'
        socketio = SocketIO(app, cors_allowed_origins="*")
        
        @socketio.on('connect')
        def handle_connect():
            """Handle WebSocket connection."""
            self.logger.info(f"WebSocket connection established: {request.sid}")
        
        @socketio.on('disconnect')
        def handle_disconnect():
            """Handle WebSocket disconnection."""
            self.logger.info(f"WebSocket disconnected: {request.sid}")
            self.cleanup_connection(request.sid)
        
        @socketio.on('join_call')
        def handle_join_call(data):
            """Handle joining a call room."""
            call_sid = data.get('call_sid')
            if call_sid:
                join_room(call_sid)
                self.active_connections[request.sid] = {
                    'call_sid': call_sid,
                    'connected_at': time.time()
                }
                self.logger.info(f"Connection {request.sid} joined call {call_sid}")
        
        @socketio.on('audio_data')
        def handle_audio_data(data):
            """Handle incoming audio data from Twilio."""
            call_sid = data.get('call_sid')
            audio_payload = data.get('audio')
            
            if not call_sid or not audio_payload:
                return
            
            try:
                # Decode base64 audio data
                audio_bytes = base64.b64decode(audio_payload)
                
                # Convert to numpy array (assuming 16-bit PCM, 8kHz)
                audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
                
                # Process through VOCA orchestrator
                self.process_audio_chunk(call_sid, audio_array)
                
            except Exception as e:
                self.logger.error(f"Error processing audio data: {e}")
        
        @socketio.on('call_status')
        def handle_call_status(data):
            """Handle call status updates."""
            call_sid = data.get('call_sid')
            status = data.get('status')
            
            if call_sid:
                self.logger.info(f"Call {call_sid} status: {status}")
                
                if status in ['completed', 'failed', 'busy', 'no-answer']:
                    self.cleanup_call(call_sid)
        
        return app, socketio
    
    def process_audio_chunk(self, call_sid: str, audio_array: np.ndarray):
        """Process audio chunk through VOCA orchestrator."""
        try:
            # Store in buffer for potential processing
            if call_sid not in self.audio_buffers:
                self.audio_buffers[call_sid] = []
            
            self.audio_buffers[call_sid].append(audio_array)
            
            # Process through VOCA orchestrator
            self.orchestrator.handle_audio_chunk(audio_array)
            
        except Exception as e:
            self.logger.error(f"Error processing audio chunk for call {call_sid}: {e}")
    
    def send_audio_response(self, call_sid: str, audio_data: bytes):
        """Send audio response back to Twilio."""
        try:
            # Encode audio data as base64
            audio_b64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Send to all connections in the call room
            from flask_socketio import emit
            emit('audio_response', {
                'call_sid': call_sid,
                'audio': audio_b64
            }, room=call_sid)
            
        except Exception as e:
            self.logger.error(f"Error sending audio response: {e}")
    
    def cleanup_connection(self, connection_id: str):
        """Clean up WebSocket connection."""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
    
    def cleanup_call(self, call_sid: str):
        """Clean up all resources for a call."""
        # Remove from active connections
        connections_to_remove = [
            conn_id for conn_id, conn_data in self.active_connections.items()
            if conn_data.get('call_sid') == call_sid
        ]
        
        for conn_id in connections_to_remove:
            del self.active_connections[conn_id]
        
        # Clean up audio buffer
        if call_sid in self.audio_buffers:
            del self.audio_buffers[call_sid]
        
        self.logger.info(f"Cleaned up resources for call {call_sid}")


class TwilioMediaStreamHandler:
    """Handles Twilio Media Streams for real-time audio processing."""
    
    def __init__(self, orchestrator: VocaOrchestrator):
        self.orchestrator = orchestrator
        self.logger = logging.getLogger(__name__)
        self.active_streams: Dict[str, Dict] = {}
        
    def handle_media_stream(self, call_sid: str, media_data: dict):
        """Handle incoming media stream from Twilio."""
        try:
            # Extract audio data from Twilio media stream
            audio_payload = media_data.get('payload')
            if not audio_payload:
                return
            
            # Decode base64 audio data
            audio_bytes = base64.b64decode(audio_payload)
            
            # Convert to numpy array (Twilio uses μ-law encoding, 8kHz)
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
            
            # Process through VOCA orchestrator
            self.orchestrator.handle_audio_chunk(audio_array)
            
        except Exception as e:
            self.logger.error(f"Error handling media stream for call {call_sid}: {e}")
    
    def start_media_stream(self, call_sid: str):
        """Start media stream for a call."""
        self.active_streams[call_sid] = {
            'started_at': time.time(),
            'audio_chunks': []
        }
        self.logger.info(f"Started media stream for call {call_sid}")
    
    def stop_media_stream(self, call_sid: str):
        """Stop media stream for a call."""
        if call_sid in self.active_streams:
            del self.active_streams[call_sid]
            self.logger.info(f"Stopped media stream for call {call_sid}")
