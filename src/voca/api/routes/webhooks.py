"""
Twilio webhook endpoints for handling calls.
"""
import logging
import time
from typing import Optional

from fastapi import Request, Response, HTTPException
from fastapi.routing import APIRouter
from twilio.twiml.voice_response import VoiceResponse

from src.voca.api.app_state import app_state
from src.voca.api.utils import resolve_org_id
from src.voca.twilio_config import get_twilio_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/outbound")
async def handle_outbound_call(request: Request):
    """Handle outbound call TwiML - forwarded from Twilio webhook server."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        # Return basic TwiML if Twilio not configured
        response = VoiceResponse()
        response.say("Service temporarily unavailable")
        return Response(content=str(response), media_type='text/xml')
    
    # Get the voice handler from the manager
    voice_handler = twilio_manager.voice_handler
    
    form_data = await request.form()
    call_sid = form_data.get('CallSid')
    
    # Fetch call details from Twilio API to get language information
    if call_sid:
        try:
            from twilio.rest import Client
            config = get_twilio_config()
            if config and config.account_sid and config.auth_token:
                logger.info(f"[CALL_INFO] Fetching call details for outbound call {call_sid}...")
                client = Client(config.account_sid, config.auth_token)
                call = client.calls(call_sid).fetch()
                logger.info(f"[CALL_INFO] Outbound Call {call_sid} - Status: {call.status}, Direction: {call.direction}")
                logger.info(f"[CALL_INFO] Outbound Call {call_sid} - From: {call.from_formatted}, To: {call.to_formatted}")
        except Exception as e:
            logger.error(f"[CALL_INFO] Could not fetch outbound call details from Twilio API: {e}", exc_info=True)
    
    # Store call information
    if call_sid:
        voice_handler.active_calls[call_sid] = {
            'to_number': 'outbound',
            'status': 'ringing',
            'start_time': time.time(),
            'audio_buffer': []
        }
    
    response = VoiceResponse()
    
    # Generate greeting from system prompt
    try:
        org_id = form_data.get('organization_id') or app_state.get_orchestrator().default_organization_id
        greeting = app_state.get_orchestrator().generate_greeting(
            conversation_id=call_sid,
            organization_id=org_id
        )
    except Exception as e:
        logger.error(f"Error generating greeting: {e}")
        greeting = "Hello! This is VOCA calling. How can I help you today?"
    
    # Log greeting as AI response
    logger.info(f"📞 Call {call_sid[:8]}... | AI: {greeting}")
    response.say(greeting)
    
    # Gather user input
    if call_sid:
        gather = response.gather(
            input='speech',
            timeout=10,
            speech_timeout='auto',
            action=f'/process_speech/{call_sid}',
            method='POST'
        )
        gather.say("I'm listening...")
        response.redirect(f'/process_speech/{call_sid}')
    
    return Response(content=str(response), media_type='text/xml')


@router.post("/webhook/voice")
async def handle_incoming_call_webhook(request: Request):
    """Handle incoming Twilio call webhook - forwarded from Twilio webhook server."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        response.say("Service temporarily unavailable")
        return Response(content=str(response), media_type='text/xml')
    
    voice_handler = twilio_manager.voice_handler
    
    form_data = await request.form()
    call_sid = form_data.get('CallSid')
    from_number = form_data.get('From')
    
    if call_sid:
        voice_handler.active_calls[call_sid] = {
            'from_number': from_number,
            'status': 'ringing',
            'start_time': time.time(),
            'audio_buffer': []
        }
    
    response = VoiceResponse()
    
    # Generate greeting from system prompt
    try:
        org_id = form_data.get('organization_id') or app_state.get_orchestrator().default_organization_id
        greeting = app_state.get_orchestrator().generate_greeting(
            conversation_id=call_sid,
            organization_id=org_id
        )
    except Exception as e:
        logger.error(f"Error generating greeting: {e}")
        greeting = "Hello! You've reached VOCA, your AI voice assistant. Please speak after the tone."
    
    # Log greeting as AI response
    logger.info(f"📞 Call {call_sid[:8]}... | AI: {greeting}")
    response.say(greeting)
    
    if call_sid:
        gather = response.gather(
            input='speech',
            timeout=10,
            speech_timeout='auto',
            action=f'/process_speech/{call_sid}',
            method='POST'
        )
        gather.say("I'm listening...")
        response.redirect(f'/process_speech/{call_sid}')
    
    return Response(content=str(response), media_type='text/xml')


