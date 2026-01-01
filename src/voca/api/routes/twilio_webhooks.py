import logging
import time
import asyncio
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum

from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, JSONResponse
import numpy as np

from src.voca.api.state import app_state
from src.voca.Twilio.twilio_config import get_twilio_config
from src.voca.config import Config
# Removed unused imports: deepgramtts, stream_tts_to_twilio, WebRTCSession, DeepgramSTTClient
# These were used by the old STT-LLM-TTS pipeline which is now replaced by custom LLM pipeline

# Import custom LLM pipeline components
from src.voca.orchestrator import VocaOrchestrator
from src.voca.services.sarvam_stt import SarvamSTTClient
from src.voca.services.sarvam_tts import SarvamTTSClient
from src.voca.audio_utils import mulaw_to_pcm, pcm_to_mulaw

router = APIRouter()
logger = logging.getLogger(__name__)


# def _append_vad_gather(response: VoiceResponse, base_url: str, call_sid: str, language: str = "en-IN"):
#     """Attach a speech-only Gather to keep the call alive using VAD (no barge-in)."""
#     action_url = f"{base_url}/gather/continue/{call_sid}"
#     gather = Gather(
#         input="speech",
#         speech_timeout="auto",  # Let VAD decide end-of-speech
#         action=action_url,
#         method="POST",
#         language=language,
#         bargeIn=False,  # Ensure greeting finishes before listening
#     )
#     response.append(gather)
#     return response


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
    """
    Handle outbound Twilio call webhook.
    Note: Since TwiML Bin is used, this endpoint is kept for compatibility but returns minimal response.
    Twilio should be configured to use the TwiML Bin URL directly.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    to_number = form_data.get("To")
    
    logger.info(f"[DEEPGRAM_AGENT] Outbound call to {to_number}, SID: {call_sid} (TwiML Bin should handle this)")
    
    # Return minimal response - TwiML Bin handles the actual TwiML
    return PlainTextResponse(content="OK", status_code=200)


# @router.post("/call/status")
# async def handle_call_status_callback(request: Request):
#     """Handle call status callbacks from Twilio to track call state."""
#     form_data = await request.form()
#     call_sid = form_data.get("CallSid")
#     call_status = form_data.get("CallStatus")
#     call_duration = form_data.get("CallDuration", "0")
    
#     logger.info(f"[CALL_STATUS] ===== Call Status Callback =====")
#     logger.info(f"[CALL_STATUS] Call SID: {call_sid}")
#     logger.info(f"[CALL_STATUS] Status: {call_status}")
#     logger.info(f"[CALL_STATUS] Duration: {call_duration}s")
#     logger.info(f"[CALL_STATUS] All form data: {dict(form_data)}")
    
#     # Update call state if we have it
#     twilio_manager = app_state.get_twilio_manager()
#     if twilio_manager and call_sid:
#         voice_handler = twilio_manager.voice_handler
#         if call_sid in voice_handler.active_calls:
#             voice_handler.active_calls[call_sid]["status"] = call_status
#             voice_handler.active_calls[call_sid]["duration"] = call_duration
#             logger.info(f"[CALL_STATUS] Updated call state for {call_sid}: {call_status}")
    
#     # Log important status changes
#     if call_status == "answered":
#         logger.info(f"[CALL_STATUS] ⚠️  Call {call_sid} was ANSWERED - Media Streams should connect now!")
#     elif call_status == "completed":
#         logger.info(f"[CALL_STATUS] ⚠️  Call {call_sid} COMPLETED after {call_duration}s")
#     elif call_status in ["busy", "no-answer", "failed", "canceled"]:
#         logger.warning(f"[CALL_STATUS] ⚠️  Call {call_sid} ended with status: {call_status} - Media Streams will NOT connect")
    
#     return Response(content="OK", media_type="text/plain")


@router.post("/webhook/voice")
async def handle_incoming_call_webhook(request: Request):
    """
    Handle incoming Twilio call webhook.
    Note: Since TwiML Bin is used, this endpoint is kept for compatibility but returns minimal response.
    Twilio should be configured to use the TwiML Bin URL directly.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")
    
    logger.info(f"[DEEPGRAM_AGENT] Incoming call from {from_number}, SID: {call_sid} (TwiML Bin should handle this)")
    
    # Return minimal response - TwiML Bin handles the actual TwiML
    return PlainTextResponse(content="OK", status_code=200)


# @router.post("/gather/continue/{call_sid}")
# async def handle_gather_continue(call_sid: str, request: Request):
#     """
#     Twilio posts here after a speech Gather completes. We optionally TTS an AI reply, then
#     re-attach another VAD Gather so the call stays alive and continues listening.
#     """
#     twilio_manager = app_state.get_twilio_manager()
#     if not twilio_manager:
#         response = VoiceResponse()
#         logger.error("[GATHER] Twilio manager not available")
#         return Response(content=str(response), media_type="text/xml")

#     voice_handler = twilio_manager.voice_handler
#     form_data = await request.form()
#     speech_result = (form_data.get("SpeechResult") or "").strip()
#     confidence = form_data.get("Confidence", "")
#     language = form_data.get("Language", "") or "en-IN"

#     logger.info(f"[GATHER] Call {call_sid}: SpeechResult='{speech_result}', Confidence={confidence}, Language={language}")

#     response = VoiceResponse()

#     # If we got speech text, generate an AI reply and play it before continuing to listen.
#     if speech_result:
#         try:
#             org_id = None
#             if call_sid in voice_handler.active_calls:
#                 org_id = voice_handler.active_calls[call_sid].get('organization_id')
#             if not org_id:
#                 org_id = app_state.get_orchestrator().default_organization_id

#             ai_response = voice_handler.orchestrator.generate_reply(
#                 speech_result,
#                 conversation_id=call_sid,
#                 call_sid=call_sid,
#                 organization_id=org_id,
#             )
#             logger.info(f"[GATHER] AI Response: {ai_response}")

#             # Stream AI response via Deepgram TTS to Twilio Media Streams
#             try:
#                 streamed = await stream_tts_to_twilio(voice_handler, call_sid, ai_response)
#                 if not streamed:
#                     # Fallback to <Say> if streaming fails
#                     logger.warning(f"[GATHER] Streaming failed for AI response, using <Say> fallback")
#                     response.say(ai_response)
#             except Exception as tts_err:
#                 logger.error(f"[GATHER] TTS streaming failed, using <Say> fallback: {tts_err}")
#                 response.say(ai_response)
#         except Exception as e:
#             logger.error(f"[GATHER] Error processing speech result: {e}", exc_info=True)
#             response.pause(length=1)

#     # Re-attach Gather to keep VAD listening
#     config = get_twilio_config()
#     base_url = config.get_webhook_url().replace('/webhook/voice', '').replace('/outbound', '')
#     _append_vad_gather(response, base_url, call_sid, language=language or "en-IN")

#     return Response(content=str(response), media_type="text/xml")


# @router.post("/transcription/{call_sid}")
# async def handle_transcription(call_sid: str, request: Request):
#     """Handle real-time transcription callbacks from Twilio with Deepgram."""
#     twilio_manager = app_state.get_twilio_manager()
#     if not twilio_manager:
#         return PlainTextResponse("OK")

#     voice_handler = twilio_manager.voice_handler
#     form_data = await request.form()
    
#     # Extract transcription data
#     transcription_text = form_data.get('TranscriptionText', '')
#     transcription_status = form_data.get('TranscriptionStatus', '')
#     transcription_sid = form_data.get('TranscriptionSid', '')
#     confidence = form_data.get('Confidence', '0')
#     # Check for language in webhook (may not be present for all transcription services)
#     language = form_data.get('Language', None) or form_data.get('LanguageCode', None)
    
#     logger.info(f"[TRANSCRIPTION] Call {call_sid}: Status={transcription_status}, Text='{transcription_text}', Confidence={confidence}, Language={language or 'N/A'}")
    
#     # Only process completed transcriptions with text
#     if transcription_status == 'completed' and transcription_text and transcription_text.strip():
#         try:
#             # If language not in webhook, try to fetch from Twilio API using transcription_sid
#             if not language and transcription_sid:
#                 try:
#                     trans_obj = voice_handler.client.transcriptions(transcription_sid).fetch()
#                     language = getattr(trans_obj, 'language', None) or getattr(trans_obj, 'languageCode', None)
#                     if language:
#                         logger.info(f"[TRANSCRIPTION] Fetched language from API: {language}")
#                 except Exception as lang_e:
#                     logger.debug(f"[TRANSCRIPTION] Could not fetch language from API: {lang_e}")
            
