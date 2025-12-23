import logging
import uuid
import time
import json
import base64
import audioop
import asyncio
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect, HTTPException
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream, Start, Transcription

from src.voca.api.app_state import app_state
from src.voca.api.models import MedicalDemoRequest, TestStatus
from src.voca.api.utils import pcm_to_mulaw, mulaw_to_pcm
from src.voca.system_prompt import MEDICAL_ASSISTANT_SYSTEM_PROMPT
from src.voca.config import Config
from src.voca.twilio_config import get_twilio_config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/demo", tags=["demo"])

# Filler audio buffers (mu-law)
FILLER_BUFFERS: List[bytes] = []

async def pregenerate_fillers():
    """Pre-generate a few 'thinking' sounds in Hindi."""
    global FILLER_BUFFERS
    phrases = [
        "Ji, main check kar raha hoon...",
        "Ek minute, main aapki reports dekh raha hoon...",
        "Theek hai, main jankari nikaal raha hoon..."
    ]
    
    try:
        from sarvamai import SarvamAI
        client = SarvamAI(api_subscription_key=Config.sarvam_api_key)
        for p in phrases:
            response = client.text_to_speech.convert(
                text=p,
                target_language_code="hi-IN",
                speaker="anushka",
                model="bulbul:v2"
            )
            audio_data = None
            if hasattr(response, 'audios') and response.audios:
                audio_data = response.audios[0]
                if isinstance(audio_data, str):
                    audio_data = base64.b64decode(audio_data)
            
            if audio_data:
                # Resample and convert to mu-law
                mulaw = audioop.ratecv(audio_data, 2, 1, 22050, 8000, None)[0]
                mulaw = audioop.lin2ulaw(mulaw, 2)
                FILLER_BUFFERS.append(mulaw)
        logger.info(f"Pre-generated {len(FILLER_BUFFERS)} filler phrases")
    except Exception as e:
        logger.error(f"Failed to pre-generate fillers: {e}")

# Global store for active demo WebSockets
active_websockets: Dict[str, WebSocket] = {}

# Helper to format test results for the prompt
def format_test_results(results):
    lines = []
    for r in results:
        status_emoji = "🔴" if r.status == TestStatus.RED else "🟡" if r.status == TestStatus.YELLOW else "🟢"
        lines.append(f"- {r.name}: {r.value} {r.unit} ({status_emoji} {r.status})")
    return "\n".join(lines)

@router.post("/medical-call")
async def trigger_medical_call(request: MedicalDemoRequest, req: Request):
    """Initiate a medical demo call with pre-generated greeting."""
    demo_id = str(uuid.uuid4())
    
    # 1. Compose the personalized greeting
    red_results = [r.name for r in request.test_results if r.status == TestStatus.RED]
    greeting_text = f"Namaste {request.patient_name}, main aapka medical assistant hoon. "
    if red_results:
        greeting_text += f"Maine aapki reports dekhi hain, aur aapka {', '.join(red_results)} thoda badha hua hai. "
    else:
        greeting_text += "Maine aapki reports dekhi hain, sab theek lag raha hai. "
    greeting_text += "Kya aap is baare mein kuch poochna chahte hain?"

    # 2. Pre-generate the greeting audio (PCM16)
    try:
        from sarvamai import SarvamAI
        client = SarvamAI(api_subscription_key=Config.sarvam_api_key)
        response = client.text_to_speech.convert(
            text=greeting_text,
            target_language_code="hi-IN",
            speaker="anushka",
            model="bulbul:v2"
        )
        
        audio_data = None
        if hasattr(response, 'audios') and response.audios:
            audio_data = response.audios[0]
            if isinstance(audio_data, str):
                audio_data = base64.b64decode(audio_data)
        
        if not audio_data:
            raise ValueError("Failed to get audio data from Sarvam")

        # 3. Convert to mu-law (Twilio format) and resample to 8kHz
        resampled = audioop.ratecv(audio_data, 2, 1, 22050, 8000, None)[0]
        mulaw_data = audioop.lin2ulaw(resampled, 2)
        
        # 4. Store context
        app_state.demo_contexts[demo_id] = {
            "patient_name": request.patient_name,
            "age": request.age,
            "gender": request.gender,
            "medical_report": format_test_results(request.test_results),
            "medical_advice": request.medical_advice,
            "greeting_audio": mulaw_data,
            "greeting_text": greeting_text,
            "messages": [], # Track messages for this demo session
            "call_sid": None
        }
        
        # 5. Trigger Twilio Call
        twilio_manager = app_state.get_twilio_manager()
        config = get_twilio_config()
        base_url = config.get_webhook_url().replace("/webhook/voice", "")
        
        # Outbound URL for Twilio to get TwiML
        outbound_url = f"{base_url}/api/demo/outbound-twiml?demo_id={demo_id}"
        
        call = twilio_manager.voice_handler.client.calls.create(
            to=request.phone_number,
            from_=config.phone_number,
            url=outbound_url
        )
        
        app_state.demo_contexts[demo_id]["call_sid"] = call.sid
        
        return {"status": "success", "call_sid": call.sid, "demo_id": demo_id}
        
    except Exception as e:
        logger.error(f"Error in medical-call: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/outbound-twiml")
