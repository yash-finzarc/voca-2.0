import logging
import time
import asyncio
import base64
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, JSONResponse
from twilio.twiml.voice_response import VoiceResponse, Start, Stream, Transcription, Gather, Pause, Connect
import numpy as np

from src.voca.api.state import app_state
from src.voca.Twilio.twilio_config import get_twilio_config
from src.voca.config import Config
from src.voca.Twilio.twilio_voice import deepgramtts, stream_tts_to_twilio
from src.voca.Twilio.webrtc import WebRTCSession, DeepgramSTTClient

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
    """Handle outbound call TwiML using WebRTC-first architecture."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        logger.error("[WebRTC] Twilio manager not available")
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
            "name_attempt_count": 0,
            "organization_id": org_id
        }

    # Create TwiML response
    response = VoiceResponse()

    # Generate greeting from system prompt (Step 3)
    try:
        org_id = form_data.get('organization_id') or app_state.get_orchestrator().default_organization_id
        greeting = voice_handler.orchestrator.generate_greeting(
            conversation_id=call_sid,
            organization_id=org_id
        )
        logger.info(f"[WebRTC] Generated greeting for outbound call {call_sid}: {greeting}")
    except Exception as e:
        logger.error(f"[WebRTC] Error generating greeting: {e}")
        greeting = "Hello! This is VOCA calling. How can I help you today?"

    # Store greeting for WebRTC session
    voice_handler.pending_greetings[call_sid] = greeting

    # Connect call to WebRTC (Step 1)
    config = get_twilio_config()
    webhook_url = config.get_webhook_url()
    base_url = webhook_url.replace('/webhook/voice', '').replace('/outbound', '')
    
    # Convert to WebSocket URL for WebRTC connection
    if base_url.startswith('http://'):
        wss_base_url = base_url.replace('http://', 'wss://')
    elif base_url.startswith('https://'):
        wss_base_url = base_url.replace('https://', 'wss://')
    elif not base_url.startswith('wss://'):
        wss_base_url = f"wss://{base_url.lstrip('/')}"
    else:
        wss_base_url = base_url
    
    # Connect to WebRTC endpoint (Step 1)
    # CRITICAL: Use ACTUAL call_sid in URL - Twilio does NOT substitute {CallSid} in Stream URLs
    stream_url = f"{wss_base_url}/webrtc/{call_sid}"
    # Use <Connect><Stream> for WebRTC connection
    # NOTE: For testing, you can change track to 'inbound_track' to only receive audio
    # For production, use 'both_tracks' to send and receive audio
    track_mode = os.getenv('TWILIO_STREAM_TRACK', 'both_tracks')  # Default: both_tracks, can be 'inbound_track' for testing
    connect = Connect()
    stream = Stream(
        url=stream_url, 
        track=track_mode, 
        parameters={'call_sid': call_sid}
    )
    logger.info(f"[WebRTC] Stream URL with actual CallSid: {stream_url}")
    logger.info(f"[WebRTC] Track mode: {track_mode} (set TWILIO_STREAM_TRACK env var to change)")
    logger.info(f"[TWiML_DEBUG] Stream track parameter: {track_mode}")
    connect.append(stream)
    response.append(connect)
    
    # Log the actual TwiML being sent to Twilio
    twiml_xml = str(response)
    logger.info(f"[WebRTC] Enabled WebRTC connection for outbound call {call_sid}")
    logger.info(f"[WebRTC] Stream URL with actual CallSid: {stream_url}")
    logger.info(f"[TWiML_DEBUG] TwiML XML for call {call_sid}:\n{twiml_xml}")
    
    # Verify TwiML contains <Connect><Stream> and actual CallSid in URL
    if "<Connect>" in twiml_xml and "<Stream" in twiml_xml:
        logger.info(f"[TWiML_DEBUG] ✓ TwiML contains <Connect><Stream> - Twilio should connect")
        if call_sid in twiml_xml:
            logger.info(f"[TWiML_DEBUG] ✓ Stream URL contains actual CallSid: {call_sid}")
        else:
            logger.error(f"[TWiML_DEBUG] ✗ Stream URL does NOT contain actual CallSid - check URL format!")
        if "{CallSid}" in twiml_xml or "{{CallSid}}" in twiml_xml:
            logger.error(f"[TWiML_DEBUG] ✗ Stream URL contains {CallSid} variable - Twilio will NOT substitute it!")
    else:
        logger.error(f"[TWiML_DEBUG] ✗ TwiML MISSING <Connect><Stream> - Twilio will NOT connect!")
    
    return Response(content=twiml_xml, media_type="text/xml")


@router.post("/webhook/voice")
async def handle_incoming_call_webhook(request: Request):
    """Handle incoming Twilio call webhook using WebRTC-first architecture."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        logger.error("[WebRTC] Twilio manager not available")
        return Response(content=str(response), media_type="text/xml")

    voice_handler = twilio_manager.voice_handler

    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")

    logger.info(f"[WebRTC] Incoming call from {from_number}, SID: {call_sid}")

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
            "name_attempt_count": 0,
            "organization_id": org_id
        }

    # Create TwiML response
    response = VoiceResponse()

    # Generate welcome message from system prompt (Step 3)
    try:
        org_id = form_data.get('organization_id') or app_state.get_orchestrator().default_organization_id
        greeting = voice_handler.orchestrator.generate_greeting(
            conversation_id=call_sid,
            organization_id=org_id
        )
        logger.info(f"[WebRTC] Generated greeting for call {call_sid}: {greeting}")
    except Exception as e:
        logger.error(f"[WebRTC] Error generating greeting: {e}")
        greeting = "Hello! How can I help you today?"

    # Store greeting for WebRTC session
    voice_handler.pending_greetings[call_sid] = greeting

    # Connect call to WebRTC (Step 1) - Use <Connect> with WebRTC gateway URL
    config = get_twilio_config()
    webhook_url = config.get_webhook_url()
    base_url = webhook_url.replace('/webhook/voice', '')
    
    # Connect to WebRTC endpoint (Step 1)
    # Convert to WebSocket URL for WebRTC connection
    if base_url.startswith('http://'):
        wss_base_url = base_url.replace('http://', 'wss://')
    elif base_url.startswith('https://'):
        wss_base_url = base_url.replace('https://', 'wss://')
    elif not base_url.startswith('wss://'):
        wss_base_url = f"wss://{base_url.lstrip('/')}"
    else:
        wss_base_url = base_url
    
    # CRITICAL: Use ACTUAL call_sid in URL - Twilio does NOT substitute {CallSid} in Stream URLs
    stream_url = f"{wss_base_url}/webrtc/{call_sid}"
    # Use <Connect><Stream> for WebRTC connection
    # NOTE: For testing, you can change track to 'inbound_track' to only receive audio
    # For production, use 'both_tracks' to send and receive audio
    track_mode = os.getenv('TWILIO_STREAM_TRACK', 'both_tracks')  # Default: both_tracks, can be 'inbound_track' for testing
    connect = Connect()
    stream = Stream(
        url=stream_url, 
        track=track_mode, 
        parameters={'call_sid': call_sid}
    )
    logger.info(f"[WebRTC] Stream URL with actual CallSid: {stream_url}")
    connect.append(stream)
    response.append(connect)
    
    # Log the actual TwiML being sent to Twilio
    twiml_xml = str(response)
    logger.info(f"[WebRTC] Enabled WebRTC connection for call {call_sid}")
    logger.info(f"[TWiML_DEBUG] TwiML XML for call {call_sid}:\n{twiml_xml}")
    
    # Verify TwiML contains <Connect><Stream> and actual CallSid in URL
    if "<Connect>" in twiml_xml and "<Stream" in twiml_xml:
        logger.info(f"[TWiML_DEBUG] ✓ TwiML contains <Connect><Stream> - Twilio should connect")
        if call_sid in twiml_xml:
            logger.info(f"[TWiML_DEBUG] ✓ Stream URL contains actual CallSid: {call_sid}")
        else:
            logger.error(f"[TWiML_DEBUG] ✗ Stream URL does NOT contain actual CallSid - check URL format!")
        if "{CallSid}" in twiml_xml or "{{CallSid}}" in twiml_xml:
            logger.error(f"[TWiML_DEBUG] ✗ Stream URL contains {CallSid} variable - Twilio will NOT substitute it!")
    else:
        logger.error(f"[TWiML_DEBUG] ✗ TwiML MISSING <Connect><Stream> - Twilio will NOT connect!")
    
    return Response(content=twiml_xml, media_type="text/xml")


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