#             # Process transcription through VOCA orchestrator
#             org_id = None
#             if call_sid in voice_handler.active_calls:
#                 org_id = voice_handler.active_calls[call_sid].get('organization_id')
#             if not org_id:
#                 org_id = app_state.get_orchestrator().default_organization_id
            
#             ai_response = voice_handler.orchestrator.generate_reply(
#                 transcription_text,
#                 conversation_id=call_sid,
#                 call_sid=call_sid,
#                 organization_id=org_id,
#             )
#             logger.info(f"[TRANSCRIPTION] AI Response: {ai_response}")
            
#             # Store transcription in call metadata
#             if call_sid in voice_handler.active_calls:
#                 if 'transcriptions' not in voice_handler.active_calls[call_sid]:
#                     voice_handler.active_calls[call_sid]['transcriptions'] = []
#                 voice_handler.active_calls[call_sid]['transcriptions'].append({
#                     'text': transcription_text,
#                     'status': transcription_status,
#                     'transcription_sid': transcription_sid,
#                     'confidence': confidence,
#                     'language': language,
#                     'languageCode': language,  # Alias for compatibility
#                     'timestamp': datetime.now(timezone.utc).isoformat()
#                 })
                
#                 # Log language detection when we have transcriptions with language
#                 if language:
#                     # Get all unique languages from all transcriptions for this call
#                     all_languages = []
#                     for trans in voice_handler.active_calls[call_sid]['transcriptions']:
#                         trans_lang = trans.get('language') or trans.get('languageCode')
#                         if trans_lang:
#                             all_languages.append(trans_lang)
#                     if all_languages:
#                         unique_languages = list(set(all_languages))
#                         logger.info(f"[CALL_INFO] Call {call_sid} - Detected Languages: {', '.join(unique_languages)}")
            
#             # Stream AI response via Deepgram TTS to Twilio Media Streams
#             try:
#                 streamed = await stream_tts_to_twilio(voice_handler, call_sid, ai_response)
#                 if not streamed:
#                     # Fallback to <Say> if streaming fails
#                     logger.warning(f"[TRANSCRIPTION] Streaming failed for AI response, using <Say> fallback")
#                     response = VoiceResponse()
#                     response.say(ai_response)
#                 else:
#                     # Return empty response - audio is streaming via Media Streams
#                     response = VoiceResponse()
#             except Exception as tts_err:
#                 logger.error(f"[TRANSCRIPTION] TTS streaming failed, using <Say> fallback: {tts_err}")
#                 response = VoiceResponse()
#                 response.say(ai_response)
            
#             # Return response - transcriptions will continue automatically
#             return Response(content=str(response), media_type='text/xml')
            
#         except Exception as e:
#             logger.error(f"[TRANSCRIPTION] Error processing transcription: {e}", exc_info=True)
#             # Return empty response with short pause to continue call
#             response = VoiceResponse()
#             response.pause(length=1)
#             return Response(content=str(response), media_type='text/xml')
#     else:
#         # For in-progress or empty transcriptions, just acknowledge
#         logger.debug(f"[TRANSCRIPTION] Ignoring transcription: status={transcription_status}, has_text={bool(transcription_text)}")
#         return PlainTextResponse("OK")


# # Removed /audio/tts endpoint - TTS now uses streaming via Media Streams WebSocket (no file storage)


# @router.get("/media/{call_sid}/test")
# async def test_media_stream_endpoint(call_sid: str):
#     """Test endpoint to verify Media Streams route is accessible."""
#     logger.info(f"[MEDIA_STREAM_TEST] Test endpoint accessed for call {call_sid}")
#     return {
#         "status": "ok",
#         "call_sid": call_sid,
#         "message": "Media Streams endpoint is accessible",
#         "websocket_url": f"wss://voca-2.duckdns.org/media/{call_sid}",
#         "note": "WebSocket endpoint should be at /media/{call_sid}",
#         "test_time": datetime.now(timezone.utc).isoformat()
#     }


# @router.post("/media/status/{call_sid}")
# async def handle_media_stream_status(call_sid: str, request: Request):
#     """Handle Media Streams status callbacks from Twilio."""
#     form_data = await request.form()
#     status = form_data.get('Status', 'unknown')
#     error_code = form_data.get('ErrorCode', '')
#     error_message = form_data.get('ErrorMessage', '')
    
#     logger.info(f"[MEDIA_STREAM_STATUS] Call {call_sid}: Status={status}, ErrorCode={error_code}, ErrorMessage={error_message}")
    
#     if status == 'failed' or error_code:
#         logger.error(f"[MEDIA_STREAM_STATUS] Media Stream failed for call {call_sid}: {error_code} - {error_message}")
    
#     return PlainTextResponse("OK")


# @router.websocket("/webrtc/{call_sid}")
# async def handle_webrtc_websocket(websocket: WebSocket, call_sid: str):
#     """Handle WebRTC WebSocket connection for real-time AI voice calls (WebRTC-first architecture)."""
#     logger.info(f"[WebRTC] ===== WebRTC WebSocket handler CALLED for call {call_sid} =====")
#     logger.info(f"[WebRTC] WebSocket path: {websocket.url.path}")
#     logger.info(f"[WebRTC] WebSocket client: {websocket.client}")
#     logger.info(f"[WebRTC] WebSocket headers: {dict(websocket.headers)}")
    
#     twilio_manager = app_state.get_twilio_manager()
#     if not twilio_manager:
#         logger.error(f"[WebRTC] ✗ CRITICAL: Twilio manager not available for WebRTC WebSocket")
#         try:
#             await websocket.close(code=1008, reason="Twilio manager not available")
#         except:
#             pass
#         return
    
#     voice_handler = twilio_manager.voice_handler
    
#     try:
#         # Log before accepting to catch any connection issues
#         logger.info(f"[WebRTC] Attempting to accept WebSocket connection for call {call_sid}...")
#         await websocket.accept()
#         logger.info(f"[WebRTC] ===== WebRTC WebSocket ACCEPTED for call {call_sid} =====")
#         logger.info(f"[WebRTC] WebSocket client: {websocket.client}")
#         logger.info(f"[WebRTC] WebSocket URL: {websocket.url}")
#         logger.info(f"[WebRTC] WebSocket state: {websocket.client_state if hasattr(websocket, 'client_state') else 'unknown'}")
#         logger.info(f"[WebRTC] Waiting for Twilio stream events...")
#     except Exception as e:
#         logger.error(f"[WebRTC] ✗ CRITICAL ERROR accepting WebSocket for call {call_sid}: {e}", exc_info=True)
#         logger.error(f"[WebRTC] Exception type: {type(e).__name__}")
#         logger.error(f"[WebRTC] Exception args: {e.args}")
#         try:
#             await websocket.close(code=1011, reason=f"Error accepting connection: {str(e)}")
#         except:
#             pass
#         return
    
#     # Initialize call state if not exists
#     if call_sid not in voice_handler.active_calls:
#         voice_handler.active_calls[call_sid] = {
#             "status": "connected",
#             "start_time": time.time(),
#             "welcome_sent": False,
#             "turn_count": 0
#         }
    
#     call_state = voice_handler.active_calls[call_sid]
#     org_id = call_state.get("organization_id") or app_state.get_orchestrator().default_organization_id
    
#     # Create WebRTC session (Step 2)
#     # Note: Since Twilio uses Media Streams (not true WebRTC), we'll simulate WebRTC behavior
#     # by handling the Media Streams WebSocket as if it were WebRTC
    
#     def handle_transcript(transcript: str, is_final: bool):
#         """Handle transcription from Deepgram STT."""
#         if not transcript.strip():
#             return
        
#         logger.info(f"[WebRTC] Transcription ({'final' if is_final else 'interim'}): {transcript}")
        
#         if is_final:
#             # Only process final transcripts
#             app_state._log_callback("=" * 80)
#             app_state._log_callback(f"[USER] Call {call_sid} - Transcription: \"{transcript}\"")
#             app_state._log_callback("=" * 80)
            
#             # Process through VOCA orchestrator (Step 7)
#             try:
#                 ai_response = voice_handler.orchestrator.generate_reply(
#                     transcript,
#                     conversation_id=call_sid,
#                     call_sid=call_sid,
#                     organization_id=org_id,
#                 )
#                 logger.info(f"[WebRTC] AI Response: {ai_response}")
#                 app_state._log_callback("=" * 80)
#                 app_state._log_callback(f"[AI] Call {call_sid} - AI Response: \"{ai_response}\"")
#                 app_state._log_callback("=" * 80)
                
