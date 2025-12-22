import logging
import time

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect, ConversationRelay

from src.voca.api.state import app_state
from src.voca.Twilio.twilio_config import get_twilio_config

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/conversation/{call_sid}")
async def handle_conversation_relay(websocket: WebSocket, call_sid: str):
    """Handle ConversationRelay WebSocket connection from Twilio."""
    await websocket.accept()
    logger.info(f"[CONVERSATION_RELAY] WebSocket connected for call {call_sid}")
    
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        await websocket.close()
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
            data = await websocket.receive_json()
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
                        await websocket.send_json(welcome_message)
                        logger.info(f"[CONVERSATION_RELAY] Sent welcome message to ConversationRelay")
                        
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
                    await websocket.send_json(response_message)
                    logger.info(f"[CONVERSATION_RELAY] Sent AI response to ConversationRelay")
                    
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
    """Handle outbound call TwiML using ConversationRelay with Deepgram."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        logger.error("[CONVERSATION_RELAY] Twilio manager not available")
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
            "welcome_sent": False,
            "turn_count": 0,
            "organization_id": org_id
        }

    # Create TwiML response
    response = VoiceResponse()

    # Get WebSocket URL for ConversationRelay
    config = get_twilio_config()
    webhook_url = config.get_webhook_url()
    base_url = webhook_url.replace('/webhook/voice', '').replace('/outbound', '').replace('/process_speech/', '')

    # Convert to WebSocket URL (wss://)
    if base_url.startswith('http://'):
        wss_base_url = base_url.replace('http://', 'wss://')
    elif base_url.startswith('https://'):
        wss_base_url = base_url.replace('https://', 'wss://')
    elif not base_url.startswith('wss://'):
        wss_base_url = f"wss://{base_url.lstrip('/')}"
    else:
        wss_base_url = base_url

    websocket_url = f"{wss_base_url}/conversation/{call_sid}"

    # Set up ConversationRelay with Deepgram
    connect = Connect()
    conversationrelay = ConversationRelay(url=websocket_url)

    # Configure English (India) with Deepgram TTS and STT
    conversationrelay.language(
        code='en-IN',
        tts_provider='deepgram',
        voice='aura-2-odysseus-en',  # Deepgram TTS model
        transcription_provider='deepgram',
        speech_model='nova-3'  # Deepgram STT model
    )

    connect.append(conversationrelay)
    response.append(connect)

    logger.info(f"[CONVERSATION_RELAY] Enabled ConversationRelay for outbound call {call_sid}")
    logger.info(f"[CONVERSATION_RELAY] WebSocket URL: {websocket_url}")
    logger.info(f"[CONVERSATION_RELAY] Using Deepgram TTS (aura-2-odysseus-en) and STT (nova-3)")

    return Response(content=str(response), media_type="text/xml")


@router.post("/webhook/voice")
async def handle_incoming_call_webhook(request: Request):
    """Handle incoming Twilio call webhook using ConversationRelay with Deepgram."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        logger.error("[CONVERSATION_RELAY] Twilio manager not available")
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
            "name_attempt_count": 0,
            "welcome_sent": False,
            "turn_count": 0,
            "organization_id": org_id
        }

    # Create TwiML response
    response = VoiceResponse()

    # Get WebSocket URL for ConversationRelay
    config = get_twilio_config()
    webhook_url = config.get_webhook_url()
    base_url = webhook_url.replace('/webhook/voice', '').replace('/outbound', '').replace('/process_speech/', '')

    # Convert to WebSocket URL (wss://)
    if base_url.startswith('http://'):
        wss_base_url = base_url.replace('http://', 'wss://')
    elif base_url.startswith('https://'):
        wss_base_url = base_url.replace('https://', 'wss://')
    elif not base_url.startswith('wss://'):
        wss_base_url = f"wss://{base_url.lstrip('/')}"
    else:
        wss_base_url = base_url

    websocket_url = f"{wss_base_url}/conversation/{call_sid}"

    # Set up ConversationRelay with Deepgram
    connect = Connect()
    conversationrelay = ConversationRelay(url=websocket_url)

    # Configure English (India) with Deepgram TTS and STT
    conversationrelay.language(
        code='en-IN',
        tts_provider='deepgram',
        voice='aura-2-odysseus-en',  # Deepgram TTS model
        transcription_provider='deepgram',
        speech_model='nova-3'  # Deepgram STT model
    )

    connect.append(conversationrelay)
    response.append(connect)

    logger.info(f"[CONVERSATION_RELAY] Enabled ConversationRelay for call {call_sid}")
    logger.info(f"[CONVERSATION_RELAY] WebSocket URL: {websocket_url}")
    logger.info(f"[CONVERSATION_RELAY] Using Deepgram TTS (aura-2-odysseus-en) and STT (nova-3)")

    return Response(content=str(response), media_type="text/xml")

# Note: /process_speech endpoint removed - ConversationRelay handles speech via WebSocket

