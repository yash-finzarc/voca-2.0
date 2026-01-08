import logging
import asyncio
import base64
import json
from datetime import datetime

from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, JSONResponse

from src.voca.api.state import app_state
from src.voca.Twilio.twilio_config import get_twilio_config
from src.voca.config import Config
from src.voca.services.ultravox import UltravoxSession, create_ultravox_call

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
    
    logger.info(f"[ULTRAVOX] Outbound call to {to_number}, SID: {call_sid} (TwiML Bin should handle this)")
    
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
    
    logger.info(f"[ULTRAVOX] Incoming call from {from_number}, SID: {call_sid} (TwiML Bin should handle this)")
    
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
    Handle Twilio Media Streams WebSocket connection using Ultravox.
    This endpoint bridges Twilio Media Streams with Ultravox's AI voice assistant.
    """
    # #region agent log
    try:
        with open(r"c:\Users\Yash\Desktop\voca-2.0\.cursor\debug.log", "a", encoding="utf-8") as f:
            entry = {
                "sessionId": "debug-session",
                "runId": "websocket-handler",
                "hypothesisId": "C",
                "location": "twilio_webhooks.py:handle_twilio_websocket:1",
                "message": "WebSocket handler called",
                "timestamp": int(datetime.now().timestamp() * 1000),
                "data": {
                    "client": str(websocket.client) if websocket.client else None,
                    "url": str(websocket.url) if hasattr(websocket, "url") else None
                }
            }
            f.write(json.dumps(entry) + "\n")
    except:
        pass
    # #endregion
    
    client_ip = websocket.client.host if websocket.client else "unknown"
    logger.info(f"[ULTRAVOX] ===== WebSocket connection attempt to /twilio from {client_ip} =====")
    
    # Get Ultravox API key
    ultravox_api_key = Config.ultravox_api_key
    if not ultravox_api_key:
        logger.error("[ULTRAVOX] ULTRAVOX_API_KEY not set")
        try:
            await websocket.accept()
            await websocket.close(code=1008, reason="Ultravox API key not configured")
        except Exception:
            pass
        return
    
    # State management
    call_sid = ""
    streamsid = ""
    ultravox_session: UltravoxSession = None
    
    try:
        await websocket.accept()
        logger.info(f"[ULTRAVOX] ✓ WebSocket accepted from {client_ip}")
        
        # Create Ultravox call
        logger.info("[ULTRAVOX] Creating Ultravox call...")
        try:
            call_info = await create_ultravox_call(
                api_key=ultravox_api_key,
                organization_id=Config.default_organization_id
            )
            join_url = call_info.get("joinUrl")
            if not join_url:
                logger.error("[ULTRAVOX] No joinUrl returned from Ultravox")
                await websocket.close(code=1008, reason="Failed to create Ultravox call")
                return
            
            logger.info(f"[ULTRAVOX] ✓ Ultravox call created, joinUrl: {join_url}")
        except Exception as e:
            logger.error(f"[ULTRAVOX] Failed to create Ultravox call: {e}", exc_info=True)
            await websocket.close(code=1008, reason="Failed to create Ultravox call")
            return
        
        # Initialize Ultravox session
        ultravox_session = UltravoxSession(
            api_key=ultravox_api_key,
            organization_id=Config.default_organization_id
        )
        
        # Set up audio output callback (Ultravox → Twilio)
        async def ultravox_audio_callback(audio_bytes: bytes):
            """Callback for audio from Ultravox - send to Twilio."""
            nonlocal streamsid
            
            if not streamsid:
                return
            
            # Ultravox handles Twilio audio format natively - no conversion needed
            # Encode audio to base64
            audio_payload = base64.b64encode(audio_bytes).decode("ascii")
            
            # Send to Twilio Media Stream
            media_message = {
                "event": "media",
                "streamSid": streamsid,
                "media": {"payload": audio_payload}
            }
            
            try:
                await websocket.send_json(media_message)
                # Log first audio frame
                if not hasattr(ultravox_audio_callback, '_logged'):
                    logger.info(f"[ULTRAVOX] ✓ First audio frame sent to Twilio: {len(audio_bytes)} bytes")
                    ultravox_audio_callback._logged = True
            except Exception as e:
                logger.error(f"[ULTRAVOX] Error sending audio to Twilio: {e}", exc_info=True)
        
        ultravox_session._audio_output_callback = ultravox_audio_callback
        
        # Join Ultravox call
        logger.info("[ULTRAVOX] Joining Ultravox call...")
        ultravox_session.joinCall(join_url)
        
        # Wait for Ultravox connection to establish
        max_wait = 10.0
        wait_time = 0.0
        while wait_time < max_wait and ultravox_session.status in ["disconnected", "connecting"]:
            await asyncio.sleep(0.1)
            wait_time += 0.1
        
        if ultravox_session.status not in ["idle", "listening", "thinking", "speaking"]:
            logger.warning(f"[ULTRAVOX] Ultravox connection status: {ultravox_session.status} (may still be connecting)")
        
        logger.info(f"[ULTRAVOX] ✓ Ultravox session status: {ultravox_session.status}")
        
        # Main message loop - handle Twilio Media Stream events
        logger.info("[ULTRAVOX] Starting message loop - waiting for Twilio events...")
        
        try:
            async for message in websocket.iter_text():
                try:
                    data = json.loads(message)
                    event = data.get("event")
                    
                    if event == "start":
                        logger.info("[TWILIO] event=start received")
                        start = data.get("start", {})
                        streamsid = start.get("streamSid", "")
                        call_sid = start.get("callSid", "")
                        logger.info(f"[ULTRAVOX] Stream started: SID={streamsid}, CallSid={call_sid}")
                    
                    elif event == "media":
                        media = data.get("media", {})
                        if media.get("track") == "inbound":
                            # Inbound audio from Twilio - send directly to Ultravox (no conversion needed)
                            audio_chunk = base64.b64decode(media.get("payload", ""))
                            
                            try:
                                await ultravox_session.send_audio(audio_chunk)
                                
                                # Log first audio frame
                                if not hasattr(handle_twilio_websocket, '_audio_sent_logged'):
                                    logger.info(f"[ULTRAVOX] ✓ First audio frame sent to Ultravox: {len(audio_chunk)} bytes")
                                    handle_twilio_websocket._audio_sent_logged = True
                            except Exception as e:
                                logger.error(f"[ULTRAVOX] Error sending audio to Ultravox: {e}", exc_info=True)
                    
                    elif event == "stop":
                        logger.info("[TWILIO] event=stop received")
                        logger.info("[ULTRAVOX] WebSocket loop exiting due to STOP event")
                        break
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"[ULTRAVOX] Failed to parse message: {e}")
                    continue
                except Exception as e:
                    logger.error(f"[ULTRAVOX] Error processing message: {e}", exc_info=True)
                    if "not connected" in str(e).lower() or "closed" in str(e).lower():
                        logger.info("[ULTRAVOX] WebSocket loop exiting due to connection closed")
                        break
                    continue
        
        except Exception as e:
            logger.error(f"[ULTRAVOX] Error in message loop: {e}", exc_info=True)
    
    except WebSocketDisconnect:
        logger.info("[ULTRAVOX] WebSocket disconnected by client")
    except Exception as e:
        logger.error(f"[ULTRAVOX] Error in WebSocket handler: {e}", exc_info=True)
        import traceback
        logger.error(f"[ULTRAVOX] Traceback: {traceback.format_exc()}")
    finally:
        # Cleanup - leave Ultravox call
        logger.info("[ULTRAVOX] Cleaning up connections...")
        if ultravox_session:
            try:
                await ultravox_session.leaveCall()
                logger.info("[ULTRAVOX] ✓ Ultravox session closed")
            except Exception as e:
                logger.warning(f"[ULTRAVOX] Error closing Ultravox session: {e}")