#                 # Stream TTS back to user (Step 8)
#                 logger.info(f"[WebRTC] ===== Starting AI response TTS =====")
#                 logger.info(f"[WebRTC] AI response text: {ai_response}")
#                 asyncio.create_task(stream_tts_to_twilio(voice_handler, call_sid, ai_response))
                
#                 call_state['turn_count'] = call_state.get('turn_count', 0) + 1
#             except Exception as e:
#                 logger.error(f"[WebRTC] Error processing transcription: {e}", exc_info=True)
    
#     def handle_audio_input(audio_data):
#         """Handle incoming audio (Step 5)."""
#         # Audio is being processed by Deepgram STT via WebRTC session
#         pass
    
#     # For now, we'll use Media Streams but treat it as WebRTC
#     # Store the WebSocket for TTS streaming
#     stream_sid = None
    
#     try:
#         while True:
#             # Receive JSON messages from Twilio (treating as WebRTC-like)
#             try:
#                 data = await websocket.receive_json()
#             except Exception as recv_error:
#                 logger.error(f"[WebRTC] ✗ ERROR receiving JSON from WebSocket for call {call_sid}: {recv_error}", exc_info=True)
#                 break
            
#             # Log message received (reduce verbosity - only log non-media events or first few messages)
#             event = data.get('event')
            
#             # Only log verbose details for non-media events or first 3 messages
#             if not hasattr(handle_webrtc_websocket, '_message_count'):
#                 handle_webrtc_websocket._message_count = {}
#             if call_sid not in handle_webrtc_websocket._message_count:
#                 handle_webrtc_websocket._message_count[call_sid] = 0
#             handle_webrtc_websocket._message_count[call_sid] += 1
            
#             msg_count = handle_webrtc_websocket._message_count[call_sid]
#             if event != 'media' or msg_count <= 3:
#                 logger.info(f"[WebRTC] Message #{msg_count} for call {call_sid}: event={event}")
#                 if event != 'media' and msg_count <= 10:
#                     logger.debug(f"[WebRTC] Full message: {json.dumps(data, indent=2)}")
#             else:
#                 logger.debug(f"[WebRTC] Message #{msg_count} for call {call_sid}: event={event}")
            
#             if event == 'connected':
#                 logger.info(f"[WebRTC] ===== 'connected' event received for call {call_sid} =====")
#                 logger.info(f"[WebRTC] Connection data: {json.dumps(data, indent=2)}")
#                 logger.info(f"[WebRTC] ✓ Twilio WebSocket connection established - waiting for 'start' event...")
#             elif event == 'start':
#                 logger.info(f"[WebRTC] ===== 'start' event received for call {call_sid} =====")
#                 logger.info(f"[WebRTC] Start event data: {json.dumps(data, indent=2)}")
#                 stream_sid = data.get('start', {}).get('streamSid')
#                 if stream_sid:
#                     voice_handler.twilio_media_websockets[call_sid] = {
#                         'websocket': websocket,
#                         'streamSid': stream_sid
#                     }
#                     logger.info(f"[WebRTC] ✓ Stream started - streamSid: {stream_sid}")
#                     logger.info(f"[WebRTC] ✓ WebSocket stored - ready to send/receive audio")
#                     logger.info(f"[WebRTC] Call state: {call_state.get('status', 'unknown')}")
#                     logger.info(f"[WebRTC] ===== AUDIO PIPELINE IS NOW ACTIVE =====")
                    
#                     # CRITICAL: Wait a brief moment after 'start' event before sending audio
#                     # This ensures Twilio is fully ready to receive outbound audio
#                     await asyncio.sleep(0.1)  # 100ms delay
#                     logger.info(f"[WebRTC] Waited 100ms after 'start' event - ready to send audio")
                    
#                     # Deliver welcome message (Step 4) - ONLY after stream start
#                     if call_sid in voice_handler.pending_greetings and not call_state.get('welcome_sent', False):
#                         greeting = voice_handler.pending_greetings[call_sid]
#                         welcome_start_time = time.time()
#                         logger.info(f"[WebRTC] ===== DELIVERING WELCOME MESSAGE =====")
#                         logger.info(f"[WebRTC] Call SID: {call_sid}")
#                         logger.info(f"[WebRTC] StreamSid: {stream_sid}")
#                         logger.info(f"[WebRTC] Welcome message: \"{greeting}\"")
#                         logger.info(f"[WebRTC] WebSocket ready: {websocket is not None}")
#                         logger.info(f"[WebRTC] Twilio Media Streams connection: {call_sid in voice_handler.twilio_media_websockets}")
#                         app_state._log_callback("=" * 80)
#                         app_state._log_callback(f"[AI] Call {call_sid} - Welcome Message: \"{greeting}\"")
#                         app_state._log_callback("=" * 80)
                        
#                         try:
#                             # Verify WebSocket connection is ready
#                             if call_sid not in voice_handler.twilio_media_websockets:
#                                 logger.error(f"[WebRTC] ✗ CRITICAL: Twilio Media Streams WebSocket not found for call {call_sid}")
#                                 logger.error(f"[WebRTC] Available streams: {list(voice_handler.twilio_media_websockets.keys())}")
#                                 raise Exception("Twilio Media Streams WebSocket not available")
                            
#                             success = await stream_tts_to_twilio(voice_handler, call_sid, greeting)
#                             welcome_duration = time.time() - welcome_start_time
                            
#                             if success:
#                                 logger.info(f"[WebRTC] ===== WELCOME MESSAGE DELIVERED SUCCESSFULLY =====")
#                                 logger.info(f"[WebRTC] ✓ Greeting TTS streamed in {welcome_duration:.3f}s")
#                                 logger.info(f"[WebRTC] ✓ Audio should now be audible on the call")
#                                 call_state['welcome_sent'] = True
#                                 call_state['turn_count'] = call_state.get('turn_count', 0) + 1
#                                 del voice_handler.pending_greetings[call_sid]
#                             else:
#                                 logger.error(f"[WebRTC] ✗ FAILED to stream welcome message TTS for call {call_sid}")
#                                 logger.error(f"[WebRTC] Duration: {welcome_duration:.3f}s")
#                                 logger.error(f"[WebRTC] Check TTS_STREAM logs above for error details")
#                                 logger.error(f"[WebRTC] WebSocket state: {call_sid in voice_handler.twilio_media_websockets}")
#                         except Exception as e:
#                             welcome_duration = time.time() - welcome_start_time
#                             logger.error(f"[WebRTC] ✗ ERROR delivering welcome message after {welcome_duration:.3f}s: {e}", exc_info=True)
#                             logger.error(f"[WebRTC] Call SID: {call_sid}")
#                             logger.error(f"[WebRTC] StreamSid: {stream_sid}")
#                             logger.error(f"[WebRTC] WebSocket available: {call_sid in voice_handler.twilio_media_websockets}")
#                 else:
#                     logger.error(f"[WebRTC] No streamSid in start event for call {call_sid} - cannot send audio!")
#             elif event == 'media':
#                 # Send greeting on first inbound media event if not yet sent (fallback for missed 'start' event)
#                 if call_sid in voice_handler.pending_greetings and not call_state.get('welcome_sent', False):
#                     greeting = voice_handler.pending_greetings[call_sid]
#                     logger.info(f"[WebRTC] ===== SENDING GREETING (fallback - first media event) =====")
#                     logger.info(f"[WebRTC] Call SID: {call_sid}")
#                     logger.info(f"[WebRTC] Greeting: \"{greeting}\"")
#                     try:
#                         if call_sid in voice_handler.twilio_media_websockets:
#                             success = await stream_tts_to_twilio(voice_handler, call_sid, greeting)
#                             if success:
#                                 call_state['welcome_sent'] = True
#                                 del voice_handler.pending_greetings[call_sid]
#                                 logger.info(f"[WebRTC] ✓ Greeting sent successfully (fallback)")
#                             else:
#                                 logger.error(f"[WebRTC] ✗ Failed to send greeting (fallback)")
#                         else:
#                             logger.warning(f"[WebRTC] ⚠️ Cannot send greeting - WebSocket not ready yet")
#                     except Exception as e:
#                         logger.error(f"[WebRTC] ✗ Error sending greeting (fallback): {e}", exc_info=True)
                
#                 # Incoming audio from caller (Step 5 - Live User Speech Capture)
#                 media_data = data.get('media', {})
#                 media_payload = media_data.get('payload')
#                 track = media_data.get('track', 'inbound')  # Default to 'inbound' if not specified
                
#                 # Log media events at DEBUG level (reduced verbosity)
#                 logger.debug(f"[WebRTC] Media event: call={call_sid}, track={track}, payload={len(media_payload) if media_payload else 0} bytes")
                
