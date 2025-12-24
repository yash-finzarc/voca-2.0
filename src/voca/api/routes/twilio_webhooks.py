import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from twilio.twiml.voice_response import VoiceResponse, Start, Stream, Transcription, Gather, Pause

from src.voca.api.state import app_state
from src.voca.Twilio.twilio_config import get_twilio_config
from src.voca.config import Config
from src.voca.Twilio.twilio_voice import deepgramtts, stream_tts_to_twilio

router = APIRouter()
logger = logging.getLogger(__name__)


def _append_vad_gather(response: VoiceResponse, base_url: str, call_sid: str, language: str = "en-IN"):
    """Attach a speech-only Gather to keep the call alive using VAD (no barge-in)."""
    action_url = f"{base_url}/gather/continue/{call_sid}"
    gather = Gather(
        input="speech",
        speech_timeout="auto",  # Let VAD decide end-of-speech
        action=action_url,
        method="POST",
        language=language,
        bargeIn=False,  # Ensure greeting finishes before listening
    )
    response.append(gather)
    return response


# @router.get("/conversation/{call_sid}/test")
# async def test_conversation_route(call_sid: str):
#     """Test endpoint to verify the conversation route is accessible."""
#     logger.info(f"[CONVERSATION_RELAY] Test endpoint hit for call {call_sid}")
#     return {"status": "ok", "call_sid": call_sid, "message": "Route is accessible"}


# @router.websocket("/conversation/{call_sid}")
# async def handle_conversation_relay(websocket: WebSocket, call_sid: str):
#     """Handle ConversationRelay WebSocket connection from Twilio."""
#     logger.info(f"[CONVERSATION_RELAY] WebSocket connection attempt for call {call_sid}")
#     logger.info(f"[CONVERSATION_RELAY] WebSocket client: {websocket.client if hasattr(websocket, 'client') else 'N/A'}")
#     logger.info(f"[CONVERSATION_RELAY] WebSocket URL: {websocket.url if hasattr(websocket, 'url') else 'N/A'}")
    
#     try:
#         await websocket.accept()
#         logger.info(f"[CONVERSATION_RELAY] WebSocket connected for call {call_sid}")
#     except Exception as e:
#         logger.error(f"[CONVERSATION_RELAY] Error accepting WebSocket for call {call_sid}: {e}", exc_info=True)
#         return
    
#     twilio_manager = app_state.get_twilio_manager()
#     if not twilio_manager:
#         logger.error(f"[CONVERSATION_RELAY] Twilio manager not available for call {call_sid}")
#         try:
#             await websocket.close()
#         except Exception:
#             pass
#         return
    
#     voice_handler = twilio_manager.voice_handler
    
#     # Initialize conversation state for this call
#     if call_sid not in voice_handler.active_calls:
#         voice_handler.active_calls[call_sid] = {}
    
#     call_state = voice_handler.active_calls[call_sid]
#     call_state.setdefault('welcome_sent', False)
#     call_state.setdefault('turn_count', 0)
    
#     # Get organization_id from call state if available
#     org_id = call_state.get('organization_id') or app_state.get_orchestrator().default_organization_id
    
#     try:
#         while True:
#             # Receive messages from Twilio ConversationRelay
#             try:
#                 data = await websocket.receive_json()
#             except ValueError as e:
#                 logger.error(f"[CONVERSATION_RELAY] Invalid JSON received for call {call_sid}: {e}")
#                 continue
#             except Exception as e:
#                 logger.error(f"[CONVERSATION_RELAY] Error receiving message for call {call_sid}: {e}")
#                 break
            
#             # Validate data structure
#             if not isinstance(data, dict):
#                 logger.warning(f"[CONVERSATION_RELAY] Received non-dict data for call {call_sid}: {type(data)}")
#                 continue
            
#             event_type = data.get('event', {}).get('type')
            
#             logger.debug(f"[CONVERSATION_RELAY] Received event: {event_type} for call {call_sid}")
            
#             if event_type == 'start':
#                 logger.info(f"[CONVERSATION_RELAY] Conversation started for call {call_sid}")
                
#                 # Send welcome message only once when start event is received
#                 if not call_state.get('welcome_sent', False):
#                     try:
#                         # Generate welcome message using orchestrator
#                         greeting = voice_handler.orchestrator.generate_greeting(
#                             conversation_id=call_sid,
#                             organization_id=org_id
#                         )
                        
