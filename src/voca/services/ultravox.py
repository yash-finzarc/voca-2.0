import asyncio
import json
import logging
import base64
import websockets
from websockets.legacy.client import connect
from typing import Callable, Dict, Any, Optional
from urllib.parse import urlencode
import re

import os
import httpx
from twilio.rest import Client
from src.voca.config import Config
from src.voca.system_prompt import get_prompt
from src.voca.Twilio.twilio_config import get_twilio_config

logger = logging.getLogger(__name__)

# Ultravox configuration (hardcoded as per plan)
ULTRAVOX_MODEL = "ultravox-v0.7"
ULTRAVOX_VOICE = "Riya-Hindi-Urdu"
ULTRAVOX_VOICE_ID = "c2c5cce4-72ec-4d8b-8cdb-f8a0f6610bd1"
ULTRAVOX_TEMPERATURE = 0.3
ULTRAVOX_LANGUAGE = "hi-IN"
ULTRAVOX_MEDIUM = "twilio"

# WebSocket endpoint for Ultravox Realtime API
# You can override this by setting ULTRAVOX_WS_ENDPOINT environment variable
ULTRAVOX_WS_ENDPOINT = os.getenv("ULTRAVOX_WS_ENDPOINT", "wss://api.ultravox.ai/api/calls")

# HTTP endpoint for creating calls (used to obtain joinUrl for Twilio <Stream>)
ULTRAVOX_API_URL = "https://api.ultravox.ai/api/calls"

# Default backend WebSocket URL for Twilio Media Streams
DEFAULT_BACKEND_WEBSOCKET_URL = "wss://voca-2.duckdns.org/twilio"


def validate_phone_number(phone_number: str) -> bool:
    """
    Validate phone number format (E.164).
    
    Args:
        phone_number: Phone number to validate
        
    Returns:
        True if valid E.164 format, False otherwise
    """
    pattern = r'^\+[1-9]\d{1,14}$'
    return bool(re.match(pattern, phone_number))


def validate_twilio_account_sid(account_sid: str) -> bool:
    """
    Validate Twilio Account SID format.
    
    Args:
        account_sid: Account SID to validate
        
    Returns:
        True if valid format (starts with "AC", 34 chars), False otherwise
    """
    return bool(account_sid and account_sid.startswith("AC") and len(account_sid) == 34)


def validate_twilio_auth_token(auth_token: str) -> bool:
    """
    Validate Twilio Auth Token format.
    
    Args:
        auth_token: Auth token to validate
        
    Returns:
        True if valid format (32 chars), False otherwise
    """
    return bool(auth_token and len(auth_token) == 32)


def validate_ultravox_api_key(api_key: str) -> bool:
    """
    Validate Ultravox API key format (basic check).
    
    Args:
        api_key: API key to validate
        
    Returns:
        True if not empty, False otherwise
    """
    return bool(api_key and api_key.strip() and len(api_key.strip()) > 0)