#                 if media_payload:
#                     try:
#                         # Log inbound media frame with timestamps
#                         payload_size = len(media_payload)
#                         timestamp = time.time()
#                         if not hasattr(handle_webrtc_websocket, '_media_frame_count'):
#                             handle_webrtc_websocket._media_frame_count = {}
#                         if not hasattr(handle_webrtc_websocket, '_first_frame_time'):
#                             handle_webrtc_websocket._first_frame_time = {}
#                         if call_sid not in handle_webrtc_websocket._media_frame_count:
#                             handle_webrtc_websocket._media_frame_count[call_sid] = 0
#                             handle_webrtc_websocket._first_frame_time[call_sid] = timestamp
#                         handle_webrtc_websocket._media_frame_count[call_sid] += 1
                        
#                         frame_num = handle_webrtc_websocket._media_frame_count[call_sid]
#                         elapsed = timestamp - handle_webrtc_websocket._first_frame_time[call_sid]
                        
#                         # Only log first 3 frames at INFO, rest at DEBUG (reduced verbosity)
#                         if frame_num <= 3:
#                             logger.info(f"[WebRTC] ✓ Inbound media frame #{frame_num} received: {payload_size} bytes (base64)")
#                         else:
#                             logger.debug(f"[WebRTC] Inbound media frame #{frame_num}: {payload_size} bytes (base64)")
                        
#                         # Decode base64 audio (μ-law, 8kHz from Twilio)
#                         decode_start = time.time()
#                         audio_bytes = base64.b64decode(media_payload)
#                         audio_bytes_size = len(audio_bytes)
#                         decode_time = (time.time() - decode_start) * 1000  # ms
#                         logger.debug(f"[WebRTC] Decoded audio bytes: {audio_bytes_size} bytes (μ-law) in {decode_time:.2f}ms")
                        
#                         if audio_bytes_size == 0:
#                             logger.warning(f"[WebRTC] Empty audio payload received for call {call_sid}")
#                             continue
                        
#                         # Convert μ-law to linear16 for Deepgram STT
#                         import numpy as np
#                         mu_law_array = np.frombuffer(audio_bytes, dtype=np.uint8)
#                         # Simple μ-law decoder
#                         linear = np.zeros(len(mu_law_array), dtype=np.int16)
#                         for i in range(len(mu_law_array)):
#                             mu = mu_law_array[i]
#                             sign_bit = (mu & 0x80) >> 7
#                             exponent_bits = (mu & 0x70) >> 4
#                             mantissa_bits = mu & 0x0F
                            
#                             if exponent_bits == 0:
#                                 sample = (mantissa_bits << 1) + 33
#                             else:
#                                 sample = ((mantissa_bits << 1) + 33) << (exponent_bits - 1)
                            
#                             if sign_bit == 1:
#                                 sample = -sample
                            
#                             linear[i] = np.int16(sample - 33)
                        
#                         audio_array = (linear * 16).astype(np.int16)
                        
#                         # Send to Deepgram STT (Step 6 - Real-Time Transcription)
#                         # We'll set up Deepgram STT connection per call
#                         if call_sid not in voice_handler.deepgram_stt_connections:
#                             # Initialize Deepgram STT for this call
#                             if Config.deepgram_api_key:
#                                 stt_client = DeepgramSTTClient(
#                                     on_transcript=handle_transcript,
#                                     api_key=Config.deepgram_api_key
#                                 )
#                                 stt_client.start()
#                                 voice_handler.deepgram_stt_connections[call_sid] = stt_client
#                                 logger.info(f"[WebRTC] Started Deepgram STT for call {call_sid}")
                        
#                         # Send audio to Deepgram STT
#                         if call_sid in voice_handler.deepgram_stt_connections:
#                             stt_client = voice_handler.deepgram_stt_connections[call_sid]
#                             # Convert to bytes (16-bit PCM)
#                             pcm_bytes = audio_array.astype(np.int16).tobytes()
#                             pcm_size = len(pcm_bytes)
#                             stt_timestamp = time.time()
#                             logger.debug(f"[WebRTC] Sending {pcm_size} bytes to Deepgram STT (PCM16, {len(audio_array)} samples) at {stt_timestamp:.3f}s")
#                             stt_client.send_audio(pcm_bytes)
#                         else:
#                             logger.warning(f"[WebRTC] Deepgram STT not initialized for call {call_sid}, skipping audio")
                            
#                     except Exception as e:
#                         logger.error(f"[WebRTC] Error processing media: {e}", exc_info=True)
#                 else:
#                     logger.warning(f"[WebRTC] Media event with no payload for call {call_sid}")
#             elif event == 'stop':
#                 logger.info(f"[WebRTC] ===== 'stop' event received for call {call_sid} =====")
#                 logger.info(f"[WebRTC] Stop event data: {json.dumps(data, indent=2)}")
#                 logger.info(f"[WebRTC] WebRTC stream stopped for call {call_sid}")
#                 # Cleanup (Step 10 - Call Termination & Cleanup)
#                 if call_sid in voice_handler.twilio_media_websockets:
#                     del voice_handler.twilio_media_websockets[call_sid]
#                 if call_sid in voice_handler.pending_greetings:
#                     del voice_handler.pending_greetings[call_sid]
#                 # Close Deepgram STT connection
#                 if call_sid in voice_handler.deepgram_stt_connections:
#                     try:
#                         voice_handler.deepgram_stt_connections[call_sid].stop()
#                         logger.info(f"[WebRTC] Closed Deepgram STT for call {call_sid}")
#                     except Exception as e:
#                         logger.error(f"[WebRTC] Error closing Deepgram STT: {e}")
#                     del voice_handler.deepgram_stt_connections[call_sid]
#                 break
#             else:
#                 # Log unhandled events
#                 logger.warning(f"[WebRTC] ===== UNHANDLED EVENT for call {call_sid} =====")
#                 logger.warning(f"[WebRTC] Event type: {event}")
#                 logger.warning(f"[WebRTC] Full message: {json.dumps(data, indent=2)}")
                
#     except WebSocketDisconnect:
#         logger.info(f"[WebRTC] WebRTC WebSocket disconnected for call {call_sid}")
#         # Cleanup
#         if call_sid in voice_handler.twilio_media_websockets:
#             del voice_handler.twilio_media_websockets[call_sid]
#         if call_sid in voice_handler.pending_greetings:
#             del voice_handler.pending_greetings[call_sid]
#         # Close Deepgram STT connection
#         if call_sid in voice_handler.deepgram_stt_connections:
#             try:
#                 voice_handler.deepgram_stt_connections[call_sid].stop()
#                 logger.info(f"[WebRTC] Closed Deepgram STT for call {call_sid}")
#             except Exception as e:
#                 logger.error(f"[WebRTC] Error closing Deepgram STT: {e}")
#             del voice_handler.deepgram_stt_connections[call_sid]
#     except Exception as e:
#         logger.error(f"[WebRTC] Error in WebRTC WebSocket: {e}", exc_info=True)
#         # Cleanup on error
#         if call_sid in voice_handler.twilio_media_websockets:
#             del voice_handler.twilio_media_websockets[call_sid]
#         if call_sid in voice_handler.pending_greetings:
#             del voice_handler.pending_greetings[call_sid]
#         # Close Deepgram STT connection
#         if call_sid in voice_handler.deepgram_stt_connections:
#             try:
#                 voice_handler.deepgram_stt_connections[call_sid].stop()
#             except:
#                 pass
#             del voice_handler.deepgram_stt_connections[call_sid]


# @router.websocket("/media/{call_sid}")
# async def handle_media_stream_websocket(websocket: WebSocket, call_sid: str):
#     """DEPRECATED: Old Media Streams endpoint - use /webrtc/{call_sid} instead."""
#     logger.error(f"[DEPRECATED] Old /media/{call_sid} endpoint called - this endpoint is deprecated. Use /webrtc/{call_sid} instead.")
#     try:
#         await websocket.accept()
#         await websocket.send_json({
#             "error": "DEPRECATED_ENDPOINT",
#             "message": "This endpoint is deprecated. Please use /webrtc/{call_sid} instead.",
#             "call_sid": call_sid
#         })
#         await websocket.close(code=1008, reason="Deprecated endpoint - use /webrtc/ instead")
#     except Exception as e:
#         logger.error(f"[DEPRECATED] Error handling deprecated endpoint: {e}")
#         try:
#             await websocket.close()
#         except:
#             pass


