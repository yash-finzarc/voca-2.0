# VOCA Architecture: Twilio Integration Components Explained

This document explains the purpose and functionality of each Twilio-related component in the VOCA codebase.

---

## 📋 Table of Contents

1. [twilio_config.py](#1-twilio_configpy---configuration-management)
2. [twilio_voice.py](#2-twilio_voicepy---twiml-based-voice-calls)
3. [webrtc.py](#3-webrtcpy---webrtc-client-stub)
4. [websocket_handler.py](#4-websocket_handlerpy---websocket-and-media-stream-handlers)
5. [How They Work Together](#how-they-work-together)
6. [Current Usage Status](#current-usage-status)

---

## 1. `twilio_config.py` - Configuration Management

### **Purpose**
Centralized configuration management for Twilio credentials and settings.

### **What It Does**
- **Loads environment variables** from `.env` file
- **Stores Twilio credentials**:
  - `account_sid` - Twilio account identifier
  - `auth_token` - Twilio authentication token
  - `phone_number` - Your Twilio phone number
  - `webhook_url` - URL where Twilio sends webhooks
  - `api_key_sid` / `api_key_secret` - Optional API keys for advanced features
- **Validates configuration** - Checks that required fields are present
- **Provides singleton access** - Global `get_twilio_config()` function

### **Key Classes/Functions**
```python
TwilioConfig.from_env()  # Load config from environment
TwilioConfig.validate()   # Check if config is valid
get_twilio_config()       # Get global config instance
```

### **Usage**
Used by `twilio_voice.py` to initialize Twilio client and get credentials.

---

## 2. `twilio_voice.py` - TwiML-Based Voice Calls

### **Purpose**
**Primary Twilio integration** - Handles voice calls using TwiML (Twilio Markup Language) and HTTP webhooks.

### **What It Does**

#### **TwilioVoiceHandler Class**
Main handler for Twilio voice calls using the **TwiML approach**:

1. **Starts FastAPI webhook server** (`start_webhook_server()`)
   - Listens on port 5000 (default)
   - Receives HTTP POST requests from Twilio
   - Returns TwiML XML responses

2. **Handles incoming calls** (`/webhook/voice`)
   - Receives call initiation webhook from Twilio
   - Creates TwiML response with welcome message
   - Uses Twilio's built-in speech recognition (`<Gather>`)

3. **Processes speech input** (`/process_speech/<call_sid>`)
   - Receives transcribed speech from Twilio
   - Sends to VOCA orchestrator for AI response
   - Returns TwiML with AI response (text-to-speech)
   - Loops conversation using `<Gather>` tags

4. **Handles call status updates** (`/call/status`)
   - Receives status webhooks (ringing, in-progress, completed, etc.)
   - Updates call state
   - Cleans up when call ends

5. **Handles outbound calls** (`/outbound`)
   - TwiML endpoint for outbound calls
   - Similar to incoming call handler

6. **Makes outbound calls** (`make_outbound_call()`)
   - Uses Twilio REST API to initiate calls
   - Provides webhook URL for call handling

7. **Manages call state** (`active_calls` dictionary)
   - Tracks all active calls by CallSid
   - Stores call metadata (from, to, status, timestamps)

#### **TwilioCallManager Class**
Higher-level manager that:
- Wraps `TwilioVoiceHandler`
- Ensures VOCA models are loaded before starting
- Provides convenient methods (`make_call()`, `hangup_all_calls()`, `get_call_status()`)

### **How It Works (TwiML Flow)**

```
1. Call comes in → Twilio sends POST to /webhook/voice
2. Server returns TwiML: <Say> welcome message </Say>
3. Server returns TwiML: <Gather input="speech"> listen </Gather>
4. User speaks → Twilio transcribes speech
5. Twilio POSTs transcription to /process_speech/<call_sid>
6. Server sends text to VOCA orchestrator (LLM)
7. Server gets AI response
8. Server returns TwiML: <Say> AI response </Say>
9. Loop back to step 3 (continue conversation)
10. Call ends → Twilio POSTs to /call/status
```

### **Key Features**
- ✅ **Uses Twilio's built-in speech recognition** (no STT needed)
- ✅ **Uses Twilio's built-in text-to-speech** (no TTS needed)
- ✅ **Simple HTTP webhooks** (no WebSocket/WebRTC complexity)
- ✅ **Works with standard phone calls** (PSTN)
- ❌ **Not real-time streaming** (uses Twilio's batch transcription)
- ❌ **Higher latency** (each turn requires full transcription)

### **Current Status**
**✅ ACTIVELY USED** - This is the main integration method currently in use.

---

## 3. `webrtc.py` - WebRTC Client Stub

### **Purpose**
WebRTC client implementation for **direct peer-to-peer audio streaming** (not currently used with Twilio).

### **What It Does**

#### **TwilioWebRTCClient Class**
- Creates WebRTC peer connection using `aiortc`
- Handles SDP (Session Description Protocol) offers/answers
- Receives audio tracks from remote peer
- Converts audio to PCM16 format for VOCA processing
- **Placeholder for sending audio** (TTS output)

#### **WebRTCClient Class**
- Legacy stub for backward compatibility
- Basic WebRTC connection setup

### **How It Would Work (If Used)**
```
1. Establish WebRTC connection with Twilio
2. Receive real-time audio stream (low latency)
3. Process audio chunks through VOCA STT
4. Send audio responses back via WebRTC
```

### **Key Features**
- ✅ **Real-time audio streaming** (low latency)
- ✅ **Bidirectional audio** (can send/receive)
- ✅ **Direct audio processing** (bypasses Twilio transcription)
- ❌ **More complex** (requires WebRTC negotiation)
- ❌ **Not currently integrated** with Twilio Voice
- ❌ **Requires WebRTC gateway** (Twilio Media Streams)

### **Current Status**
**⚠️ NOT ACTIVELY USED** - This is a stub/preparation for future real-time streaming. The current implementation uses TwiML approach instead.

---

## 4. `websocket_handler.py` - WebSocket and Media Stream Handlers

### **Purpose**
Alternative handlers for **real-time audio streaming** using WebSockets and Twilio Media Streams.

### **What It Does**

#### **TwilioWebSocketHandler Class**
- Creates FastAPI app with WebSocket support for WebSocket connections
- Handles WebSocket events:
  - `connect` - New WebSocket connection
  - `disconnect` - Connection closed
  - `join_call` - Join a call room
  - `audio_data` - Receive audio data from client
  - `call_status` - Receive call status updates
- Processes audio chunks through VOCA orchestrator
- Sends audio responses back via WebSocket

#### **TwilioMediaStreamHandler Class**
- Handles Twilio Media Streams API
- Receives base64-encoded audio payloads
- Decodes audio to numpy arrays
- Processes through VOCA orchestrator

### **How It Would Work (If Used)**
```
1. Call established via TwiML
2. TwiML includes <Start><Stream> to WebSocket URL
3. Twilio opens WebSocket connection
4. Real-time audio streamed via WebSocket
5. Audio chunks processed through VOCA STT
6. AI responses sent back via WebSocket
```

### **Key Features**
- ✅ **Real-time audio streaming** (low latency)
- ✅ **Bidirectional communication** (send/receive)
- ✅ **WebSocket-based** (persistent connection)
- ❌ **Not currently integrated** in main flow
- ❌ **Requires Twilio Media Streams setup**
- ❌ **More complex than TwiML approach**

### **Current Status**
**⚠️ PREPARED BUT NOT ACTIVELY USED** - These handlers are created but not integrated into the main call flow. The current implementation uses the simpler TwiML approach.

---

## How They Work Together

### **Current Implementation Flow**

```
┌─────────────────────────────────────────────────────────────┐
│                     twilio_app.py                            │
│  (Main Application - Coordinates Everything)                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ├──────────────────────────────────────┐
                       │                                      │
            ┌──────────▼──────────┐              ┌────────────▼──────────┐
            │  twilio_config.py   │              │  twilio_voice.py      │
            │  (Loads credentials)│──────────────▶│  (TwiML webhooks)     │
            └─────────────────────┘              └────────────┬──────────┘
                                                              │
                                                              │
                       ┌──────────────────────────────────────┘
                       │
            ┌──────────▼──────────┐
            │  VocaOrchestrator   │
            │  (STT, LLM, TTS)    │
            └─────────────────────┘
```

### **Current Call Flow**

1. **Initialization** (`twilio_app.py`)
   - Loads config from `twilio_config.py`
   - Creates `TwilioCallManager` from `twilio_voice.py`
   - Starts FastAPI webhook server

2. **Incoming Call** (`twilio_voice.py`)
   - Twilio POSTs to `/webhook/voice`
   - Server returns TwiML with `<Say>` and `<Gather>`
   - User speaks → Twilio transcribes

3. **Speech Processing** (`twilio_voice.py`)
   - Twilio POSTs transcription to `/process_speech/<call_sid>`
   - Text sent to `VocaOrchestrator.generate_reply()`
   - AI response returned as TwiML `<Say>`

4. **Call Status** (`twilio_voice.py`)
   - Twilio POSTs status updates to `/call/status`
   - Server updates call state
   - Cleans up on call end

### **Unused Components**

- **`webrtc.py`** - Prepared for future WebRTC integration
- **`websocket_handler.py`** - Prepared for future Media Streams integration

---

## Current Usage Status

| Component | Status | Purpose | Used In Production? |
|-----------|--------|---------|---------------------|
| `twilio_config.py` | ✅ Active | Configuration management | ✅ Yes |
| `twilio_voice.py` | ✅ Active | TwiML-based voice calls | ✅ Yes |
| `webrtc.py` | ⚠️ Stub | WebRTC client (future) | ❌ No |
| `websocket_handler.py` | ⚠️ Prepared | WebSocket/Media Streams (future) | ❌ No |

---

## Key Differences: TwiML vs WebRTC/WebSocket

### **TwiML Approach (Current)**
- ✅ Simple HTTP webhooks
- ✅ Uses Twilio's speech recognition
- ✅ Uses Twilio's text-to-speech
- ✅ Works with standard phone calls
- ❌ Higher latency (batch processing)
- ❌ Not real-time streaming

### **WebRTC/WebSocket Approach (Future)**
- ✅ Real-time audio streaming
- ✅ Lower latency
- ✅ Direct audio processing
- ✅ More control over audio pipeline
- ❌ More complex implementation
- ❌ Requires Media Streams setup
- ❌ Need to handle STT/TTS ourselves

---

## Recommendations for Phase 1

### **What to Use**
1. ✅ **Keep using `twilio_voice.py`** - It's working and simpler
2. ✅ **Use `twilio_config.py`** - Already integrated
3. ✅ **Focus on TwiML approach** - More stable for Phase 1

### **What to Prepare (Not Implement)**
1. ⚠️ **Keep `webrtc.py` and `websocket_handler.py`** - For future Phase 2
2. ⚠️ **Don't integrate them yet** - Focus on Phase 1 requirements first

### **Phase 1 Priorities**
1. Add authentication layer
2. Add database persistence (Assistants, Phone Numbers, Calls, Sessions)
3. Add management API endpoints
4. Add webhook event delivery system
5. **Keep using TwiML approach** - It's sufficient for Phase 1 success criteria

---

## Summary

- **`twilio_config.py`** - Configuration management (✅ Active)
- **`twilio_voice.py`** - Main Twilio integration using TwiML (✅ Active)
- **`webrtc.py`** - WebRTC client stub (⚠️ Not used)
- **`websocket_handler.py`** - WebSocket/Media Stream handlers (⚠️ Not used)

**Current implementation uses TwiML approach** which is simpler and sufficient for Phase 1. The WebRTC/WebSocket components are prepared for future real-time streaming features but are not needed for Phase 1 success criteria.