@router.post("/process_speech/{call_sid}")
async def handle_speech_webhook(call_sid: str, request: Request):
    """Handle speech input from Twilio - forwarded from Twilio webhook server."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        response.say("Service temporarily unavailable")
        return Response(content=str(response), media_type='text/xml')
    
    voice_handler = twilio_manager.voice_handler
    
    if call_sid not in voice_handler.active_calls:
        raise HTTPException(status_code=404, detail="Call not found")
    
    form_data = await request.form()
    speech_result = form_data.get('SpeechResult', '')
    confidence = form_data.get('Confidence', '0')
    
    if speech_result and float(confidence) > 0.5:
        # Log user message clearly in terminal
        logger.info(f"📞 Call {call_sid[:8]}... | USER: {speech_result}")
        app_state._log_callback(f"Speech received for call {call_sid}: {speech_result} (confidence: {confidence})")
        try:
            # User message and AI response are logged in orchestrator.generate_reply
            ai_response = voice_handler.orchestrator.generate_reply(
                speech_result,
                conversation_id=call_sid,
                call_sid=call_sid,
            )
            # Log AI response clearly in terminal
            logger.info(f"📞 Call {call_sid[:8]}... | AI: {ai_response}")
            app_state._log_callback(f"AI Response: {ai_response}")
            
            if not ai_response or len(ai_response.strip()) == 0:
                ai_response = "I understand. Can you tell me more about that?"
            
            if len(ai_response) > 500:
                ai_response = ai_response[:500] + "..."
            
            response = VoiceResponse()
            response.say(ai_response)
            
            # Check if user declined further assistance and AI responded with closing message
            speech_lower = speech_result.lower()
            ai_response_lower = ai_response.lower()
            
            # Check if user said "no thank you" or similar declining phrases
            decline_phrases = [
                "no thank you", "no thanks", "no, thank you", "no, thanks",
                "that's all", "nothing else", "i'm good", "i'm fine",
                "not really", "no more", "no, that's all", "no that's all"
            ]
            
            user_declined = any(phrase in speech_lower for phrase in decline_phrases)
            
            # Check if AI responded with closing message
            closing_phrases = [
                "thank you for calling. have a great day",
                "thank you for calling, have a great day",
                "have a great day"
            ]
            
            ai_closing = any(phrase in ai_response_lower for phrase in closing_phrases)
            
            # If user declined and AI gave closing message, end the call
            if user_declined and ai_closing:
                response.hangup()
                app_state._log_callback(f"Call {call_sid} ended - user declined further assistance")
                return Response(content=str(response), media_type='text/xml')
            
            if call_sid:
                gather = response.gather(
                    input='speech',
                    timeout=10,
                    speech_timeout='auto',
                    action=f'/process_speech/{call_sid}',
                    method='POST'
                )
                gather.say("I'm listening...")
                response.redirect(f'/process_speech/{call_sid}')
            
            return Response(content=str(response), media_type='text/xml')
            
        except Exception as e:
            app_state._log_callback(f"Error processing speech: {e}")
            response = VoiceResponse()
            response.say("I'm sorry, I had trouble processing that. Please try again.")
            if call_sid:
                response.redirect(f'/process_speech/{call_sid}')
            return Response(content=str(response), media_type='text/xml')
    else:
        response = VoiceResponse()
        response.say("I didn't catch that. Please speak clearly.")
        if call_sid:
            response.redirect(f'/process_speech/{call_sid}')
        return Response(content=str(response), media_type='text/xml')

