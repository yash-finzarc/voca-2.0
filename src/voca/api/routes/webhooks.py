"""
Twilio webhook endpoints for handling calls.

This module now supports two paths:
- Legacy <Gather>-based speech recognition (Twilio STT)
- Real-Time Transcriptions using Deepgram Nova-3 Hindi via Twilio
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import Request, Response, HTTPException
from fastapi.routing import APIRouter
from twilio.twiml.voice_response import VoiceResponse, Start, Transcription

from src.voca.api.app_state import app_state
from src.voca.api.utils import resolve_org_id
from src.voca.twilio_config import get_twilio_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/outbound")
async def handle_outbound_call(request: Request):
    """Handle outbound call TwiML using Deepgram Nova-3 Hindi Real-Time Transcriptions."""
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

    # Enable Real-Time Transcriptions for Hindi using Google's short model (supported combo)
    if call_sid:
        config = get_twilio_config()
        webhook_url = config.get_webhook_url()
        # Typically .../webhook/voice; strip that to get the base URL
        base_url = webhook_url.replace("/webhook/voice", "")

        transcription_callback_url = f"{base_url}/transcription/{call_sid}"
        start = Start()
        transcription = Transcription(
            statusCallbackUrl=transcription_callback_url,
            transcriptionEngine="google",
            speechModel="short",
            languageCode="hi-IN",
            enableAutomaticPunctuation="true",
            profanityFilter="true",
            hints="संपर्क, सेवा, समर्थन, ग्राहक",
        )
        start.append(transcription)

        response.append(start)
        logger.info(
            f"[TRANSCRIPTION] Enabled Real-Time Transcription (google, hi-IN, short) "
            f"for outbound call {call_sid} (callback={transcription_callback_url})"
        )

    # Generate greeting from system prompt
    try:
        org_id = form_data.get("organization_id") or app_state.get_orchestrator().default_organization_id
        greeting = app_state.get_orchestrator().generate_greeting(
            conversation_id=call_sid,
            organization_id=org_id,
        )
    except Exception as e:
        logger.error(f"Error generating greeting: {e}")
        greeting = "Hello! This is VOCA calling. How can I help you today?"

    # Log greeting as AI response
    if call_sid:
        logger.info(f"📞 Call {call_sid[:8]}... | AI: {greeting}")
    response.say(greeting)

    # IMPORTANT:
    # Twilio Real-Time Transcriptions (Deepgram) do NOT use TwiML returned from the
    # /transcription callback to control the call. The call is controlled ONLY by this
    # initial TwiML. To keep the call open after the greeting, we also include a
    # legacy <Gather> loop here. Deepgram still streams in parallel for better logs
    # and future migration, while <Gather> ensures the call doesn't hang up.
    if call_sid:
        gather = response.gather(
            input="speech",
            timeout=60,
            speech_timeout="auto",
            language="hi-IN",
            action=f"/process_speech/{call_sid}",
            method="POST",
        )
        gather.say("I'm listening...")
        response.redirect(f"/process_speech/{call_sid}")

    return Response(content=str(response), media_type="text/xml")


@router.post("/webhook/voice")
async def handle_incoming_call_webhook(request: Request):
    """Handle incoming Twilio call webhook using Deepgram Nova-3 Hindi Real-Time Transcriptions."""
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

    # Enable Real-Time Transcriptions for Hindi using Google's short model (supported combo)
    if call_sid:
        config = get_twilio_config()
        webhook_url = config.get_webhook_url()
        base_url = webhook_url.replace("/webhook/voice", "")

        transcription_callback_url = f"{base_url}/transcription/{call_sid}"
        start = Start()
        transcription = Transcription(
            statusCallbackUrl=transcription_callback_url,
            transcriptionEngine="google",
            speechModel="short",
            languageCode="hi-IN",
            enableAutomaticPunctuation="true",
            profanityFilter="true",
            hints="संपर्क, सेवा, समर्थन, ग्राहक",
        )
        start.append(transcription)

        response.append(start)
        logger.info(
            f"[TRANSCRIPTION] Enabled Real-Time Transcription (google, hi-IN, short) "
            f"for inbound call {call_sid} (callback={transcription_callback_url})"
        )

    # Generate greeting from system prompt
    try:
        org_id = form_data.get("organization_id") or app_state.get_orchestrator().default_organization_id
        greeting = app_state.get_orchestrator().generate_greeting(
            conversation_id=call_sid,
            organization_id=org_id,
        )
    except Exception as e:
        logger.error(f"Error generating greeting: {e}")
        greeting = "Hello! You've reached VOCA, your AI voice assistant. Please speak after the tone."

    # Log greeting as AI response
    if call_sid:
        logger.info(f"📞 Call {call_sid[:8]}... | AI: {greeting}")
    response.say(greeting)

    # See note in handle_outbound_call: we must keep a TwiML verb active to prevent
    # Twilio from ending the call immediately. We therefore also use a legacy
    # <Gather> loop here, while Deepgram continues streaming in parallel.
    if call_sid:
        gather = response.gather(
            input="speech",
            timeout=60,
            speech_timeout="auto",
            language="hi-IN",
            action=f"/process_speech/{call_sid}",
            method="POST",
        )
        gather.say("I'm listening...")
        response.redirect(f"/process_speech/{call_sid}")

    return Response(content=str(response), media_type="text/xml")


@router.post("/process_speech/{call_sid}")
async def handle_speech_webhook(call_sid: str, request: Request):
    """LEGACY: Handle speech input from Twilio <Gather> webhooks (not used with Deepgram)."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        response = VoiceResponse()
        response.say("Service temporarily unavailable")
        return Response(content=str(response), media_type='text/xml')
    
    voice_handler = twilio_manager.voice_handler
    
    if call_sid not in voice_handler.active_calls:
        raise HTTPException(status_code=404, detail="Call not found")
    
    form_data = await request.form()
    speech_result = form_data.get("SpeechResult", "") or ""
    confidence_str = form_data.get("Confidence", "0")
    try:
        confidence = float(confidence_str)
        # Clamp confidence to valid range [0.0, 1.0]
        confidence = max(0.0, min(1.0, confidence))
    except (ValueError, TypeError):
        confidence = 0.0

    # Primary source of truth: latest completed Real-Time Transcription text
    call_data = voice_handler.active_calls.get(call_sid, {})
    transcripts = call_data.get("transcriptions", [])
    user_text = ""

    if transcripts:
        latest = transcripts[-1]
        t_text = (latest.get("text") or "").strip()
        if t_text:
            user_text = t_text

    # Fallback: if we have no transcript text yet, fall back to SpeechResult
    if not user_text and speech_result.strip():
        user_text = speech_result.strip()

    # If we still have nothing, go to the "no speech" branch
    if user_text:
        # Log user message clearly in terminal
        logger.info(f"📞 Call {call_sid[:8]}... | USER: {user_text}")
        app_state._log_callback(
            f"Speech received for call {call_sid}: {user_text} "
            f"(confidence={confidence}, source={'rt_transcription' if transcripts else 'gather'})"
        )
        try:
            # User message and AI response are logged in orchestrator.generate_reply
            ai_response = voice_handler.orchestrator.generate_reply(
                user_text,
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
                gather = response.gather(
                    input="speech",
                    timeout=60,
                    speech_timeout="auto",
                    language="hi-IN",
                    action=f"/process_speech/{call_sid}",
                    method="POST",
                )
                gather.say("I'm listening...")
                response.redirect(f"/process_speech/{call_sid}")
            return Response(content=str(response), media_type="text/xml")
    else:
        # No speech or empty result – gently prompt again, but ALWAYS start a new <Gather>
        response = VoiceResponse()
        response.say("I didn't catch that. Please speak clearly.")
        if call_sid:
            gather = response.gather(
                input="speech",
                timeout=60,
                speech_timeout="auto",
                language="hi-IN",
                action=f"/process_speech/{call_sid}",
                method="POST",
            )
            gather.say("I'm listening...")
            response.redirect(f"/process_speech/{call_sid}")
        return Response(content=str(response), media_type="text/xml")


@router.post("/transcription/{call_sid}")
async def handle_transcription_webhook(call_sid: str, request: Request):
    """Handle real-time transcription callbacks from Twilio (Deepgram Nova-3 Hindi)."""
    twilio_manager = app_state.get_twilio_manager()
    if not twilio_manager:
        # If Twilio isn't configured, just acknowledge so the call isn't broken.
        return Response(content="", media_type="text/plain")

    voice_handler = twilio_manager.voice_handler
    form_data = await request.form()

    # Extract transcription data from Twilio
    transcription_text = form_data.get("TranscriptionText", "")
    transcription_status = form_data.get("TranscriptionStatus", "")
    transcription_sid = form_data.get("TranscriptionSid", "")
    confidence = form_data.get("Confidence", "0")
    language = form_data.get("Language") or form_data.get("LanguageCode")

    logger.info(
        f"[TRANSCRIPTION] Call {call_sid}: Status={transcription_status}, "
        f"Text='{transcription_text}', Confidence={confidence}, Language={language or 'N/A'}"
    )

    # Only act on completed transcriptions that contain text
    if transcription_status == "completed" and transcription_text and transcription_text.strip():
        try:
            # Optionally look up language via Twilio API if missing
            if not language and transcription_sid:
                try:
                    client = voice_handler.client
                    trans_obj = client.transcriptions(transcription_sid).fetch()
                    language = getattr(trans_obj, "language", None) or getattr(
                        trans_obj, "languageCode", None
                    )
                    if language:
                        logger.info(f"[TRANSCRIPTION] Fetched language from API: {language}")
                except Exception as lang_e:
                    logger.debug(f"[TRANSCRIPTION] Could not fetch language from API: {lang_e}")

            # Run the AI pipeline on the transcription text
            ai_response = voice_handler.orchestrator.generate_reply(
                transcription_text,
                conversation_id=call_sid,
                call_sid=call_sid,
            )
            logger.info(f"[TRANSCRIPTION] AI Response: {ai_response}")

            # Store transcription metadata on the call for later inspection
            if call_sid in voice_handler.active_calls:
                call_data = voice_handler.active_calls[call_sid]
                if "transcriptions" not in call_data:
                    call_data["transcriptions"] = []
                call_data["transcriptions"].append(
                    {
                        "text": transcription_text,
                        "status": transcription_status,
                        "transcription_sid": transcription_sid,
                        "confidence": confidence,
                        "language": language,
                        "languageCode": language,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

                # Log all distinct detected languages for this call
                languages = {
                    (t.get("language") or t.get("languageCode"))
                    for t in call_data["transcriptions"]
                    if t.get("language") or t.get("languageCode")
                }
                if languages:
                    logger.info(
                        f"[CALL_INFO] Call {call_sid} - Detected Languages: {', '.join(sorted(languages))}"
                    )

            # Respond with TwiML to speak the AI response
            response = VoiceResponse()
            response.say(ai_response)
            return Response(content=str(response), media_type="text/xml")

        except Exception as e:
            logger.error(f"[TRANSCRIPTION] Error processing transcription: {e}", exc_info=True)
            # Return empty TwiML so call continues even on backend error
            response = VoiceResponse()
            return Response(content=str(response), media_type="text/xml")

    # For in-progress or empty transcriptions, return an empty but valid TwiML <Response>
    # so Twilio keeps the call open and continues streaming.
    logger.debug(
        f"[TRANSCRIPTION] Ignoring transcription for call {call_sid}: "
        f"status={transcription_status}, has_text={bool(transcription_text)}"
    )
    empty = VoiceResponse()
    return Response(content=str(empty), media_type="text/xml")

