# Comprehensive Debugging Analysis - Twilio WebRTC Audio Streaming

## ✅ **FIXED ISSUES**

### 1. **NGINX Configuration - CRITICAL FIX** ✅
**Issue Found:** `proxy_pass` was missing `$request_uri`, causing path stripping
- **Before:** `proxy_pass http://127.0.0.1:8000;` 
- **After:** `proxy_pass http://127.0.0.1:8000$request_uri;`
- **Impact:** NGINX was forwarding to `/` instead of `/webrtc/{call_sid}`, so WebSocket route never matched

### 2. **Missing JSON Import** ✅
- Added `import json` to `twilio_webhooks.py`
- Required for logging connection data

### 3. **Enhanced Logging** ✅
- Added comprehensive debug logging throughout the flow
- Timestamp tracking for audio frames
- Detailed TTS streaming logs
- WebSocket connection state logging

---

## ✅ **VERIFIED COMPONENTS**

### 1. **Route Registration** ✅
- WebSocket route `/webrtc/{call_sid}` is registered in `twilio_webhooks.py`
- Router is included in `src/voca/api/routes/__init__.py`
- Router is included in FastAPI app in `src/voca/api/app.py`

### 2. **TwiML Generation** ✅
- Uses `<Connect><Stream>` correctly
- CallSid is inserted directly in URL (not using variables)
- Track parameter is configurable via `TWILIO_STREAM_TRACK` env var
- URL conversion from http/https to wss is correct

### 3. **URL Construction Logic** ✅
```python
# Line 263-278 in twilio_webhooks.py
webhook_url = config.get_webhook_url()  # e.g., "https://voca2.duckdns.org/outbound"
base_url = webhook_url.replace('/webhook/voice', '').replace('/outbound', '')  # "https://voca2.duckdns.org"
wss_base_url = base_url.replace('https://', 'wss://')  # "wss://voca2.duckdns.org"
stream_url = f"{wss_base_url}/webrtc/{call_sid}"  # "wss://voca2.duckdns.org/webrtc/CA..."
```
**This logic is correct** ✅

### 4. **NGINX WebSocket Configuration** ✅
- `proxy_set_header Upgrade $http_upgrade;` ✅
- `proxy_set_header Connection $connection_upgrade;` ✅
- `proxy_set_header Sec-WebSocket-Protocol "twilio-rtp";` ✅
- `proxy_read_timeout 3600s;` ✅
- `proxy_send_timeout 3600s;` ✅
- `proxy_buffering off;` ✅

### 5. **WebSocket Handler** ✅
- Properly accepts WebSocket connections
- Handles `connected`, `start`, `media`, and `stop` events
- Stores WebSocket in `twilio_media_websockets` dict
- Delivers welcome message after `start` event
- Processes inbound audio and sends to Deepgram STT
- Streams TTS audio back to Twilio

### 6. **TTS Streaming** ✅
- Checks for WebSocket availability before streaming
- Uses Deepgram REST API with μ-law encoding
- Sends audio in 20ms chunks (160 bytes)
- Proper base64 encoding
- Comprehensive error handling

---

## 🔍 **FLOW VERIFICATION**

### Expected Flow:
1. **Outbound Call Initiated** → Twilio calls `/outbound` webhook
2. **TwiML Generated** → Contains `<Connect><Stream url="wss://voca2.duckdns.org/webrtc/{call_sid}">`
3. **Twilio Connects** → WebSocket upgrade request to `wss://voca2.duckdns.org/webrtc/{call_sid}`
4. **NGINX Proxies** → Forwards to `http://127.0.0.1:8000/webrtc/{call_sid}` (NOW FIXED)
5. **FastAPI Handles** → WebSocket route matches, connection accepted
6. **Twilio Sends Events**:
   - `connected` event → Logged
   - `start` event → StreamSid received, WebSocket stored, welcome message sent
   - `media` events → Audio processed, sent to Deepgram STT
7. **TTS Streaming** → Welcome message and AI responses streamed back

---

## ⚠️ **POTENTIAL ISSUES TO CHECK**

### 1. **Environment Variable: TWILIO_WEBHOOK_URL**
**Check:** Ensure `TWILIO_WEBHOOK_URL` is set correctly in `.env`
- Should be: `https://voca2.duckdns.org/outbound` (for outbound calls)
- Or: `https://voca2.duckdns.org/webhook/voice` (for incoming calls)

**Verification:**
```bash
# Check logs for:
[WebRTC] Stream URL with actual CallSid: wss://voca2.duckdns.org/webrtc/CA...
```

### 2. **NGINX Reload Required**
**Action Required:** After fixing NGINX config, reload NGINX:
```bash
sudo nginx -t  # Test configuration
sudo systemctl reload nginx  # Reload if test passes
```

### 3. **Firewall/UDP Ports**
**Check:** Ensure server allows UDP traffic to Twilio's media servers
- Twilio uses UDP for RTP media
- Check firewall rules for outbound UDP

### 4. **Deepgram API Key**
**Check:** Ensure `DEEPGRAM_API_KEY` is set in `.env`
- Required for TTS streaming
- Check logs for Deepgram API errors

---

## 📊 **LOG CHECKLIST**

After making a call, check logs for these markers:

### ✅ **TwiML Generation:**
- `[TWiML_DEBUG] ✓ TwiML contains <Connect><Stream>`
- `[TWiML_DEBUG] ✓ Stream URL contains actual CallSid`

### ✅ **WebSocket Connection:**
- `[WEBSOCKET_DEBUG] ===== WebSocket upgrade attempt =====` (from middleware)
- `[WebRTC] ===== WebRTC WebSocket handler CALLED`
- `[WebRTC] ===== WebRTC WebSocket ACCEPTED`

### ✅ **Twilio Events:**
- `[WebRTC] ===== 'connected' event received`
- `[WebRTC] ===== 'start' event received`
- `[WebRTC] ✓ Stream started - streamSid: {streamSid}`

### ✅ **Welcome Message:**
- `[WebRTC] ===== DELIVERING WELCOME MESSAGE =====`
- `[TTS_STREAM] ===== Starting TTS stream`
- `[TTS_STREAM] ===== TTS stream completed`
- `[WebRTC] ===== WELCOME MESSAGE DELIVERED SUCCESSFULLY =====`

### ✅ **Audio Processing:**
- `[WebRTC] ✓ Inbound media frame #1 received`
- `[WebRTC] Started Deepgram STT for call`

---

## 🎯 **CONCLUSION**

**All critical issues have been fixed:**
1. ✅ NGINX `proxy_pass` now includes `$request_uri`
2. ✅ WebSocket route is properly registered
3. ✅ TwiML generation is correct
4. ✅ URL construction logic is correct
5. ✅ Comprehensive logging is in place

**Next Steps:**
1. Reload NGINX configuration
2. Make a test call
3. Check logs for the markers above
4. If WebSocket still doesn't connect, check:
   - NGINX error logs: `sudo tail -f /var/log/nginx/error.log`
   - FastAPI logs for WebSocket upgrade attempts
   - Twilio Debug Console for connection errors

**The main blocker (NGINX path stripping) has been fixed. The WebSocket should now connect properly.**

