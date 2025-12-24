# WebRTC Audio Pipeline Debugging Guide

## 🎯 Goal
Verify that audio plays correctly for outbound calls using the WebRTC-first architecture.

---

## 📋 Step-by-Step Verification Checklist

### **Step 1: Verify TwiML Contains Actual CallSid**

**What to Check:**
- TwiML XML must contain the actual CallSid in the Stream URL
- URL format: `wss://voca2.duckdns.org/webrtc/CAxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

**Expected Logs:**
```
[TWiML_DEBUG] TwiML XML for call CAxxxxx:
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://voca2.duckdns.org/webrtc/CAxxxxxxxxxxxxxxxxxxxxxxxxxxxx" track="both_tracks">
      <Parameter name="call_sid" value="CAxxxxxxxxxxxxxxxxxxxxxxxxxxxx"/>
    </Stream>
  </Connect>
</Response>

[TWiML_DEBUG] ✓ TwiML contains <Connect><Stream> - Twilio should connect
[TWiML_DEBUG] ✓ Stream URL contains actual CallSid: CAxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**❌ Red Flags:**
- `{CallSid}` or `{{CallSid}}` appears in the URL
- Stream URL doesn't contain the actual CallSid
- Missing `<Connect><Stream>` tags

**✅ Success Criteria:**
- TwiML shows actual CallSid in URL
- No `{CallSid}` variable present
- `<Connect><Stream>` is present

---

### **Step 2: Confirm WebSocket Connection**

**What to Check:**
- Twilio attempts to connect to `/webrtc/{CallSid}`
- Server accepts the WebSocket connection

**Expected Logs:**
```
[WEBSOCKET_DEBUG] ===== WebSocket upgrade attempt =====
[WEBSOCKET_DEBUG] Method: GET
[WEBSOCKET_DEBUG] Path: /webrtc/CAxxxxxxxxxxxxxxxxxxxxxxxxxxxx
[WEBSOCKET_DEBUG] Client: ('54.152.15.87', 12345)
[WEBSOCKET_DEBUG] Headers: {...}

[WebRTC] ===== WebRTC WebSocket handler CALLED for call CAxxxxx =====
[WebRTC] WebSocket path: /webrtc/CAxxxxx
[WebRTC] WebSocket client: ('54.152.15.87', 12345)
[WebRTC] ===== WebRTC WebSocket ACCEPTED for call CAxxxxx =====
[WebRTC] Waiting for Twilio stream events...
```

**❌ Red Flags:**
- No `[WEBSOCKET_DEBUG]` logs
- No `[WebRTC] WebSocket handler CALLED` log
- WebSocket accept fails

**✅ Success Criteria:**
- WebSocket upgrade attempt logged
- Handler called and accepted
- Connection established

---

### **Step 3: Watch for 'start' Event**

**What to Check:**
- Twilio sends 'start' event with streamSid
- streamSid is stored for audio transmission

**Expected Logs:**
```
[WebRTC] ===== 'connected' event received for call CAxxxxx =====
[WebRTC] ✓ Twilio WebSocket connection established - waiting for 'start' event...

[WebRTC] ===== 'start' event received for call CAxxxxx =====
[WebRTC] Start event data: {
  "event": "start",
  "start": {
    "streamSid": "MZxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "accountSid": "ACxxxxx",
    "callSid": "CAxxxxx",
    ...
  }
}
[WebRTC] ✓ Stream started - streamSid: MZxxxxxxxxxxxxxxxxxxxxxxxxxxxx
[WebRTC] ✓ WebSocket stored - ready to send/receive audio
[WebRTC] ===== AUDIO PIPELINE IS NOW ACTIVE =====
```

**❌ Red Flags:**
- No 'start' event received
- streamSid is None or missing
- WebSocket not stored

**✅ Success Criteria:**
- 'start' event received
- streamSid is valid
- WebSocket stored in `twilio_media_websockets`

---

### **Step 4: Check for Incoming Media Frames**

**What to Check:**
- User speech generates 'media' events
- Audio payloads are non-zero

**Expected Logs:**
```
[WebRTC] ✓ Inbound media frame #1 received: 240 bytes (base64)
[WebRTC] Decoded audio bytes: 160 bytes (μ-law)
[WebRTC] Sending 160 bytes to Deepgram STT (PCM16, 160 samples)
[WebRTC] ✓ Inbound media frame #2 received: 240 bytes (base64)
...
```

**❌ Red Flags:**
- No 'media' events received
- Empty audio payloads (0 bytes)
- Media events stop after a few frames

**✅ Success Criteria:**
- Regular 'media' events (every ~20ms)
- Non-zero payload sizes
- Audio being sent to Deepgram STT

---

### **Step 5: Verify TTS Audio Generation & Transmission**

**What to Check:**
- TTS generates PCM16 @ 8kHz audio
- Audio is chunked into ~20ms frames (160 bytes μ-law)
- Frames are sent over WebSocket

**Expected Logs:**
```
[WebRTC] Delivering welcome message for call CAxxxxx (streamSid: MZxxxxx)
[WebRTC] Starting TTS for welcome message: Hello! This is Heal Card Health checkup calling.
[TTS_STREAM] Starting TTS stream for call CAxxxxx: text='Hello! This is Heal Card Health checkup calling.', chunk_size=160 bytes
[TTS_STREAM] Sent chunk 1 to Twilio: 160 bytes (μ-law) = 240 bytes (base64), streamSid=MZxxxxx
[TTS_STREAM] Sent chunk 2 to Twilio: 160 bytes (μ-law) = 240 bytes (base64), streamSid=MZxxxxx
...
[TTS_STREAM] Streamed TTS audio to Twilio for call CAxxxxx: 45 chunks, 7200 total bytes, text='Hello! This is Heal Card Health checkup calling.'
[WebRTC] Welcome message TTS streamed successfully for call CAxxxxx
```