# @router.get("/webrtc/{call_sid}/test-audio")
# async def test_audio_endpoint(call_sid: str):
#     """
#     Test endpoint to verify WebRTC audio setup.
#     Returns diagnostic information about the call's audio state.
#     """
#     twilio_manager = app_state.get_twilio_manager()
#     if not twilio_manager:
#         return JSONResponse({"error": "Twilio manager not available"})
    
#     voice_handler = twilio_manager.voice_handler
    
#     # Check call state
#     call_info = {
#         "call_sid": call_sid,
#         "has_active_call": call_sid in voice_handler.active_calls,
#         "has_websocket": call_sid in voice_handler.twilio_media_websockets,
#         "has_pending_greeting": call_sid in voice_handler.pending_greetings,
#         "has_stt_connection": call_sid in voice_handler.deepgram_stt_connections,
#     }
    
#     if call_sid in voice_handler.active_calls:
#         call_info["call_state"] = voice_handler.active_calls[call_sid]
    
#     if call_sid in voice_handler.twilio_media_websockets:
#         stream_info = voice_handler.twilio_media_websockets[call_sid]
#         call_info["stream_sid"] = stream_info.get("streamSid")
#         call_info["websocket_connected"] = stream_info.get("websocket") is not None
    
#     return JSONResponse(call_info)


# @router.post("/webrtc/{call_sid}/send-test-tone")
# async def send_test_tone(call_sid: str):
#     """
#     Send a 1-second static PCM tone to test WebSocket audio pipeline.
#     This bypasses TTS/LLM to verify raw audio transmission works.
#     """
#     twilio_manager = app_state.get_twilio_manager()
#     if not twilio_manager:
#         return JSONResponse({"error": "Twilio manager not available"})
    
#     voice_handler = twilio_manager.voice_handler
    
#     if call_sid not in voice_handler.twilio_media_websockets:
#         return JSONResponse({"error": "No active WebSocket connection for this call"})
    
#     try:
#         twilio_stream = voice_handler.twilio_media_websockets[call_sid]
#         twilio_websocket = twilio_stream['websocket']
#         stream_sid = twilio_stream['streamSid']
        
#         # Generate 1 second of 440Hz tone (A4 note) at 8kHz μ-law
#         # 1 second = 8000 samples at 8kHz
#         # Generate sine wave: sin(2π * 440 * t)
#         import numpy as np
#         sample_rate = 8000
#         duration = 1.0  # 1 second
#         frequency = 440  # A4 note
        
#         t = np.linspace(0, duration, int(sample_rate * duration), False)
#         sine_wave = np.sin(2 * np.pi * frequency * t)
        
#         # Convert to μ-law (8-bit)
#         # First normalize to [-1, 1], then scale to int16, then convert to μ-law
#         audio_int16 = (sine_wave * 32767).astype(np.int16)
        
#         # Simple μ-law encoder
#         def encode_mulaw(sample):
#             """Encode 16-bit linear PCM to 8-bit μ-law"""
#             sign = 0 if sample >= 0 else 0x80
#             sample = abs(sample)
#             if sample > 32635:
#                 sample = 32635
#             sample += 0x84
#             exponent = 0
#             exp_mask = 0x4000
#             while (sample & exp_mask) == 0 and exponent < 7:
#                 exponent += 1
#                 exp_mask >>= 1
#             mantissa = (sample >> (exponent + 3)) & 0x0F
#             return sign | ((exponent + 1) << 4) | mantissa
        
#         mu_law_audio = np.array([encode_mulaw(s) for s in audio_int16], dtype=np.uint8)
#         audio_length = len(mu_law_audio)
        
#         # CRITICAL: Send in EXACTLY 160-byte chunks (20ms at 8kHz) with proper pacing
#         FRAME_SIZE = 160  # 20ms of audio at 8kHz
#         FRAME_INTERVAL_MS = 20.0
#         FRAME_INTERVAL_SEC = FRAME_INTERVAL_MS / 1000.0
        
#         # Calculate number of complete frames
#         num_complete_frames = audio_length // FRAME_SIZE
#         remainder = audio_length % FRAME_SIZE
        
#         logger.info(f"[TEST_TONE] Sending 1-second test tone (440Hz) for call {call_sid}")
#         logger.info(f"[TEST_TONE] Total audio: {audio_length} bytes, will send as {num_complete_frames} complete frames" + 
#                    (f" + 1 padded frame" if remainder > 0 else ""))
        
#         total_chunks = 0
#         total_bytes = 0
#         last_frame_time = None
#         stream_start_time = time.time()
        
#         # Send complete 160-byte frames
#         for i in range(num_complete_frames):
#             start_idx = i * FRAME_SIZE
#             end_idx = start_idx + FRAME_SIZE
#             chunk_bytes = mu_law_audio[start_idx:end_idx].tobytes()
            
#             # Verify frame is exactly 160 bytes
#             if len(chunk_bytes) != FRAME_SIZE:
#                 logger.error(f"[TEST_TONE] ✗ Frame {total_chunks} is {len(chunk_bytes)} bytes, expected {FRAME_SIZE} bytes")
#                 return JSONResponse({"error": f"Frame size mismatch: {len(chunk_bytes)} != {FRAME_SIZE}"}, status_code=500)
            
#             audio_base64 = base64.b64encode(chunk_bytes).decode('utf-8')
            
#             # When using both_tracks mode, Twilio REQUIRES the "track" field to route audio correctly
#             message = {
#                 "event": "media",
#                 "streamSid": stream_sid,
#                 "media": {
#                     "track": "outbound",
#                     "payload": audio_base64
#                 }
#             }
            
#             # Track timing for pacing
#             frame_start_time = time.time()
            
#             await twilio_websocket.send_json(message)
#             total_chunks += 1
#             total_bytes += len(chunk_bytes)
            
#             # Calculate time since last frame and sleep if needed
#             if last_frame_time is not None:
#                 elapsed_ms = (frame_start_time - last_frame_time) * 1000
#                 if elapsed_ms < FRAME_INTERVAL_MS:
#                     sleep_time = FRAME_INTERVAL_SEC - (elapsed_ms / 1000.0)
#                     await asyncio.sleep(sleep_time)
            
#             last_frame_time = frame_start_time
            
#             if total_chunks == 1 or total_chunks % 10 == 0:  # Log first frame and every 10th
#                 logger.info(f"[TEST_TONE] ✓ Sent frame {total_chunks}: {len(chunk_bytes)} bytes (EXACTLY)")
        
#         # Handle remainder: pad last chunk to exactly 160 bytes with μ-law silence (0xFF)
#         if remainder > 0:
#             start_idx = num_complete_frames * FRAME_SIZE
#             chunk_bytes = mu_law_audio[start_idx:].tobytes()
            
#             # Pad to exactly 160 bytes with μ-law silence (0xFF)
#             padding_needed = FRAME_SIZE - len(chunk_bytes)
#             padded_chunk = chunk_bytes + bytes([0xFF] * padding_needed)
            
#             if len(padded_chunk) != FRAME_SIZE:
#                 logger.error(f"[TEST_TONE] ✗ Padded frame is {len(padded_chunk)} bytes, expected {FRAME_SIZE} bytes")
#                 return JSONResponse({"error": f"Padded frame size mismatch: {len(padded_chunk)} != {FRAME_SIZE}"}, status_code=500)
            
#             logger.info(f"[TEST_TONE] Padded last frame from {len(chunk_bytes)} to {FRAME_SIZE} bytes with μ-law silence")
            
#             audio_base64 = base64.b64encode(padded_chunk).decode('utf-8')
            
#             # When using both_tracks mode, Twilio REQUIRES the "track" field to route audio correctly
#             message = {
#                 "event": "media",
#                 "streamSid": stream_sid,
#                 "media": {
#                     "track": "outbound",
#                     "payload": audio_base64
#                 }
#             }
            
#             frame_start_time = time.time()
            
#             await twilio_websocket.send_json(message)
#             total_chunks += 1
#             total_bytes += len(padded_chunk)
            
#             # Calculate time since last frame and sleep if needed
#             if last_frame_time is not None:
#                 elapsed_ms = (frame_start_time - last_frame_time) * 1000
#                 if elapsed_ms < FRAME_INTERVAL_MS:
#                     sleep_time = FRAME_INTERVAL_SEC - (elapsed_ms / 1000.0)
#                     await asyncio.sleep(sleep_time)
            
#             logger.info(f"[TEST_TONE] ✓ Sent frame {total_chunks}: {len(padded_chunk)} bytes (padded)")
        
