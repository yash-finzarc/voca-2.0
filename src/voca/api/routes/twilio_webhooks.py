import logging
import time

from fastapi import APIRouter, HTTPException, Request, Response
from twilio.twiml.voice_response import VoiceResponse

from src.voca.api.state import app_state
from src.voca.Twilio.twilio_config import get_twilio_config

router = APIRouter()
logger = logging.getLogger(__name__)


def add_deepgram_tts_to_response(voice_handler, response: VoiceResponse, text: str, language: str = 'en'):
    """Add Deepgram TTS audio to TwiML response using voice_handler. Logs error if TTS fails (no fallback)."""
    try:
        config = get_twilio_config()
        webhook_url = config.get_webhook_url()
        base_url = webhook_url.replace('/webhook/voice', '').replace('/outbound', '').replace('/process_speech/', '')
        
        logger.info(f"[TTS] Generating Deepgram TTS for text: {text[:100]}... (language: {language})")
        tts_url = voice_handler.get_tts_audio_url(text, base_url, language=language)
        if tts_url:
            response.play(tts_url)
            logger.info(f"[TTS] ✓ Using Deepgram TTS - URL: {tts_url}")
            logger.info(f"[TTS] TwiML will use <Play> verb (not <Say>)")
        else:
            logger.error(f"[TTS] ✗ Deepgram TTS generation FAILED for text: {text[:100]}... - no audio will be played (no fallback to TwiML say())")
    except Exception as e:
        logger.error(f"[TTS] Error in add_deepgram_tts_to_response: {e}", exc_info=True)