**❌ Red Flags:**
- No TTS logs
- Chunk size is wrong (not 160 bytes)
- TTS errors or failures
- No "Streamed TTS audio" completion log

**✅ Success Criteria:**
- TTS starts and completes
- Chunks are 160 bytes (20ms @ 8kHz)
- Total bytes sent matches expected duration
- No errors in TTS streaming

---

### **Step 6: Verify No TwiML Conflicts**

**What to Check:**
- No `<Say>` or `<Play>` verbs in TwiML
- Only `<Connect><Stream>` is present

**Expected TwiML:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://voca2.duckdns.org/webrtc/CAxxxxx" track="both_tracks">
      <Parameter name="call_sid" value="CAxxxxx"/>
    </Stream>
  </Connect>
</Response>
```

**❌ Red Flags:**
- `<Say>` tag present
- `<Play>` tag present
- Multiple audio sources

**✅ Success Criteria:**
- Only `<Connect><Stream>` in TwiML
- No conflicting audio verbs

---

### **Step 7: Test with Static PCM Audio (Optional)**

**What to Check:**
- WebSocket can send raw audio without TTS/LLM
- Audio is heard on the call

**How to Test:**
1. Wait for 'start' event (Step 3)
2. Call the test endpoint:
   ```bash
   curl -X POST http://localhost:8000/webrtc/{CallSid}/send-test-tone
   ```

**Expected Logs:**
```
[TEST_TONE] Sending 1-second test tone (440Hz) for call CAxxxxx
[TEST_TONE] Total audio: 8000 bytes, will send in 50 chunks
[TEST_TONE] Sent 10 chunks (1600 bytes)
[TEST_TONE] Sent 20 chunks (3200 bytes)
...
[TEST_TONE] ✓ Test tone sent: 50 chunks, 8000 bytes total
```

**Expected Result:**
- You hear a 1-second 440Hz tone (A4 note) on the call

**✅ Success Criteria:**
- Test tone endpoint succeeds
- Audio is heard on call
- No WebSocket errors

---

### **Step 8: End-to-End Greeting Verification**

**What to Check:**
- Welcome message is fetched from system_prompts
- TTS generates audio
- Audio is streamed and heard

**Expected Flow:**
1. Call initiated → TwiML generated
2. WebSocket connects → 'start' event
3. Welcome message fetched → TTS generated
4. Audio streamed → Heard on call

**Expected Logs:**
```
[WebRTC] Generated greeting for outbound call CAxxxxx: Hello! This is Heal Card Health checkup calling.
[TWiML_DEBUG] ✓ TwiML contains <Connect><Stream>
[WebRTC] ===== WebRTC WebSocket ACCEPTED =====
[WebRTC] ===== 'start' event received =====
[WebRTC] Delivering welcome message for call CAxxxxx
[TTS_STREAM] Starting TTS stream for call CAxxxxx
[TTS_STREAM] Streamed TTS audio: 45 chunks, 7200 total bytes
[WebRTC] Welcome message TTS streamed successfully
```

**✅ Success Criteria:**
- All steps complete without errors
- Greeting is heard on the call
- Call continues to listen for user speech

---

## 🔍 Diagnostic Commands

### Check Call State
```bash
curl http://localhost:8000/webrtc/{CallSid}/test-audio
```

### Send Test Tone
```bash
curl -X POST http://localhost:8000/webrtc/{CallSid}/send-test-tone
```

### View Logs (Real-time)
```bash
tail -f logs/app.log | grep -E "\[WebRTC\]|\[TTS_STREAM\]|\[TWiML_DEBUG\]|\[WEBSOCKET_DEBUG\]"
```

---

## 🚨 Common Issues & Solutions

### Issue: No WebSocket Connection
**Symptoms:**
- No `[WEBSOCKET_DEBUG]` logs
- No `[WebRTC] WebSocket handler CALLED` log

**Solutions:**
1. Check TwiML contains actual CallSid (not `{CallSid}`)
2. Verify URL is `wss://` (not `ws://` or `http://`)
3. Check firewall/network allows WebSocket connections
4. Verify server is publicly accessible

### Issue: No 'start' Event
**Symptoms:**
- WebSocket connects but no 'start' event
- streamSid is None

**Solutions:**
1. Wait longer (Twilio may delay 'start' event)
2. Check call status is "in-progress"
3. Verify TwiML is correct
4. Check Twilio account has Media Streams enabled

### Issue: No Media Events
**Symptoms:**
- 'start' event received but no 'media' events
- User speaks but no audio frames

**Solutions:**
1. Verify user is actually speaking
2. Check microphone permissions on user's device
3. Verify `track='both_tracks'` in Stream config
4. Check Twilio call quality

### Issue: TTS Not Playing
**Symptoms:**
- TTS logs show success but no audio heard
- Chunks sent but silence on call

**Solutions:**
1. Verify chunk size is 160 bytes (20ms)
2. Check audio format is μ-law @ 8kHz
3. Test with static tone (Step 7)
4. Verify streamSid matches in all messages
5. Check WebSocket is still connected

---

## ✅ Final Verification Checklist

Before considering audio working:

- [ ] TwiML contains actual CallSid in URL
- [ ] WebSocket connection established
- [ ] 'start' event received with valid streamSid
- [ ] Inbound media frames received
- [ ] TTS generates and sends audio chunks
- [ ] No TwiML conflicts (`<Say>`, `<Play>`)
- [ ] Welcome message heard on call
- [ ] Test tone works (if tested)

**If ALL above are true → Audio pipeline is working! 🎉**