#         stream_duration = time.time() - stream_start_time
#         logger.info(f"[TEST_TONE] ✓ Test tone sent: {total_chunks} frames, {total_bytes} bytes total")
#         logger.info(f"[TEST_TONE]   - Frame size: {FRAME_SIZE} bytes per frame (EXACTLY)")
#         logger.info(f"[TEST_TONE]   - Pacing: ~{FRAME_INTERVAL_MS}ms between frames")
#         logger.info(f"[TEST_TONE]   - Streaming duration: {stream_duration:.2f}s")
        
#         return JSONResponse({
#             "status": "success",
#             "message": "Test tone sent",
#             "chunks": total_chunks,
#             "bytes": total_bytes,
#             "duration_seconds": duration,
#             "frequency_hz": frequency
#         })
        
#     except Exception as e:
#         logger.error(f"[TEST_TONE] Error sending test tone: {e}", exc_info=True)
#         return JSONResponse({"error": str(e)}, status_code=500)


# Removed WebSocketAdapter - no longer needed without server.py dependency


@router.get("/twilio")
async def twilio_websocket_info():
    """HTTP GET endpoint to verify /twilio WebSocket route is accessible."""
    return JSONResponse({
        "status": "ok",
        "message": "WebSocket endpoint /twilio is registered",
        "websocket_url": "wss://voca-2.duckdns.org/twilio",
        "note": "Twilio should connect to this WebSocket URL from TwiML Bin"
    })