@router.websocket("/webrtc/{call_sid}")
async def handle_webrtc_websocket(websocket: WebSocket, call_sid: str):
    """Handle WebRTC WebSocket connection for real-time AI voice calls (WebRTC-first architecture)."""
    logger.info(f"[WebRTC] ===== WebRTC WebSocket handler CALLED for call {call_sid} =====")
    
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        logger.error(f"[WebRTC] Twilio manager not available for WebRTC WebSocket")
        try:
            await websocket.close()
        except:
            pass
        return
    
    voice_handler = twilio_manager.voice_handler
    
    try:
        await websocket.accept()
        logger.info(f"[WebRTC] ===== WebRTC WebSocket ACCEPTED for call {call_sid} =====")
        logger.info(f"[WebRTC] WebSocket client: {websocket.client}")
        logger.info(f"[WebRTC] WebSocket URL: {websocket.url}")
        logger.info(f"[WebRTC] Waiting for Twilio stream events...")
    except Exception as e:
        logger.error(f"[WebRTC] Error accepting WebSocket for call {call_sid}: {e}", exc_info=True)
        return
    
    # Initialize call state if not exists
    if call_sid not in voice_handler.active_calls:
        voice_handler.active_calls[call_sid] = {
            "status": "connected",
            "start_time": time.time(),
            "welcome_sent": False,
            "turn_count": 0
        }
    
    call_state = voice_handler.active_calls[call_sid]
    org_id = call_state.get("organization_id") or app_state.get_orchestrator().default_organization_id
    
    # Create WebRTC session (Step 2)
    # Note: Since Twilio uses Media Streams (not true WebRTC), we'll simulate WebRTC behavior
    # by handling the Media Streams WebSocket as if it were WebRTC
    
    def handle_transcript(transcript: str, is_final: bool):
        """Handle transcription from Deepgram STT."""
        if not transcript.strip():
            return
        
        logger.info(f"[WebRTC] Transcription ({'final' if is_final else 'interim'}): {transcript}")
        
        if is_final:
            # Only process final transcripts
            app_state._log_callback("=" * 80)
            app_state._log_callback(f"[USER] Call {call_sid} - Transcription: \"{transcript}\"")
            app_state._log_callback("=" * 80)
            
            # Process through VOCA orchestrator (Step 7)
            try:
                ai_response = voice_handler.orchestrator.generate_reply(
                    transcript,
                    conversation_id=call_sid,
                    call_sid=call_sid,
                    organization_id=org_id,
                )
                logger.info(f"[WebRTC] AI Response: {ai_response}")
                app_state._log_callback("=" * 80)
                app_state._log_callback(f"[AI] Call {call_sid} - AI Response: \"{ai_response}\"")
                app_state._log_callback("=" * 80)
                
                # Stream TTS back to user (Step 8)
                logger.info(f"[WebRTC] ===== Starting AI response TTS =====")
                logger.info(f"[WebRTC] AI response text: {ai_response}")
                asyncio.create_task(stream_tts_to_twilio(voice_handler, call_sid, ai_response))
                
                call_state['turn_count'] = call_state.get('turn_count', 0) + 1
            except Exception as e:
                logger.error(f"[WebRTC] Error processing transcription: {e}", exc_info=True)
    
    def handle_audio_input(audio_data):
        """Handle incoming audio (Step 5)."""
        # Audio is being processed by Deepgram STT via WebRTC session
        pass
    
    # For now, we'll use Media Streams but treat it as WebRTC
    # Store the WebSocket for TTS streaming
    stream_sid = None
    
    try:
        while True:
            # Receive JSON messages from Twilio (treating as WebRTC-like)
            data = await websocket.receive_json()
            event = data.get('event')
            
            if event == 'connected':
                logger.info(f"[WebRTC] ===== 'connected' event received for call {call_sid} =====")
                logger.info(f"[WebRTC] Connection data: {json.dumps(data, indent=2)}")
                logger.info(f"[WebRTC] ✓ Twilio WebSocket connection established - waiting for 'start' event...")
            elif event == 'start':
                logger.info(f"[WebRTC] ===== 'start' event received for call {call_sid} =====")
                logger.info(f"[WebRTC] Start event data: {json.dumps(data, indent=2)}")
                stream_sid = data.get('start', {}).get('streamSid')
                if stream_sid:
                    voice_handler.twilio_media_websockets[call_sid] = {
                        'websocket': websocket,
                        'streamSid': stream_sid
                    }
                    logger.info(f"[WebRTC] ✓ Stream started - streamSid: {stream_sid}")
                    logger.info(f"[WebRTC] ✓ WebSocket stored - ready to send/receive audio")
                    logger.info(f"[WebRTC] Call state: {call_state.get('status', 'unknown')}")
                    logger.info(f"[WebRTC] ===== AUDIO PIPELINE IS NOW ACTIVE =====")
                    
                    # Deliver welcome message (Step 4) - ONLY after stream start
                    if call_sid in voice_handler.pending_greetings and not call_state.get('welcome_sent', False):
                        greeting = voice_handler.pending_greetings[call_sid]
                        welcome_start_time = time.time()
                        logger.info(f"[WebRTC] ===== DELIVERING WELCOME MESSAGE =====")
                        logger.info(f"[WebRTC] Call SID: {call_sid}")
                        logger.info(f"[WebRTC] StreamSid: {stream_sid}")
                        logger.info(f"[WebRTC] Welcome message: \"{greeting}\"")
                        logger.info(f"[WebRTC] WebSocket ready: {websocket is not None}")
                        logger.info(f"[WebRTC] Twilio Media Streams connection: {call_sid in voice_handler.twilio_media_websockets}")
                        app_state._log_callback("=" * 80)
                        app_state._log_callback(f"[AI] Call {call_sid} - Welcome Message: \"{greeting}\"")
                        app_state._log_callback("=" * 80)
                        
                        try:
                            # Verify WebSocket connection is ready
                            if call_sid not in voice_handler.twilio_media_websockets:
                                logger.error(f"[WebRTC] ✗ CRITICAL: Twilio Media Streams WebSocket not found for call {call_sid}")
                                logger.error(f"[WebRTC] Available streams: {list(voice_handler.twilio_media_websockets.keys())}")
                                raise Exception("Twilio Media Streams WebSocket not available")
                            
                            success = await stream_tts_to_twilio(voice_handler, call_sid, greeting)
                            welcome_duration = time.time() - welcome_start_time
                            
                            if success:
                                logger.info(f"[WebRTC] ===== WELCOME MESSAGE DELIVERED SUCCESSFULLY =====")
                                logger.info(f"[WebRTC] ✓ Greeting TTS streamed in {welcome_duration:.3f}s")
                                logger.info(f"[WebRTC] ✓ Audio should now be audible on the call")
                                call_state['welcome_sent'] = True
                                call_state['turn_count'] = call_state.get('turn_count', 0) + 1
                                del voice_handler.pending_greetings[call_sid]
                            else:
                                logger.error(f"[WebRTC] ✗ FAILED to stream welcome message TTS for call {call_sid}")
                                logger.error(f"[WebRTC] Duration: {welcome_duration:.3f}s")
                                logger.error(f"[WebRTC] Check TTS_STREAM logs above for error details")
                                logger.error(f"[WebRTC] WebSocket state: {call_sid in voice_handler.twilio_media_websockets}")
                        except Exception as e:
                            welcome_duration = time.time() - welcome_start_time
                            logger.error(f"[WebRTC] ✗ ERROR delivering welcome message after {welcome_duration:.3f}s: {e}", exc_info=True)
                            logger.error(f"[WebRTC] Call SID: {call_sid}")
                            logger.error(f"[WebRTC] StreamSid: {stream_sid}")
                            logger.error(f"[WebRTC] WebSocket available: {call_sid in voice_handler.twilio_media_websockets}")
                else:
                    logger.error(f"[WebRTC] No streamSid in start event for call {call_sid} - cannot send audio!")
            elif event == 'media':
                # Incoming audio from caller (Step 5 - Live User Speech Capture)
                media_payload = data.get('media', {}).get('payload')
                if media_payload:
                    try:
                        # Log inbound media frame with timestamps
                        payload_size = len(media_payload)
                        timestamp = time.time()
                        if not hasattr(handle_webrtc_websocket, '_media_frame_count'):
                            handle_webrtc_websocket._media_frame_count = {}
                        if not hasattr(handle_webrtc_websocket, '_first_frame_time'):
                            handle_webrtc_websocket._first_frame_time = {}
                        if call_sid not in handle_webrtc_websocket._media_frame_count:
                            handle_webrtc_websocket._media_frame_count[call_sid] = 0
                            handle_webrtc_websocket._first_frame_time[call_sid] = timestamp
                        handle_webrtc_websocket._media_frame_count[call_sid] += 1
                        
                        frame_num = handle_webrtc_websocket._media_frame_count[call_sid]
                        elapsed = timestamp - handle_webrtc_websocket._first_frame_time[call_sid]
                        
                        if frame_num <= 5 or frame_num % 50 == 0:  # Log first 5, then every 50th
                            logger.info(f"[WebRTC] ✓ Inbound media frame #{frame_num} received at {timestamp:.3f}s (elapsed: {elapsed:.3f}s): {payload_size} bytes (base64)")
                        
                        # Decode base64 audio (μ-law, 8kHz from Twilio)
                        decode_start = time.time()
                        audio_bytes = base64.b64decode(media_payload)
                        audio_bytes_size = len(audio_bytes)
                        decode_time = (time.time() - decode_start) * 1000  # ms
                        logger.debug(f"[WebRTC] Decoded audio bytes: {audio_bytes_size} bytes (μ-law) in {decode_time:.2f}ms")
                        
                        if audio_bytes_size == 0:
                            logger.warning(f"[WebRTC] Empty audio payload received for call {call_sid}")
                            continue
                        
                        # Convert μ-law to linear16 for Deepgram STT
                        import numpy as np
                        mu_law_array = np.frombuffer(audio_bytes, dtype=np.uint8)
                        # Simple μ-law decoder
                        linear = np.zeros(len(mu_law_array), dtype=np.int16)
                        for i in range(len(mu_law_array)):
                            mu = mu_law_array[i]
                            sign_bit = (mu & 0x80) >> 7
                            exponent_bits = (mu & 0x70) >> 4
                            mantissa_bits = mu & 0x0F
                            
                            if exponent_bits == 0:
                                sample = (mantissa_bits << 1) + 33
                            else:
                                sample = ((mantissa_bits << 1) + 33) << (exponent_bits - 1)
                            
                            if sign_bit == 1:
                                sample = -sample
                            
                            linear[i] = np.int16(sample - 33)
                        
                        audio_array = (linear * 16).astype(np.int16)
                        
                        # Send to Deepgram STT (Step 6 - Real-Time Transcription)
                        # We'll set up Deepgram STT connection per call
                        if call_sid not in voice_handler.deepgram_stt_connections:
                            # Initialize Deepgram STT for this call
                            if Config.deepgram_api_key:
                                stt_client = DeepgramSTTClient(
                                    on_transcript=handle_transcript,
                                    api_key=Config.deepgram_api_key
                                )
                                stt_client.start()
                                voice_handler.deepgram_stt_connections[call_sid] = stt_client
                                logger.info(f"[WebRTC] Started Deepgram STT for call {call_sid}")
                        
                        # Send audio to Deepgram STT
                        if call_sid in voice_handler.deepgram_stt_connections:
                            stt_client = voice_handler.deepgram_stt_connections[call_sid]
                            # Convert to bytes (16-bit PCM)
                            pcm_bytes = audio_array.astype(np.int16).tobytes()
                            pcm_size = len(pcm_bytes)
                            stt_timestamp = time.time()
                            logger.debug(f"[WebRTC] Sending {pcm_size} bytes to Deepgram STT (PCM16, {len(audio_array)} samples) at {stt_timestamp:.3f}s")
                            stt_client.send_audio(pcm_bytes)
                        else:
                            logger.warning(f"[WebRTC] Deepgram STT not initialized for call {call_sid}, skipping audio")
                            
                    except Exception as e:
                        logger.error(f"[WebRTC] Error processing media: {e}", exc_info=True)
            elif event == 'stop':
                logger.info(f"[WebRTC] WebRTC stream stopped for call {call_sid}")
                # Cleanup (Step 10 - Call Termination & Cleanup)
                if call_sid in voice_handler.twilio_media_websockets:
                    del voice_handler.twilio_media_websockets[call_sid]
                if call_sid in voice_handler.pending_greetings:
                    del voice_handler.pending_greetings[call_sid]
                # Close Deepgram STT connection
                if call_sid in voice_handler.deepgram_stt_connections:
                    try:
                        voice_handler.deepgram_stt_connections[call_sid].stop()
                        logger.info(f"[WebRTC] Closed Deepgram STT for call {call_sid}")
                    except Exception as e:
                        logger.error(f"[WebRTC] Error closing Deepgram STT: {e}")
                    del voice_handler.deepgram_stt_connections[call_sid]
                break
                
    except WebSocketDisconnect:
        logger.info(f"[WebRTC] WebRTC WebSocket disconnected for call {call_sid}")
        # Cleanup
        if call_sid in voice_handler.twilio_media_websockets:
            del voice_handler.twilio_media_websockets[call_sid]
        if call_sid in voice_handler.pending_greetings:
            del voice_handler.pending_greetings[call_sid]
        # Close Deepgram STT connection
        if call_sid in voice_handler.deepgram_stt_connections:
            try:
                voice_handler.deepgram_stt_connections[call_sid].stop()
                logger.info(f"[WebRTC] Closed Deepgram STT for call {call_sid}")
            except Exception as e:
                logger.error(f"[WebRTC] Error closing Deepgram STT: {e}")
            del voice_handler.deepgram_stt_connections[call_sid]
    except Exception as e:
        logger.error(f"[WebRTC] Error in WebRTC WebSocket: {e}", exc_info=True)
        # Cleanup on error
        if call_sid in voice_handler.twilio_media_websockets:
            del voice_handler.twilio_media_websockets[call_sid]
        if call_sid in voice_handler.pending_greetings:
            del voice_handler.pending_greetings[call_sid]
        # Close Deepgram STT connection
        if call_sid in voice_handler.deepgram_stt_connections:
            try:
                voice_handler.deepgram_stt_connections[call_sid].stop()
            except:
                pass
            del voice_handler.deepgram_stt_connections[call_sid]


