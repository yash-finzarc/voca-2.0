import asyncio
import json
import logging
import base64
import websockets
from websockets.legacy.client import connect
from typing import Callable, Dict, Any

logger = logging.getLogger(__name__)


def create_stt_client(api_key: str, config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "api_key": api_key,
        "config": {
            "language": config.get("language", "hi-IN"),
            "sample_rate": config.get("sample_rate", 16000),
            "model": config.get("model", "saarika:v2.5"),
            "input_audio_codec": "pcm_s16le",
            "high_vad_sensitivity": config.get("high_vad_sensitivity", True),
            "vad_signals": config.get("vad_signals", True),
            "flush_signal": config.get("flush_signal", True),
        },
        "websocket": None,
        "is_connected": False,
        "transcript_callback": None,
        "_receive_task": None,
        "_stop_event": asyncio.Event()
    }


async def connect_stt(client: Dict[str, Any]):
    config = client["config"]

    query_params = {
        "language-code": config["language"],
        "model": config["model"],
        "input_audio_codec": config["input_audio_codec"],
        "sample_rate": config["sample_rate"],
        "high_vad_sensitivity": str(config["high_vad_sensitivity"]).lower(),
        "vad_signals": str(config["vad_signals"]).lower(),
        "flush_signal": str(config["flush_signal"]).lower(),
    }

    uri = "wss://api.sarvam.ai/speech-to-text/ws"

    headers = {
        "Api-Subscription-Key": client["api_key"]
    }

    logger.info(f"Connecting to Sarvam STT → {uri}")

    websocket = await connect(uri, extra_headers=headers)
    client["websocket"] = websocket
    client["is_connected"] = True
    client["_stop_event"].clear()

    client["_receive_task"] = asyncio.create_task(_receive_responses(client))


async def _receive_responses(client: Dict[str, Any]):
    ws = client["websocket"]

    try:
        async for message in ws:
            if client["_stop_event"].is_set():
                break

            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "data":
                transcript = data["data"].get("transcript", "")
                metrics = data["data"].get("metrics")
                is_final = metrics is not None

                if transcript.strip():
                    cb = client.get("transcript_callback")
                    if cb:
                        await cb(transcript, is_final)

            elif msg_type == "error":
                logger.error(f"STT Error: {data}")

            elif msg_type == "events":
                logger.debug(f"STT Event: {data}")

    except websockets.exceptions.ConnectionClosed:
        client["is_connected"] = False


async def send_audio(client: Dict[str, Any], pcm_audio: bytes):
    if not client["is_connected"]:
        return

    if not pcm_audio or len(pcm_audio) % 2 != 0:
        logger.warning("Invalid PCM frame dropped")
        return

    audio_base64 = base64.b64encode(pcm_audio).decode("ascii")

    payload = {
        "audio": {
            "data": audio_base64,
            "encoding": "pcm_s16le",
            "sample_rate": client["config"]["sample_rate"]
        }
    }

    await client["websocket"].send(json.dumps(payload))


async def send_flush(client: Dict[str, Any]):
    if client["is_connected"]:
        await client["websocket"].send(json.dumps({"type": "flush"}))


def set_transcript_callback(client: Dict[str, Any], callback: Callable[[str, bool], None]):
    client["transcript_callback"] = callback


async def stop_stt(client: Dict[str, Any]):
    client["_stop_event"].set()

    if client["_receive_task"]:
        client["_receive_task"].cancel()

    if client["websocket"]:
        await client["websocket"].close()

    client["is_connected"] = False


class SarvamSTTClient:
    """
    SarvamAI STT client for speech-to-text conversion.
    
    Wraps the functional STT API with a class-based interface for easier usage.
    """
    
    def __init__(self, api_key: str, language: str = "hi-IN", sample_rate: int = 16000, 
                 model: str = "saarika:v2.5", high_vad_sensitivity: bool = True,
                 vad_signals: bool = True, flush_signal: bool = True):
        """
        Initialize SarvamAI STT client.
        
        Args:
            api_key: SarvamAI API subscription key
            language: Language code (default: hi-IN)
            sample_rate: Audio sample rate in Hz (default: 16000)
            model: STT model to use (default: saarika:v2.5)
            high_vad_sensitivity: Enable high VAD sensitivity (default: True)
            vad_signals: Enable VAD signals (default: True)
            flush_signal: Enable flush signal (default: True)
        """
        config = {
            "language": language,
            "sample_rate": sample_rate,
            "model": model,
            "high_vad_sensitivity": high_vad_sensitivity,
            "vad_signals": vad_signals,
            "flush_signal": flush_signal,
        }
        self._client = create_stt_client(api_key, config)
    
    @property
    def is_connected(self) -> bool:
        """Check if STT client is connected."""
        return self._client.get("is_connected", False)
    
    async def connect(self):
        """Establish WebSocket connection to SarvamAI STT service."""
        await connect_stt(self._client)
    
    async def send_audio(self, pcm_audio: bytes):
        """Send PCM audio data to STT service."""
        await send_audio(self._client, pcm_audio)
    
    async def send_flush(self):
        """Send flush signal to STT service."""
        await send_flush(self._client)
    
    def set_transcript_callback(self, callback: Callable[[str, bool], None]):
        """
        Set callback function for transcript updates.
        
        Args:
            callback: Async function that receives (transcript: str, is_final: bool)
        """
        set_transcript_callback(self._client, callback)
    
    async def stop(self):
        """Stop STT client and close WebSocket connection."""
        await stop_stt(self._client)
