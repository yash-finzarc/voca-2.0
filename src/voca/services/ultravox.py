"""
Ultravox Client SDK implementation for Python.

This module implements the complete Ultravox SDK according to the official documentation,
including REST API client for creating calls and WebSocket client for joining calls.
"""
import asyncio
import json
import logging
import base64
import websockets
from websockets.legacy.client import connect
from typing import Callable, Dict, Any, Optional, List
from enum import Enum
import httpx
from src.voca.config import Config
from src.voca.system_prompt import get_prompt

logger = logging.getLogger(__name__)

# Ultravox API endpoints
ULTRAVOX_API_URL = "https://api.ultravox.ai/api/calls"
ULTRAVOX_WS_ENDPOINT = Config.ultravox_ws_endpoint or "wss://api.ultravox.ai/api/calls"


class UltravoxSessionStatus(Enum):
    """Session status enum matching Ultravox SDK."""
    DISCONNECTED = "disconnected"
    DISCONNECTING = "disconnecting"
    CONNECTING = "connecting"
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


class Medium(Enum):
    """Output medium enum."""
    TEXT = "text"
    VOICE = "voice"


class Role(Enum):
    """Speaker role enum."""
    USER = "user"
    AGENT = "agent"


class Transcript:
    """Transcript object matching Ultravox SDK format."""
    def __init__(self, text: str, is_final: bool, speaker: str, medium: str):
        self.text = text
        self.isFinal = is_final
        self.speaker = speaker
        self.medium = medium
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "isFinal": self.isFinal,
            "speaker": self.speaker,
            "medium": self.medium
        }