#                         logger.info(f"[CONVERSATION_RELAY] Sending welcome message: {greeting}")
#                         app_state._log_callback("=" * 80)
#                         app_state._log_callback(f"[AI] Call {call_sid} - Welcome Message: \"{greeting}\"")
#                         app_state._log_callback("=" * 80)
                        
#                         # Send welcome message as first assistant turn
#                         welcome_message = {
#                             'event': {
#                                 'type': 'text',
#                                 'text': greeting
#                             }
#                         }
#                         try:
#                             await websocket.send_json(welcome_message)
#                             logger.info(f"[CONVERSATION_RELAY] Sent welcome message to ConversationRelay")
#                         except Exception as send_error:
#                             logger.error(f"[CONVERSATION_RELAY] Error sending welcome message: {send_error}")
#                             raise
                        
#                         # Mark welcome as sent, increment turn count, and track activity
#                         call_state['welcome_sent'] = True
#                         call_state['turn_count'] = call_state.get('turn_count', 0) + 1
#                         call_state['last_activity'] = time.time()
#                     except Exception as e:
#                         logger.error(f"[CONVERSATION_RELAY] Error sending welcome message: {e}", exc_info=True)
#                 else:
#                     logger.debug(f"[CONVERSATION_RELAY] Welcome already sent for call {call_sid}, skipping")
                    
#             elif event_type == 'media':
#                 # Audio data from the call - ConversationRelay handles this automatically
#                 logger.debug(f"[CONVERSATION_RELAY] Received audio data for call {call_sid}")
                
#             elif event_type == 'text':
#                 # Text transcription from Deepgram STT
#                 transcription_text = data.get('event', {}).get('text', '').strip()
                
#                 if not transcription_text:
#                     continue
                
#                 # Prevent assistant from responding to its own welcome message (STT echo)
#                 # Only process text events after welcome has been sent
#                 if not call_state.get('welcome_sent', False):
#                     logger.debug(f"[CONVERSATION_RELAY] Ignoring text event before welcome sent: {transcription_text}")
#                     continue
                
#                 # Update last activity timestamp when user sends text
#                 call_state['last_activity'] = time.time()
                
#                 logger.info(f"[CONVERSATION_RELAY] Transcription: {transcription_text}")
#                 app_state._log_callback("=" * 80)
#                 app_state._log_callback(f"[USER] Call {call_sid} - Transcription: \"{transcription_text}\"")
#                 app_state._log_callback("=" * 80)
                
#                 # Process through VOCA orchestrator
#                 try:
#                     ai_response = voice_handler.orchestrator.generate_reply(
#                         transcription_text,
#                         conversation_id=call_sid,
#                         call_sid=call_sid,
#                         organization_id=org_id,
#                     )
#                     logger.info(f"[CONVERSATION_RELAY] AI Response: {ai_response}")
#                     app_state._log_callback("=" * 80)
#                     app_state._log_callback(f"[AI] Call {call_sid} - AI Response: \"{ai_response}\"")
#                     app_state._log_callback("=" * 80)
                    
#                     # Send text response back to ConversationRelay (will be converted to speech by Deepgram TTS)
#                     response_message = {
#                         'event': {
#                             'type': 'text',
#                             'text': ai_response
#                         }
#                     }
#                     try:
#                         await websocket.send_json(response_message)
#                         logger.info(f"[CONVERSATION_RELAY] Sent AI response to ConversationRelay")
#                     except Exception as send_error:
#                         logger.error(f"[CONVERSATION_RELAY] Error sending AI response: {send_error}")
#                         # Don't raise - allow conversation to continue
                    
#                     # Increment turn count and update last activity
#                     call_state['turn_count'] = call_state.get('turn_count', 0) + 1
#                     call_state['last_activity'] = time.time()
#                 except Exception as e:
#                     logger.error(f"[CONVERSATION_RELAY] Error processing transcription: {e}", exc_info=True)
                        
#             elif event_type == 'stop':
#                 logger.info(f"[CONVERSATION_RELAY] Conversation stopped for call {call_sid}")
#                 logger.info(f"[CONVERSATION_RELAY] Total turns: {call_state.get('turn_count', 0)}")
#                 break
#             else:
#                 logger.debug(f"[CONVERSATION_RELAY] Unhandled event type: {event_type}")
                