async def outbound_twiml(demo_id: str):
    """TwiML for connecting the call to the Media Stream and enabling Transcription."""
    response = VoiceResponse()
    
    # Enable Real-Time Transcription
    config = get_twilio_config()
    base_url = config.get_webhook_url().replace("/webhook/voice", "")
    transcription_url = f"{base_url}/api/demo/transcription/{demo_id}"
    
    start = Start()
    transcription = Transcription(
        statusCallbackUrl=transcription_url,
        transcriptionEngine="google",
        speechModel="short",
        languageCode="hi-IN"
    )
    start.append(transcription)
    
    ws_base_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    stream_url = f"{ws_base_url}/api/demo/media/{demo_id}"
    
    logger.info(f"[TWIML] Sending Stream URL to Twilio: {stream_url}")
    
    connect = Connect()
    connect.stream(url=stream_url)
    
    response.append(start)
    response.append(connect)
    
    # Add a dummy Gather to keep the call alive while streaming
    response.gather(input="speech", timeout=60)
    
    return Response(content=str(response), media_type="text/xml")

@router.get("/media/{demo_id}")
async def medical_media_stream_diagnostic(demo_id: str, request: Request):
    """Diagnostic endpoint to check why WebSockets are failing."""
    return {
        "error": "This endpoint requires a WebSocket connection.",
        "suggestion": "Ensure your proxy (e.g., Nginx) is configured to pass 'Upgrade' and 'Connection' headers and uses HTTP/1.1.",
        "received_headers": dict(request.headers),
        "protocol": request.scope.get("http_version")
    }

@router.post("/transcription/{demo_id}")
async def handle_demo_transcription(demo_id: str, request: Request):
    """Handle transcription and push reply via WebSocket."""
    form_data = await request.form()
    text = form_data.get("TranscriptionText", "").strip()
    status = form_data.get("TranscriptionStatus", "")
    
    if status == "completed" and text:
        logger.info(f"Demo {demo_id} Transcription: {text}")
        
        context = app_state.demo_contexts.get(demo_id)
        if not context:
            return Response(content="", media_type="text/plain")

        # 1. Generate LLM Reply
        orchestrator = app_state.get_orchestrator()
        
        # Prepare specialized system prompt
        system_prompt = MEDICAL_ASSISTANT_SYSTEM_PROMPT.format(
            patient_name=context['patient_name'],
            age=context['age'],
            gender=context['gender'],
            medical_report=context['medical_report'],
            medical_advice=context['medical_advice']
        )
        
        # Use orchestrator to generate reply
        # Note: We manually handle the prompt here to stay "lean"
        from langchain_core.messages import HumanMessage, AIMessage
        context['messages'].append(HumanMessage(content=text))
        
        # Send filler if it's been a while
        ws = active_websockets.get(demo_id)
        if ws and FILLER_BUFFERS:
            import random
            filler = random.choice(FILLER_BUFFERS)
            try:
                # We need the streamSid. For simplicity, we'll store it in context.
                stream_sid = context.get('stream_sid')
                if stream_sid:
                    await ws.send_json({
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": base64.b64encode(filler).decode('utf-8')}
                    })
            except: pass

        try:
            result = orchestrator.llm.generate_reply(
                organization_id=None,
                system_prompt=system_prompt,
                messages=context['messages'],
                collected_data={},
                lead_status=None,
                transcript=[],
            )
            reply_text = result.reply
            context['messages'].append(AIMessage(content=reply_text))
            logger.info(f"Demo {demo_id} AI Reply: {reply_text}")

            # 2. Synthesize to mu-law
            from sarvamai import SarvamAI
            client = SarvamAI(api_subscription_key=Config.sarvam_api_key)
            response = client.text_to_speech.convert(
                text=reply_text,
                target_language_code="hi-IN",
                speaker="anushka",
                model="bulbul:v2"
            )
            
            audio_data = None
            if hasattr(response, 'audios') and response.audios:
                audio_data = response.audios[0]
                if isinstance(audio_data, str):
                    audio_data = base64.b64decode(audio_data)
            
            if audio_data and ws and context.get('stream_sid'):
                resampled = audioop.ratecv(audio_data, 2, 1, 22050, 8000, None)[0]
                mulaw = audioop.lin2ulaw(resampled, 2)
                
                # Push to WebSocket
                await ws.send_json({
                    "event": "media",
                    "streamSid": context['stream_sid'],
                    "media": {"payload": base64.b64encode(mulaw).decode('utf-8')}
                })
                logger.info(f"Pushed AI reply to demo {demo_id}")

        except Exception as e:
            logger.error(f"Error processing demo reply: {e}")

    return Response(content="", media_type="text/plain")

@router.websocket("/media/{demo_id}")
async def medical_media_stream(websocket: WebSocket, demo_id: str):
    """WebSocket for bi-directional audio streaming."""
    await websocket.accept()
    active_websockets[demo_id] = websocket
    logger.info(f"WebSocket connected for demo: {demo_id}")
    
    context = app_state.demo_contexts.get(demo_id)
    if not context:
        logger.error(f"No context found for demo_id: {demo_id}")
        await websocket.close()
        return

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            
            if data['event'] == "start":
                stream_sid = data['start']['streamSid']
                context['stream_sid'] = stream_sid
                logger.info(f"Stream started: {stream_sid}")
                
                # Immediately push the pre-generated greeting
                greeting_payload = base64.b64encode(context['greeting_audio']).decode('utf-8')
                await websocket.send_json({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": greeting_payload}
                })
                logger.info("Sent pre-generated greeting")

            elif data['event'] == "stop":
                logger.info(f"Stream stopped")
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for demo: {demo_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        active_websockets.pop(demo_id, None)
        # We'll keep the context for a short while or until the call completes

