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

# Import custom LLM pipeline components
from src.voca.orchestrator import VocaOrchestrator
from src.voca.services.sarvam_stt import SarvamSTTClient
from src.voca.services.sarvam_tts import SarvamTTSClient
from src.voca.audio_utils import mulaw_to_pcm, pcm_to_mulaw

router = APIRouter()
logger = logging.getLogger(__name__)


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