class UltravoxSession:
    """
    Ultravox Session class implementing the complete SDK.
    
    This class provides all SDK methods as documented:
    - joinCall, leaveCall
    - sendText, setOutputMedium
    - registerToolImplementation, registerToolImplementations
    - muteMic, unmuteMic, muteSpeaker, unmuteSpeaker
    - isMicMuted, isSpeakerMuted
    - Status and transcript event listeners
    """
    
    def __init__(self, api_key: str, organization_id: Optional[str] = None, 
                 experimental_messages: Optional[List[str]] = None):
        """
        Initialize Ultravox session.
        
        Args:
            api_key: Ultravox API key
            organization_id: Optional organization ID for fetching system prompt
            experimental_messages: Optional list of experimental message types (e.g., ["debug"])
        """
        self.api_key = api_key
        self.organization_id = organization_id
        self.experimental_messages = experimental_messages or []
        
        # Session state
        self._status = UltravoxSessionStatus.DISCONNECTED
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._join_url: Optional[str] = None
        self._client_version: Optional[str] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        
        # Mute state
        self._mic_muted = False
        self._speaker_muted = False
        
        # Output medium
        self._output_medium = Medium.VOICE
        
        # Tool implementations
        self._tool_implementations: Dict[str, Callable] = {}
        
        # Transcripts
        self._transcripts: List[Transcript] = []
        
        # Event listeners
        self._status_listeners: List[Callable] = []
        self._transcript_listeners: List[Callable] = []
        self._experimental_message_listeners: List[Callable] = []
        
        # Audio callbacks
        self._audio_output_callback: Optional[Callable[[bytes], None]] = None
        self._transcript_callback: Optional[Callable[[str, bool], None]] = None
    
    @property
    def status(self) -> str:
        """Get current session status."""
        return self._status.value
    
    @property
    def transcripts(self) -> List[Dict[str, Any]]:
        """Get transcripts array."""
        return [t.to_dict() for t in self._transcripts]
    
    def _set_status(self, new_status: UltravoxSessionStatus):
        """Set status and emit status event."""
        if self._status != new_status:
            old_status = self._status
            self._status = new_status
            logger.debug(f"Status changed: {old_status.value} -> {new_status.value}")
            # Emit status event
            for listener in self._status_listeners:
                try:
                    if asyncio.iscoroutinefunction(listener):
                        asyncio.create_task(listener(None))
                    else:
                        listener(None)
                except Exception as e:
                    logger.error(f"Error in status listener: {e}")
    
    def addEventListener(self, event_type: str, callback: Callable):
        """
        Add event listener.
        
        Args:
            event_type: Event type ('status', 'transcripts', 'experimental_message')
            callback: Callback function
        """
        if event_type == 'status':
            self._status_listeners.append(callback)
        elif event_type == 'transcripts':
            self._transcript_listeners.append(callback)
        elif event_type == 'experimental_message':
            self._experimental_message_listeners.append(callback)
        else:
            logger.warning(f"Unknown event type: {event_type}")
    
    def joinCall(self, join_url: str, client_version: Optional[str] = None):
        """
        Join a call via WebSocket.
        
        Args:
            join_url: The joinUrl returned from Create Call request
            client_version: Optional string for application version tracking
        """
        if self._status != UltravoxSessionStatus.DISCONNECTED:
            logger.warning(f"Cannot join call: already in status {self._status.value}")
            return
        
        self._join_url = join_url
        self._client_version = client_version
        self._set_status(UltravoxSessionStatus.CONNECTING)
        
        # Start connection task
        self._receive_task = asyncio.create_task(self._connect_and_receive())
    
    async def leaveCall(self):
        """Leave the current call."""
        if self._status == UltravoxSessionStatus.DISCONNECTED:
            return
        
        self._set_status(UltravoxSessionStatus.DISCONNECTING)
        self._stop_event.set()
        
        # Close WebSocket
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")
        
        # Cancel receive task
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        self._websocket = None
        self._set_status(UltravoxSessionStatus.DISCONNECTED)
        logger.info("Left call successfully")
    
    def sendText(self, text: str, defer_response: Optional[bool] = False):
        """
        Send a text message to the agent.
        
        Args:
            text: The message to send to the agent
            defer_response: Set to True to skip LLM generation (agent won't reply)
        """
        if not self._websocket or self._status == UltravoxSessionStatus.DISCONNECTED:
            logger.warning("Cannot send text: not connected")
            return
        
        message = {
            "type": "text",
            "text": text,
            "deferResponse": defer_response
        }
        
        asyncio.create_task(self._send_message(message))
    
    def setOutputMedium(self, medium: str):
        """
        Set the agent's output medium for future utterances.
        
        Args:
            medium: How replies are communicated. Must be either 'text' or 'voice'
        """
        if medium not in ["text", "voice"]:
            raise ValueError(f"Invalid medium: {medium}. Must be 'text' or 'voice'")
        
        self._output_medium = Medium.TEXT if medium == "text" else Medium.VOICE
        
        if not self._websocket or self._status == UltravoxSessionStatus.DISCONNECTED:
            return
        
        message = {
            "type": "set_output_medium",
            "medium": medium
        }
        
        asyncio.create_task(self._send_message(message))
    
    def registerToolImplementation(self, name: str, implementation: Callable):
        """
        Register a client tool implementation.
        
        Args:
            name: The name of the tool (must match selectedTools during Create Call)
            implementation: Function that implements the tool's logic
        """
        self._tool_implementations[name] = implementation
        logger.debug(f"Registered tool implementation: {name}")
    
    def registerToolImplementations(self, implementation_map: Dict[str, Callable]):
        """
        Convenience batch wrapper for registerToolImplementation.
        
        Args:
            implementation_map: Object where keys are tool names and values are implementations
        """
        for name, implementation in implementation_map.items():
            self.registerToolImplementation(name, implementation)
    
    def isMicMuted(self) -> bool:
        """Returns a boolean indicating if the end user's microphone is muted."""
        return self._mic_muted
    
    def isSpeakerMuted(self) -> bool:
        """Returns a boolean indicating if the speaker (the agent's voice output) is muted."""
        return self._speaker_muted
    
    def muteMic(self):
        """Mutes the end user's microphone."""
        self._mic_muted = True
        logger.debug("Microphone muted")
    
    def unmuteMic(self):
        """Unmutes the end user's microphone."""
        self._mic_muted = False
        logger.debug("Microphone unmuted")
    
    def muteSpeaker(self):
        """Mutes the end user's speaker (the agent's voice output)."""
        self._speaker_muted = True
        logger.debug("Speaker muted")
    
    def unmuteSpeaker(self):
        """Unmutes the end user's speaker (the agent's voice output)."""
        self._speaker_muted = False
        logger.debug("Speaker unmuted")
    
    async def _connect_and_receive(self):
        """Connect to WebSocket and receive messages."""
        try:
            # Connect to WebSocket
            logger.info(f"Connecting to Ultravox WebSocket: {self._join_url}")
            self._websocket = await connect(self._join_url)
            logger.info("Connected to Ultravox WebSocket")
            
            self._set_status(UltravoxSessionStatus.IDLE)
            
            # Receive messages
            async for message in self._websocket:
                if self._stop_event.is_set():
                    break
                
                try:
                    if isinstance(message, str):
                        data = json.loads(message)
                    else:
                        data = json.loads(message.decode('utf-8'))
                    
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse message: {e}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}", exc_info=True)
        
        except asyncio.CancelledError:
            logger.info("WebSocket receive task cancelled")
        except Exception as e:
            logger.error(f"Error in WebSocket connection: {e}", exc_info=True)
            self._set_status(UltravoxSessionStatus.DISCONNECTED)
        finally:
            if self._websocket:
                try:
                    await self._websocket.close()
                except Exception:
                    pass
            self._websocket = None
    
    async def _handle_message(self, data: Dict[str, Any]):
        """Handle incoming WebSocket message."""
        msg_type = data.get("type")
        
        if msg_type == "status":
            status_str = data.get("status", "").lower()
            status_map = {
                "disconnected": UltravoxSessionStatus.DISCONNECTED,
                "disconnecting": UltravoxSessionStatus.DISCONNECTING,
                "connecting": UltravoxSessionStatus.CONNECTING,
                "idle": UltravoxSessionStatus.IDLE,
                "listening": UltravoxSessionStatus.LISTENING,
                "thinking": UltravoxSessionStatus.THINKING,
                "speaking": UltravoxSessionStatus.SPEAKING,
            }
            if status_str in status_map:
                self._set_status(status_map[status_str])
        
        elif msg_type == "transcript":
            text = data.get("text", "")
            is_final = data.get("isFinal", False)
            speaker = data.get("speaker", "user")
            medium = data.get("medium", "voice")
            
            transcript = Transcript(text, is_final, speaker, medium)
            self._transcripts.append(transcript)
            
            # Emit transcript event
            for listener in self._transcript_listeners:
                try:
                    if asyncio.iscoroutinefunction(listener):
                        asyncio.create_task(listener(None))
                    else:
                        listener(None)
                except Exception as e:
                    logger.error(f"Error in transcript listener: {e}")
            
            # Call transcript callback if set
            if self._transcript_callback:
                try:
                    if asyncio.iscoroutinefunction(self._transcript_callback):
                        await self._transcript_callback(text, is_final)
                    else:
                        self._transcript_callback(text, is_final)
                except Exception as e:
                    logger.error(f"Error in transcript callback: {e}")
        
        elif msg_type == "audio":
            # Handle audio data
            audio_data = data.get("audio")
            if audio_data:
                try:
                    # Decode base64 audio
                    audio_bytes = base64.b64decode(audio_data)
                    
                    # Call audio output callback if set
                    if self._audio_output_callback and not self._speaker_muted:
                        try:
                            if asyncio.iscoroutinefunction(self._audio_output_callback):
                                await self._audio_output_callback(audio_bytes)
                            else:
                                self._audio_output_callback(audio_bytes)
                        except Exception as e:
                            logger.error(f"Error in audio output callback: {e}")
                except Exception as e:
                    logger.error(f"Error decoding audio: {e}")
        
        elif msg_type == "tool_call":
            # Handle tool call
            tool_name = data.get("tool_name")
            parameters = data.get("parameters", {})
            invocation_id = data.get("invocation_id")
            
            if tool_name in self._tool_implementations:
                try:
                    implementation = self._tool_implementations[tool_name]
                    result = implementation(parameters)
                    
                    # Handle async results
                    if asyncio.iscoroutine(result):
                        result = await result
                    
                    # Handle result format (string or object with result and responseType)
                    if isinstance(result, str):
                        result_text = result
                        response_type = None
                    elif isinstance(result, dict):
                        result_text = result.get("result", "")
                        response_type = result.get("responseType")
                    else:
                        result_text = str(result)
                        response_type = None
                    
                    # Send tool result back
                    await self._send_message({
                        "type": "tool_result",
                        "invocation_id": invocation_id,
                        "result": result_text,
                        "responseType": response_type
                    })
                except Exception as e:
                    logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
                    await self._send_message({
                        "type": "tool_result",
                        "invocation_id": invocation_id,
                        "result": f"Error: {str(e)}"
                    })
            else:
                logger.warning(f"Tool {tool_name} not registered")
        
        elif msg_type == "experimental_message":
            # Handle debug/experimental messages
            if "debug" in self.experimental_messages:
                for listener in self._experimental_message_listeners:
                    try:
                        if asyncio.iscoroutinefunction(listener):
                            asyncio.create_task(listener(data))
                        else:
                            listener(data)
                    except Exception as e:
                        logger.error(f"Error in experimental message listener: {e}")
        
        else:
            logger.debug(f"Unhandled message type: {msg_type}")
    
    async def _send_message(self, message: Dict[str, Any]):
        """Send message to WebSocket."""
        if not self._websocket:
            logger.warning("Cannot send message: WebSocket not connected")
            return
        
        try:
            await self._websocket.send(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending message: {e}")
    
    async def send_audio(self, audio_data: bytes):
        """
        Send audio data to Ultravox.
        
        Args:
            audio_data: PCM audio data (16-bit, 8kHz)
        """
        if not self._websocket or self._mic_muted:
            return
        
        # Encode audio as base64
        audio_b64 = base64.b64encode(audio_data).decode('ascii')
        
        await self._send_message({
            "type": "audio",
            "audio": audio_b64
        })


async def create_ultravox_call(
    api_key: str,
    organization_id: Optional[str] = None,
    first_speaker_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create an Ultravox call via HTTP POST and return the call payload (expects joinUrl).

    Args:
        api_key: Ultravox API key
        organization_id: Optional organization ID for fetching system prompt
        first_speaker_settings: Optional dict for firstSpeakerSettings (e.g., {"user": {}} for outgoing calls)
            If provided, this will be used instead of default "FIRST_SPEAKER_AGENT"

    Returns:
        Dict containing call information including joinUrl
    """
    if not api_key or not api_key.strip():
        raise ValueError("Ultravox API key is empty or not set")

    # Fetch system prompt
    try:
        system_prompt = get_prompt(organization_id=organization_id)
        logger.info("System prompt fetched successfully")
    except Exception as e:
        logger.warning(f"Failed to fetch system prompt: {e}, using default")
        system_prompt = "You are a helpful assistant."

    # Build config dictionary with model values directly in the dict
    ULTRAVOX_CALL_CONFIG = {
        "systemPrompt": system_prompt,
        "model": "fixie-ai/ultravox",
        "voice": "Mark",
        "temperature": 0.3,
        "firstSpeaker": "FIRST_SPEAKER_AGENT" if first_speaker_settings is None else None,
        "firstSpeakerSettings": first_speaker_settings if first_speaker_settings is not None else None,
        "medium": {"twilio": {}}
    }
    
    # Remove None values
    ULTRAVOX_CALL_CONFIG = {k: v for k, v in ULTRAVOX_CALL_CONFIG.items() if v is not None}

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key.strip(),
    }

    logger.info(f"Creating Ultravox call via HTTP POST to {ULTRAVOX_API_URL}")
    logger.debug(f"Ultravox call config: model={ULTRAVOX_CALL_CONFIG.get('model')} voice={ULTRAVOX_CALL_CONFIG.get('voice')} temperature={ULTRAVOX_CALL_CONFIG.get('temperature')}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                ULTRAVOX_API_URL,
                json=ULTRAVOX_CALL_CONFIG,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
            logger.info("Ultravox call created successfully")
            return result
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error creating Ultravox call: {e.response.status_code} - {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"Error creating Ultravox call: {e}", exc_info=True)
        raise


# Backwards-compatible helper functions

def create_ultravox_client(api_key: str, organization_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Initialize Ultravox client (backwards compatibility).
    
    Returns a dict that can be used with helper functions.
    For new code, use UltravoxSession directly.
    """
    session = UltravoxSession(api_key=api_key, organization_id=organization_id)
    return {
        "_session": session,
        "api_key": api_key,
        "organization_id": organization_id,
        "is_connected": False
    }


async def connect_ultravox(client: Dict[str, Any]):
    """Connect to Ultravox (backwards compatibility)."""
    session = client.get("_session")
    if not session:
        raise ValueError("Invalid client dict - missing _session")
    
    # Create call first to get joinUrl
    call_info = await create_ultravox_call(
        api_key=client["api_key"],
        organization_id=client.get("organization_id")
    )
    
    join_url = call_info.get("joinUrl")
    if not join_url:
        raise RuntimeError("Ultravox call creation succeeded but joinUrl was missing")
    
    session.joinCall(join_url)
    client["is_connected"] = True


async def send_audio(client: Dict[str, Any], audio_data: bytes):
    """Send audio to Ultravox (backwards compatibility)."""
    session = client.get("_session")
    if not session:
        raise ValueError("Invalid client dict - missing _session")
    
    await session.send_audio(audio_data)


def set_audio_output_callback(client: Dict[str, Any], callback: Callable[[bytes], None]):
    """Set audio output callback (backwards compatibility)."""
    session = client.get("_session")
    if not session:
        raise ValueError("Invalid client dict - missing _session")
    
    session._audio_output_callback = callback


def set_transcript_callback(client: Dict[str, Any], callback: Callable[[str, bool], None]):
    """Set transcript callback (backwards compatibility)."""
    session = client.get("_session")
    if not session:
        raise ValueError("Invalid client dict - missing _session")
    
    session._transcript_callback = callback


async def stop_ultravox(client: Dict[str, Any]):
    """Stop Ultravox connection (backwards compatibility)."""
    session = client.get("_session")
    if not session:
        return
    
    await session.leaveCall()
    client["is_connected"] = False


# Export UltravoxClient class alias for backwards compatibility
UltravoxClient = UltravoxSession

