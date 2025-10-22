"""
Twilio Voice integration for VOCA project.
Handles SIP to WebRTC bridge and call management with real-time audio processing.
"""
import asyncio
import json
import logging
import time
import base64
import io
from typing import Optional, Callable, Dict, Any
from flask import Flask, request, Response, jsonify
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Start, Stream
from twilio.twiml.messaging_response import MessagingResponse
import threading
import queue
import numpy as np
import websocket
import ssl
from urllib.parse import urlencode

from .twilio_config import get_twilio_config
from .orchestrator import VocaOrchestrator


class TwilioVoiceHandler:
    """Handles Twilio voice calls and bridges them to VOCA orchestrator with real-time audio streaming."""
    
    def __init__(self, orchestrator: VocaOrchestrator):
        self.orchestrator = orchestrator
        config = get_twilio_config()
        self.client = Client(config.account_sid, config.auth_token)
        self.active_calls: Dict[str, Dict[str, Any]] = {}
        self.audio_queue = queue.Queue()
        self.logger = logging.getLogger(__name__)
        self._loop = None
        self.websocket_connections: Dict[str, websocket.WebSocket] = {}
        self.audio_buffers: Dict[str, list] = {}
        
    def start_webhook_server(self, host='0.0.0.0', port=5000):
        """Start Flask server to handle Twilio webhooks with real-time audio streaming."""
        app = Flask(__name__)
        
        @app.route('/webhook/voice', methods=['POST'])
        def handle_incoming_call():
            """Handle incoming Twilio voice calls."""
            call_sid = request.form.get('CallSid')
            from_number = request.form.get('From')
            
            self.logger.info(f"Incoming call from {from_number}, SID: {call_sid}")
            
            # Store call information
            self.active_calls[call_sid] = {
                'from_number': from_number,
                'status': 'ringing',
                'start_time': time.time(),
                'audio_buffer': []
            }
            
            # Create TwiML response
            response = VoiceResponse()
            
            # Say welcome message
            response.say("Hello! You've reached VOCA, your AI voice assistant. Please speak after the tone.")
            
            # Gather user input
            gather = response.gather(
                input='speech',
                timeout=10,
                speech_timeout='auto',
                action=f'/process_speech/{call_sid}',
                method='POST'
            )
            gather.say("I'm listening...")
            
            # If no input, redirect to process
            response.redirect(f'/process_speech/{call_sid}')
            
            return Response(str(response), mimetype='text/xml')
        
        @app.route('/process_speech/<call_sid>', methods=['POST'])
        def handle_speech(call_sid):
            """Handle speech input from user."""
            if call_sid not in self.active_calls:
                return Response("Call not found", status=404)
            
            # Get speech result
            speech_result = request.form.get('SpeechResult', '')
            confidence = request.form.get('Confidence', '0')
            
            self.logger.info(f"Speech received for call {call_sid}: {speech_result} (confidence: {confidence})")
            
            if speech_result and float(confidence) > 0.5:
                # Process speech through VOCA orchestrator
                try:
                    # Generate AI response with error handling
                    try:
                        ai_response = self.orchestrator.generate_reply(speech_result)
                        self.logger.info(f"AI Response: {ai_response}")
                        
                        # Ensure response is not empty
                        if not ai_response or len(ai_response.strip()) == 0:
                            ai_response = "I understand. Can you tell me more about that?"
                        
                        # Limit response length to avoid TwiML issues
                        if len(ai_response) > 500:
                            ai_response = ai_response[:500] + "..."
                        
                    except Exception as ai_error:
                        self.logger.error(f"AI processing error: {ai_error}")
                        # Use simple fallback response
                        if 'hello' in speech_result.lower():
                            ai_response = "Hello! Nice to meet you. How are you doing today?"
                        elif 'help' in speech_result.lower():
                            ai_response = "I'm here to help! What would you like to know?"
                        else:
                            ai_response = "I understand. Could you please repeat that?"
                    
                    # Create TwiML response
                    response = VoiceResponse()
                    response.say(ai_response)
                    
                    # Continue the conversation
                    gather = response.gather(
                        input='speech',
                        timeout=10,
                        speech_timeout='auto',
                        action=f'/process_speech/{call_sid}',
                        method='POST'
                    )
                    gather.say("I'm listening...")
                    
                    # If no input, redirect to process
                    response.redirect(f'/process_speech/{call_sid}')
                    
                    twiml_str = str(response)
                    self.logger.info(f"TwiML Response: {twiml_str}")
                    return Response(twiml_str, mimetype='text/xml')
                    
                except Exception as e:
                    self.logger.error(f"Error processing speech: {e}")
                    response = VoiceResponse()
                    response.say("I'm sorry, I had trouble processing that. Please try again.")
                    response.redirect(f'/process_speech/{call_sid}')
                    twiml_str = str(response)
                    return Response(twiml_str, mimetype='text/xml')
            else:
                # No speech or low confidence
                response = VoiceResponse()
                response.say("I didn't catch that. Please speak clearly.")
                response.redirect(f'/process_speech/{call_sid}')
                return Response(str(response), mimetype='text/xml')
        
        @app.route('/media/<call_sid>', methods=['POST'])
        def handle_media_stream(call_sid):
            """Handle incoming media stream from Twilio."""
            if call_sid not in self.active_calls:
                return Response("Call not found", status=404)
            
            # Get audio data from request
            audio_data = request.get_data()
            if audio_data:
                # Process audio through VOCA orchestrator
                self.process_audio_stream(call_sid, audio_data)
            
            return Response("OK", mimetype='text/plain')
        
        @app.route('/call/status', methods=['POST'])
        def handle_call_status():
            """Handle call status updates from Twilio."""
            call_sid = request.form.get('CallSid')
            call_status = request.form.get('CallStatus')
            
            if call_sid in self.active_calls:
                self.active_calls[call_sid]['status'] = call_status
                self.logger.info(f"Call {call_sid} status: {call_status}")
                
                if call_status in ['completed', 'failed', 'busy', 'no-answer']:
                    # Clean up call
                    self.cleanup_call(call_sid)
            
            return Response("OK", mimetype='text/plain')
        
        @app.route('/outbound', methods=['POST'])
        def handle_outbound_call():
            """Handle outbound call TwiML."""
            call_sid = request.form.get('CallSid')
            
            # Store call information
            self.active_calls[call_sid] = {
                'to_number': 'outbound',
                'status': 'ringing',
                'start_time': time.time(),
                'audio_buffer': []
            }
            
            response = VoiceResponse()
            response.say("Hello! This is VOCA calling. How can I help you today?")
            
            # Gather user input
            gather = response.gather(
                input='speech',
                timeout=10,
                speech_timeout='auto',
                action=f'/process_speech/{call_sid}',
                method='POST'
            )
            gather.say("I'm listening...")
            
            # If no input, redirect to process
            response.redirect(f'/process_speech/{call_sid}')
            
            return Response(str(response), mimetype='text/xml')
        
        # Start server in a separate thread
        def run_server():
            app.run(host=host, port=port, debug=False, threaded=True)
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        self.logger.info(f"Twilio webhook server started on {host}:{port}")
        
        return app
    
    def make_outbound_call(self, to_number: str, message: str = None) -> str:
        """Make an outbound call using Twilio."""
        try:
            config = get_twilio_config()
            call = self.client.calls.create(
                to=to_number,
                from_=config.phone_number,
                url=f"{config.get_webhook_url().replace('/webhook/voice', '')}/outbound",
                method='POST'
            )
            
            call_sid = call.sid
            self.active_calls[call_sid] = {
                'to_number': to_number,
                'status': 'initiated',
                'start_time': time.time()
            }
            
            self.logger.info(f"Outbound call initiated to {to_number}, SID: {call_sid}")
            return call_sid
            
        except Exception as e:
            self.logger.error(f"Failed to make outbound call: {e}")
            return None
    
    def hangup_call(self, call_sid: str) -> bool:
        """Hang up an active call."""
        try:
            if call_sid in self.active_calls:
                call = self.client.calls(call_sid).update(status='completed')
                del self.active_calls[call_sid]
                self.logger.info(f"Call {call_sid} hung up")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to hang up call {call_sid}: {e}")
            return False
    
    def get_active_calls(self) -> Dict[str, Dict[str, Any]]:
        """Get information about active calls."""
        return self.active_calls.copy()
    
    def process_audio_stream(self, call_sid: str, audio_data: bytes):
        """Process incoming audio stream from Twilio."""
        if call_sid not in self.active_calls:
            return
        
        # Store audio data in buffer
        if call_sid not in self.audio_buffers:
            self.audio_buffers[call_sid] = []
        
        self.audio_buffers[call_sid].append(audio_data)
        
        # Convert audio data to numpy array (assuming 16-bit PCM, 8kHz)
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Process through VOCA orchestrator
            self.orchestrator.handle_audio_chunk(audio_array)
            
        except Exception as e:
            self.logger.error(f"Error processing audio for call {call_sid}: {e}")
    
    def cleanup_call(self, call_sid: str):
        """Clean up resources for a call."""
        if call_sid in self.active_calls:
            del self.active_calls[call_sid]
        
        if call_sid in self.audio_buffers:
            del self.audio_buffers[call_sid]
        
        if call_sid in self.websocket_connections:
            try:
                self.websocket_connections[call_sid].close()
            except:
                pass
            del self.websocket_connections[call_sid]
        
        self.logger.info(f"Cleaned up resources for call {call_sid}")


