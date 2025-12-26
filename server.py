import os
import base64
import json
import re
import websockets
from websockets.legacy.client import connect
import asyncio
from supabase import create_client
from dotenv import load_dotenv
from src.voca.langgraph_agent import FUNCTION_MAP

load_dotenv()

def sts_connect():
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise Exception("DEEPGRAM_API_KEY is not set in environment variables")
    
    # Log API key status (first 10 chars only for security)
    api_key_preview = api_key[:10] + "..." if len(api_key) > 10 else api_key[:len(api_key)]
    print(f"Using Deepgram API key: {api_key_preview} (length: {len(api_key)})")

    # Deepgram Agent STS requires Authorization header
    # Use legacy client for websockets 15.0.1 compatibility
    print(f"Connecting to Deepgram STS: wss://agent.deepgram.com/v1/agent/converse")
    print(f"Using Authorization header (Token {api_key_preview}...)")
    
    sts_ws = connect(
        "wss://agent.deepgram.com/v1/agent/converse",
        extra_headers={
            "Authorization": f"Token {api_key}"
        }
    )
    return sts_ws

def load_config():
    # Get system prompt and welcome message from Supabase
    system_prompt, welcome_message = get_system_prompt("customer_service")
    
    # Build the config payload
    config = {
        "type": "Settings",
        "audio": {
            "input": {
                "encoding": "mulaw",
                "sample_rate": 8000
            },
            "output": {
                "encoding": "mulaw",
                "sample_rate": 8000,
                "container": "none"
            }
        },
        "agent": {
            "language": "hi",
            "listen": {
                "provider": {
                    "type": "deepgram",
                    "model": "nova-3",
                    "keyterms": ["नमस्ते", "अलविदा"]
                }
            },
            "think": {
                "provider": {
                    "type": "open_ai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.7
                },
                "prompt": system_prompt
            },
            "speak": {
                "provider": {
                    "type": "sarvam",
                    "model": "sarvam-tts",
                    "voice": "hi-IN-female"
                },
                "endpoint": {
                    "url": "https://api.sarvam.ai/tts",
                    "headers": {
                        "authorization": "Bearer {{SARVAM_API_KEY}}",
                        "content-type": "application/json"
                    }
                }
            },
            "greeting": welcome_message
            # Functions temporarily removed - Deepgram rejecting format
            # Will add back once correct format is confirmed
            # "functions": [...]
        }
    }
    
    return config

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
        print(f"Function call result: {result}")
        return result
    else:
        print(f"error: Unknown function: {func_name}")
        return {"error": f"Unknown function: {func_name}"}

async def handle_barge_in(decoded,twilio_ws, streamsid):
    if decoded["type"] == "UserStartedSpeaking":
        clear_message = {
            "event": "clear",
            "streamSid": streamsid
        }
        await twilio_ws.send(json.dumps(clear_message))

def create_function_call_response(func_id, func_name, result):
    return {
        "type": "FunctionCallResponse",
        "functionId": func_id,
        "functionName": func_name,
        "content": json.dumps(result)
    }
async def handle_function_call_request(decoded, sts_ws):
    try:
        for function_call in decoded["functions"]:
            func_name = function_call["name"]
            func_id = function_call["id"]
            arguments = json.loads(function_call["arguments"])

            print(f"Function call: {func_name} with id {func_id} and arguments {arguments}")

            result = await execute_function_call(func_name, arguments)

            function_result = create_function_call_response(func_id, func_name, result)
            await sts_ws.send(json.dumps(function_result))
            print(f"Function call response sent: {function_result}")

    except Exception as e:
            print(f"Error handling function call: {e}")
            error_result = create_function_call_response(
                func_id if func_id in locals() else "unknown",
                func_name if "func_name" in locals() else "unknown",
                {"error": f"Function call failed with: {str(e)}"}
            )
            await sts_ws.send(json.dumps(error_result))

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

async def handle_text_message(decoded,twilio_ws, sts_ws, streamsid):
    await handle_barge_in(decoded,twilio_ws, streamsid)

    if decoded["type"] == "FunctionCallRequest":
        await handle_function_call_request(decoded, sts_ws)

async def sts_sender(sts_ws, audio_queue):
    print("STS sender started")
    while True:
        chunk = await audio_queue.get()
        await sts_ws.send(chunk)

async def sts_receiver(sts_ws, twilio_ws, streamsid_queue):
    print("STS receiver started")
    streamsid = await streamsid_queue.get()
    
    async for message in sts_ws:
        if type(message) is str:
            print(message)
            decoded = json.loads(message)
            await handle_text_message(decoded,twilio_ws, sts_ws, streamsid)
            continue
        raw_mulaw = message

        media_message = {
            "event": "media",
            "streamSid": streamsid,
            "media": {"payload": base64.b64encode(raw_mulaw).decode("ascii")}
        }
        await twilio_ws.send(json.dumps(media_message))

async def twilio_receiver(twilio_ws, audio_queue, streamsid_queue):
    BUFFER_SIZE = 20*160
    inbuffer = bytearray(b"")

    async for message in twilio_ws:
        try:
            # message is a string, use json.loads() instead of json.load()
            data = json.loads(message)
            event = data["event"]

            if event == "start":
                print("get our streamsid")
                start = data["start"]
                streamsid = start["streamSid"]
                streamsid_queue.put_nowait(streamsid)
            elif event == "connected":
                continue
            elif event == "media":
                media = data["media"]
                chunk = base64.b64decode(media["payload"])
                if media["track"] == "inbound":
                    inbuffer.extend(chunk)
                    # Process buffer and send chunks to Deepgram continuously
                    while len(inbuffer) >= BUFFER_SIZE:
                        chunk_to_send = inbuffer[:BUFFER_SIZE]
                        audio_queue.put_nowait(chunk_to_send)
                        inbuffer = inbuffer[BUFFER_SIZE:]
            elif event == "stop":
                # Send any remaining audio in buffer before stopping
                while len(inbuffer) > 0:
                    chunk = inbuffer[:BUFFER_SIZE] if len(inbuffer) > BUFFER_SIZE else inbuffer
                    audio_queue.put_nowait(chunk)
                    inbuffer = inbuffer[len(chunk):]
                break
        except:
            break

async def twilio_handler(twilio_ws):
    print("twilio_handler started")
    audio_queue = asyncio.Queue()
    streamsid_queue = asyncio.Queue()

    try:
        print("Connecting to Deepgram STS...")
        async with sts_connect() as sts_ws:
            print("Connected to Deepgram STS")
            print("Loading config...")
            config_message = load_config()
            config_json = json.dumps(config_message)
            print(f"Sending config to Deepgram (full): {config_json}")
            await sts_ws.send(config_json)
            print("Config sent to Deepgram")

            print("Starting async tasks...")
            await asyncio.wait(
                [
                    asyncio.ensure_future(sts_sender(sts_ws, audio_queue)),
                    asyncio.ensure_future(sts_receiver(sts_ws, twilio_ws, streamsid_queue)),
                    asyncio.ensure_future(twilio_receiver(twilio_ws, audio_queue, streamsid_queue)),
                ]
            )
            print("Async tasks completed")
    except Exception as e:
        print(f"Error in twilio_handler: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            await twilio_ws.close()
            print("WebSocket closed")
        except:
            pass


async def server():
    await websockets.serve(twilio_handler, host="0.0.0.0", port=5000)
    print("Twilio server started")
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(server())
