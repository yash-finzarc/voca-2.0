"""
Real-time voice AI system using SarvamAI STT/TTS with Twilio Media Streams.
Handles full-duplex audio streaming with barge-in support.

AUDIO PIPELINE:
Twilio (μ-law, 8kHz) → PCM conversion → SarvamAI STT → Transcripts → 
LLM (OpenAI) → Response text → SarvamAI TTS → PCM audio → μ-law conversion → Twilio

NOTE: SarvamAI API endpoints and message formats are based on common WebSocket
streaming patterns. Adjust the endpoints in sarvam_stt.py and sarvam_tts.py based
on actual SarvamAI API documentation if needed.
"""
import os
import base64
import json
import re
import websockets
import asyncio
from supabase import create_client
from dotenv import load_dotenv
from openai import AsyncOpenAI
import logging

# Import SarvamAI services and audio utilities
from src.voca.services.sarvam_stt import SarvamSTTClient
from src.voca.services.sarvam_tts import SarvamTTSClient
from src.voca.audio_utils import mulaw_to_pcm, pcm_to_mulaw
from src.voca.langgraph_agent import FUNCTION_MAP

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client for LLM
openai_client = None
if os.getenv("OPENAI_API_KEY"):
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    logger.info("OpenAI client initialized")
else:
    logger.warning("OPENAI_API_KEY not set - LLM responses will fail")

# Initialize Supabase client
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)


def get_system_prompt(prompt_name: str):
    """
    Get system prompt and welcome message from Supabase.
    First tries to find by name and is_active=True, then falls back to is_default=True.
    """
    # Try to find by name and is_active
    response = (
        supabase
        .table("system_prompts")
        .select("prompt, welcome_message")
        .eq("name", prompt_name)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    
    if response.data:
        row = response.data[0]
        return row["prompt"], row["welcome_message"]
    
    # Fallback to default prompt if named prompt not found
    response = (
        supabase
        .table("system_prompts")
        .select("prompt, welcome_message")
        .eq("is_default", True)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    
    if not response.data:
        raise RuntimeError("No active system prompt found (neither by name nor default)")
    
    row = response.data[0]
    return row["prompt"], row["welcome_message"]


async def execute_function_call(func_name, arguments):
    """Execute a function call from the FUNCTION_MAP."""
    if func_name in FUNCTION_MAP:
        result = await FUNCTION_MAP[func_name](**arguments)
        logger.info(f"Function call result: {result}")
        return result
    else:
        logger.error(f"Unknown function: {func_name}")
        return {"error": f"Unknown function: {func_name}"}


def strip_markdown(text: str) -> str:
    """Remove markdown formatting from text to prevent TTS from reading formatting characters."""
    if not text:
        return text
    # Remove bold/italic markers (**text**, *text*)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Remove markdown list markers (-, *, •)
    text = re.sub(r'^[\s]*[-*•]\s+', '', text, flags=re.MULTILINE)
    # Remove markdown headers (#)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    # Clean up extra whitespace
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()


async def generate_llm_response(user_message: str, system_prompt: str, conversation_history: list) -> str:
    """
    Generate LLM response using OpenAI.
    
    Args:
        user_message: User's transcribed message
        system_prompt: System prompt for the conversation
        conversation_history: List of previous messages in format [{"role": "user/assistant", "content": "..."}]
    
    Returns:
        Assistant's response text
    """
    if not openai_client:
        logger.error("OpenAI client not initialized")
        return "I'm sorry, I'm having trouble processing your request right now."
    
    try:
        # Build messages list
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})
        
        # Call OpenAI API
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        
        assistant_message = response.choices[0].message.content
        logger.info(f"LLM response generated: {assistant_message[:100]}...")
        return assistant_message
        
    except Exception as e:
        logger.error(f"Error generating LLM response: {e}", exc_info=True)
        return "I'm sorry, I encountered an error processing your request."


