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
from datetime import datetime, timezone
from typing import Optional, Callable, Dict, Any, List
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import PlainTextResponse
import uvicorn
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
        """Start FastAPI server to handle Twilio webhooks with real-time audio streaming."""
        app = FastAPI(title="VOCA Twilio Webhook Server")
        
        # Store reference to self for route handlers
        handler = self
        
        @app.post('/webhook/voice')
        async def handle_incoming_call(request: Request):
            """Handle incoming Twilio voice calls."""
            form_data = await request.form()
            call_sid = form_data.get('CallSid')
            from_number = form_data.get('From')
            
            handler.logger.info(f"Incoming call from {from_number}, SID: {call_sid}")
            
            # Store call information
            handler.active_calls[call_sid] = {
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
            
            return Response(content=str(response), media_type='text/xml')
        
        @app.post('/process_speech/{call_sid}')
        async def handle_speech(call_sid: str, request: Request):
            """Handle speech input from user."""
            if call_sid not in handler.active_calls:
                raise HTTPException(status_code=404, detail="Call not found")
            
            form_data = await request.form()
            speech_result = form_data.get('SpeechResult', '')
            confidence = form_data.get('Confidence', '0')
            
            handler.logger.info(f"Speech received for call {call_sid}: {speech_result} (confidence: {confidence})")
            
            if speech_result and float(confidence) > 0.5:
                # Process speech through VOCA orchestrator
                try:
                    # Generate AI response with error handling
                    try:
                        ai_response = handler.orchestrator.generate_reply(speech_result)
                        handler.logger.info(f"AI Response: {ai_response}")
                        
                        # Ensure response is not empty
                        if not ai_response or len(ai_response.strip()) == 0:
                            ai_response = "I understand. Can you tell me more about that?"
                        
                        # Limit response length to avoid TwiML issues
                        if len(ai_response) > 500:
                            ai_response = ai_response[:500] + "..."
                        
                    except Exception as ai_error:
                        handler.logger.error(f"AI processing error: {ai_error}")
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
                    handler.logger.info(f"TwiML Response: {twiml_str}")
                    return Response(content=twiml_str, media_type='text/xml')
                    
                except Exception as e:
                    handler.logger.error(f"Error processing speech: {e}")
                    response = VoiceResponse()
                    response.say("I'm sorry, I had trouble processing that. Please try again.")
                    response.redirect(f'/process_speech/{call_sid}')
                    twiml_str = str(response)
                    return Response(content=twiml_str, media_type='text/xml')
            else:
                # No speech or low confidence
                response = VoiceResponse()
                response.say("I didn't catch that. Please speak clearly.")
                response.redirect(f'/process_speech/{call_sid}')
                return Response(content=str(response), media_type='text/xml')
        
        @app.post('/media/{call_sid}')
        async def handle_media_stream(call_sid: str, request: Request):
            """Handle incoming media stream from Twilio."""
            if call_sid not in handler.active_calls:
                raise HTTPException(status_code=404, detail="Call not found")
            
            # Get audio data from request body
            audio_data = await request.body()
            if audio_data:
                # Process audio through VOCA orchestrator
                handler.process_audio_stream(call_sid, audio_data)
            
            return PlainTextResponse("OK")
        
        @app.post('/call/status')
        async def handle_call_status(request: Request):
            """Handle call status updates from Twilio."""
            form_data = await request.form()
            call_sid = form_data.get('CallSid')
            call_status = form_data.get('CallStatus')
            
            if call_sid in handler.active_calls:
                handler.active_calls[call_sid]['status'] = call_status
                handler.logger.info(f"Call {call_sid} status: {call_status}")
                
                if call_status in ['completed', 'failed', 'busy', 'no-answer']:
                    # Clean up call
                    handler.cleanup_call(call_sid)
            
            return PlainTextResponse("OK")
        
        @app.post('/outbound')
        async def handle_outbound_call(request: Request):
            """Handle outbound call TwiML."""
            form_data = await request.form()
            call_sid = form_data.get('CallSid')
            
            # Store call information
            handler.active_calls[call_sid] = {
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
            
            return Response(content=str(response), media_type='text/xml')
        
        # Start server in a separate thread using uvicorn
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        
        def run_server():
            import asyncio
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(server.serve())
        
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
    
    def fetch_call_history(
        self,
        limit: int = 50,
        start_time_after: Optional[datetime] = None,
        start_time_before: Optional[datetime] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch recent call records from Twilio and bucket them by status."""
        client = self.voice_handler.client

        def _to_iso(dt: Optional[datetime]) -> Optional[str]:
            if not dt:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()

        def _format_duration(duration_seconds: Optional[int]) -> Optional[str]:
            if duration_seconds is None:
                return None
            hours, remainder = divmod(duration_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:02}:{minutes:02}:{seconds:02}"

        declined_statuses = {"busy", "failed", "no-answer", "canceled"}
        ongoing_statuses = {"queued", "ringing", "in-progress"}
        completed_statuses = {"completed"}

        summary: Dict[str, List[Dict[str, Any]]] = {
            "ongoing": [],
            "declined": [],
            "completed": [],
            "others": [],
        }

        seen: Dict[str, Dict[str, Any]] = {}

        def _upsert_call(call_obj):
            if call_obj.sid in seen:
                return
            duration_seconds: Optional[int] = None
            if call_obj.duration is not None:
                try:
                    duration_seconds = int(call_obj.duration)
                except (TypeError, ValueError):
                    duration_seconds = None

            record = {
                "call_sid": call_obj.sid,
                "status": call_obj.status,
                "from_number": getattr(call_obj, "from_", None),
                "to_number": getattr(call_obj, "to", None),
                "direction": getattr(call_obj, "direction", None),
                "start_time": _to_iso(getattr(call_obj, "start_time", None)),
                "end_time": _to_iso(getattr(call_obj, "end_time", None)),
                "duration_seconds": duration_seconds,
                "duration_human": _format_duration(duration_seconds) if duration_seconds is not None else None,
            }
            seen[call_obj.sid] = record

        # Fetch specific status buckets first for accuracy with in-progress calls.
        status_fetch_plan = [
            ("ongoing", list(ongoing_statuses)),
            ("declined", list(declined_statuses)),
            ("completed", list(completed_statuses)),
        ]

        for _, status_list in status_fetch_plan:
            for status in status_list:
                try:
                    calls_by_status = client.calls.list(
                        status=status,
                        limit=limit,
                        start_time_after=start_time_after,
                        start_time_before=start_time_before,
                    )
                except Exception:
                    continue
                for call_obj in calls_by_status:
                    _upsert_call(call_obj)

        # Fallback: fetch recent calls without status filter to pick up any remaining records.
        try:
            fallback_calls = client.calls.list(
                limit=limit,
                start_time_after=start_time_after,
                start_time_before=start_time_before,
            )
            for call_obj in fallback_calls:
                _upsert_call(call_obj)
        except Exception:
            pass

        for record in seen.values():
            status_value = record["status"]
            if status_value in ongoing_statuses:
                summary["ongoing"].append(record)
            elif status_value in declined_statuses:
                summary["declined"].append(record)
            elif status_value in completed_statuses:
                summary["completed"].append(record)
            else:
                summary["others"].append(record)

        # Merge locally tracked active calls to surface immediate state changes before Twilio propagates them.
        timestamp_now = datetime.now(timezone.utc).isoformat()
        for call_sid, call_info in self.voice_handler.get_active_calls().items():
            if call_sid in seen:
                continue
            status = call_info.get("status", "initiated")
            start_ts = call_info.get("start_time")
            if isinstance(start_ts, (int, float)):
                start_iso = datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat()
            else:
                start_iso = _to_iso(start_ts) if isinstance(start_ts, datetime) else None
            local_record = {
                "call_sid": call_sid,
                "status": status,
                "from_number": call_info.get("from_number"),
                "to_number": call_info.get("to_number"),
                "direction": call_info.get("direction", "outbound-api"),
                "start_time": start_iso or timestamp_now,
                "end_time": None,
                "duration_seconds": int(time.time() - start_ts) if isinstance(start_ts, (int, float)) else None,
                "duration_human": None,
            }
            if status in ongoing_statuses or status == "initiated":
                summary["ongoing"].append(local_record)
            elif status in declined_statuses:
                summary["declined"].append(local_record)
            elif status in completed_statuses:
                summary["completed"].append(local_record)
            else:
                summary["others"].append(local_record)

        return summary
    
    def stop(self):
        """Stop the call manager and clean up resources."""
        self.hangup_all_calls()
        self.logger.info("Twilio Call Manager stopped")