@router.websocket("/media/{call_sid}")
async def handle_media_stream_websocket(websocket: WebSocket, call_sid: str):
    """DEPRECATED: Old Media Streams endpoint - use /webrtc/{call_sid} instead."""
    logger.error(f"[DEPRECATED] Old /media/{call_sid} endpoint called - this endpoint is deprecated. Use /webrtc/{call_sid} instead.")
    try:
        await websocket.accept()
        await websocket.send_json({
            "error": "DEPRECATED_ENDPOINT",
            "message": "This endpoint is deprecated. Please use /webrtc/{call_sid} instead.",
            "call_sid": call_sid
        })
        await websocket.close(code=1008, reason="Deprecated endpoint - use /webrtc/ instead")
    except Exception as e:
        logger.error(f"[DEPRECATED] Error handling deprecated endpoint: {e}")
        try:
            await websocket.close()
        except:
            pass


@router.get("/webrtc/{call_sid}/test-audio")
async def test_audio_endpoint(call_sid: str):
    """
    Test endpoint to verify WebRTC audio setup.
    Returns diagnostic information about the call's audio state.
    """
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        return JSONResponse({"error": "Twilio manager not available"})
    
    voice_handler = twilio_manager.voice_handler
    
    # Check call state
    call_info = {
        "call_sid": call_sid,
        "has_active_call": call_sid in voice_handler.active_calls,
        "has_websocket": call_sid in voice_handler.twilio_media_websockets,
        "has_pending_greeting": call_sid in voice_handler.pending_greetings,
        "has_stt_connection": call_sid in voice_handler.deepgram_stt_connections,
    }
    
    if call_sid in voice_handler.active_calls:
        call_info["call_state"] = voice_handler.active_calls[call_sid]
    
    if call_sid in voice_handler.twilio_media_websockets:
        stream_info = voice_handler.twilio_media_websockets[call_sid]
        call_info["stream_sid"] = stream_info.get("streamSid")
        call_info["websocket_connected"] = stream_info.get("websocket") is not None
    
    return JSONResponse(call_info)