async def twilio_receiver(
    twilio_ws,
    stt_client: SarvamSTTClient,
    streamsid_queue: asyncio.Queue,
    audio_queue: asyncio.Queue
):
    """
    Receive audio from Twilio Media Streams, convert μ-law to PCM, and send to STT.
    
    Args:
        twilio_ws: WebSocket connection to Twilio
        stt_client: SarvamAI STT client
        streamsid_queue: Queue to send stream SID when received
        audio_queue: Queue for buffered audio chunks (unused, kept for compatibility)
    """
    BUFFER_SIZE = 20 * 160  # 20ms of audio at 8kHz (160 samples * 1 byte per μ-law sample)
    inbuffer = bytearray(b"")
    
    logger.info("Twilio receiver started")
    
    async for message in twilio_ws:
        try:
            # Parse JSON message from Twilio
            data = json.loads(message)
            event = data.get("event")
            
            if event == "start":
                logger.info("Twilio stream started")
                start = data.get("start", {})
                streamsid = start.get("streamSid", "")
                logger.info(f"Stream SID: {streamsid}")
                if streamsid:
                    await streamsid_queue.put(streamsid)
                
            elif event == "connected":
                logger.info("Twilio stream connected")
                continue
                
            elif event == "media":
                # Receive μ-law audio from Twilio
                media = data.get("media", {})
                mulaw_chunk = base64.b64decode(media.get("payload", ""))
                
                if media.get("track") == "inbound":
                    inbuffer.extend(mulaw_chunk)
                    
                    # Process buffer and convert to PCM in chunks
                    while len(inbuffer) >= BUFFER_SIZE:
                        mulaw_to_convert = bytes(inbuffer[:BUFFER_SIZE])
                        inbuffer = inbuffer[BUFFER_SIZE:]
                        
                        # Convert μ-law to PCM
                        pcm_audio = mulaw_to_pcm(mulaw_to_convert)
                        
                        # Send PCM to STT
                        if stt_client.is_connected:
                            await stt_client.send_audio(pcm_audio)
                            
            elif event == "stop":
                logger.info("Twilio stream stopped")
                # Send any remaining audio in buffer
                while len(inbuffer) > 0:
                    mulaw_to_convert = bytes(inbuffer[:BUFFER_SIZE] if len(inbuffer) >= BUFFER_SIZE else inbuffer)
                    inbuffer = inbuffer[len(mulaw_to_convert):]
                    
                    if mulaw_to_convert:
                        pcm_audio = mulaw_to_pcm(mulaw_to_convert)
                        if stt_client.is_connected:
                            await stt_client.send_audio(pcm_audio)
                break
                
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Twilio message: {e}")
        except Exception as e:
            logger.error(f"Error in twilio_receiver: {e}", exc_info=True)
            break


async def handle_tts_audio(
    pcm_audio: bytes,
    twilio_ws,
    streamsid: str
):
    """
    Convert PCM audio to μ-law and send to Twilio Media Streams.
    
    Args:
        pcm_audio: PCM audio bytes (16-bit, little-endian)
        twilio_ws: WebSocket connection to Twilio
        streamsid: Twilio stream SID
    """
    try:
        # Convert PCM to μ-law
        mulaw_audio = pcm_to_mulaw(pcm_audio)
        
        # Send to Twilio
        media_message = {
            "event": "media",
            "streamSid": streamsid,
            "media": {"payload": base64.b64encode(mulaw_audio).decode("ascii")}
        }
        await twilio_ws.send(json.dumps(media_message))
        
    except Exception as e:
        logger.error(f"Error sending TTS audio to Twilio: {e}", exc_info=True)