#     except WebSocketDisconnect:
#         logger.info(f"[CONVERSATION_RELAY] WebSocket disconnected for call {call_sid}")
#     except Exception as e:
#         logger.error(f"[CONVERSATION_RELAY] Error in WebSocket: {e}", exc_info=True)


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

    # Enable Media Streams for streaming TTS (always enabled for streaming)
    # Media Streams are required for bidirectional audio streaming
    if True:  # Always enable Media Streams for TTS streaming
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
        # Stream does not support statusCallback - use minimal configuration
        stream = Stream(
            url=stream_url, 
            track='both_tracks', 
            parameters={'call_sid': call_sid}
        )
        start.append(stream)
        logger.info(f"[AUDIO_DEBUG] Enabled Media Stream for outbound call {call_sid}: {stream_url}")

    response.append(start)
    logger.info(f"[TRANSCRIPTION] Enabled Real-Time Transcription for outbound call {call_sid}")
    
    # Add a very short pause to trigger audio activity and Media Streams connection
    # Media Streams may only connect when there's audio activity
    response.append(Pause(length=0.1))
    
    # Log the full TwiML response for debugging
    twiml_str = str(response)
    logger.info(f"[TWiML_DEBUG] TwiML response for call {call_sid}:\n{twiml_str}")

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

    # Store greeting to send when Media Streams WebSocket connects
    # Media Streams WebSocket connects asynchronously after TwiML response
    voice_handler.pending_greetings[call_sid] = greeting
    logger.info(f"[TTS] Stored greeting for call {call_sid}, will send when Media Streams connect")

    # Keep the call alive after greeting by enabling speech-only Gather with VAD.
    _append_vad_gather(response, base_url, call_sid, language="en-IN")

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

    # Enable Media Streams for streaming TTS (always enabled for streaming)
    # Media Streams are required for bidirectional audio streaming
    if True:  # Always enable Media Streams for TTS streaming
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
        # Stream does not support statusCallback - use minimal configuration
        stream = Stream(
            url=stream_url, 
            track='both_tracks', 
            parameters={'call_sid': call_sid}
        )
        start.append(stream)
        logger.info(f"[AUDIO_DEBUG] Enabled Media Stream for call {call_sid}: {stream_url}")

    # Store greeting to send when Media Streams WebSocket connects
    # Media Streams WebSocket connects asynchronously after TwiML response
    voice_handler.pending_greetings[call_sid] = greeting
    logger.info(f"[TTS] Stored welcome message for call {call_sid}, will send when Media Streams connect")

    # Keep the call alive after greeting by enabling speech-only Gather with VAD.
    _append_vad_gather(response, base_url, call_sid, language="en-IN")

    return Response(content=str(response), media_type="text/xml")


@router.post("/gather/continue/{call_sid}")
async def handle_gather_continue(call_sid: str, request: Request):
    """
    Twilio posts here after a speech Gather completes. We optionally TTS an AI reply, then
    re-attach another VAD Gather so the call stays alive and continues listening.
    """
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        logger.error("[GATHER] Twilio manager not available")
        return Response(content=str(response), media_type="text/xml")

    voice_handler = twilio_manager.voice_handler
    form_data = await request.form()
    speech_result = (form_data.get("SpeechResult") or "").strip()
    confidence = form_data.get("Confidence", "")
    language = form_data.get("Language", "") or "en-IN"

    logger.info(f"[GATHER] Call {call_sid}: SpeechResult='{speech_result}', Confidence={confidence}, Language={language}")

    response = VoiceResponse()

    # If we got speech text, generate an AI reply and play it before continuing to listen.
    if speech_result:
        try:
            org_id = None
            if call_sid in voice_handler.active_calls:
                org_id = voice_handler.active_calls[call_sid].get('organization_id')
            if not org_id:
                org_id = app_state.get_orchestrator().default_organization_id

            ai_response = voice_handler.orchestrator.generate_reply(
                speech_result,
                conversation_id=call_sid,
                call_sid=call_sid,
                organization_id=org_id,
            )
            logger.info(f"[GATHER] AI Response: {ai_response}")

            # Stream AI response via Deepgram TTS to Twilio Media Streams
            try:
                streamed = await stream_tts_to_twilio(voice_handler, call_sid, ai_response)
                if not streamed:
                    # Fallback to <Say> if streaming fails
                    logger.warning(f"[GATHER] Streaming failed for AI response, using <Say> fallback")
                    response.say(ai_response)
            except Exception as tts_err:
                logger.error(f"[GATHER] TTS streaming failed, using <Say> fallback: {tts_err}")
                response.say(ai_response)
        except Exception as e:
            logger.error(f"[GATHER] Error processing speech result: {e}", exc_info=True)
            response.pause(length=1)

    # Re-attach Gather to keep VAD listening
    config = get_twilio_config()
    base_url = config.get_webhook_url().replace('/webhook/voice', '').replace('/outbound', '')
    _append_vad_gather(response, base_url, call_sid, language=language or "en-IN")

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
            
            # Stream AI response via Deepgram TTS to Twilio Media Streams
            try:
                streamed = await stream_tts_to_twilio(voice_handler, call_sid, ai_response)
                if not streamed:
                    # Fallback to <Say> if streaming fails
                    logger.warning(f"[TRANSCRIPTION] Streaming failed for AI response, using <Say> fallback")
                    response = VoiceResponse()
                    response.say(ai_response)
                else:
                    # Return empty response - audio is streaming via Media Streams
                    response = VoiceResponse()
            except Exception as tts_err:
                logger.error(f"[TRANSCRIPTION] TTS streaming failed, using <Say> fallback: {tts_err}")
                response = VoiceResponse()
                response.say(ai_response)
            
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


