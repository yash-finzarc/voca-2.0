"""
Deepgram integration for Twilio Media Streams.
Replaces Twilio's STT and TTS with Deepgram's services.
"""
import asyncio
import json
import logging
import time
import base64
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
import uvicorn
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Start, Stream
import numpy as np
import queue

from .twilio_config import get_twilio_config
from .orchestrator import VocaOrchestrator
from .stt import DeepgramSTT
from .tts import DeepgramTTS
from .config import Config


class DeepgramTwilioHandler:
    """Handles Twilio voice calls using Deepgram for STT and TTS via Media Streams."""
    
    def __init__(self, orchestrator: VocaOrchestrator):
        self.orchestrator = orchestrator
        config = get_twilio_config()
        self.client = Client(config.account_sid, config.auth_token)
        self.active_calls: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
        self.deepgram_stt: Optional[DeepgramSTT] = None
        self.deepgram_tts: Optional[DeepgramTTS] = None
        self._initialize_deepgram()
        
    def _initialize_deepgram(self):
        """Initialize Deepgram STT and TTS clients."""
        try:
            if not Config.deepgram_api_key:
                self.logger.warning("Deepgram API key not configured. Set DEEPGRAM_API_KEY environment variable.")
                return
            
            self.logger.info("Initializing Deepgram STT...")
            self.deepgram_stt = DeepgramSTT()
            self.deepgram_stt.load()
            if self.deepgram_stt.keyterms:
                self.logger.info(f"   ✓ Deepgram STT loaded with {len(self.deepgram_stt.keyterms)} keyterms")
            else:
                self.logger.info("   ✓ Deepgram STT loaded (no keyterms)")
            
            self.logger.info("Initializing Deepgram TTS...")
            self.deepgram_tts = DeepgramTTS()
            self.deepgram_tts.load()
            self.logger.info("   ✓ Deepgram TTS loaded")
            
            self.logger.info("✅ Deepgram STT and TTS initialized successfully")
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Deepgram: {e}")
            raise
    
    def start_webhook_server(self, host='0.0.0.0', port=5000):
        """Start FastAPI server to handle Twilio webhooks with Deepgram Media Streams."""
        app = FastAPI(title="VOCA Twilio Webhook Server with Deepgram")
        
        handler = self
        
        @app.post('/webhook/voice')
        async def handle_incoming_call(request: Request):
            """Handle incoming Twilio voice calls with Media Streams."""
            form_data = await request.form()
            call_sid = form_data.get('CallSid')
            from_number = form_data.get('From')
            
            handler.logger.info(f"Incoming call from {from_number}, SID: {call_sid}")
            
            # Store call information
            handler.active_calls[call_sid] = {
                'from_number': from_number,
                'status': 'ringing',
                'start_time': time.time(),
                'transcription_buffer': '',
                'last_transcript_time': time.time(),
                'audio_queue': queue.Queue(),
                'response_queue': queue.Queue(),
            }
            
            # Create TwiML response with Media Streams
            response = VoiceResponse()
            
            # Generate welcome message
            try:
                org_id = form_data.get('organization_id') or handler.orchestrator.default_organization_id
                greeting = handler.orchestrator.generate_greeting(
                    conversation_id=call_sid,
                    organization_id=org_id
                )
                handler.logger.info(f"Generated greeting for call {call_sid}: {greeting}")
            except Exception as e:
                handler.logger.error(f"Error generating greeting: {e}")
                greeting = "Hello! How can I help you today?"
            
            # Use Deepgram TTS to generate greeting audio
            # For now, we'll use Say for the greeting, then switch to Media Streams
            # In production, you'd want to pre-generate the greeting audio
            response.say(greeting)
            
            # Get webhook URL for WebSocket
            config = get_twilio_config()
            webhook_base = config.get_webhook_url().replace('/webhook/voice', '')
            # Convert http/https to wss for WebSocket
            if webhook_base.startswith('http://'):
                ws_url = webhook_base.replace('http://', 'wss://')
            elif webhook_base.startswith('https://'):
                ws_url = webhook_base.replace('https://', 'wss://')
            else:
                # Fallback - use host/port (requires proper SSL setup)
                ws_url = f"wss://{host}:{port}" if port != 443 else f"wss://{host}"
            
            # Start Media Stream to WebSocket endpoint
            stream = Stream(url=f'{ws_url}/media/{call_sid}')
            start = Start()
            start.stream(stream)
            response.append(start)
            
            return Response(content=str(response), media_type='text/xml')
        
        @app.websocket('/media/{call_sid}')
        async def handle_media_stream(websocket: WebSocket, call_sid: str):
            """Handle WebSocket connection for Twilio Media Streams with Deepgram."""
            await websocket.accept()
            
            if call_sid not in handler.active_calls:
                handler.logger.error(f"Call {call_sid} not found in active calls")
                await websocket.close()
                return
            
            handler.logger.info(f"Media stream connected for call {call_sid}")
            
            call_info = handler.active_calls[call_sid]
            call_info['websocket'] = websocket
            call_info['status'] = 'connected'
            
            # Initialize Deepgram live connection for this call
            deepgram_connection = None
            transcript_queue = asyncio.Queue()
            
            def on_transcript(text: str):
                """Callback for Deepgram transcriptions."""
                if text:
                    asyncio.create_task(transcript_queue.put(text))
            
            try:
                if handler.deepgram_stt:
                    deepgram_connection = handler.deepgram_stt.create_live_connection(
                        on_transcript=on_transcript
                    )
                    call_info['deepgram_connection'] = deepgram_connection
                    call_info['transcript_queue'] = transcript_queue
            except Exception as e:
                handler.logger.error(f"Failed to create Deepgram connection: {e}")
            
            try:
                # Send initial message to Twilio
                await websocket.send_json({
                    "event": "connected",
                    "protocol": "Call",
                    "version": "1.0.0"
                })
                
                # Start background tasks
                response_task = asyncio.create_task(
                    handler._process_responses(call_sid, websocket)
                )
                transcript_task = asyncio.create_task(
                    handler._process_transcripts(call_sid, transcript_queue)
                )
                
                # Store streamSid when received
                stream_sid = None
                
                # Listen for messages from Twilio
                while True:
                    try:
                        message = await websocket.receive_text()
                        data = json.loads(message)
                        
                        event_type = data.get('event')
                        
                        if event_type == 'start':
                            stream_sid = data.get('streamSid')
                            call_info['stream_sid'] = stream_sid
                            handler.logger.info(f"Media stream started for call {call_sid}, streamSid: {stream_sid}")
                            await websocket.send_json({
                                "event": "start",
                                "streamSid": stream_sid,
                                "start": {
                                    "accountSid": data.get('accountSid'),
                                    "callSid": call_sid
                                }
                            })
                        
                        elif event_type == 'media':
                            # Receive audio from Twilio
                            payload = data.get('media', {}).get('payload')
                            if payload:
                                # Decode base64 audio (Twilio sends μ-law encoded audio)
                                audio_bytes = base64.b64decode(payload)
                                
                                # Convert μ-law to linear16 PCM
                                audio_array = handler._mulaw_to_linear16(audio_bytes)
                                
                                # Send to Deepgram for transcription
                                if deepgram_connection:
                                    handler.deepgram_stt.send_audio_chunk(deepgram_connection, audio_array)
                        
                        elif event_type == 'stop':
                            handler.logger.info(f"Media stream stopped for call {call_sid}")
                            break
                            
                    except WebSocketDisconnect:
                        handler.logger.info(f"WebSocket disconnected for call {call_sid}")
                        break
                    except Exception as e:
                        handler.logger.error(f"Error processing media stream message: {e}")
                        break
                
                # Cancel background tasks
                response_task.cancel()
                transcript_task.cancel()
                
            except Exception as e:
                handler.logger.error(f"Error in media stream handler: {e}")
            finally:
                # Clean up Deepgram connection
                if deepgram_connection:
                    try:
                        deepgram_connection.finish()
                    except:
                        pass
                
                # Clean up call
                handler.cleanup_call(call_sid)
        
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
                    handler.cleanup_call(call_sid)
            
            return PlainTextResponse("OK")
        
        # Start server in a separate thread
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        
        def run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(server.serve())
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        self.logger.info(f"Twilio webhook server with Deepgram started on {host}:{port}")
        
        return app
    
    async def _process_transcripts(self, call_sid: str, transcript_queue: asyncio.Queue):
        """Process transcripts from Deepgram queue."""
        last_processed_text = None  # Track last processed text to avoid duplicates
        
        while True:
            try:
                # Wait for transcript (reduced timeout for faster response)
                try:
                    text = await asyncio.wait_for(transcript_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                
                if not text or call_sid not in self.active_calls:
                    continue
                
                # Skip if this is the same text we just processed (avoid duplicate processing)
                if text.strip() == last_processed_text:
                    continue
                
                call_info = self.active_calls[call_sid]
                
                # Update transcription buffer
                call_info['transcription_buffer'] = text
                call_info['last_transcript_time'] = time.time()
                
                self.logger.info(f"[USER] Call {call_sid} - Deepgram Transcript: \"{text}\"")
                
                # Process through orchestrator (run in executor to avoid blocking)
                try:
                    loop = asyncio.get_event_loop()
                    # Use functools.partial to pass keyword arguments
                    from functools import partial
                    ai_response = await loop.run_in_executor(
                        None,
                        partial(
                            self.orchestrator.generate_reply,
                            text,
                            conversation_id=call_sid,
                            call_sid=call_sid,
                        )
                    )
                    
                    last_processed_text = text.strip()  # Update last processed
                    
                    self.logger.info(f"[AI] Call {call_sid} - AI Response: \"{ai_response}\"")
                    
                    # Add response to queue for TTS processing
                    call_info['response_queue'].put(ai_response)
                    
                except Exception as e:
                    self.logger.error(f"Error processing transcript: {e}")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in transcript processor: {e}")
                # Reduced sleep time for faster error recovery
                await asyncio.sleep(0.01)
    
    async def _process_responses(self, call_sid: str, websocket: WebSocket):
        """Process AI responses and send audio back via Media Streams."""
        if call_sid not in self.active_calls:
            return
        
        call_info = self.active_calls[call_sid]
        
        while True:
            try:
                # Wait for response (reduced timeout for faster processing)
                try:
                    response_text = call_info['response_queue'].get(timeout=0.1)
                except queue.Empty:
                    # Reduced sleep time for faster polling
                    await asyncio.sleep(0.01)
                    continue
                
                if not response_text:
                    continue
                
                # Generate audio using Deepgram TTS (run in executor to avoid blocking)
                if self.deepgram_tts:
                    # Run TTS in thread pool to avoid blocking the event loop
                    loop = asyncio.get_event_loop()
                    audio_data = await loop.run_in_executor(
                        None,
                        self.deepgram_tts.speak,
                        response_text
                    )
                    
                    if audio_data:
                        # Convert to base64 for Twilio Media Streams
                        # Twilio expects μ-law encoded audio at 8kHz
                        audio_array = np.frombuffer(audio_data, dtype=np.int16)
                        mulaw_audio = self._linear16_to_mulaw(audio_array)
                        audio_b64 = base64.b64encode(mulaw_audio).decode('utf-8')
                        
                        # Send audio to Twilio
                        await websocket.send_json({
                            "event": "media",
                            "streamSid": call_info.get('stream_sid', ''),
                            "media": {
                                "payload": audio_b64
                            }
                        })
                        
                        self.logger.info(f"Sent TTS audio for call {call_sid}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing response: {e}")
                # Reduced sleep time for faster error recovery
                await asyncio.sleep(0.01)
    
    def _mulaw_to_linear16(self, mulaw_bytes: bytes) -> np.ndarray:
        """Convert μ-law encoded audio to linear16 PCM."""
        # μ-law to linear conversion
        mulaw_array = np.frombuffer(mulaw_bytes, dtype=np.uint8)
        sign = (mulaw_array & 0x80) >> 7
        exponent = (mulaw_array & 0x70) >> 4
        mantissa = mulaw_array & 0x0F
        
        linear = np.zeros_like(mulaw_array, dtype=np.int16)
        linear = (sign * -1) * ((mantissa << (exponent + 3)) + 0x84 << exponent)
        return linear.astype(np.int16)
    
    def _linear16_to_mulaw(self, linear_array: np.ndarray) -> bytes:
        """Convert linear16 PCM to μ-law encoded audio."""
        # Linear to μ-law conversion
        sign = (linear_array < 0).astype(np.uint8)
        linear_abs = np.abs(linear_array).astype(np.int32)
        
        # Clamp to valid range
        linear_abs = np.clip(linear_abs, 0, 32635)
        
        # Find exponent
        exponent = np.zeros_like(linear_abs, dtype=np.uint8)
        for i in range(8):
            mask = linear_abs >= (0x1F << (i + 2))
            exponent[mask] = i
        
        # Calculate mantissa
        mantissa = (linear_abs >> (exponent + 3)) & 0x0F
        
        # Combine into μ-law
        mulaw = (sign << 7) | (exponent << 4) | mantissa
        mulaw ^= 0xFF  # Invert all bits
        
        return mulaw.astype(np.uint8).tobytes()
    
    def cleanup_call(self, call_sid: str):
        """Clean up resources for a call."""
        if call_sid in self.active_calls:
            call_info = self.active_calls[call_sid]
            
            # Close Deepgram connection if exists
            if 'deepgram_connection' in call_info:
                try:
                    call_info['deepgram_connection'].finish()
                except:
                    pass
            
            del self.active_calls[call_sid]
            self.logger.info(f"Cleaned up resources for call {call_sid}")
    
    def make_outbound_call(self, to_number: str, message: str = None) -> str:
        """Make an outbound call using Twilio."""
        try:
            config = get_twilio_config()
            call = self.client.calls.create(
                to=to_number,
                from_=config.phone_number,
                url=f"{config.get_webhook_url().replace('/webhook/voice', '')}/webhook/voice",
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


class DeepgramCallManager:
    """Manages Twilio calls using Deepgram for STT and TTS via Media Streams."""
    
    def __init__(self, orchestrator: VocaOrchestrator):
        self.orchestrator = orchestrator
        self.voice_handler = DeepgramTwilioHandler(orchestrator)
        self.logger = logging.getLogger(__name__)
        self._server_thread = None
    
    def start(self, host='0.0.0.0', port=5000):
        """Start the Deepgram call manager with real-time AI processing."""
        self.logger.info("=" * 80)
        self.logger.info("🔵 Starting Deepgram Call Manager with VOCA AI...")
        self.logger.info("=" * 80)
        
        # Ensure models are loaded
        try:
            self.orchestrator.ensure_models_loaded()
            self.logger.info("✓ VOCA models loaded successfully")
        except Exception as e:
            self.logger.error(f"❌ Failed to load VOCA models: {e}")
            raise
        
        # Start webhook server
        self.voice_handler.start_webhook_server(host, port)
        
        self.logger.info("=" * 80)
        self.logger.info("✅ Deepgram Call Manager started successfully")
        self.logger.info(f"   Webhook URL: http://{host}:{port}/webhook/voice")
        self.logger.info("   STT: Deepgram Nova-2")
        self.logger.info("   TTS: Deepgram Aura")
        self.logger.info("   Ready to receive calls with Deepgram STT/TTS!")
        self.logger.info("=" * 80)
    
    def make_call(self, phone_number: str, message: str = None) -> Optional[str]:
        """Make an outbound call with AI assistant."""
        self.logger.info(f"Making outbound call to {phone_number}")
        return self.voice_handler.make_outbound_call(phone_number, message)
    
    def hangup_all_calls(self):
        """Hang up all active calls."""
        for call_sid in list(self.voice_handler.active_calls.keys()):
            try:
                call = self.voice_handler.client.calls(call_sid).update(status='completed')
                del self.voice_handler.active_calls[call_sid]
            except:
                pass
        self.logger.info("All calls hung up")
    
    def get_call_status(self) -> Dict[str, Any]:
        """Get status of all calls."""
        return {
            'active_calls': len(self.voice_handler.active_calls),
            'calls': self.voice_handler.active_calls.copy(),
            'models_ready': self.orchestrator.models_ready()
        }
    
    def fetch_call_history(
        self,
        limit: int = 50,
        start_time_after: Optional[datetime] = None,
        start_time_before: Optional[datetime] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch recent call records from Twilio and bucket them by status."""
        from datetime import datetime, timezone
        
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
        for call_sid, call_info in self.voice_handler.active_calls.items():
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
        self.logger.info("Deepgram Call Manager stopped")

