# Deepgram Integration Guide for Twilio

This guide explains how to replace Twilio's built-in STT and TTS with Deepgram's services.

## Overview

The Deepgram integration uses Twilio Media Streams to get raw audio, processes it through Deepgram STT, and streams responses back using Deepgram TTS. This provides:

- **Better accuracy**: Deepgram's Nova-2 model for speech recognition
- **Better voice quality**: Deepgram's Aura voices for text-to-speech
- **Real-time streaming**: Lower latency than TwiML batch processing
- **More control**: Direct access to audio streams

## Prerequisites

1. **Deepgram API Key**: Get one from [Deepgram Console](https://console.deepgram.com/)
2. **Twilio Account**: With Media Streams enabled
3. **SSL/HTTPS**: WebSocket connections require WSS (secure WebSocket)

## Setup

### 1. Install Dependencies

The Deepgram SDK is already added to `requirements.txt`. Install it:

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Add to your `.env` file:

```env
# Deepgram Configuration
DEEPGRAM_API_KEY=your_deepgram_api_key_here

# Optional: Add keyterms for better accuracy with names, email addresses, etc.
# Comma-separated list of terms that should be recognized accurately
DEEPGRAM_KEYTERMS=Yash Verma,vermayash849,john@example.com
```

**Keyterms** help Deepgram accurately recognize:
- Names (e.g., "Yash Verma")
- Email addresses (e.g., "vermayash849")
- Uncommon words or proper nouns
- Technical terms

**Note:** Only add uncommon terms. Adding common words can reduce overall accuracy.

### 3. Choose Integration Method

You have two options:

#### Option A: Use Deepgram Handler (Recommended for new implementations)

The `DeepgramTwilioHandler` class provides a complete Media Streams implementation:

```python
from src.voca.deepgram_twilio_handler import DeepgramTwilioHandler
from src.voca.orchestrator import VocaOrchestrator

orchestrator = VocaOrchestrator()
orchestrator.load_models()

handler = DeepgramTwilioHandler(orchestrator)
handler.start_webhook_server(host='0.0.0.0', port=5000)
```

#### Option B: Modify Existing Handler

To use Deepgram with the existing `TwilioVoiceHandler`, you'll need to:

1. Set `VOCA_STT_BACKEND=deepgram` in your `.env`
2. Ensure `DEEPGRAM_API_KEY` is set
3. The system will automatically use Deepgram for STT

However, TTS will still use Twilio's `<Say>` verb unless you switch to Media Streams.

### 4. Configure WebSocket URL

Media Streams require a WebSocket (WSS) URL. Update your Twilio webhook configuration:

1. If using ngrok or similar tunnel:
   ```env
   TWILIO_WEBHOOK_URL=https://your-ngrok-url.ngrok.io
   ```

2. The handler will automatically convert HTTP/HTTPS URLs to WSS for WebSocket connections.

### 5. Update Twilio Phone Number Configuration

In Twilio Console:
1. Go to Phone Numbers → Manage → Active Numbers
2. Click your phone number
3. Set Voice Webhook to: `https://your-server-url/webhook/voice`
4. Set HTTP Method to: `POST`

## How It Works

### Architecture

```
┌─────────────┐
│   Twilio    │
│   Phone     │
└──────┬──────┘
       │
       │ Media Stream (WebSocket)
       │
┌──────▼──────────────────────────┐
│  DeepgramTwilioHandler         │
│  - Receives audio from Twilio   │
│  - Sends to Deepgram STT        │
│  - Processes with AI            │
│  - Generates audio with TTS     │
│  - Streams back to Twilio       │
└─────────────────────────────────┘
```

### Flow

1. **Call Incoming**: Twilio sends webhook to `/webhook/voice`
2. **TwiML Response**: Returns TwiML with `<Start><Stream>` pointing to WebSocket endpoint
3. **WebSocket Connection**: Twilio connects to `/media/{call_sid}`
4. **Audio Streaming**: 
   - Twilio sends audio chunks (μ-law encoded)
   - Handler converts to linear16 PCM
   - Sends to Deepgram STT for transcription
5. **AI Processing**: Transcript sent to orchestrator for AI response
6. **TTS Generation**: AI response converted to audio using Deepgram TTS
7. **Audio Streaming Back**: Generated audio sent back to Twilio via WebSocket

## API Reference

### DeepgramSTT Class

Located in `src/voca/stt.py`:

```python
from src.voca.stt import DeepgramSTT

stt = DeepgramSTT(api_key="your_key", sample_rate=8000)
stt.load()

# For prerecorded audio
transcript = stt.transcribe_pcm16(audio_array)

# For live streaming
connection = stt.create_live_connection(on_transcript=callback)
stt.send_audio_chunk(connection, audio_array)
```

### DeepgramTTS Class

Located in `src/voca/tts.py`:

```python
from src.voca.tts import DeepgramTTS

tts = DeepgramTTS(api_key="your_key", voice="aura-asteria-en")
tts.load()

# Generate audio
audio_bytes = tts.speak("Hello, world!")
audio_array = tts.speak_to_numpy("Hello, world!")
```

### DeepgramTwilioHandler Class

Located in `src/voca/deepgram_twilio_handler.py`:

```python
from src.voca.deepgram_twilio_handler import DeepgramTwilioHandler

handler = DeepgramTwilioHandler(orchestrator)
handler.start_webhook_server(host='0.0.0.0', port=5000)
```

## Configuration Options

### Environment Variables

- `DEEPGRAM_API_KEY`: Your Deepgram API key (required)
- `DEEPGRAM_KEYTERMS`: Comma-separated list of terms for better accuracy (optional)
  - Example: `DEEPGRAM_KEYTERMS=Yash Verma,vermayash849,john@example.com`
  - Use for names, email addresses, and uncommon words
  - Don't use for common words as it can reduce accuracy
- `VOCA_STT_BACKEND`: Set to `"deepgram"` to force Deepgram STT

### Deepgram STT Options

- `sample_rate`: Audio sample rate (default: 8000 Hz for phone calls)
- `model`: Deepgram model (default: "nova-2")

### Deepgram TTS Options

- `voice`: Voice model (default: "aura-asteria-en")
- `sample_rate`: Output sample rate (default: 24000 Hz)

## Troubleshooting

### "Deepgram API key not configured"

- Ensure `DEEPGRAM_API_KEY` is set in your `.env` file
- Restart your application after adding the key

### "WebSocket connection failed"

- Ensure your server has SSL/HTTPS enabled
- WebSocket URLs must use `wss://` (secure WebSocket)
- Check that your webhook URL is accessible from the internet

### "Failed to start Deepgram live connection"

- Verify your Deepgram API key is valid
- Check your Deepgram account has sufficient credits
- Ensure network connectivity to Deepgram servers

### Audio quality issues

- Adjust sample rate settings if needed
- Check μ-law to linear16 conversion is working correctly
- Verify audio format matches Deepgram requirements

### Names or email addresses being misspelled

- Add the terms to `DEEPGRAM_KEYTERMS` in your `.env` file
- Use comma-separated format: `DEEPGRAM_KEYTERMS=Yash Verma,vermayash849`
- Restart the application after adding keyterms
- Keyterms help Deepgram prioritize these specific terms during transcription
- Only add uncommon terms - adding common words can reduce overall accuracy

## Cost Considerations

- **Deepgram STT**: Pay-per-minute of audio transcribed
- **Deepgram TTS**: Pay-per-character of text synthesized
- **Twilio Media Streams**: Standard Twilio pricing applies

Check [Deepgram Pricing](https://deepgram.com/pricing) for current rates.

## Migration from TwiML

If you're currently using TwiML `<Gather>` and `<Say>`:

1. **Backup your current implementation**
2. **Test Deepgram handler in development**
3. **Update webhook URLs** to point to new handler
4. **Monitor call quality** and adjust settings as needed

## Support

For issues:
- Deepgram: [Deepgram Support](https://deepgram.com/support)
- Twilio: [Twilio Support](https://support.twilio.com/)
- VOCA: Check project documentation or GitHub issues

