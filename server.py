import os
import base64
import json
import websockets
import asyncio
from supabase import create_client
from dotenv import load_dotenv
from src.voca.langgraph_agent import FUNCTION_MAP

load_dotenv()

def sts_connect():
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise Exception("DEEPGRAM_API_KEY is not set")

    sts_ws = websockets.connect(
        "wss://agent.deepgram.com/v1/agent/converse",
        subprotocols=["token", "api_key"],
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
            "language": "en",
            "listen": {
                "provider": {
                    "type": "deepgram",
                    "model": "nova-3",
                    "keyterms": ["hello", "goodbye"]
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
                    "type": "deepgram",
                    "model": "aura-2-thalia-en"
                }
            },
            "greeting": welcome_message,
            "functions": [
                {
                    "name": "book_appointment",
                    "description": "Book an appointment for a customer. Use this when the customer wants to schedule an appointment, meeting, or consultation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_name": {
                                "type": "string",
                                "description": "The name of the customer booking the appointment"
                            },
                            "appointment_date": {
                                "type": "string",
                                "description": "The date of the appointment in YYYY-MM-DD format"
                            },
                            "appointment_time": {
                                "type": "string",
                                "description": "The time of the appointment in HH:MM format (24-hour format)"
                            },
                            "service_type": {
                                "type": "string",
                                "description": "The type of service or appointment (e.g., consultation, checkup, follow-up)"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Any additional notes or special requests for the appointment"
                            }
                        },
                        "required": ["customer_name", "appointment_date", "appointment_time"]
                    }
                },
                {
                    "name": "book_room",
                    "description": "Book a room or venue for a customer. Use this when the customer wants to reserve a room, meeting space, or venue.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_name": {
                                "type": "string",
                                "description": "The name of the customer booking the room"
                            },
                            "check_in_date": {
                                "type": "string",
                                "description": "The check-in date in YYYY-MM-DD format"
                            },
                            "check_out_date": {
                                "type": "string",
                                "description": "The check-out date in YYYY-MM-DD format (for multi-day bookings)"
                            },
                            "room_type": {
                                "type": "string",
                                "description": "The type of room requested (e.g., single, double, suite, conference room, meeting hall)"
                            },
                            "number_of_guests": {
                                "type": "integer",
                                "description": "The number of guests or people for the room booking"
                            },
                            "special_requests": {
                                "type": "string",
                                "description": "Any special requests or requirements for the room booking"
                            }
                        },
                        "required": ["customer_name", "check_in_date", "room_type"]
                    }
                }
            ]
        }
    }
    
    return config

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

def get_system_prompt(prompt_name: str):
    response = (
        supabase
        .table("system_prompts")
        .select("system_prompt, welcome_message")
        .eq("name", prompt_name)
        .single()
        .execute()
    )

    return response.data["system_prompt"], response.data["welcome_message"]

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
            elif event == "stop":
                break
                while len(inbuffer) > BUFFER_SIZE:
                    chunk = inbuffer[:BUFFER_SIZE]
                    audio_queue.put_nowait(chunk)
                    inbuffer = inbuffer[BUFFER_SIZE:]
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
            print(f"Sending config to Deepgram: {json.dumps(config_message)[:200]}...")
            await sts_ws.send(json.dumps(config_message))
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