@router.post("/outbound")
async def handle_outbound_call(request: Request):
    """Handle outbound call TwiML - forwarded from Twilio webhook server."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        # Can't use Deepgram TTS if twilio_manager is not available, but we should still try
        logger.error("[TTS] Twilio manager not available - cannot generate TTS")
        # Return empty response instead of using say()
        return Response(content=str(response), media_type="text/xml")

    voice_handler = twilio_manager.voice_handler

    form_data = await request.form()
    call_sid = form_data.get("CallSid")

    if call_sid:
        voice_handler.active_calls[call_sid] = {
            "to_number": "outbound",
            "status": "ringing",
            "start_time": time.time(),
            "audio_buffer": [],
        }

    response = VoiceResponse()

    try:
        org_id = form_data.get("organization_id") or app_state.get_orchestrator().default_organization_id
        from src.voca.system_prompt import get_prompt_with_name

        prompt_data = get_prompt_with_name(organization_id=org_id)
        service_type = prompt_data.get("service_type", "conversational")

        if service_type == "announcement":
            try:
                announcement = app_state.get_orchestrator().generate_announcement(conversation_id=call_sid, organization_id=org_id)
                logger.info(f"Generated announcement for outbound call {call_sid} (length: {len(announcement)} chars)")
                add_deepgram_tts_to_response(voice_handler, response, announcement, language='en')
                response.hangup()
                logger.info(f"Outbound call {call_sid} will play announcement and hangup (announcement mode)")
            except Exception as e:
                logger.error(f"Error generating announcement: {e}")
                fallback_text = "कृपया अपनी रिपोर्ट की विस्तृत समीक्षा के लिए डॉक्टर से परामर्श अवश्य करें।"
                add_deepgram_tts_to_response(voice_handler, response, fallback_text, language='hi-IN')
                response.hangup()
        else:
            greeting = app_state.get_orchestrator().generate_greeting(conversation_id=call_sid, organization_id=org_id)
            add_deepgram_tts_to_response(voice_handler, response, greeting, language='en')

            if call_sid:
                gather = response.gather(input="speech", timeout=10, speech_timeout="auto", action=f"/process_speech/{call_sid}", method="POST")
                # Removed gather.say() - using Deepgram TTS only, no TwiML say()
                response.redirect(f"/process_speech/{call_sid}")
    except Exception as e:
        logger.error(f"Error in handle_outbound_call: {e}")
        try:
            org_id = form_data.get("organization_id") or app_state.get_orchestrator().default_organization_id
            greeting = app_state.get_orchestrator().generate_greeting(conversation_id=call_sid, organization_id=org_id)
        except Exception:
            greeting = "Hello! This is VOCA calling. How can I help you today?"
        add_deepgram_tts_to_response(voice_handler, response, greeting, language='en')

        if call_sid:
            gather = response.gather(input="speech", timeout=10, speech_timeout="auto", action=f"/process_speech/{call_sid}", method="POST")
            # Removed gather.say() - using Deepgram TTS only, no TwiML say()
            response.redirect(f"/process_speech/{call_sid}")

    return Response(content=str(response), media_type="text/xml")


@router.post("/webhook/voice")
async def handle_incoming_call_webhook(request: Request):
    """Handle incoming Twilio call webhook - forwarded from Twilio webhook server."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        # Can't use Deepgram TTS if twilio_manager is not available, but we should still try
        logger.error("[TTS] Twilio manager not available - cannot generate TTS")
        # Return empty response instead of using say()
        return Response(content=str(response), media_type="text/xml")

    voice_handler = twilio_manager.voice_handler

    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")

    if call_sid:
        voice_handler.active_calls[call_sid] = {
            "from_number": from_number,
            "status": "ringing",
            "start_time": time.time(),
            "audio_buffer": [],
        }

    response = VoiceResponse()

    try:
        org_id = form_data.get("organization_id") or app_state.get_orchestrator().default_organization_id
        from src.voca.system_prompt import get_prompt_with_name

        prompt_data = get_prompt_with_name(organization_id=org_id)
        service_type = prompt_data.get("service_type", "conversational")

        if service_type == "announcement":
            try:
                announcement = app_state.get_orchestrator().generate_announcement(conversation_id=call_sid, organization_id=org_id)
                logger.info(f"Generated announcement for call {call_sid} (length: {len(announcement)} chars)")
                add_deepgram_tts_to_response(voice_handler, response, announcement, language='en')
                response.hangup()
                logger.info(f"Call {call_sid} will play announcement and hangup (announcement mode)")
            except Exception as e:
                logger.error(f"Error generating announcement: {e}")
                fallback_text = "कृपया अपनी रिपोर्ट की विस्तृत समीक्षा के लिए डॉक्टर से परामर्श अवश्य करें।"
                add_deepgram_tts_to_response(voice_handler, response, fallback_text, language='hi-IN')
                response.hangup()
        else:
            greeting = app_state.get_orchestrator().generate_greeting(conversation_id=call_sid, organization_id=org_id)
            add_deepgram_tts_to_response(voice_handler, response, greeting, language='en')

            if call_sid:
                gather = response.gather(input="speech", timeout=10, speech_timeout="auto", action=f"/process_speech/{call_sid}", method="POST")
                # Removed gather.say() - using Deepgram TTS only, no TwiML say()
                response.redirect(f"/process_speech/{call_sid}")
    except Exception as e:
        logger.error(f"Error in handle_incoming_call_webhook: {e}")
        try:
            org_id = form_data.get("organization_id") or app_state.get_orchestrator().default_organization_id
            greeting = app_state.get_orchestrator().generate_greeting(conversation_id=call_sid, organization_id=org_id)
        except Exception:
            greeting = "Hello! You've reached VOCA, your AI voice assistant. Please speak after the tone."
        add_deepgram_tts_to_response(voice_handler, response, greeting, language='en')

        if call_sid:
            gather = response.gather(input="speech", timeout=10, speech_timeout="auto", action=f"/process_speech/{call_sid}", method="POST")
            # Removed gather.say() - using Deepgram TTS only, no TwiML say()
            response.redirect(f"/process_speech/{call_sid}")

    return Response(content=str(response), media_type="text/xml")


