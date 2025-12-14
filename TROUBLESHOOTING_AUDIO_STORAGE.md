# Troubleshooting Audio Storage

## Problem: No Audio Files Stored

If you're not seeing audio files after a call, check the following:

## 1. Check if Audio Storage is Enabled

```bash
# Check environment variable
echo $VOCA_DEBUG_AUDIO_STORAGE  # Should be "true"
```

Or check your `.env` file:
```
VOCA_DEBUG_AUDIO_STORAGE=true
```

## 2. Check WebSocket Support

Twilio Media Streams **require WebSocket (wss://)** connections. Your webhook URL must:
- Support WebSocket protocol
- Be accessible via `wss://` (not just `https://`)
- If using ngrok, ensure WebSocket support is enabled

### Testing WebSocket Support

1. Check your webhook URL in Twilio console
2. Ensure it uses `wss://` protocol (not `http://` or `https://`)
3. If using ngrok, make sure WebSocket is enabled:
   ```bash
   ngrok http 5000 --log=stdout
   # Or for WebSocket explicitly:
   ngrok http 5000 --log=stdout --webhook-header-add="Upgrade: websocket"
   ```

## 3. Check Logs

Look for these log messages:
- `[AUDIO_DEBUG] Enabled Media Stream for call...` - Media Stream was added to TwiML
- `[AUDIO_DEBUG] Media Stream WebSocket connected...` - WebSocket connection established
- `[AUDIO_DEBUG] Media stream started...` - Stream started receiving data
- `[AUDIO_DEBUG] Stored audio chunk #N...` - Audio was successfully stored

If you don't see these messages, Media Streams aren't connecting.

## 4. Common Issues

### Issue: WebSocket URL is HTTP instead of WSS
**Solution**: The code automatically converts `http://` to `wss://`, but ensure your webhook URL is correct.

### Issue: ngrok doesn't support WebSocket
**Solution**: Use ngrok with WebSocket support or use a different tunnel service.

### Issue: Media Streams not connecting
**Solution**: 
1. Check Twilio console for Media Stream errors
2. Verify your server is accessible from the internet
3. Check firewall/security group settings

### Issue: Audio files created but empty
**Solution**: This might be a μ-law decoding issue. Check logs for decoding errors.

## 5. Manual Testing

To test if audio storage works:

```python
# Run this test script
python -c "
from src.voca.audio_debug_storage import store_stt_audio
import numpy as np
result = store_stt_audio('test', np.zeros(16000, dtype=np.int16), 1, {}, 16000)
print(f'Test result: {result}')
"
```

If this works, audio storage is functional - the issue is with Media Streams connection.

## 6. Alternative: Use Different Audio Source

If Media Streams don't work, you could:
1. Use a different audio source (not Twilio Gather)
2. Record audio separately
3. Use a different telephony provider that supports audio streaming

## Next Steps

1. Enable audio storage: `VOCA_DEBUG_AUDIO_STORAGE=true`
2. Ensure WebSocket support in your webhook URL
3. Make a test call
4. Check logs for `[AUDIO_DEBUG]` messages
5. Verify files in `audio_logs/{call_sid}/`






