import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, FileResponse
from twilio.twiml.voice_response import VoiceResponse, Start, Stream, Transcription

from src.voca.api.state import app_state
from src.voca.Twilio.twilio_config import get_twilio_config
from src.voca.config import Config
from src.voca.Twilio.twilio_voice import deepgramtts

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/conversation/{call_sid}/test")
async def test_conversation_route(call_sid: str):
    """Test endpoint to verify the conversation route is accessible."""
    logger.info(f"[CONVERSATION_RELAY] Test endpoint hit for call {call_sid}")
    return {"status": "ok", "call_sid": call_sid, "message": "Route is accessible"}


@router.websocket("/conversation/{call_sid}")
async def handle_conversation_relay(websocket: WebSocket, call_sid: str):
    """Handle ConversationRelay WebSocket connection from Twilio."""
    logger.info(f"[CONVERSATION_RELAY] WebSocket connection attempt for call {call_sid}")
    logger.info(f"[CONVERSATION_RELAY] WebSocket client: {websocket.client if hasattr(websocket, 'client') else 'N/A'}")
    logger.info(f"[CONVERSATION_RELAY] WebSocket URL: {websocket.url if hasattr(websocket, 'url') else 'N/A'}")
    
    try:
        await websocket.accept()
        logger.info(f"[CONVERSATION_RELAY] WebSocket connected for call {call_sid}")
    except Exception as e:
        logger.error(f"[CONVERSATION_RELAY] Error accepting WebSocket for call {call_sid}: {e}", exc_info=True)
        return
    
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        logger.error(f"[CONVERSATION_RELAY] Twilio manager not available for call {call_sid}")
        try:
            await websocket.close()
        except Exception:
            pass
        return
    
    voice_handler = twilio_manager.voice_handler
    
    # Initialize conversation state for this call
    if call_sid not in voice_handler.active_calls:
        voice_handler.active_calls[call_sid] = {}
    
    call_state = voice_handler.active_calls[call_sid]
    call_state.setdefault('welcome_sent', False)
    call_state.setdefault('turn_count', 0)
    
    # Get organization_id from call state if available
    org_id = call_state.get('organization_id') or app_state.get_orchestrator().default_organization_id
    
    try:
        while True:
            # Receive messages from Twilio ConversationRelay
            try:
                data = await websocket.receive_json()
            except ValueError as e:
                logger.error(f"[CONVERSATION_RELAY] Invalid JSON received for call {call_sid}: {e}")
                continue
            except Exception as e:
                logger.error(f"[CONVERSATION_RELAY] Error receiving message for call {call_sid}: {e}")
                break
            
            # Validate data structure
            if not isinstance(data, dict):
                logger.warning(f"[CONVERSATION_RELAY] Received non-dict data for call {call_sid}: {type(data)}")
                continue
            
            event_type = data.get('event', {}).get('type')
            
            logger.debug(f"[CONVERSATION_RELAY] Received event: {event_type} for call {call_sid}")
            
            if event_type == 'start':
                logger.info(f"[CONVERSATION_RELAY] Conversation started for call {call_sid}")
                
                # Send welcome message only once when start event is received
                if not call_state.get('welcome_sent', False):
                    try:
                        # Generate welcome message using orchestrator
                        greeting = voice_handler.orchestrator.generate_greeting(
                            conversation_id=call_sid,
                            organization_id=org_id
                        )
                        
                        logger.info(f"[CONVERSATION_RELAY] Sending welcome message: {greeting}")
                        app_state._log_callback("=" * 80)
                        app_state._log_callback(f"[AI] Call {call_sid} - Welcome Message: \"{greeting}\"")
                        app_state._log_callback("=" * 80)
                        
                        # Send welcome message as first assistant turn
                        welcome_message = {
                            'event': {
                                'type': 'text',
                                'text': greeting
                            }
                        }
                        try:
                            await websocket.send_json(welcome_message)
                            logger.info(f"[CONVERSATION_RELAY] Sent welcome message to ConversationRelay")
                        except Exception as send_error:
                            logger.error(f"[CONVERSATION_RELAY] Error sending welcome message: {send_error}")
                            raise
                        
                        # Mark welcome as sent, increment turn count, and track activity
                        call_state['welcome_sent'] = True
                        call_state['turn_count'] = call_state.get('turn_count', 0) + 1
                        call_state['last_activity'] = time.time()
                    except Exception as e:
                        logger.error(f"[CONVERSATION_RELAY] Error sending welcome message: {e}", exc_info=True)
                else:
                    logger.debug(f"[CONVERSATION_RELAY] Welcome already sent for call {call_sid}, skipping")
                    
            elif event_type == 'media':
                # Audio data from the call - ConversationRelay handles this automatically
                logger.debug(f"[CONVERSATION_RELAY] Received audio data for call {call_sid}")
                
            elif event_type == 'text':
                # Text transcription from Deepgram STT
                transcription_text = data.get('event', {}).get('text', '').strip()
                
                if not transcription_text:
                    continue
                
                # Prevent assistant from responding to its own welcome message (STT echo)
                # Only process text events after welcome has been sent
                if not call_state.get('welcome_sent', False):
                    logger.debug(f"[CONVERSATION_RELAY] Ignoring text event before welcome sent: {transcription_text}")
                    continue
                
                # Update last activity timestamp when user sends text
                call_state['last_activity'] = time.time()
                
                logger.info(f"[CONVERSATION_RELAY] Transcription: {transcription_text}")
                app_state._log_callback("=" * 80)
                app_state._log_callback(f"[USER] Call {call_sid} - Transcription: \"{transcription_text}\"")
                app_state._log_callback("=" * 80)
                
                # Process through VOCA orchestrator
                try:
                    ai_response = voice_handler.orchestrator.generate_reply(
                        transcription_text,
                        conversation_id=call_sid,
                        call_sid=call_sid,
                        organization_id=org_id,
                    )
                    logger.info(f"[CONVERSATION_RELAY] AI Response: {ai_response}")
                    app_state._log_callback("=" * 80)
                    app_state._log_callback(f"[AI] Call {call_sid} - AI Response: \"{ai_response}\"")
                    app_state._log_callback("=" * 80)
                    
                    # Send text response back to ConversationRelay (will be converted to speech by Deepgram TTS)
                    response_message = {
                        'event': {
                            'type': 'text',
                            'text': ai_response
                        }
                    }
                    try:
                        await websocket.send_json(response_message)
                        logger.info(f"[CONVERSATION_RELAY] Sent AI response to ConversationRelay")
                    except Exception as send_error:
                        logger.error(f"[CONVERSATION_RELAY] Error sending AI response: {send_error}")
                        # Don't raise - allow conversation to continue
                    
                    # Increment turn count and update last activity
                    call_state['turn_count'] = call_state.get('turn_count', 0) + 1
                    call_state['last_activity'] = time.time()
                except Exception as e:
                    logger.error(f"[CONVERSATION_RELAY] Error processing transcription: {e}", exc_info=True)
                        
            elif event_type == 'stop':
                logger.info(f"[CONVERSATION_RELAY] Conversation stopped for call {call_sid}")
                logger.info(f"[CONVERSATION_RELAY] Total turns: {call_state.get('turn_count', 0)}")
                break
            else:
                logger.debug(f"[CONVERSATION_RELAY] Unhandled event type: {event_type}")
                
    except WebSocketDisconnect:
        logger.info(f"[CONVERSATION_RELAY] WebSocket disconnected for call {call_sid}")
    except Exception as e:
        logger.error(f"[CONVERSATION_RELAY] Error in WebSocket: {e}", exc_info=True)