async def twilio_handler(twilio_ws):
    """
    Main handler for Twilio Media Streams WebSocket connection.
    Manages STT, LLM, and TTS pipeline with barge-in support.
    """
    logger.info("Twilio handler started")
    
    # Get SarvamAI API key
    sarvam_api_key = os.getenv("SARVAM_API_KEY")
    if not sarvam_api_key:
        logger.error("SARVAM_API_KEY not set in environment variables")
        await twilio_ws.close()
        return
    
    # Get system prompt and welcome message
    try:
        system_prompt, welcome_message = get_system_prompt("customer_service")
    except Exception as e:
        logger.error(f"Error loading system prompt: {e}")
        system_prompt = "You are a helpful assistant."
        welcome_message = "Hello, how can I help you today?"
    
    # Initialize STT and TTS clients
    stt_client = SarvamSTTClient(api_key=sarvam_api_key, language="en-IN", sample_rate=8000)
    tts_client = SarvamTTSClient(api_key=sarvam_api_key, language="en-IN", voice="anushka", sample_rate=8000)
    
    # State management
    streamsid = ""
    conversation_history = []
    current_tts_task = None
    user_speaking = False
    tts_active = False
    
    # Queue for audio chunks
    audio_queue = asyncio.Queue()
    
    try:
        # Connect to SarvamAI STT
        logger.info("Connecting to SarvamAI STT...")
        await stt_client.connect()
        
        # Connect to SarvamAI TTS
        logger.info("Connecting to SarvamAI TTS...")
        await tts_client.connect()
        
        # Set up TTS audio callback (will be updated with streamsid once received)
        async def tts_audio_callback(pcm_audio: bytes):
            """Callback for TTS audio output."""
            nonlocal streamsid
            if not tts_active or not streamsid:
                return
            await handle_tts_audio(pcm_audio, twilio_ws, streamsid)
        
        tts_client.set_audio_callback(tts_audio_callback)
        
        # Set up STT transcript callback
        async def stt_transcript_callback(transcript: str, is_final: bool):
            """Callback for STT transcripts."""
            nonlocal user_speaking, current_tts_task, tts_active
            
            if not transcript.strip():
                return
            
            logger.info(f"STT transcript (final={is_final}): {transcript}")
            
            # Handle barge-in: if user starts speaking (any transcript) while TTS is active, cancel TTS
            if tts_active:
                logger.info("Barge-in detected: cancelling TTS")
                user_speaking = True
                tts_active = False
                if current_tts_task:
                    await tts_client.cancel()
                    current_tts_task = None
                
                # Clear Twilio audio buffer
                clear_message = {
                    "event": "clear",
                    "streamSid": streamsid
                }
                try:
                    await twilio_ws.send(json.dumps(clear_message))
                except Exception as e:
                    logger.error(f"Error clearing Twilio buffer: {e}")
            
            # Only process final transcripts for LLM
            if is_final:
                user_speaking = True
                tts_active = False
                
                # Generate LLM response
                logger.info(f"Generating LLM response for: {transcript}")
                assistant_response = await generate_llm_response(
                    transcript,
                    system_prompt,
                    conversation_history
                )
                
                # Update conversation history
                conversation_history.append({"role": "user", "content": transcript})
                conversation_history.append({"role": "assistant", "content": assistant_response})
                
                # Clean response text
                clean_response = strip_markdown(assistant_response)
                logger.info(f"Assistant response: {clean_response}")
                
                # Send to TTS
                tts_active = True
                user_speaking = False
                
                async def send_tts():
                    """Send text to TTS in chunks."""
                    try:
                        await tts_client.send_text_chunks(clean_response)
                    except Exception as e:
                        logger.error(f"Error in TTS: {e}", exc_info=True)
                    finally:
                        nonlocal tts_active
                        tts_active = False
                
                current_tts_task = asyncio.create_task(send_tts())
        
        stt_client.set_transcript_callback(stt_transcript_callback)
        
        # Wait for stream SID from Twilio
        streamsid_queue = asyncio.Queue()
        
        # Start Twilio receiver task (this will handle all Twilio messages)
        receiver_task = asyncio.create_task(
            twilio_receiver(twilio_ws, stt_client, streamsid_queue, audio_queue)
        )
        
        # Wait for stream SID
        try:
            streamsid = await asyncio.wait_for(streamsid_queue.get(), timeout=10.0)
            logger.info(f"Received stream SID: {streamsid}")
            
            # Send welcome message
            if welcome_message:
                tts_active = True
                async def send_welcome():
                    try:
                        await tts_client.send_text_chunks(welcome_message)
                    finally:
                        nonlocal tts_active
                        tts_active = False
                asyncio.create_task(send_welcome())
            
            # Wait for receiver task to complete
            await receiver_task
            
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for stream SID")
            receiver_task.cancel()
            raise
        
    except Exception as e:
        logger.error(f"Error in twilio_handler: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        logger.info("Cleaning up connections...")
        try:
            await stt_client.stop()
            await tts_client.stop()
        except Exception as e:
            logger.error(f"Error stopping clients: {e}")
        
        try:
            await twilio_ws.close()
            logger.info("WebSocket closed")
        except Exception as e:
            logger.error(f"Error closing WebSocket: {e}")


async def server():
    """Start WebSocket server for Twilio Media Streams."""
    server = await websockets.serve(twilio_handler, host="0.0.0.0", port=5000)
    logger.info("Twilio server started on 0.0.0.0:5000")
    await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(server())