class TwilioCallManager:
    """Manages Twilio calls and integrates with VOCA orchestrator for real-time voice AI."""
    
    def __init__(self, orchestrator: VocaOrchestrator):
        self.orchestrator = orchestrator
        self.voice_handler = TwilioVoiceHandler(orchestrator)
        self.logger = logging.getLogger(__name__)
        self._server_thread = None
    
    def start(self, host='0.0.0.0', port=5000):
        """Start the Twilio call manager with real-time AI processing."""
        self.logger.info("Starting Twilio Call Manager with VOCA AI...")
        
        # Ensure models are loaded
        try:
            self.orchestrator.ensure_models_loaded()
            self.logger.info("VOCA models loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load VOCA models: {e}")
            raise
        
        # Start webhook server
        self.voice_handler.start_webhook_server(host, port)
        
        self.logger.info("Twilio Call Manager started successfully")
        self.logger.info(f"Webhook URL: http://{host}:{port}/webhook/voice")
        self.logger.info("Ready to receive calls with real-time AI processing!")
    
    def make_call(self, phone_number: str, message: str = None) -> Optional[str]:
        """Make an outbound call with AI assistant."""
        self.logger.info(f"Making outbound call to {phone_number}")
        return self.voice_handler.make_outbound_call(phone_number, message)
    
    def hangup_all_calls(self):
        """Hang up all active calls."""
        for call_sid in list(self.voice_handler.active_calls.keys()):
            self.voice_handler.hangup_call(call_sid)
        self.logger.info("All calls hung up")
    
    def get_call_status(self) -> Dict[str, Any]:
        """Get status of all calls."""
        return {
            'active_calls': len(self.voice_handler.active_calls),
            'calls': self.voice_handler.get_active_calls(),
            'models_ready': self.orchestrator.models_ready()
        }
    
    def stop(self):
        """Stop the call manager and clean up resources."""
        self.hangup_all_calls()
        self.logger.info("Twilio Call Manager stopped")