@router.post("/webrtc/{call_sid}/send-test-tone")
async def send_test_tone(call_sid: str):
    """
    Send a 1-second static PCM tone to test WebSocket audio pipeline.
    This bypasses TTS/LLM to verify raw audio transmission works.
    """
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        return JSONResponse({"error": "Twilio manager not available"})
    
    voice_handler = twilio_manager.voice_handler
    
    if call_sid not in voice_handler.twilio_media_websockets:
        return JSONResponse({"error": "No active WebSocket connection for this call"})
    
    try:
        twilio_stream = voice_handler.twilio_media_websockets[call_sid]
        twilio_websocket = twilio_stream['websocket']
        stream_sid = twilio_stream['streamSid']
        
        # Generate 1 second of 440Hz tone (A4 note) at 8kHz μ-law
        # 1 second = 8000 samples at 8kHz
        # Generate sine wave: sin(2π * 440 * t)
        import numpy as np
        sample_rate = 8000
        duration = 1.0  # 1 second
        frequency = 440  # A4 note
        
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        sine_wave = np.sin(2 * np.pi * frequency * t)
        
        # Convert to μ-law (8-bit)
        # First normalize to [-1, 1], then scale to int16, then convert to μ-law
        audio_int16 = (sine_wave * 32767).astype(np.int16)
        
        # Simple μ-law encoder
        def encode_mulaw(sample):
            """Encode 16-bit linear PCM to 8-bit μ-law"""
            sign = 0 if sample >= 0 else 0x80
            sample = abs(sample)
            if sample > 32635:
                sample = 32635
            sample += 0x84
            exponent = 0
            exp_mask = 0x4000
            while (sample & exp_mask) == 0 and exponent < 7:
                exponent += 1
                exp_mask >>= 1
            mantissa = (sample >> (exponent + 3)) & 0x0F
            return sign | ((exponent + 1) << 4) | mantissa
        
        mu_law_audio = np.array([encode_mulaw(s) for s in audio_int16], dtype=np.uint8)
        
        # Send in 20ms chunks (160 bytes at 8kHz)
        chunk_size = 160
        total_chunks = 0
        total_bytes = 0
        
        logger.info(f"[TEST_TONE] Sending 1-second test tone (440Hz) for call {call_sid}")
        logger.info(f"[TEST_TONE] Total audio: {len(mu_law_audio)} bytes, will send in {len(mu_law_audio) // chunk_size} chunks")
        
        for i in range(0, len(mu_law_audio), chunk_size):
            chunk = mu_law_audio[i:i + chunk_size]
            audio_base64 = base64.b64encode(chunk.tobytes()).decode('utf-8')
            
            message = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {
                    "payload": audio_base64
                }
            }
            
            await twilio_websocket.send_json(message)
            total_chunks += 1
            total_bytes += len(chunk)
            
            if total_chunks % 10 == 0:  # Log every 200ms
                logger.info(f"[TEST_TONE] Sent {total_chunks} chunks ({total_bytes} bytes)")
        
        logger.info(f"[TEST_TONE] ✓ Test tone sent: {total_chunks} chunks, {total_bytes} bytes total")
        
        return JSONResponse({
            "status": "success",
            "message": "Test tone sent",
            "chunks": total_chunks,
            "bytes": total_bytes,
            "duration_seconds": duration,
            "frequency_hz": frequency
        })
        
    except Exception as e:
        logger.error(f"[TEST_TONE] Error sending test tone: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