@router.websocket("/twilio")
async def handle_twilio_websocket(websocket: WebSocket):
    """
    Handle Twilio Media Streams WebSocket connection using custom LLM pipeline.
    This endpoint uses SarvamAI STT/TTS with orchestrator-based Gemini LLM.
    """
    # #region agent log
    try:
        with open(r"c:\Users\Yash\Desktop\voca-2.0\.cursor\debug.log", "a", encoding="utf-8") as f:
            from datetime import datetime
            entry = {"sessionId": "debug-session", "runId": "websocket-handler", "hypothesisId": "C", "location": "twilio_webhooks.py:handle_twilio_websocket:1", "message": "WebSocket handler called", "timestamp": int(datetime.now().timestamp() * 1000), "data": {"client": str(websocket.client) if websocket.client else None, "url": str(websocket.url) if hasattr(websocket, "url") else None}}
            f.write(json.dumps(entry) + "\n")
    except: pass
    # #endregion
    client_ip = websocket.client.host if websocket.client else "unknown"
    logger.info(f"[CUSTOM_LLM_PIPELINE] ===== WebSocket connection attempt to /twilio from {client_ip} =====")
    
    # Get SarvamAI API key
    sarvam_api_key = Config.sarvam_api_key
    if not sarvam_api_key:
        logger.error("[CUSTOM_LLM_PIPELINE] SARVAM_API_KEY not set")
        try:
            await websocket.accept()
            await websocket.close(code=1008, reason="SarvamAI API key not configured")
        except Exception:
            pass
        return
    
    # Initialize orchestrator for LLM pipeline
    orchestrator = VocaOrchestrator(
        on_log=lambda msg: app_state._log_callback(f"[CUSTOM_LLM_PIPELINE] {msg}"),
        organization_id=Config.default_organization_id
    )
    
    # Initialize STT and TTS clients (but don't connect yet - sequential connection required)
    stt_client = SarvamSTTClient(api_key=sarvam_api_key, language=Config.sarvam_language, sample_rate=8000)
    tts_client = SarvamTTSClient(api_key=sarvam_api_key, language=Config.sarvam_language, voice=Config.sarvam_voice, sample_rate=8000)
    
    # State machine: INIT → WELCOME → LISTENING → PROCESSING → SPEAKING
    class CallState(Enum):
        INIT = "init"  # WebSocket accepted, waiting for start event
        WELCOME = "welcome"  # TTS connected, playing welcome message
        LISTENING = "listening"  # Welcome complete, STT connected, listening for user
        PROCESSING = "processing"  # User spoke, processing through LLM
        SPEAKING = "speaking"  # TTS playing response
    
    call_state = CallState.INIT
    
    # State management
    call_sid = ""
    streamsid = ""
    conversation_history = []
    current_tts_task = None
    welcome_complete_event = asyncio.Event()  # Signals when welcome TTS completes
    welcome_audio_received = False  # Track if we've received any audio for welcome
    tts_active = False  # Flag to track if TTS is currently streaming audio
    tts_audio_sent = False  # Flag to track if any TTS audio has been sent to Twilio
    pending_closing_message = False  # Flag to track if current TTS is a closing message
    audio_buffer = bytearray()
    BUFFER_SIZE = 20 * 160  # 20ms of audio at 8kHz
    should_end_call = asyncio.Event()  # Event to signal call should end after closing message
    
    try:
        await websocket.accept()
        logger.info(f"[CUSTOM_LLM_PIPELINE] ✓ WebSocket accepted from {client_ip}")
        call_state = CallState.INIT
        
        # CRITICAL: Connect TTS once and keep it open for the entire call (persistent connection)
        # This eliminates handshake/config overhead and reduces latency
        logger.info("[CUSTOM_LLM_PIPELINE] Connecting to SarvamAI TTS (persistent connection)...")
        await tts_client.connect()
        logger.info("[CUSTOM_LLM_PIPELINE] ✓ TTS connected")
        
        # CRITICAL: Connect STT early for full-duplex operation
        # STT must run continuously, independently of TTS, from the start of the call
        logger.info("[CUSTOM_LLM_PIPELINE] Connecting to SarvamAI STT (full-duplex)...")
        try:
            await stt_client.connect()
            logger.info("[CUSTOM_LLM_PIPELINE] ✓ STT connected (ready for continuous audio forwarding)")
        except Exception as e:
            logger.error(f"[CUSTOM_LLM_PIPELINE] Failed to connect STT: {e}", exc_info=True)
            # Don't fail the entire call if STT connection fails - we can retry later
        
        # Set up TTS audio callback
        async def tts_audio_callback(pcm_audio: bytes):
            """Callback for TTS audio output."""
            nonlocal call_state, welcome_audio_received, tts_audio_sent
            if not tts_active or not streamsid:
                return
            
            # CRITICAL: Convert PCM to μ-law (sample width = 2 bytes for 16-bit PCM)
            # Twilio REQUIRES μ-law encoding, NOT raw PCM
            mulaw_audio = pcm_to_mulaw(pcm_audio, sample_width=2)
            
            # Diagnostic logging (first few chunks only to avoid spam)
            if not hasattr(tts_audio_callback, '_logged_diag'):
                logger.info(f"[AUDIO_CONVERSION] PCM len={len(pcm_audio)} bytes → μ-law len={len(mulaw_audio)} bytes (ratio: {len(mulaw_audio)/len(pcm_audio):.2f})")
                tts_audio_callback._logged_diag = True
            
            # Encode μ-law to base64 (do NOT log the payload - it's too large)
            audio_payload = base64.b64encode(mulaw_audio).decode("ascii")
            
            # Twilio Media Stream format: {"event": "media", "media": {"payload": "<base64_mulaw>"}}
            media_message = {
                "event": "media",
                "streamSid": streamsid,
                "media": {"payload": audio_payload}
            }
            await websocket.send_json(media_message)
            
            # Log audio being sent to Twilio
            logger.info(f"[AUDIO_OUT] Sent {len(audio_payload)} bytes (base64) to Twilio stream {streamsid}")
            
            # Log first outbound audio frame
            if not tts_audio_sent:
                logger.info("[AUDIO_OUT] First TTS audio frame sent to Twilio")
                tts_audio_sent = True
            
            # Mark that we've received audio (for welcome message tracking)
            if call_state == CallState.WELCOME:
                welcome_audio_received = True
        
        # Set audio callback for persistent TTS connection
        tts_client.set_audio_callback(tts_audio_callback)
        
        # Set completion callback to track when TTS audio streaming finishes
        async def tts_completion_callback():
            """Callback when TTS audio streaming completes."""
            nonlocal tts_active, pending_closing_message, should_end_call
            logger.info("[STATE] TTS audio streaming completed")
            tts_active = False
            
            # If this was a closing message, signal that call should end
            if pending_closing_message:
                logger.info("[CUSTOM_LLM_PIPELINE] Closing message TTS completed - signaling call end")
                pending_closing_message = False
                should_end_call.set()
            
            # Note: State transition to LISTENING will happen via VAD (when STT detects silence AND tts_active == False)
        
        tts_client.set_completion_callback(tts_completion_callback)
        
        # Set up STT transcript callback
        async def stt_transcript_callback(transcript: str, is_final: bool):
            """Callback for STT transcripts."""
            nonlocal tts_active, current_tts_task, call_sid, call_state, should_end_call, pending_closing_message
            
            if not transcript.strip():
                return
            
            # Log transcript receipt to prove STT continuity
            logger.info(f"[STT] transcript received (final={is_final}, state={call_state.value}): {transcript}")
            
            # Handle barge-in FIRST: cancel TTS if user speaks during TTS playback (SPEAKING state)
            # This must happen before state filtering so barge-in can work
            if call_state == CallState.SPEAKING and tts_active:
                logger.info("[BARGE-IN] User interrupted TTS - cancelling TTS and transitioning to LISTENING")
                tts_active = False
                # Cancel TTS if possible
                try:
                    await tts_client.cancel()
                except Exception as e:
                    logger.warning(f"[BARGE-IN] Error cancelling TTS: {e}")
                
                # Clear Twilio audio buffer to stop playing TTS audio
                clear_message = {"event": "clear", "streamSid": streamsid}
                try:
                    await websocket.send_json(clear_message)
                except Exception as e:
                    logger.error(f"[BARGE-IN] Error clearing buffer: {e}")
                
                # Transition to LISTENING state immediately
                call_state = CallState.LISTENING
                logger.info("[STATE] SPEAKING → LISTENING (user barge-in)")
            
            # CRITICAL: Ignore non-final transcripts if we're not in LISTENING or PROCESSING state
            # This prevents processing transcripts during TTS playback or initial welcome
            # However, STT continues to receive audio (full-duplex), we just ignore transcripts
            # For final transcripts, we allow processing (barge-in may have just transitioned us to LISTENING)
            if not is_final and call_state not in [CallState.LISTENING, CallState.PROCESSING]:
                logger.debug(f"[STT] Ignoring non-final transcript in state {call_state.value} (STT still receiving audio)")
                return
            
            # Only process final transcripts (VAD detected end of speech/silence)
            if is_final:
                # If we're in a non-listening state and this is final, log but still allow processing
                # (barge-in may have just happened, or we need to handle the transcript)
                if call_state not in [CallState.LISTENING, CallState.PROCESSING]:
                    logger.debug(f"[STT] Processing final transcript in state {call_state.value} (allowing for barge-in handling)")
                
                # Transition to LISTENING only if TTS is not active (VAD-driven state transition)
                if call_state == CallState.SPEAKING and not tts_active:
                    call_state = CallState.LISTENING
                    logger.info("[STATE] SPEAKING → LISTENING (VAD silence, TTS inactive)")
                
                # Process the transcript through LLM pipeline
                call_state = CallState.PROCESSING
                logger.info(f"[LLM] Received transcript: {transcript}")
                
                # Get organization ID (use default if not available)
                org_id = Config.default_organization_id
                
                # Process through orchestrator (LLM pipeline)
                logger.info(f"[LLM] Generating response...")
                try:
                    assistant_response = await orchestrator.process_user_text(
                        text=transcript,
                        session_id=call_sid,
                        organization_id=org_id
                    )
                    
                    logger.info(f"[LLM] Generated response: {assistant_response}")
                    logger.info(f"[TTS] Sending LLM output to Twilio")
                except Exception as e:
                    logger.error(f"[LLM] Error processing transcript through orchestrator: {e}", exc_info=True)
                    # On error, transition back to LISTENING to continue the call
                    call_state = CallState.LISTENING
                    return
                
                # Check if this is a closing message (call should end after this)
                # Common closing phrases in Hindi/English
                closing_phrases = [
                    "कॉल करने के लिए धन्यवाद",
                    "धन्यवाद.*दिन शुभ",
                    "thank you.*good day",
                    "thank you.*have a nice",
                ]
                import re
                is_closing_message = any(re.search(phrase, assistant_response, re.IGNORECASE) for phrase in closing_phrases)
                
                # Send to persistent TTS connection
                call_state = CallState.SPEAKING
                tts_active = True
                logger.info("[STATE] → SPEAKING (TTS started)")
                
                # Set flag if this is a closing message
                if is_closing_message:
                    logger.info("[CUSTOM_LLM_PIPELINE] Closing message detected - call will end after TTS completes")
                    pending_closing_message = True
                
                async def send_tts():
                    """Send text to persistent TTS connection with reconnection handling."""
                    nonlocal tts_active
                    try:
                        # Check if TTS is connected, reconnect if needed
                        if not tts_client.is_connected:
                            logger.warning("[CUSTOM_LLM_PIPELINE] TTS connection lost, reconnecting...")
                            try:
                                tts_client.set_audio_callback(tts_audio_callback)
                                await tts_client.connect()
                                logger.info("[CUSTOM_LLM_PIPELINE] ✓ TTS reconnected")
                            except Exception as reconnect_err:
                                logger.error(f"[CUSTOM_LLM_PIPELINE] Failed to reconnect TTS: {reconnect_err}", exc_info=True)
                                tts_active = False
                                return
                        
                        # Send text to persistent TTS connection
                        # TTS will stream audio via audio_callback
                        # Completion will be signaled via completion_callback (when "done" message received)
                        logger.info(f"[TTS] Sending text to persistent TTS connection: {assistant_response[:100]}...")
                        await tts_client.send_text_chunks(assistant_response)
                        logger.debug("[TTS] Text chunks sent, sending flush message...")
                        
                        # CRITICAL: Send flush message to flush audio from Sarvam's pipeline
                        # This signals that all text has been sent and audio generation should start
                        try:
                            await tts_client.send_flush()
                            logger.info("[TTS] Flush message sent - audio generation should start now")
                        except Exception as e:
                            logger.warning(f"[TTS] Error sending flush: {e}")
                            # Don't fail the whole operation if flush fails, but log it
                        
                        # Note: tts_active will be set to False by completion_callback when TTS sends "done" message
                        # State transition to LISTENING will happen via VAD (when STT detects silence AND tts_active == False)
                    except Exception as e:
                        logger.error(f"[CUSTOM_LLM_PIPELINE] Error in TTS: {e}", exc_info=True)
                        tts_active = False
                
                current_tts_task = asyncio.create_task(send_tts())
        
        stt_client.set_transcript_callback(stt_transcript_callback)
        
        # Main message loop
        welcome_sent = False
        
        # Create a task to monitor should_end_call event
        async def monitor_end_call():
            await should_end_call.wait()
            logger.info("[CUSTOM_LLM_PIPELINE] Closing message event set - closing WebSocket to end call")
            try:
                await websocket.close(code=1000, reason="Call ended after closing message")
            except Exception as e:
                logger.debug(f"[CUSTOM_LLM_PIPELINE] WebSocket already closed: {e}")
        
        end_call_task = asyncio.create_task(monitor_end_call())
        
        # Persistent message loop - stays open until explicit stop or disconnect
        logger.info("[CUSTOM_LLM_PIPELINE] Starting persistent message loop - waiting for Twilio events...")
        loop_exit_reason = None
        
        try:
            async for message in websocket.iter_text():
                try:
                    logger.debug(f"[CUSTOM_LLM_PIPELINE] Received message: {message[:100] if len(message) > 100 else message}")
                    data = json.loads(message)
                    event = data.get("event")
                    
                    if event == "start":
                        logger.info("[TWILIO] event=start received")
                        start = data.get("start", {})
                        streamsid = start.get("streamSid", "")
                        call_sid = start.get("callSid", "")
                        logger.info(f"[CUSTOM_LLM_PIPELINE] Stream started: SID={streamsid}, CallSid={call_sid}")
                        
                        # CRITICAL: Send welcome message FIRST (state: WELCOME)
                        if not welcome_sent:
                            call_state = CallState.WELCOME
                            welcome_message = orchestrator.generate_greeting(
                                conversation_id=call_sid,
                                organization_id=Config.default_organization_id
                            )
                            if welcome_message:
                                welcome_sent = True
                                tts_active = True
                                
                                async def send_welcome():
                                    """Send welcome message via persistent TTS connection."""
                                    nonlocal tts_active, call_state, welcome_complete_event
                                    welcome_tts_complete = None
                                    original_completion_callback = None
                                    
                                    try:
                                        logger.info(f"[CUSTOM_LLM_PIPELINE] Sending welcome message: {welcome_message}")
                                        tts_active = True
                                        
                                        # Ensure TTS is connected
                                        if not tts_client.is_connected:
                                            logger.error("[CUSTOM_LLM_PIPELINE] TTS not connected for welcome message")
                                            tts_active = False
                                            return
                                        
                                        # CRITICAL: Set up completion callback BEFORE sending text
                                        # This ensures we catch the "done" message even if it arrives quickly
                                        welcome_tts_complete = asyncio.Event()
                                        
                                        # Store original completion callback
                                        original_completion_callback = getattr(tts_client, 'completion_callback', None)
                                        
                                        # Temporary completion callback for welcome
                                        async def welcome_completion():
                                            nonlocal tts_active
                                            logger.info("[STATE] Welcome TTS audio streaming completed")
                                            tts_active = False
                                            if welcome_tts_complete:
                                                welcome_tts_complete.set()
                                            # Also call original callback if it exists
                                            if original_completion_callback:
                                                try:
                                                    await original_completion_callback()
                                                except Exception as e:
                                                    logger.warning(f"Error in original completion callback: {e}")
                                        
                                        # Set completion callback BEFORE sending text
                                        tts_client.set_completion_callback(welcome_completion)
                                        logger.debug("[CUSTOM_LLM_PIPELINE] Welcome completion callback set, sending text...")
                                        
                                        # Send text to persistent TTS connection
                                        # TTS will stream audio via audio_callback
                                        # Completion will be signaled via completion_callback (when "done" message received)
                                        await tts_client.send_text_chunks(welcome_message)
                                        
                                        # Send flush message to flush audio from Sarvam's pipeline
                                        try:
                                            await tts_client.send_flush()
                                            logger.debug("[CUSTOM_LLM_PIPELINE] Sent flush message for welcome audio")
                                        except Exception as e:
                                            logger.warning(f"[CUSTOM_LLM_PIPELINE] Error sending flush: {e}")
                                        
                                        # Wait for TTS completion (event-driven, not time-based)
                                        logger.debug("[CUSTOM_LLM_PIPELINE] Waiting for TTS completion (done message)...")
                                        await welcome_tts_complete.wait()
                                        logger.info("[CUSTOM_LLM_PIPELINE] Welcome TTS completion event received")
                                        
                                        # Restore original completion callback
                                        if original_completion_callback:
                                            tts_client.set_completion_callback(original_completion_callback)
                                        else:
                                            # Restore the main completion callback if there was no original
                                            tts_client.set_completion_callback(tts_completion_callback)
                                        
                                        # Signal welcome completion
                                        welcome_complete_event.set()
                                        
                                        # STT is already connected (connected early for full-duplex operation)
                                        # Just transition to LISTENING state
                                        if stt_client.is_connected:
                                            call_state = CallState.LISTENING
                                            logger.info("[STATE] → LISTENING (ready for user input, STT already active)")
                                        else:
                                            # STT connection failed earlier, try to reconnect
                                            logger.warning("[CUSTOM_LLM_PIPELINE] STT not connected, attempting to reconnect...")
                                            try:
                                                await stt_client.connect()
                                                logger.info("[CUSTOM_LLM_PIPELINE] ✓ STT reconnected")
                                                call_state = CallState.LISTENING
                                                logger.info("[STATE] → LISTENING (ready for user input)")
                                            except Exception as e:
                                                logger.error(f"[CUSTOM_LLM_PIPELINE] Failed to reconnect STT: {e}", exc_info=True)
                                                call_state = CallState.INIT
                                    except Exception as e:
                                        logger.error(f"[CUSTOM_LLM_PIPELINE] Error sending welcome: {e}", exc_info=True)
                                        tts_active = False
                                        # Restore callback on error
                                        if original_completion_callback:
                                            tts_client.set_completion_callback(original_completion_callback)
                                        else:
                                            tts_client.set_completion_callback(tts_completion_callback)
                                
                                # Start welcome TTS (non-blocking)
                                asyncio.create_task(send_welcome())
                    
                    elif event == "media":
                        # Log first media frame
                        if not hasattr(stt_transcript_callback, '_first_media_logged'):
                            logger.info("[TWILIO] first media frame received")
                            stt_transcript_callback._first_media_logged = True
                        
                        media = data.get("media", {})
                        if media.get("track") == "inbound":
                            # Log media received after TTS (implicit playback confirmation)
                            if tts_audio_sent and not hasattr(stt_transcript_callback, '_media_after_tts_logged'):
                                logger.info("[TWILIO] Media received after TTS playback (playback confirmed)")
                                stt_transcript_callback._media_after_tts_logged = True
                            
                            # CRITICAL: Always forward audio to STT if connected (full-duplex operation)
                            # STT runs continuously, independently of call_state or TTS
                            # The STT VAD will handle speech detection internally
                            if not stt_client.is_connected:
                                logger.debug(f"[STT] Dropping audio: STT not connected (state={call_state.value})")
                                continue
                            
                            mulaw_chunk = base64.b64decode(media.get("payload", ""))
                            audio_buffer.extend(mulaw_chunk)
                            
                            # Process buffer in chunks
                            while len(audio_buffer) >= BUFFER_SIZE:
                                mulaw_to_convert = bytes(audio_buffer[:BUFFER_SIZE])
                                audio_buffer = audio_buffer[BUFFER_SIZE:]
                                
                                # Convert μ-law to PCM and forward to STT (always, if STT is connected)
                                try:
                                    pcm_audio = mulaw_to_pcm(mulaw_to_convert)
                                    await stt_client.send_audio(pcm_audio)
                                    # Log first few audio frames to prove STT continuity
                                    if not hasattr(stt_transcript_callback, '_audio_forwarded_logged'):
                                        logger.info(f"[STT] Audio frame forwarded to STT (bytes={len(pcm_audio)}, state={call_state.value})")
                                        stt_transcript_callback._audio_forwarded_logged = True
                                except Exception as e:
                                    logger.error(f"[STT] Error forwarding audio to STT: {e}", exc_info=True)
                    
                    elif event == "stop":
                        logger.info("[TWILIO] event=stop received")
                        logger.info("[PIPELINE] WebSocket loop exiting due to STOP event")
                        # Send remaining audio
                        while len(audio_buffer) > 0:
                            mulaw_to_convert = bytes(audio_buffer[:BUFFER_SIZE] if len(audio_buffer) >= BUFFER_SIZE else audio_buffer)
                            audio_buffer = audio_buffer[len(mulaw_to_convert):]
                            if mulaw_to_convert:
                                pcm_audio = mulaw_to_pcm(mulaw_to_convert)
                                if stt_client.is_connected:
                                    await stt_client.send_audio(pcm_audio)
                        loop_exit_reason = "STOP event"
                        break
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"[CUSTOM_LLM_PIPELINE] Failed to parse message: {e}")
                    # Continue loop - don't exit on JSON errors
                    continue
                except Exception as e:
                    logger.error(f"[CUSTOM_LLM_PIPELINE] Error processing message: {e}", exc_info=True)
                    # If WebSocket was closed (by monitor_end_call), break the loop
                    if "not connected" in str(e).lower() or "closed" in str(e).lower():
                        logger.info("[PIPELINE] WebSocket loop exiting due to connection closed")
                        loop_exit_reason = "connection closed"
                        break
                    # For other errors, continue the loop - don't exit
                    continue
            
            # Log why the loop exited
            if loop_exit_reason:
                logger.info(f"[PIPELINE] WebSocket loop exited: {loop_exit_reason}")
            else:
                logger.info("[PIPELINE] WebSocket loop exited: iterator exhausted (normal disconnect)")
        finally:
            # Cancel the monitoring task if it's still running
            if not end_call_task.done():
                end_call_task.cancel()
                try:
                    await end_call_task
                except asyncio.CancelledError:
                    pass
        
    except WebSocketDisconnect:
        logger.info("[CUSTOM_LLM_PIPELINE] WebSocket disconnected by client")
    except Exception as e:
        logger.error(f"[CUSTOM_LLM_PIPELINE] Error in WebSocket handler: {e}", exc_info=True)
        import traceback
        logger.error(f"[CUSTOM_LLM_PIPELINE] Traceback: {traceback.format_exc()}")
    finally:
        # Cleanup - close persistent TTS and STT connections
        # This only runs after the message loop exits (on stop event or disconnect)
        logger.info("[CUSTOM_LLM_PIPELINE] Cleaning up connections...")
        try:
            await stt_client.stop()
        except Exception as e:
            logger.warning(f"[CUSTOM_LLM_PIPELINE] Error stopping STT: {e}")
        try:
            if tts_client.is_connected:
                await tts_client.stop()
                logger.info("[CUSTOM_LLM_PIPELINE] TTS connection closed")
        except Exception as e:
            logger.warning(f"[CUSTOM_LLM_PIPELINE] Error stopping TTS: {e}")
        # Note: Don't close websocket here - FastAPI handles it automatically on handler exit


# Removed Deepgram agent endpoints - using custom LLM pipeline instead

