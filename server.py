import os
import base64
import json
import websockets
import asyncio
from supabase import create_client
from dotenv import load_dotenv
from src.voca.langgraph_agent import FUNCTION_MAP
from ..langgraph_agent import FUNCTION_MAP
from langgraph_agent import FUNCTION_MAP

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
    with open("config.json", "r") as f:
        return json.load(f)

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

async def handle_barge_in(decoded,twilio_ws, streamsid):
    if decoded["type"] == "UserStartedSpeaking":
        clear_message = {
            "event": "clear",
            "streamSid": streamsid
        }
        await twilio_ws.send(json.dumps(clear_message))

        async def execute_function_call(func_name, arguments):
            if func_name in FUNCTION_MAP:
                result = await FUNCTION_MAP[func_name](**arguments)
                print(f"Function call result: {result}")
                return result
            else:
                print{"error"f"Unknown function: {func_name}"}
                print(result)
                return result
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

            result = execute_function_call(func_name, arguments)

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
        await handle_function_call(decoded, sts_ws)

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
            data = json.load(message)
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
    audio_queue = asyncio.Queue()
    streamsid_queue = asyncio.Queue()

    async with sts_connect() as sts_ws:
        config_message = load_config()
        await sts_ws.send(json.dumps(config_message))

        await asyncio.wait(
            [
                asyncio.ensure_future(sts_sender(sts_ws, audio_queue)),
                asyncio.ensure_future(sts_receiver(sts_ws, twilio_ws, streamsid_queue)),
                asyncio.ensure_future(twilio_receiver(twilio_ws, audio_queue, streamsid_queue)),
            ]
        )

        await twilio_ws.close()


async def server():
    await websockets.serve(twilio_handler, host="0.0.0.0", port=5000)
    print("Twilio server started")
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(server())