@router.post("/process_speech/{call_sid}")
async def handle_speech_webhook(call_sid: str, request: Request):
    """Handle speech input from Twilio - forwarded from Twilio webhook server."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        # Can't use Deepgram TTS if twilio_manager is not available, but we should still try
        logger.error("[TTS] Twilio manager not available - cannot generate TTS")
        # Return empty response instead of using say()
        return Response(content=str(response), media_type="text/xml")

    voice_handler = twilio_manager.voice_handler

    if call_sid not in voice_handler.active_calls:
        raise HTTPException(status_code=404, detail="Call not found")

    form_data = await request.form()
    speech_result = form_data.get("SpeechResult", "")
    confidence = form_data.get("Confidence", "0")

    if speech_result:
        app_state._log_callback("=" * 80)
        app_state._log_callback(f"[USER] Call {call_sid} - Speech Recognized by Twilio:")
        app_state._log_callback(f"[USER] Confidence: {confidence}")
        app_state._log_callback(f"[USER] Text: \"{speech_result}\"")
        app_state._log_callback("=" * 80)
    else:
        app_state._log_callback("=" * 80)
        app_state._log_callback(f"[USER] Call {call_sid} - No speech recognized (confidence: {confidence})")
        app_state._log_callback("=" * 80)

    if speech_result and float(confidence) > 0.5:
        try:
            ai_response = voice_handler.orchestrator.generate_reply(speech_result, conversation_id=call_sid, call_sid=call_sid)
            app_state._log_callback("=" * 80)
            app_state._log_callback(f"[AI] Call {call_sid} - AI Response Generated:")
            app_state._log_callback(f"[AI] Response: \"{ai_response}\"")
            app_state._log_callback("=" * 80)

            if not ai_response or len(ai_response.strip()) == 0:
                ai_response = "I understand. Can you tell me more about that?"

            if len(ai_response) > 500:
                ai_response = ai_response[:500] + "..."

            response = VoiceResponse()
            add_deepgram_tts_to_response(voice_handler, response, ai_response, language='en')

            speech_lower = speech_result.lower()
            ai_response_lower = ai_response.lower()

            decline_phrases = [
                "no thank you",
                "no thanks",
                "no, thank you",
                "no, thanks",
                "that's all",
                "nothing else",
                "i'm good",
                "i'm fine",
                "not really",
                "no more",
                "no, that's all",
                "no that's all",
            ]

            user_declined = any(phrase in speech_lower for phrase in decline_phrases)

            closing_phrases = [
                "thank you for calling. have a great day",
                "thank you for calling, have a great day",
                "have a great day",
            ]

            ai_closing = any(phrase in ai_response_lower for phrase in closing_phrases)

            if user_declined and ai_closing:
                response.hangup()
                app_state._log_callback(f"Call {call_sid} ended - user declined further assistance")
                return Response(content=str(response), media_type="text/xml")

            if call_sid:
                gather = response.gather(input="speech", timeout=10, speech_timeout="auto", action=f"/process_speech/{call_sid}", method="POST")
                # Removed gather.say() - using Deepgram TTS only, no TwiML say()
                response.redirect(f"/process_speech/{call_sid}")

            return Response(content=str(response), media_type="text/xml")

        except Exception as e:
            app_state._log_callback(f"Error processing speech: {e}")
            response = VoiceResponse()
            error_text = "I'm sorry, I had trouble processing that. Please try again."
            add_deepgram_tts_to_response(voice_handler, response, error_text, language='en')
            if call_sid:
                response.redirect(f"/process_speech/{call_sid}")
            return Response(content=str(response), media_type="text/xml")
    else:
        app_state._log_callback("=" * 80)
        app_state._log_callback(f"[USER] Call {call_sid} - Speech Recognition Failed:")
        app_state._log_callback(f"[USER] SpeechResult: \"{speech_result or '(empty)'}\"")
        app_state._log_callback(f"[USER] Confidence: {confidence} (below 0.5 threshold)")
        app_state._log_callback("=" * 80)

        response = VoiceResponse()

        if call_sid and call_sid in voice_handler.active_calls:
            voice_handler.active_calls[call_sid]["unclear_count"] = voice_handler.active_calls[call_sid].get("unclear_count", 0) + 1
            unclear_count = voice_handler.active_calls[call_sid]["unclear_count"]
        else:
            unclear_count = 1

        MAX_UNCLEAR_ATTEMPTS = 3

        if unclear_count >= MAX_UNCLEAR_ATTEMPTS:
            error_text = "I'm having trouble understanding you over the phone. Please try speaking more slowly and clearly, or call back if you continue to experience issues. Thank you!"
            add_deepgram_tts_to_response(voice_handler, response, error_text, language='en')
            if call_sid:
                response.hangup()
            return Response(content=str(response), media_type="text/xml")
        elif unclear_count >= 2:
            error_text = "I'm having trouble understanding. Could you please speak a bit slower and more clearly?"
            add_deepgram_tts_to_response(voice_handler, response, error_text, language='en')
        else:
            error_text = "I didn't catch that. Please speak clearly."
            add_deepgram_tts_to_response(voice_handler, response, error_text, language='en')

        if call_sid:
            gather = response.gather(input="speech", timeout=10, speech_timeout="auto", action=f"/process_speech/{call_sid}", method="POST")
            # Removed gather.say() - using Deepgram TTS only, no TwiML say()
            response.redirect(f"/process_speech/{call_sid}")
        return Response(content=str(response), media_type="text/xml")