# Removed /audio/tts endpoint - TTS now uses streaming via Media Streams WebSocket (no file storage)


@router.get("/media/{call_sid}/test")
async def test_media_stream_endpoint(call_sid: str):
    """Test endpoint to verify Media Streams route is accessible."""
    logger.info(f"[MEDIA_STREAM_TEST] Test endpoint accessed for call {call_sid}")
    return {
        "status": "ok",
        "call_sid": call_sid,
        "message": "Media Streams endpoint is accessible",
        "websocket_url": f"wss://voca2.duckdns.org/media/{call_sid}",
        "note": "WebSocket endpoint should be at /media/{call_sid}",
        "test_time": datetime.now(timezone.utc).isoformat()
    }


@router.post("/media/status/{call_sid}")
async def handle_media_stream_status(call_sid: str, request: Request):
    """Handle Media Streams status callbacks from Twilio."""
    form_data = await request.form()
    status = form_data.get('Status', 'unknown')
    error_code = form_data.get('ErrorCode', '')
    error_message = form_data.get('ErrorMessage', '')
    
    logger.info(f"[MEDIA_STREAM_STATUS] Call {call_sid}: Status={status}, ErrorCode={error_code}, ErrorMessage={error_message}")
    
    if status == 'failed' or error_code:
        logger.error(f"[MEDIA_STREAM_STATUS] Media Stream failed for call {call_sid}: {error_code} - {error_message}")
    
    return PlainTextResponse("OK")