def create_ultravox_client(api_key: str, organization_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Initialize Ultravox client with configuration.
    
    Args:
        api_key: Ultravox API key
        organization_id: Optional organization ID for fetching system prompt
    
    Returns:
        Client dictionary with configuration and state
    """
    # Fetch system prompt from Supabase
    try:
        system_prompt = get_prompt(organization_id=organization_id)
        logger.info("System prompt fetched from Supabase successfully")
    except Exception as e:
        logger.warning(f"Failed to fetch system prompt from Supabase: {e}, using default")
        system_prompt = "You are a helpful assistant."
    
    return {
        "api_key": api_key,
        "organization_id": organization_id,
        "system_prompt": system_prompt,
        "config": {
            "model": ULTRAVOX_MODEL,
            "voice": ULTRAVOX_VOICE,
            "voice_id": ULTRAVOX_VOICE_ID,
            "temperature": ULTRAVOX_TEMPERATURE,
            "language": ULTRAVOX_LANGUAGE,
            "medium": ULTRAVOX_MEDIUM,
            "first_speaker": {
                "user": {}
            }
        },
        "websocket": None,
        "is_connected": False,
        "audio_input_callback": None,
        "audio_output_callback": None,
        "transcript_callback": None,
        "_receive_task": None,
        "_stop_event": asyncio.Event()
    }


async def create_ultravox_call(
    api_key: str,
    organization_id: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    first_speaker_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create an Ultravox call via HTTP POST and return the call payload (expects joinUrl).

    This matches the JavaScript pattern:
    - POST https://api.ultravox.ai/api/calls
    - Header: X-API-Key
    - Body: { systemPrompt, model, voice, temperature, firstSpeaker/firstSpeakerSettings, medium: { twilio: {} } }

    Args:
        api_key: Ultravox API key
        organization_id: Optional organization ID for fetching system prompt
        config: Optional full config dict (if provided, used as-is)
        first_speaker_settings: Optional dict for firstSpeakerSettings (e.g., {"user": {}} for outgoing calls)
            If provided, this will be used instead of default "FIRST_SPEAKER_AGENT"
    """
    if not api_key or not api_key.strip():
        raise ValueError("Ultravox API key is empty or not set")

    api_key_clean = api_key.strip()

    if config is None:
        # Fetch system prompt from Supabase
        try:
            system_prompt = get_prompt(organization_id=organization_id)
            logger.info("System prompt fetched from Supabase successfully")
        except Exception as e:
            logger.warning(f"Failed to fetch system prompt from Supabase: {e}, using default")
            system_prompt = "You are a helpful assistant."

        config = {
            "systemPrompt": system_prompt,
            "model": ULTRAVOX_MODEL,
            "voice": ULTRAVOX_VOICE,
            "temperature": ULTRAVOX_TEMPERATURE,
            "medium": {"twilio": {}},
        }
        
        # Set firstSpeaker or firstSpeakerSettings based on parameter
        if first_speaker_settings is not None:
            # Use firstSpeakerSettings for outgoing calls (user speaks first)
            config["firstSpeakerSettings"] = first_speaker_settings
        else:
            # Default: agent speaks first
            config["firstSpeaker"] = "FIRST_SPEAKER_AGENT"

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key_clean,
    }

    logger.info(f"Creating Ultravox call via HTTP POST → {ULTRAVOX_API_URL}")
    logger.debug(
        "Ultravox call config: model=%s voice=%s temperature=%s",
        config.get("model"),
        config.get("voice"),
        config.get("temperature"),
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(ULTRAVOX_API_URL, json=config, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        if not isinstance(data, dict):
            raise RuntimeError("Ultravox call creation returned non-object JSON")

        if not data.get("joinUrl"):
            # Don’t hard fail on schema drift, but surface it clearly.
            raise RuntimeError(f"Ultravox call creation response missing joinUrl: keys={list(data.keys())}")

        return data

    except httpx.HTTPStatusError as e:
        logger.error(f"Ultravox call creation failed with HTTP {e.response.status_code}")
        logger.error(f"Response: {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"Error creating Ultravox call: {e}", exc_info=True)
        raise


async def make_outbound_ultravox_call(
    destination_phone_number: str,
    organization_id: Optional[str] = None,
    twilio_account_sid: Optional[str] = None,
    twilio_auth_token: Optional[str] = None,
    twilio_phone_number: Optional[str] = None,
    ultravox_api_key: Optional[str] = None,
    backend_websocket_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Make an outbound Twilio call using Ultravox via Twilio Media Streams.
    
    This function:
    1. Validates all configuration (Twilio and Ultravox)
    2. Creates an Ultravox call to initialize it with system prompt
    3. Makes a Twilio outbound call with TwiML that streams to backend WebSocket
    
    Args:
        destination_phone_number: Phone number to call (E.164 format, e.g., +1234567890)
        organization_id: Optional organization ID for fetching system prompt
        twilio_account_sid: Optional Twilio Account SID (uses config if not provided)
        twilio_auth_token: Optional Twilio Auth Token (uses config if not provided)
        twilio_phone_number: Optional Twilio phone number (uses config if not provided)
        ultravox_api_key: Optional Ultravox API key (uses Config if not provided)
        backend_websocket_url: Optional backend WebSocket URL (defaults to wss://voca-2.duckdns.org/twilio)
    
    Returns:
        Dictionary with:
            - call_sid: Twilio Call SID
            - status: Call status
            - join_url: Ultravox joinUrl (for reference)
            - backend_websocket_url: Backend WebSocket URL used
            - destination: Destination phone number
            - from_number: Twilio phone number used
    
    Raises:
        ValueError: If configuration is invalid or missing
        RuntimeError: If Ultravox call creation fails
        Exception: If Twilio call creation fails
    """
    # ============================================================
    # Step 1: Validate Configuration
    # ============================================================
    errors = []
    
    # Get Twilio config
    twilio_config = get_twilio_config()
    account_sid = twilio_account_sid or twilio_config.account_sid
    auth_token = twilio_auth_token or twilio_config.auth_token
    from_number = twilio_phone_number or twilio_config.phone_number
    
    # Validate Twilio Account SID
    if not account_sid or account_sid.strip() == "" or account_sid.startswith("your_"):
        errors.append("TWILIO_ACCOUNT_SID is not set or contains placeholder text")
    elif not validate_twilio_account_sid(account_sid):
        errors.append("TWILIO_ACCOUNT_SID format appears invalid (should start with 'AC' and be 34 characters)")
    
    # Validate Twilio Auth Token
    if not auth_token or auth_token.strip() == "" or auth_token.startswith("your_"):
        errors.append("TWILIO_AUTH_TOKEN is not set or contains placeholder text")
    elif not validate_twilio_auth_token(auth_token):
        errors.append("TWILIO_AUTH_TOKEN format appears invalid (should be 32 characters)")
    
    # Validate Twilio Phone Number
    if not from_number or from_number.strip() == "" or from_number.startswith("your_"):
        errors.append("TWILIO_PHONE_NUMBER is not set or contains placeholder text")
    elif not validate_phone_number(from_number):
        errors.append("TWILIO_PHONE_NUMBER format appears invalid (should be E.164 format, e.g., +1234567890)")
    
    # Validate Destination Phone Number
    if not destination_phone_number or destination_phone_number.strip() == "":
        errors.append("DESTINATION_PHONE_NUMBER is required")
    elif not validate_phone_number(destination_phone_number):
        errors.append("DESTINATION_PHONE_NUMBER format appears invalid (should be E.164 format, e.g., +1234567890)")
    
    # Validate Ultravox API Key
    ultravox_key = ultravox_api_key or Config.ultravox_api_key
    if not ultravox_key or ultravox_key.strip() == "" or ultravox_key.startswith("your_"):
        errors.append("ULTRAVOX_API_KEY is not set or contains placeholder text")
    elif not validate_ultravox_api_key(ultravox_key):
        errors.append("ULTRAVOX_API_KEY appears invalid")
    
    # Get backend WebSocket URL
    backend_url = backend_websocket_url or DEFAULT_BACKEND_WEBSOCKET_URL
    if not backend_url or not backend_url.startswith(("ws://", "wss://")):
        errors.append(f"Backend WebSocket URL must start with ws:// or wss:// (got: {backend_url})")
    
    # Get organization ID
    org_id = organization_id or Config.default_organization_id or None
    
    # Report all errors at once
    if errors:
        error_msg = "Configuration Error(s):\n" + "\n".join(f"   ❌ {e}" for e in errors)
        error_msg += "\n\n💡 Please update the configuration:"
        error_msg += "\n   • TWILIO_ACCOUNT_SID should start with 'AC' and be 34 characters"
        error_msg += "\n   • TWILIO_AUTH_TOKEN should be 32 characters"
        error_msg += "\n   • Phone numbers should be in E.164 format (e.g., +1234567890)"
        error_msg += "\n   • ULTRAVOX_API_KEY should be set in .env file"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info("✅ Configuration validation passed!")
    
    # ============================================================
    # Step 2: Create Ultravox Call
    # ============================================================
    logger.info("📞 Creating Ultravox call...")
    try:
        ultravox_response = await create_ultravox_call(
            api_key=ultravox_key,
            organization_id=org_id,
            first_speaker_settings={"user": {}}  # For outgoing calls, user speaks first
        )
        
        join_url = ultravox_response.get("joinUrl")
        if not join_url:
            raise RuntimeError("No joinUrl received from Ultravox API")
        
        logger.info(f"✅ Got Ultravox joinUrl: {join_url}")
        
    except Exception as e:
        logger.error(f"💥 Error creating Ultravox call: {e}")
        if "Authentication" in str(e) or "401" in str(e) or "403" in str(e):
            raise RuntimeError(f"Ultravox API authentication failed - check your API key: {e}")
        raise RuntimeError(f"Failed to create Ultravox call: {e}")
    
    # ============================================================
    # Step 3: Make Twilio Outbound Call
    # ============================================================
    logger.info("📱 Initiating Twilio call...")
    try:
        # Create Twilio client
        twilio_client = Client(account_sid, auth_token)
        
        # Generate inline TwiML that streams to backend WebSocket
        twiml = f'<Response><Connect><Stream url="{backend_url}" name="ultravox"/></Connect></Response>'
        
        logger.info(f"📋 TwiML: {twiml}")
        logger.info(f"📞 Calling {destination_phone_number} from {from_number}")
        
        # Make the call
        call = twilio_client.calls.create(
            to=destination_phone_number,
            from_=from_number,
            twiml=twiml
        )
        
        logger.info("🎉 Twilio outbound phone call initiated successfully!")
        logger.info(f"📋 Twilio Call SID: {call.sid}")
        logger.info(f"📊 Call Status: {call.status}")
        
        return {
            "call_sid": call.sid,
            "status": call.status,
            "join_url": join_url,
            "backend_websocket_url": backend_url,
            "destination": destination_phone_number,
            "from_number": from_number,
            "ultravox_response": ultravox_response,
        }
        
    except Exception as e:
        logger.error(f"💥 Error making Twilio call: {e}")
        error_msg = str(e)
        
        if "Authentication" in error_msg or "401" in error_msg or "403" in error_msg:
            raise RuntimeError(f"Twilio authentication failed - check your credentials: {e}")
        elif "phone number" in error_msg.lower() or "invalid" in error_msg.lower():
            raise RuntimeError(f"Phone number issue - verify your phone numbers are correct: {e}")
        else:
            raise RuntimeError(f"Failed to make Twilio call: {e}")


async def connect_ultravox(client: Dict[str, Any]):
    """
    Establish WebSocket connection to Ultravox Realtime API.
    
    Args:
        client: Ultravox client dictionary
    """
    config = client["config"]
    api_key = client["api_key"]
    
    # Validate API key
    if not api_key or not api_key.strip():
        raise ValueError("Ultravox API key is empty or not set")
    
    api_key_clean = api_key.strip()
    
    # Prepare authentication headers
    headers = {
        "Authorization": f"Bearer {api_key_clean}"
    }
    
    # Build WebSocket URI - check environment variable first, then use default
    uri = os.getenv("ULTRAVOX_WS_ENDPOINT") or ULTRAVOX_WS_ENDPOINT
    
    # Convert https:// to wss:// and http:// to ws:// if needed (WebSocket requires ws/wss protocol)
    if uri.startswith("https://"):
        uri = uri.replace("https://", "wss://", 1)
        logger.debug(f"Converted https:// to wss://: {uri}")
    elif uri.startswith("http://"):
        uri = uri.replace("http://", "ws://", 1)
        logger.debug(f"Converted http:// to ws://: {uri}")
    
    logger.info(f"Connecting to Ultravox Realtime → {uri}")
    logger.debug(f"API key present: {bool(api_key)}, length: {len(api_key) if api_key else 0}")
    logger.debug(f"Configuration: model={config['model']}, voice={config['voice']}, temperature={config['temperature']}")
    
    try:
        websocket = await connect(uri, extra_headers=headers)
        client["websocket"] = websocket
        client["is_connected"] = True
        client["_stop_event"].clear()
        
        # Send initial configuration message
        initial_config = {
            "model": config["model"],
            "voice": config["voice"],
            "voice_id": config["voice_id"],
            "temperature": config["temperature"],
            "language": config["language"],
            "medium": config["medium"],
            "first_speaker": config["first_speaker"],
            "system_prompt": client["system_prompt"]
        }
        
        await websocket.send(json.dumps(initial_config))
        logger.info("Initial configuration sent to Ultravox")
        
        # Start receiving responses
        client["_receive_task"] = asyncio.create_task(_receive_responses(client))
        
    except (websockets.exceptions.InvalidStatusCode, websockets.InvalidStatusCode) as e:
        logger.error(f"Ultravox connection failed with HTTP {e.status_code}")
        logger.error(f"API key length: {len(api_key) if api_key else 0}")
        logger.error(f"URI used: {uri}")
        if hasattr(e, 'headers'):
            logger.error(f"Response headers: {e.headers}")
        
        if e.status_code == 404:
            logger.error("=" * 60)
            logger.error("ERROR: WebSocket endpoint not found (404)")
            logger.error("The endpoint URL may be incorrect or account-specific.")
            logger.error("")
            logger.error("To find your correct endpoint:")
            logger.error("1. Log in to your Ultravox account dashboard at https://ultravox.ai")
            logger.error("2. Navigate to API/Settings section")
            logger.error("3. Look for WebSocket/Realtime endpoint URL")
            logger.error("4. Check documentation at https://docs.ultravox.ai")
            logger.error("")
            logger.error(f"Current endpoint: {uri}")
            logger.error("")
            logger.error("You can set the correct endpoint by:")
            logger.error("- Adding to .env: ULTRAVOX_WS_ENDPOINT=wss://correct-endpoint-here")
            logger.error("- Or using --endpoint flag in the test script")
            logger.error("=" * 60)
        raise
    except Exception as e:
        logger.error(f"Error connecting to Ultravox: {e}", exc_info=True)
        client["is_connected"] = False
        raise


async def _receive_responses(client: Dict[str, Any]):
    """
    Handle responses from Ultravox WebSocket.
    
    Args:
        client: Ultravox client dictionary
    """
    ws = client["websocket"]
    
    try:
        async for message in ws:
            if client["_stop_event"].is_set():
                break
            
            try:
                # Try to parse as JSON first
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "audio":
                    # Received audio output from Ultravox
                    audio_data = data.get("audio")
                    if audio_data:
                        # Decode base64 audio if needed
                        if isinstance(audio_data, str):
                            audio_bytes = base64.b64decode(audio_data)
                        else:
                            audio_bytes = audio_data
                        
                        # Call audio output callback
                        cb = client.get("audio_output_callback")
                        if cb:
                            await cb(audio_bytes)
                
                elif msg_type == "transcript":
                    # Received transcription
                    transcript = data.get("text", "")
                    is_final = data.get("is_final", False)
                    
                    if transcript.strip():
                        cb = client.get("transcript_callback")
                        if cb:
                            await cb(transcript, is_final)
                
                elif msg_type == "error":
                    logger.error(f"Ultravox Error: {data}")
                
                elif msg_type == "event":
                    logger.debug(f"Ultravox Event: {data}")
                
                else:
                    logger.debug(f"Ultravox Message: {data}")
                    
            except json.JSONDecodeError:
                # If not JSON, treat as raw audio data
                cb = client.get("audio_output_callback")
                if cb:
                    await cb(message)
            
    except websockets.exceptions.ConnectionClosed as e:
        logger.warning(f"Ultravox WebSocket connection closed: {e.code} - {e.reason}")
        client["is_connected"] = False
    except Exception as e:
        logger.error(f"Error in Ultravox receive loop: {e}", exc_info=True)
        client["is_connected"] = False


async def send_audio(client: Dict[str, Any], audio_data: bytes):
    """
    Send audio chunks to Ultravox.
    
    Args:
        client: Ultravox client dictionary
        audio_data: Audio data bytes (PCM or other format)
    """
    if not client.get("is_connected") or not client.get("websocket"):
        logger.warning("Ultravox not connected, cannot send audio")
        return
    
    if not audio_data:
        logger.warning("Empty audio data, skipping")
        return
    
    try:
        # Encode audio as base64 for JSON transmission
        audio_base64 = base64.b64encode(audio_data).decode("ascii")
        
        # Send audio message
        payload = {
            "type": "audio",
            "audio": audio_base64,
            "encoding": "pcm_s16le",  # Assuming PCM 16-bit little-endian
            "sample_rate": 16000  # Default sample rate
        }
        
        await client["websocket"].send(json.dumps(payload))
        
    except websockets.exceptions.ConnectionClosed as e:
        logger.warning(f"Ultravox connection closed while sending audio: {e.code} - {e.reason}")
        client["is_connected"] = False
    except Exception as e:
        logger.error(f"Error sending audio to Ultravox: {e}", exc_info=True)
        client["is_connected"] = False


def set_audio_input_callback(client: Dict[str, Any], callback: Callable[[bytes], None]):
    """
    Set callback for audio input (for receiving audio from Twilio).
    
    Args:
        client: Ultravox client dictionary
        callback: Async function that receives audio bytes and forwards to Ultravox
    """
    client["audio_input_callback"] = callback


def set_audio_output_callback(client: Dict[str, Any], callback: Callable[[bytes], None]):
    """
    Set callback for audio output (for sending audio to Twilio).
    
    Args:
        client: Ultravox client dictionary
        callback: Async function that receives audio bytes from Ultravox and forwards to Twilio
    """
    client["audio_output_callback"] = callback


def set_transcript_callback(client: Dict[str, Any], callback: Callable[[str, bool], None]):
    """
    Set callback for transcript updates.
    
    Args:
        client: Ultravox client dictionary
        callback: Async function that receives (transcript: str, is_final: bool)
    """
    client["transcript_callback"] = callback


async def stop_ultravox(client: Dict[str, Any]):
    """
    Stop Ultravox client and close WebSocket connection.
    
    Args:
        client: Ultravox client dictionary
    """
    client["_stop_event"].set()
    
    if client["_receive_task"]:
        client["_receive_task"].cancel()
        try:
            await client["_receive_task"]
        except asyncio.CancelledError:
            pass
    
    if client["websocket"]:
        await client["websocket"].close()
    
    client["is_connected"] = False
    logger.info("Ultravox client stopped")


class UltravoxClient:
    """
    Ultravox Realtime speech-to-speech client for realtime audio processing.
    
    Provides a class-based interface for Ultravox WebSocket API.
    """
    
    def __init__(self, api_key: Optional[str] = None, organization_id: Optional[str] = None):
        """
        Initialize Ultravox client.
        
        Args:
            api_key: Ultravox API key (defaults to Config.ultravox_api_key)
            organization_id: Optional organization ID for fetching system prompt
        """
        if api_key is None:
            api_key = Config.ultravox_api_key
        
        if not api_key:
            raise ValueError("Ultravox API key is required. Set ULTRAVOX_API_KEY in .env or pass api_key parameter.")
        
        self._client = create_ultravox_client(api_key, organization_id)
    
    @property
    def is_connected(self) -> bool:
        """Check if Ultravox client is connected."""
        return self._client.get("is_connected", False)
    
    async def connect(self):
        """Establish WebSocket connection to Ultravox Realtime service."""
        await connect_ultravox(self._client)
    
    async def send_audio(self, audio_data: bytes):
        """Send PCM audio data to Ultravox service."""
        await send_audio(self._client, audio_data)
    
    def set_audio_input_callback(self, callback: Callable[[bytes], None]):
        """
        Set callback for audio input (receives audio from Twilio, forwards to Ultravox).
        
        Args:
            callback: Async function that receives audio bytes
        """
        set_audio_input_callback(self._client, callback)
    
    def set_audio_output_callback(self, callback: Callable[[bytes], None]):
        """
        Set callback for audio output (receives audio from Ultravox, forwards to Twilio).
        
        Args:
            callback: Async function that receives audio bytes
        """
        set_audio_output_callback(self._client, callback)
    
    def set_transcript_callback(self, callback: Callable[[str, bool], None]):
        """
        Set callback function for transcript updates.
        
        Args:
            callback: Async function that receives (transcript: str, is_final: bool)
        """
        set_transcript_callback(self._client, callback)
    
    async def stop(self):
        """Stop Ultravox client and close WebSocket connection."""
        await stop_ultravox(self._client)
