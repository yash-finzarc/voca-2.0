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
import os
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from fastapi import FastAPI, Request, Response, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, FileResponse, JSONResponse
import uvicorn
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Start, Stream, Transcription
from twilio.twiml.messaging_response import MessagingResponse
import threading
import queue
import numpy as np
import websocket
import ssl
from urllib.parse import urlencode
import requests

from .twilio_config import get_twilio_config
from src.voca.orchestrator import VocaOrchestrator
from src.voca.config import Config

# Deepgram SDK changed the public API across versions; older releases do not
# expose SpeakOptions at the package root. Fall back gracefully so the server
# can start even if an older SDK is installed.
try:
    from deepgram import DeepgramClient, SpeakOptions  # SDK >=3.0
except ImportError:  # Older SDKs
    from deepgram import DeepgramClient  # type: ignore
    SpeakOptions = None  # type: ignore


def deepgramtts(text: str, filename: Optional[str] = None, model: str = "aura-2-odysseus-en") -> bytes:
    """
    Convert text to speech using Deepgram TTS.
    
    Args:
        text: Text to convert to speech
        filename: Optional filename to save audio file. If None, uses temporary file.
        model: Deepgram TTS model (default: "aura-2-odysseus-en")
    
    Returns:
        bytes: Audio data as bytes (MP3 format)
    """
    import tempfile
    
    try:
        # Deepgram SDK v3+ requires keyword arg; older versions also accept it
        deepgram = DeepgramClient(api_key=Config.deepgram_api_key)
        
        # Construct speak options; tolerate older SDKs that lack SpeakOptions
        if SpeakOptions:
            options = SpeakOptions(model=model)
        else:
            options = {"model": model}
        
        text_data = {
            "text": text
        }
        
        # Use temporary file if filename not provided
        if not filename:
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
            filename = tmp_file.name
            tmp_file.close()
        
        # Save audio to file; try SDK first, then REST fallback for compatibility
        try:
            deepgram.speak.v("1").save(
                filename,
                text_data,
                options,
            )
        except Exception:
            api_url = f"https://api.deepgram.com/v1/speak?model={model}"
            headers = {
                "Authorization": f"Token {Config.deepgram_api_key}",
                "Content-Type": "application/json",
            }
            resp = requests.post(api_url, headers=headers, json=text_data, timeout=30)
            resp.raise_for_status()
            with open(filename, "wb") as f:
                f.write(resp.content)
        
        # Read and return audio bytes
        with open(filename, 'rb') as f:
            audio_bytes = f.read()
        
        # Clean up temporary file if we created it
        if filename.startswith(tempfile.gettempdir()):
            try:
                os.unlink(filename)
            except:
                pass
        
        return audio_bytes
            
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error in deepgramtts: {e}", exc_info=True)
        raise


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
        
        # Audio storage for testing/debugging
        self.audio_storage_dir = Path(Config.audio_storage_dir)
        self.audio_storage_dir.mkdir(parents=True, exist_ok=True)
        self.audio_writers: Dict[str, wave.Wave_write] = {}  # call_sid -> wave writer
        self.audio_chunk_counts: Dict[str, int] = {}  # Track chunk count per call
        
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
                'audio_buffer': [],
                'unclear_count': 0,  # Track consecutive unclear responses
                'last_speech_attempt': None,  # Track last speech attempt to detect name collection
                'name_attempt_count': 0  # Track attempts to provide name
            }
            
            # Create TwiML response
            response = VoiceResponse()
            
            # Generate welcome message from system prompt
            try:
                # Get organization_id from call metadata if available
                org_id = form_data.get('organization_id') or handler.orchestrator.default_organization_id
                greeting = handler.orchestrator.generate_greeting(
                    conversation_id=call_sid,
                    organization_id=org_id
                )
                handler.logger.info(f"Generated greeting for call {call_sid}: {greeting}")
            except Exception as e:
                handler.logger.error(f"Error generating greeting: {e}")
                greeting = "Hello! How can I help you today?"
            
            # Enable Real-Time Transcriptions with Deepgram Nova-3 for Hindi
            # This provides real-time transcriptions via callbacks (no Deepgram API key needed)
            config = get_twilio_config()
            webhook_url = config.get_webhook_url()
            base_url = webhook_url.replace('/webhook/voice', '')
            
            # Set up Real-Time Transcription with Deepgram Nova-3 for Hindi
            # This provides real-time transcriptions via callbacks (no Deepgram API key needed)
            transcription_callback_url = f'{base_url}/transcription/{call_sid}'
            start = Start()
            transcription = Transcription(
                statusCallbackUrl=transcription_callback_url,
                transcription_engine='deepgram',
                speech_model='nova-3',  # Use nova-3 for best accuracy
                languageCode='en-IN'   # English (India) language
            )
            start.append(transcription)
            response.append(start)
            handler.logger.info(f"[TRANSCRIPTION] Enabled Real-Time Transcription for call {call_sid}")
            handler.logger.info(f"[TRANSCRIPTION] Callback URL: {transcription_callback_url}")
            
            # Enable Media Streams for audio storage/debugging (if enabled)
            # This streams raw audio to /media/{call_sid} WebSocket endpoint for storage
            if Config.audio_storage_enabled:
                # Twilio Media Streams require WebSocket (wss://) not HTTP
                # Convert http:// to wss:// or https:// to wss://
                if base_url.startswith('http://'):
                    wss_base_url = base_url.replace('http://', 'wss://')
                elif base_url.startswith('https://'):
                    wss_base_url = base_url.replace('https://', 'wss://')
                elif not base_url.startswith('wss://'):
                    wss_base_url = f"wss://{base_url.lstrip('/')}"
                else:
                    wss_base_url = base_url
                
                stream_url = f"{wss_base_url}/media/{call_sid}"
                stream = Stream(url=stream_url, parameters={'call_sid': call_sid})
                start.stream(stream)
                handler.logger.info(f"[AUDIO_DEBUG] Enabled Media Stream for call {call_sid}")
                handler.logger.info(f"[AUDIO_DEBUG] Stream URL: {stream_url}")
            
            # Say welcome message
            response.say(greeting)
            
            # No need for Gather - Real-Time Transcriptions will handle speech recognition
            # Transcriptions will be sent to /transcription/{call_sid} callback
            # The callback will process transcriptions and generate AI responses
            
            return Response(content=str(response), media_type='text/xml')
        
        @app.post('/process_speech/{call_sid}')
        async def handle_speech(call_sid: str, request: Request):
            """Handle speech input from user."""
            if call_sid not in handler.active_calls:
                raise HTTPException(status_code=404, detail="Call not found")
            
            form_data = await request.form()
            speech_result = form_data.get('SpeechResult', '')
            confidence = form_data.get('Confidence', '0')
            language = form_data.get('Language', 'N/A')
            
            handler.logger.info(f"Speech received for call {call_sid}: {speech_result} (confidence: {confidence}, language: {language})")
            
            # Get session to check if we're collecting a name
            session = handler.orchestrator._get_session(call_sid, None)
            
            # Detect if user is providing their name
            # Check if speech contains name-related phrases or looks like a name (2-3 words)
            speech_lower = speech_result.lower() if speech_result else ''
            looks_like_name = False
            if speech_result:
                words = speech_result.strip().split()
                # If it's 2-3 words and doesn't contain common question words, might be a name
                if 2 <= len(words) <= 3:
                    question_words = {'what', 'who', 'where', 'when', 'why', 'how', 'is', 'are', 'can', 'could', 'would', 'should'}
                    if not any(qw in speech_lower for qw in question_words):
                        looks_like_name = True
            
            is_collecting_name = (
                'name' in speech_lower or 
                'my name is' in speech_lower or 
                "i'm" in speech_lower or
                "i am" in speech_lower or
                looks_like_name
            ) or (
                session.collected_data.get('name') is not None and 
                (not session.collected_data.get('name') or len(str(session.collected_data.get('name', '')).strip()) < 2)
            )
            
            if speech_result and float(confidence) > 0.5:
                # Reset unclear count on successful speech recognition
                if call_sid in handler.active_calls:
                    handler.active_calls[call_sid]['unclear_count'] = 0
                    handler.active_calls[call_sid]['last_speech_attempt'] = speech_result
                    # Track if this looks like a name attempt
                    if is_collecting_name:
                        handler.active_calls[call_sid]['name_attempt_count'] = handler.active_calls[call_sid].get('name_attempt_count', 0) + 1
                    else:
                        handler.active_calls[call_sid]['name_attempt_count'] = 0
                # Process speech through VOCA orchestrator
                try:
                    # Generate AI response with error handling
                    try:
                        ai_response = handler.orchestrator.generate_reply(
                            speech_result,
                            conversation_id=call_sid,
                            call_sid=call_sid,
                        )
                        handler.logger.info(f"AI Response: {ai_response}")
                        
                        # Check if AI is asking to repeat and we're in a name collection loop
                        ai_response_lower = ai_response.lower() if ai_response else ''
                        is_asking_to_repeat = any(phrase in ai_response_lower for phrase in [
                            "didn't catch", "didn't understand", "couldn't catch", "couldn't understand",
                            "speak clearly", "please repeat", "say that again", "didn't hear"
                        ])
                        
                        # If AI is asking to repeat and we've had multiple name attempts, ask to spell instead
                        if is_asking_to_repeat and is_collecting_name:
                            name_attempt_count = handler.active_calls.get(call_sid, {}).get('name_attempt_count', 0)
                            if name_attempt_count >= 2:
                                ai_response = "I'm having trouble understanding your name. Could you please spell it for me? First, tell me your first name letter by letter, and then your last name."
                                handler.logger.info(f"Intercepted AI response - asking to spell name after {name_attempt_count} attempts")
                        
                        # Ensure response is not empty
                        if not ai_response or len(ai_response.strip()) == 0:
                            ai_response = "I understand. Can you tell me more about that?"
                        
                        # Limit response length to avoid TwiML issues
                        if len(ai_response) > 500:
                            ai_response = ai_response[:500] + "..."
                        
                    except Exception as ai_error:
                        handler.logger.error(f"AI processing error: {ai_error}")
                        # Use graceful fallback response - never mention technical errors
                        if 'name' in speech_result.lower():
                            ai_response = "I'm sorry, I couldn't quite catch that. Could you please spell your name for me? First, tell me your first name, and then your last name."
                        elif 'hello' in speech_result.lower() or 'hi' in speech_result.lower():
                            ai_response = "Hello! How can I help you today?"
                        elif 'help' in speech_result.lower():
                            ai_response = "I'm here to help! What would you like to know?"
                        else:
                            ai_response = "I'm sorry, I couldn't quite understand what you're saying. Could you please repeat that?"
                    
                    # Create TwiML response
                    response = VoiceResponse()
                    response.say(ai_response)
                    
                    # No need for Gather - Real-Time Transcriptions continue automatically
                    # Transcriptions will be sent to /transcription/{call_sid} callback
                    
                    twiml_str = str(response)
                    handler.logger.info(f"TwiML Response: {twiml_str}")
                    return Response(content=twiml_str, media_type='text/xml')
                    
                except Exception as e:
                    handler.logger.error(f"Error processing speech: {e}")
                    response = VoiceResponse()
                    # Never mention technical errors - use graceful response
                    if 'name' in speech_result.lower() if speech_result else False:
                        response.say("I'm sorry, I couldn't quite catch that. Could you please spell your name for me? First, tell me your first name, and then your last name.")
                    else:
                        response.say("I'm sorry, I couldn't quite understand what you're saying. Could you please repeat that?")
                    # No need for Gather - Real-Time Transcriptions continue automatically
                    twiml_str = str(response)
                    return Response(content=twiml_str, media_type='text/xml')
            else:
                # No speech or low confidence
                # Track unclear responses
                if call_sid in handler.active_calls:
                    handler.active_calls[call_sid]['unclear_count'] = handler.active_calls[call_sid].get('unclear_count', 0) + 1
                    unclear_count = handler.active_calls[call_sid]['unclear_count']
                    last_speech = handler.active_calls[call_sid].get('last_speech_attempt', '')
                else:
                    unclear_count = 1
                    last_speech = ''
                
                # Get session to check if we're collecting a name
                session = handler.orchestrator._get_session(call_sid, None)
                
                # Detect if user is providing their name (same logic as above)
                last_speech_lower = last_speech.lower() if last_speech else ''
                looks_like_name = False
                if last_speech:
                    words = last_speech.strip().split()
                    if 2 <= len(words) <= 3:
                        question_words = {'what', 'who', 'where', 'when', 'why', 'how', 'is', 'are', 'can', 'could', 'would', 'should'}
                        if not any(qw in last_speech_lower for qw in question_words):
                            looks_like_name = True
                
                is_collecting_name = (
                    'name' in last_speech_lower or 
                    'my name is' in last_speech_lower or 
                    "i'm" in last_speech_lower or
                    "i am" in last_speech_lower or
                    looks_like_name
                ) or (
                    session.collected_data.get('name') is not None and 
                    (not session.collected_data.get('name') or len(str(session.collected_data.get('name', '')).strip()) < 2)
                )
                
                response = VoiceResponse()
                
                # If we're in a loop and it's about a name, ask to spell it
                if unclear_count >= 2 and is_collecting_name:
                    response.say("I'm having trouble understanding your name. Could you please spell it for me? First, tell me your first name letter by letter, and then your last name.")
                elif unclear_count >= 2:
                    # After multiple unclear attempts, be more helpful
                    response.say("I'm having trouble understanding. Could you please speak a bit slower and more clearly?")
                else:
                    response.say("I didn't catch that. Please speak clearly.")
                
                # No need for Gather or redirect - Real-Time Transcriptions continue automatically
                # Transcriptions will be sent to /transcription/{call_sid} callback
            return Response(content=str(response), media_type='text/xml')
        
        @app.websocket('/media/{call_sid}')
        async def handle_media_stream_websocket(websocket: WebSocket, call_sid: str):
            """Handle Twilio Media Streams via WebSocket."""
            from fastapi import WebSocketDisconnect
            await websocket.accept()
            handler.logger.info(f"[AUDIO_DEBUG] Media Stream WebSocket connected for call {call_sid}")
            
            try:
                while True:
                    # Receive JSON messages from Twilio Media Streams
                    data = await websocket.receive_json()
                    event = data.get('event')
                    
                    if event == 'connected':
                        handler.logger.info(f"[AUDIO_DEBUG] Media stream connected for call {call_sid}")
                    elif event == 'start':
                        handler.logger.info(f"[AUDIO_DEBUG] Media stream started for call {call_sid}")
                    elif event == 'media':
                        # Extract base64 audio payload
                        media_payload = data.get('media', {}).get('payload')
                        if media_payload:
                            try:
                                audio_bytes = base64.b64decode(media_payload)
                                # Twilio Media Streams use μ-law encoding at 8kHz
                                # Convert μ-law to linear PCM16
                                # Simple μ-law to linear conversion
                                mu_law_array = np.frombuffer(audio_bytes, dtype=np.uint8)
                                # μ-law decoder: expand 8-bit μ-law to 16-bit linear
                                sign = (mu_law_array & 0x80) >> 7
                                exponent = (mu_law_array & 0x70) >> 4
                                mantissa = mu_law_array & 0x0F
                                
                                # Decode μ-law
                                linear = np.zeros(len(mu_law_array), dtype=np.int16)
                                for i in range(len(mu_law_array)):
                                    mu = mu_law_array[i]
                                    sign_bit = (mu & 0x80) >> 7
                                    exponent_bits = (mu & 0x70) >> 4
                                    mantissa_bits = mu & 0x0F
                                    
                                    # μ-law expansion formula
                                    if exponent_bits == 0:
                                        sample = (mantissa_bits << 1) + 33
                                    else:
                                        sample = ((mantissa_bits << 1) + 33) << (exponent_bits - 1)
                                    
                                    if sign_bit == 1:
                                        sample = -sample
                                    
                                    linear[i] = np.int16(sample - 33)
                                
                                # Scale to int16 range
                                audio_array = (linear * 16).astype(np.int16)
                                
                                # Save audio chunk BEFORE processing (for testing/debugging)
                                handler._save_audio_chunk(call_sid, audio_array, sample_rate=8000)
                                
                                # Log audio info (every 50 chunks to avoid spam)
                                if call_sid not in handler.audio_chunk_counts or handler.audio_chunk_counts.get(call_sid, 0) % 50 == 0:
                                    handler.logger.info(f"[AUDIO_CAPTURE] Call {call_sid}: Received audio chunk - "
                                                      f"size: {len(audio_array)} samples ({len(audio_array)/8000:.3f}s), "
                                                      f"min: {audio_array.min()}, max: {audio_array.max()}, "
                                                      f"mean: {audio_array.mean():.1f}")
                            
                                # Process through orchestrator with audio storage
                                handler.orchestrator.handle_audio_chunk(audio_array, call_sid=call_sid)
                            except Exception as e:
                                handler.logger.error(f"[AUDIO_DEBUG] Error processing media payload: {e}", exc_info=True)
                    elif event == 'stop':
                        handler.logger.info(f"[AUDIO_DEBUG] Media stream stopped for call {call_sid}")
                        # Close audio writer if exists
                        if call_sid in handler.audio_writers:
                            try:
                                writer = handler.audio_writers[call_sid]
                                writer.close()
                                chunk_count = handler.audio_chunk_counts.get(call_sid, 0)
                                handler.logger.info(f"[AUDIO_CAPTURE] Closed audio file for call {call_sid} ({chunk_count} chunks saved)")
                            except Exception as e:
                                handler.logger.error(f"[AUDIO_CAPTURE] Error closing audio writer: {e}")
                            del handler.audio_writers[call_sid]
                        break
                        
            except WebSocketDisconnect:
                handler.logger.info(f"[AUDIO_DEBUG] Media Stream WebSocket disconnected for call {call_sid}")
                # Close audio writer if exists
                if call_sid in handler.audio_writers:
                    try:
                        writer = handler.audio_writers[call_sid]
                        writer.close()
                        chunk_count = handler.audio_chunk_counts.get(call_sid, 0)
                        handler.logger.info(f"[AUDIO_CAPTURE] Closed audio file for call {call_sid} ({chunk_count} chunks saved)")
                    except Exception as e:
                        handler.logger.error(f"[AUDIO_CAPTURE] Error closing audio writer: {e}")
                    del handler.audio_writers[call_sid]
            except Exception as e:
                handler.logger.error(f"[AUDIO_DEBUG] Error in Media Stream WebSocket: {e}")
                # Close audio writer if exists
                if call_sid in handler.audio_writers:
                    try:
                        writer = handler.audio_writers[call_sid]
                        writer.close()
                    except:
                        pass
                    del handler.audio_writers[call_sid]
        
        @app.post('/media/{call_sid}')
        async def handle_media_stream_fallback(call_sid: str, request: Request):
            """Fallback HTTP POST endpoint for Media Streams (if WebSocket not available)."""
            try:
                data = await request.json()
                event = data.get('event')
                
                if event == 'media':
                    media_payload = data.get('media', {}).get('payload')
                    if media_payload:
                        audio_bytes = base64.b64decode(media_payload)
                        audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
                        handler.orchestrator.handle_audio_chunk(audio_array, call_sid=call_sid)
            except Exception as e:
                handler.logger.error(f"[AUDIO_DEBUG] Error in fallback media stream: {e}")
            
            return PlainTextResponse("OK")
        
        @app.post('/transcription/{call_sid}')
        async def handle_transcription(call_sid: str, request: Request):
            """Handle real-time transcription callbacks from Twilio with Deepgram."""
            form_data = await request.form()
            
            # Extract transcription data
            transcription_text = form_data.get('TranscriptionText', '')
            transcription_status = form_data.get('TranscriptionStatus', '')
            transcription_sid = form_data.get('TranscriptionSid', '')
            confidence = form_data.get('Confidence', '0')
            # Check for language in webhook (may not be present for all transcription services)
            language = form_data.get('Language', None) or form_data.get('LanguageCode', None)
            
            handler.logger.info(f"[TRANSCRIPTION] Call {call_sid}: Status={transcription_status}, Text='{transcription_text}', Confidence={confidence}, Language={language or 'N/A'}")
            
            # Only process completed transcriptions with text
            if transcription_status == 'completed' and transcription_text and transcription_text.strip():
                try:
                    # If language not in webhook, try to fetch from Twilio API using transcription_sid
                    if not language and transcription_sid:
                        try:
                            trans_obj = handler.client.transcriptions(transcription_sid).fetch()
                            language = getattr(trans_obj, 'language', None) or getattr(trans_obj, 'languageCode', None)
                            if language:
                                handler.logger.info(f"[TRANSCRIPTION] Fetched language from API: {language}")
                        except Exception as lang_e:
                            handler.logger.debug(f"[TRANSCRIPTION] Could not fetch language from API: {lang_e}")
                    
                    # Process transcription through VOCA orchestrator
                    ai_response = handler.orchestrator.generate_reply(
                        transcription_text,
                        conversation_id=call_sid,
                        call_sid=call_sid,
                    )
                    handler.logger.info(f"[TRANSCRIPTION] AI Response: {ai_response}")
                    
                    # Store transcription in call metadata
                    if call_sid in handler.active_calls:
                        if 'transcriptions' not in handler.active_calls[call_sid]:
                            handler.active_calls[call_sid]['transcriptions'] = []
                        handler.active_calls[call_sid]['transcriptions'].append({
                            'text': transcription_text,
                            'status': transcription_status,
                            'transcription_sid': transcription_sid,
                            'confidence': confidence,
                            'language': language,
                            'languageCode': language,  # Alias for compatibility
                            'timestamp': datetime.now(timezone.utc).isoformat()
                        })
                        
                        # Log language detection when we have transcriptions with language
                        if language:
                            # Get all unique languages from all transcriptions for this call
                            all_languages = []
                            for trans in handler.active_calls[call_sid]['transcriptions']:
                                trans_lang = trans.get('language') or trans.get('languageCode')
                                if trans_lang:
                                    all_languages.append(trans_lang)
                            if all_languages:
                                unique_languages = list(set(all_languages))
                                handler.logger.info(f"[CALL_INFO] Call {call_sid} - Detected Languages: {', '.join(unique_languages)}")
                    
                    # Generate TwiML response with AI reply
                    # No need for Gather - Real-Time Transcriptions continue automatically
                    # The transcription service will keep sending transcriptions as user speaks
                    response = VoiceResponse()
                    response.say(ai_response)
                    
                    # Return response - transcriptions will continue automatically
                    return Response(content=str(response), media_type='text/xml')
                    
                except Exception as e:
                    handler.logger.error(f"[TRANSCRIPTION] Error processing transcription: {e}", exc_info=True)
                    # Return empty response to continue call
                    response = VoiceResponse()
                    return Response(content=str(response), media_type='text/xml')
            else:
                # For in-progress or empty transcriptions, just acknowledge
                handler.logger.debug(f"[TRANSCRIPTION] Ignoring transcription: status={transcription_status}, has_text={bool(transcription_text)}")
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
        
        @app.get('/audio/calls')
        async def list_recorded_calls():
            """List all calls that have recorded audio."""
            try:
                audio_dir = handler.audio_storage_dir
                if not audio_dir.exists():
                    return JSONResponse({"calls": []})
                
                calls = []
                for call_dir in audio_dir.iterdir():
                    if call_dir.is_dir():
                        audio_file = call_dir / f"audio_{call_dir.name}.wav"
                        if audio_file.exists():
                            file_size = audio_file.stat().st_size
                            file_mtime = datetime.fromtimestamp(audio_file.stat().st_mtime, tz=timezone.utc)
                            chunk_count = handler.audio_chunk_counts.get(call_dir.name, 0)
                            calls.append({
                                "call_sid": call_dir.name,
                                "audio_file": str(audio_file.name),
                                "file_size": file_size,
                                "file_size_mb": round(file_size / (1024 * 1024), 2),
                                "modified_time": file_mtime.isoformat(),
                                "chunk_count": chunk_count,
                                "download_url": f"/audio/download/{call_dir.name}"
                            })
                
                # Sort by modified time, most recent first
                calls.sort(key=lambda x: x["modified_time"], reverse=True)
                return JSONResponse({"calls": calls})
            except Exception as e:
                handler.logger.error(f"Error listing recorded calls: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))
        
        @app.get('/audio/download/{call_sid}')
        async def download_audio(call_sid: str):
            """Download recorded audio file for a specific call."""
            try:
                call_dir = handler.audio_storage_dir / call_sid
                audio_file = call_dir / f"audio_{call_sid}.wav"
                
                if not audio_file.exists():
                    raise HTTPException(status_code=404, detail=f"Audio file not found for call {call_sid}")
                
                return FileResponse(
                    path=str(audio_file),
                    filename=f"audio_{call_sid}.wav",
                    media_type="audio/wav"
                )
            except HTTPException:
                raise
            except Exception as e:
                handler.logger.error(f"Error downloading audio: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))
        
        @app.get('/audio/info/{call_sid}')
        async def get_audio_info(call_sid: str):
            """Get information about recorded audio for a specific call."""
            try:
                call_dir = handler.audio_storage_dir / call_sid
                audio_file = call_dir / f"audio_{call_sid}.wav"
                
                if not audio_file.exists():
                    raise HTTPException(status_code=404, detail=f"Audio file not found for call {call_sid}")
                
                file_size = audio_file.stat().st_size
                file_mtime = datetime.fromtimestamp(audio_file.stat().st_mtime, tz=timezone.utc)
                chunk_count = handler.audio_chunk_counts.get(call_sid, 0)
                
                # Try to read WAV file info
                with wave.open(str(audio_file), 'rb') as wav_file:
                    n_frames = wav_file.getnframes()
                    sample_rate = wav_file.getframerate()
                    n_channels = wav_file.getnchannels()
                    sample_width = wav_file.getsampwidth()
                    duration = n_frames / sample_rate if sample_rate > 0 else 0
                
                return JSONResponse({
                    "call_sid": call_sid,
                    "audio_file": str(audio_file.name),
                    "file_size": file_size,
                    "file_size_mb": round(file_size / (1024 * 1024), 2),
                    "modified_time": file_mtime.isoformat(),
                    "chunk_count": chunk_count,
                    "audio_info": {
                        "sample_rate": sample_rate,
                        "channels": n_channels,
                        "sample_width": sample_width,
                        "frames": n_frames,
                        "duration_seconds": round(duration, 2),
                        "duration_formatted": f"{int(duration // 60)}m {int(duration % 60)}s"
                    },
                    "download_url": f"/audio/download/{call_sid}"
                })
            except HTTPException:
                raise
            except Exception as e:
                handler.logger.error(f"Error getting audio info: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))
        
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
                'audio_buffer': [],
                'unclear_count': 0,  # Track consecutive unclear responses
                'last_speech_attempt': None,  # Track last speech attempt to detect name collection
                'name_attempt_count': 0  # Track attempts to provide name
            }
            
            response = VoiceResponse()
            
            # Enable Real-Time Transcriptions with Deepgram Nova-3 for Hindi
            config = get_twilio_config()
            webhook_url = config.get_webhook_url()
            base_url = webhook_url.replace('/webhook/voice', '').replace('/outbound', '')
            
            # Set up Real-Time Transcription with Deepgram
            transcription_callback_url = f'{base_url}/transcription/{call_sid}'
            start = Start()
            transcription = Transcription(
                statusCallbackUrl=transcription_callback_url,
                transcriptionEngine='deepgram',
                track='both_tracks',
                speechModel='nova-3',  # Use nova-3 for best accuracy
                languageCode='en-IN'   # English (India) language
            )
            start.append(transcription)
            
            # Enable Media Streams for audio storage/debugging (if enabled)
            if Config.audio_storage_enabled:
                # Convert to WebSocket URL (wss://)
                if base_url.startswith('http://'):
                    wss_base_url = base_url.replace('http://', 'wss://')
                elif base_url.startswith('https://'):
                    wss_base_url = base_url.replace('https://', 'wss://')
                elif not base_url.startswith('wss://'):
                    wss_base_url = f"wss://{base_url.lstrip('/')}"
                else:
                    wss_base_url = base_url
                
                stream_url = f"{wss_base_url}/media/{call_sid}"
                stream = Stream(url=stream_url, parameters={'call_sid': call_sid})
                start.stream(stream)
                handler.logger.info(f"[AUDIO_DEBUG] Enabled Media Stream for outbound call {call_sid}: {stream_url}")
            
            response.append(start)
            handler.logger.info(f"[TRANSCRIPTION] Enabled Real-Time Transcription for outbound call {call_sid}")
            
            # Generate greeting from system prompt
            try:
                # Get organization_id from call metadata if available
                org_id = form_data.get('organization_id') or handler.orchestrator.default_organization_id
                greeting = handler.orchestrator.generate_greeting(
                    conversation_id=call_sid,
                    organization_id=org_id
                )
                handler.logger.info(f"Generated greeting for outbound call {call_sid}: {greeting}")
            except Exception as e:
                handler.logger.error(f"Error generating greeting: {e}")
                greeting = "Hello! This is VOCA calling. How can I help you today?"
            
            response.say(greeting)
            
            # No need for Gather - Real-Time Transcriptions will handle speech recognition
            # Transcriptions will be sent to /transcription/{call_sid} callback automatically
            # The callback will process transcriptions and generate AI responses
            
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
    
    def _save_audio_chunk(self, call_sid: str, audio_array: np.ndarray, sample_rate: int = 8000):
        """Save audio chunk to WAV file for testing/debugging."""
        try:
            # Initialize wave writer if not exists
            if call_sid not in self.audio_writers:
                call_dir = self.audio_storage_dir / call_sid
                call_dir.mkdir(parents=True, exist_ok=True)
                audio_file = call_dir / f"audio_{call_sid}.wav"
                
                writer = wave.open(str(audio_file), 'wb')
                writer.setnchannels(1)  # Mono
                writer.setsampwidth(2)  # 16-bit = 2 bytes
                writer.setframerate(sample_rate)
                self.audio_writers[call_sid] = writer
                self.audio_chunk_counts[call_sid] = 0
                self.logger.info(f"[AUDIO_CAPTURE] Started saving audio to {audio_file}")
            
            # Write audio data
            writer = self.audio_writers[call_sid]
            audio_bytes = audio_array.tobytes()
            writer.writeframes(audio_bytes)
            self.audio_chunk_counts[call_sid] += 1
            
            # Log every 100 chunks to avoid spam
            if self.audio_chunk_counts[call_sid] % 100 == 0:
                self.logger.info(f"[AUDIO_CAPTURE] Call {call_sid}: Saved {self.audio_chunk_counts[call_sid]} chunks, "
                               f"latest chunk size: {len(audio_array)} samples ({len(audio_array)/sample_rate:.2f}s)")
            
        except Exception as e:
            self.logger.error(f"[AUDIO_CAPTURE] Error saving audio chunk: {e}", exc_info=True)
    
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
            
            # Save audio chunk BEFORE processing (for testing)
            self._save_audio_chunk(call_sid, audio_array, sample_rate=8000)
            
            # Process through VOCA orchestrator
            self.orchestrator.handle_audio_chunk(audio_array, call_sid=call_sid)
            
        except Exception as e:
            self.logger.error(f"Error processing audio for call {call_sid}: {e}")
    
    def cleanup_call(self, call_sid: str):
        """Clean up resources for a call."""
        # Close and finalize audio writer
        if call_sid in self.audio_writers:
            try:
                writer = self.audio_writers[call_sid]
                writer.close()
                chunk_count = self.audio_chunk_counts.get(call_sid, 0)
                self.logger.info(f"[AUDIO_CAPTURE] Closed audio file for call {call_sid} ({chunk_count} chunks saved)")
            except Exception as e:
                self.logger.error(f"[AUDIO_CAPTURE] Error closing audio writer: {e}")
            del self.audio_writers[call_sid]
        
        if call_sid in self.audio_chunk_counts:
            del self.audio_chunk_counts[call_sid]
        
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