@router.websocket("/media/{call_sid}")
async def handle_media_stream_websocket(websocket: WebSocket, call_sid: str):
    """Handle Twilio Media Streams via WebSocket in main API app."""
    from fastapi import WebSocketDisconnect
    
    # Log immediately when handler is called (before accept)
    logger.info(f"[AUDIO_DEBUG] ===== Media Stream WebSocket handler CALLED for call {call_sid} =====")
    logger.info(f"[AUDIO_DEBUG] WebSocket path: {websocket.url.path if hasattr(websocket, 'url') else 'N/A'}")
    logger.info(f"[AUDIO_DEBUG] WebSocket client: {websocket.client if hasattr(websocket, 'client') else 'N/A'}")
    logger.info(f"[AUDIO_DEBUG] WebSocket headers: {dict(websocket.headers) if hasattr(websocket, 'headers') else 'N/A'}")
    logger.info(f"[AUDIO_DEBUG] WebSocket client: {websocket.client if hasattr(websocket, 'client') else 'N/A'}")
    logger.info(f"[AUDIO_DEBUG] WebSocket URL: {websocket.url if hasattr(websocket, 'url') else 'N/A'}")
    
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        logger.error(f"[AUDIO_DEBUG] Twilio manager not available for Media Stream WebSocket")
        try:
            await websocket.close()
        except:
            pass
        return
    
    voice_handler = twilio_manager.voice_handler
    
    try:
        await websocket.accept()
        logger.info(f"[AUDIO_DEBUG] Media Stream WebSocket connected for call {call_sid}")
    except Exception as e:
        logger.error(f"[AUDIO_DEBUG] Error accepting WebSocket for call {call_sid}: {e}", exc_info=True)
        return
    
    try:
        while True:
            # Receive JSON messages from Twilio Media Streams
            data = await websocket.receive_json()
            event = data.get('event')
            
            if event == 'connected':
                logger.info(f"[AUDIO_DEBUG] Media stream connected for call {call_sid}")
            elif event == 'start':
                logger.info(f"[AUDIO_DEBUG] Media stream started for call {call_sid}")
                # Store Twilio Media Streams WebSocket and streamSid for sending audio back
                stream_sid = data.get('start', {}).get('streamSid')
                if stream_sid:
                    voice_handler.twilio_media_websockets[call_sid] = {
                        'websocket': websocket,
                        'streamSid': stream_sid
                    }
                    logger.info(f"[TTS_STREAM] Stored Twilio Media Stream for call {call_sid}, streamSid: {stream_sid}")
                    
                    # Send pending greeting if available
                    if call_sid in voice_handler.pending_greetings:
                        greeting = voice_handler.pending_greetings[call_sid]
                        logger.info(f"[TTS_STREAM] Sending pending greeting for call {call_sid}")
                        try:
                            await stream_tts_to_twilio(voice_handler, call_sid, greeting)
                            del voice_handler.pending_greetings[call_sid]
                        except Exception as e:
                            logger.error(f"[TTS_STREAM] Error sending pending greeting: {e}", exc_info=True)
                else:
                    logger.warning(f"[TTS_STREAM] No streamSid in start event for call {call_sid}")
            elif event == 'media':
                # Extract base64 audio payload (incoming audio from caller)
                media_payload = data.get('media', {}).get('payload')
                if media_payload:
                    # Process incoming audio if needed (currently handled by transcription callbacks)
                    pass
            elif event == 'stop':
                logger.info(f"[AUDIO_DEBUG] Media stream stopped for call {call_sid}")
                # Clean up Deepgram TTS connection
                if call_sid in voice_handler.deepgram_tts_connections:
                    try:
                        voice_handler.deepgram_tts_connections[call_sid].finish()
                        logger.info(f"[TTS_STREAM] Closed Deepgram TTS connection for call {call_sid}")
                    except Exception as e:
                        logger.error(f"[TTS_STREAM] Error closing Deepgram TTS connection: {e}")
                    del voice_handler.deepgram_tts_connections[call_sid]
                # Clean up Twilio Media Streams connection
                if call_sid in voice_handler.twilio_media_websockets:
                    del voice_handler.twilio_media_websockets[call_sid]
                    logger.info(f"[TTS_STREAM] Cleaned up Twilio Media Stream for call {call_sid}")
                # Clean up pending greeting
                if call_sid in voice_handler.pending_greetings:
                    del voice_handler.pending_greetings[call_sid]
                break
                
    except WebSocketDisconnect:
        logger.info(f"[AUDIO_DEBUG] Media Stream WebSocket disconnected for call {call_sid}")
        # Clean up Deepgram TTS connection
        if call_sid in voice_handler.deepgram_tts_connections:
            try:
                voice_handler.deepgram_tts_connections[call_sid].finish()
                logger.info(f"[TTS_STREAM] Closed Deepgram TTS connection for call {call_sid}")
            except Exception as e:
                logger.error(f"[TTS_STREAM] Error closing Deepgram TTS connection: {e}")
            del voice_handler.deepgram_tts_connections[call_sid]
        # Clean up Twilio Media Streams connection
        if call_sid in voice_handler.twilio_media_websockets:
            del voice_handler.twilio_media_websockets[call_sid]
            logger.info(f"[TTS_STREAM] Cleaned up Twilio Media Stream for call {call_sid}")
        # Clean up pending greeting
        if call_sid in voice_handler.pending_greetings:
            del voice_handler.pending_greetings[call_sid]
    except Exception as e:
        logger.error(f"[AUDIO_DEBUG] Error in Media Stream WebSocket: {e}", exc_info=True)
        # Clean up on error
        if call_sid in voice_handler.twilio_media_websockets:
            del voice_handler.twilio_media_websockets[call_sid]
        if call_sid in voice_handler.pending_greetings:
            del voice_handler.pending_greetings[call_sid]