@router.post("/outbound")
async def handle_outbound_call(request: Request):
    """Handle outbound call TwiML using Real-Time Transcriptions and Media Streams."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        logger.error("[TRANSCRIPTION] Twilio manager not available")
        return Response(content=str(response), media_type="text/xml")

    voice_handler = twilio_manager.voice_handler

    form_data = await request.form()
    call_sid = form_data.get("CallSid")

    if call_sid:
        # Get organization_id from form data if available
        org_id = form_data.get("organization_id") or app_state.get_orchestrator().default_organization_id
        
        voice_handler.active_calls[call_sid] = {
            "to_number": "outbound",
            "status": "ringing",
            "start_time": time.time(),
            "audio_buffer": [],
            "unclear_count": 0,
            "last_speech_attempt": None,
            "name_attempt_count": 0
        }

    # Create TwiML response
    response = VoiceResponse()

    # Enable Real-Time Transcriptions with Deepgram Nova-3
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
        logger.info(f"[AUDIO_DEBUG] Enabled Media Stream for outbound call {call_sid}: {stream_url}")

    response.append(start)
    logger.info(f"[TRANSCRIPTION] Enabled Real-Time Transcription for outbound call {call_sid}")

    # Generate greeting from system prompt and play via Deepgram TTS
    try:
        org_id = form_data.get('organization_id') or app_state.get_orchestrator().default_organization_id
        greeting = voice_handler.orchestrator.generate_greeting(
            conversation_id=call_sid,
            organization_id=org_id
        )
        logger.info(f"Generated greeting for outbound call {call_sid}: {greeting}")
    except Exception as e:
        logger.error(f"Error generating greeting: {e}")
        greeting = "Hello! This is VOCA calling. How can I help you today?"

    # Synthesize greeting to MP3 and play; fall back to <Say> on error
    try:
        tts_dir = Path(Config.audio_storage_dir) / "tts" / call_sid
        tts_dir.mkdir(parents=True, exist_ok=True)
        tts_filename = "greeting.mp3"
        tts_path = tts_dir / tts_filename
        deepgramtts(greeting, filename=str(tts_path))

        # Build absolute URL for the audio file
        config = get_twilio_config()
        webhook_url = config.get_webhook_url()
        base_url_for_audio = webhook_url.replace('/webhook/voice', '').replace('/outbound', '')
        audio_url = f"{base_url_for_audio}/audio/tts/{call_sid}/{tts_filename}"

        response.play(audio_url)
    except Exception as tts_err:
        logger.error(f"[TTS] Greeting TTS failed, sending silent pause: {tts_err}")
        response.pause(length=1)

    # No need for Gather - Real-Time Transcriptions will handle speech recognition
    # Transcriptions will be sent to /transcription/{call_sid} callback automatically
    # The callback will process transcriptions and generate AI responses

    return Response(content=str(response), media_type="text/xml")


@router.post("/webhook/voice")
async def handle_incoming_call_webhook(request: Request):
    """Handle incoming Twilio call webhook using Real-Time Transcriptions and Media Streams."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        logger.error("[TRANSCRIPTION] Twilio manager not available")
        return Response(content=str(response), media_type="text/xml")

    voice_handler = twilio_manager.voice_handler

    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")

    logger.info(f"Incoming call from {from_number}, SID: {call_sid}")

    if call_sid:
        # Get organization_id from form data if available
        org_id = form_data.get("organization_id") or app_state.get_orchestrator().default_organization_id
        
        voice_handler.active_calls[call_sid] = {
            "from_number": from_number,
            "status": "ringing",
            "start_time": time.time(),
            "audio_buffer": [],
            "unclear_count": 0,
            "last_speech_attempt": None,
            "name_attempt_count": 0
        }

    # Create TwiML response
    response = VoiceResponse()

    # Generate welcome message from system prompt
    try:
        # Get organization_id from call metadata if available
        org_id = form_data.get('organization_id') or app_state.get_orchestrator().default_organization_id
        greeting = voice_handler.orchestrator.generate_greeting(
            conversation_id=call_sid,
            organization_id=org_id
        )
        logger.info(f"Generated greeting for call {call_sid}: {greeting}")
    except Exception as e:
        logger.error(f"Error generating greeting: {e}")
        greeting = "Hello! How can I help you today?"

    # Enable Real-Time Transcriptions with Deepgram Nova-3
    # This provides real-time transcriptions via callbacks (no Deepgram API key needed)
    config = get_twilio_config()
    webhook_url = config.get_webhook_url()
    base_url = webhook_url.replace('/webhook/voice', '')

    # Set up Real-Time Transcription with Deepgram Nova-3
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
    logger.info(f"[TRANSCRIPTION] Enabled Real-Time Transcription for call {call_sid}")
    logger.info(f"[TRANSCRIPTION] Callback URL: {transcription_callback_url}")

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
        logger.info(f"[AUDIO_DEBUG] Enabled Media Stream for call {call_sid}")
        logger.info(f"[AUDIO_DEBUG] Stream URL: {stream_url}")

    # Play welcome message via Deepgram TTS; fall back to <Say> on error
    try:
        tts_dir = Path(Config.audio_storage_dir) / "tts" / call_sid
        tts_dir.mkdir(parents=True, exist_ok=True)
        tts_filename = "greeting.mp3"
        tts_path = tts_dir / tts_filename
        deepgramtts(greeting, filename=str(tts_path))

        # Build absolute URL for the audio file
        config = get_twilio_config()
        webhook_url = config.get_webhook_url()
        base_url_for_audio = webhook_url.replace('/webhook/voice', '')
        audio_url = f"{base_url_for_audio}/audio/tts/{call_sid}/{tts_filename}"

        response.play(audio_url)
    except Exception as tts_err:
        logger.error(f"[TTS] Welcome TTS failed, sending silent pause: {tts_err}")
        response.pause(length=1)

    # No need for Gather - Real-Time Transcriptions will handle speech recognition
    # Transcriptions will be sent to /transcription/{call_sid} callback
    # The callback will process transcriptions and generate AI responses

    return Response(content=str(response), media_type="text/xml")


