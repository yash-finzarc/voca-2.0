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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from .orchestrator import VocaOrchestrator


class TwilioWebSocketHandler:
    """Handles WebSocket connections for real-time audio streaming with Twilio."""
    
    def __init__(self, orchestrator: VocaOrchestrator):
        self.orchestrator = orchestrator
        self.logger = logging.getLogger(__name__)
        self.active_connections: Dict[str, Dict] = {}
        self.audio_buffers: Dict[str, list] = {}
        self.websocket_connections: Dict[str, WebSocket] = {}
        self.call_rooms: Dict[str, set] = {}  # call_sid -> set of websocket_ids
        
    def create_websocket_app(self, host='0.0.0.0', port=5000):
        """Create FastAPI app with WebSocket support for WebSocket handling."""
        app = FastAPI(title="VOCA Twilio WebSocket Server")
        handler = self
        
        @app.websocket("/ws/{connection_id}")
        async def websocket_endpoint(websocket: WebSocket, connection_id: str):
            """Handle WebSocket connection."""
            await websocket.accept()
            handler.logger.info(f"WebSocket connection established: {connection_id}")
            handler.websocket_connections[connection_id] = websocket
            
            try:
                while True:
                    # Receive JSON message
                    data = await websocket.receive_json()
                    message_type = data.get('type')
                    
                    if message_type == 'join_call':
                        call_sid = data.get('call_sid')
                        if call_sid:
                            if call_sid not in handler.call_rooms:
                                handler.call_rooms[call_sid] = set()
                            handler.call_rooms[call_sid].add(connection_id)
                            handler.active_connections[connection_id] = {
                                'call_sid': call_sid,
                                'connected_at': time.time()
                            }
                            handler.logger.info(f"Connection {connection_id} joined call {call_sid}")
                            await websocket.send_json({'status': 'joined', 'call_sid': call_sid})
                    
                    elif message_type == 'audio_data':
                        call_sid = data.get('call_sid')
                        audio_payload = data.get('audio')
                        
                        if call_sid and audio_payload:
                            try:
                                # Decode base64 audio data
                                audio_bytes = base64.b64decode(audio_payload)
                                
                                # Convert to numpy array (assuming 16-bit PCM, 8kHz)
                                audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
                                
                                # Process through VOCA orchestrator
                                handler.process_audio_chunk(call_sid, audio_array)
                                
                            except Exception as e:
                                handler.logger.error(f"Error processing audio data: {e}")
                    
                    elif message_type == 'call_status':
                        call_sid = data.get('call_sid')
                        status = data.get('status')
                        
                        if call_sid:
                            handler.logger.info(f"Call {call_sid} status: {status}")
                            
                            if status in ['completed', 'failed', 'busy', 'no-answer']:
                                handler.cleanup_call(call_sid)
                    
            except WebSocketDisconnect:
                handler.logger.info(f"WebSocket disconnected: {connection_id}")
                handler.cleanup_connection(connection_id)
            except Exception as e:
                handler.logger.error(f"WebSocket error: {e}")
                handler.cleanup_connection(connection_id)
        
        return app
    
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
    
    async def send_audio_response(self, call_sid: str, audio_data: bytes):
        """Send audio response back to Twilio via WebSocket."""
        try:
            # Encode audio data as base64
            audio_b64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Send to all connections in the call room
            if call_sid in self.call_rooms:
                message = {
                    'type': 'audio_response',
                    'call_sid': call_sid,
                    'audio': audio_b64
                }
                disconnected = []
                for connection_id in self.call_rooms[call_sid]:
                    if connection_id in self.websocket_connections:
                        try:
                            await self.websocket_connections[connection_id].send_json(message)
                        except Exception as e:
                            self.logger.error(f"Error sending to {connection_id}: {e}")
                            disconnected.append(connection_id)
                
                # Clean up disconnected connections
                for conn_id in disconnected:
                    self.cleanup_connection(conn_id)
            
        except Exception as e:
            self.logger.error(f"Error sending audio response: {e}")
    
    def cleanup_connection(self, connection_id: str):
        """Clean up WebSocket connection."""
        # Remove from active connections
        if connection_id in self.active_connections:
            call_sid = self.active_connections[connection_id].get('call_sid')
            if call_sid and call_sid in self.call_rooms:
                self.call_rooms[call_sid].discard(connection_id)
                if not self.call_rooms[call_sid]:
                    del self.call_rooms[call_sid]
            del self.active_connections[connection_id]
        
        # Remove WebSocket connection
        if connection_id in self.websocket_connections:
            del self.websocket_connections[connection_id]
    
    def cleanup_call(self, call_sid: str):
        """Clean up all resources for a call."""
        # Remove from active connections
        connections_to_remove = [
            conn_id for conn_id, conn_data in self.active_connections.items()
            if conn_data.get('call_sid') == call_sid
        ]
        
        for conn_id in connections_to_remove:
            self.cleanup_connection(conn_id)
        
        # Clean up call room
        if call_sid in self.call_rooms:
            del self.call_rooms[call_sid]
        
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