@router.post("/transcription/{call_sid}")
async def handle_transcription(call_sid: str, request: Request):
    """Handle real-time transcription callbacks from Twilio with Deepgram."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        return PlainTextResponse("OK")

    voice_handler = twilio_manager.voice_handler
    form_data = await request.form()
    
    # Extract transcription data
    transcription_text = form_data.get('TranscriptionText', '')
    transcription_status = form_data.get('TranscriptionStatus', '')
    transcription_sid = form_data.get('TranscriptionSid', '')
    confidence = form_data.get('Confidence', '0')
    # Check for language in webhook (may not be present for all transcription services)
    language = form_data.get('Language', None) or form_data.get('LanguageCode', None)
    
    logger.info(f"[TRANSCRIPTION] Call {call_sid}: Status={transcription_status}, Text='{transcription_text}', Confidence={confidence}, Language={language or 'N/A'}")
    
    # Only process completed transcriptions with text
    if transcription_status == 'completed' and transcription_text and transcription_text.strip():
        try:
            # If language not in webhook, try to fetch from Twilio API using transcription_sid
            if not language and transcription_sid:
                try:
                    trans_obj = voice_handler.client.transcriptions(transcription_sid).fetch()
                    language = getattr(trans_obj, 'language', None) or getattr(trans_obj, 'languageCode', None)
                    if language:
                        logger.info(f"[TRANSCRIPTION] Fetched language from API: {language}")
                except Exception as lang_e:
                    logger.debug(f"[TRANSCRIPTION] Could not fetch language from API: {lang_e}")
            
            # Process transcription through VOCA orchestrator
            org_id = None
            if call_sid in voice_handler.active_calls:
                org_id = voice_handler.active_calls[call_sid].get('organization_id')
            if not org_id:
                org_id = app_state.get_orchestrator().default_organization_id
            
            ai_response = voice_handler.orchestrator.generate_reply(
                transcription_text,
                conversation_id=call_sid,
                call_sid=call_sid,
                organization_id=org_id,
            )
            logger.info(f"[TRANSCRIPTION] AI Response: {ai_response}")
            
            # Store transcription in call metadata
            if call_sid in voice_handler.active_calls:
                if 'transcriptions' not in voice_handler.active_calls[call_sid]:
                    voice_handler.active_calls[call_sid]['transcriptions'] = []
                voice_handler.active_calls[call_sid]['transcriptions'].append({
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
                    for trans in voice_handler.active_calls[call_sid]['transcriptions']:
                        trans_lang = trans.get('language') or trans.get('languageCode')
                        if trans_lang:
                            all_languages.append(trans_lang)
                    if all_languages:
                        unique_languages = list(set(all_languages))
                        logger.info(f"[CALL_INFO] Call {call_sid} - Detected Languages: {', '.join(unique_languages)}")
            
            # Synthesize TTS via Deepgram and serve as audio instead of <Say>
            tts_dir = Path(Config.audio_storage_dir) / "tts" / call_sid
            tts_dir.mkdir(parents=True, exist_ok=True)
            tts_filename = f"tts_{int(time.time() * 1000)}.mp3"
            tts_path = tts_dir / tts_filename
            try:
                deepgramtts(ai_response, filename=str(tts_path))
            except Exception as tts_err:
                logger.error(f"[TRANSCRIPTION] TTS generation failed, sending silent pause: {tts_err}")
                response = VoiceResponse()
                response.pause(length=1)
                return Response(content=str(response), media_type='text/xml')

            # Build absolute URL for the audio file based on webhook base
            config = get_twilio_config()
            webhook_url = config.get_webhook_url()
            base_url = webhook_url.replace('/webhook/voice', '').replace('/outbound', '')
            audio_url = f"{base_url}/audio/tts/{call_sid}/{tts_filename}"

            # Generate TwiML response playing the synthesized audio
            response = VoiceResponse()
            response.play(audio_url)
            
            # Return response - transcriptions will continue automatically
            return Response(content=str(response), media_type='text/xml')
            
        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Error processing transcription: {e}", exc_info=True)
            # Return empty response with short pause to continue call
            response = VoiceResponse()
            response.pause(length=1)
            return Response(content=str(response), media_type='text/xml')
    else:
        # For in-progress or empty transcriptions, just acknowledge
        logger.debug(f"[TRANSCRIPTION] Ignoring transcription: status={transcription_status}, has_text={bool(transcription_text)}")
        return PlainTextResponse("OK")


@router.get("/audio/tts/{call_sid}/{filename}")
async def get_tts_audio(call_sid: str, filename: str):
    """Serve synthesized TTS audio for Twilio <Play>."""
    audio_path = Path(Config.audio_storage_dir) / "tts" / call_sid / filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path=str(audio_path), media_type="audio/mpeg", filename=filename)

