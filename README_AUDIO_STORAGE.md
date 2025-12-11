# Audio Storage Debug Guide

## Current Status

Audio storage is **enabled** in your configuration, but **no audio files were stored** from your recent call.

## Why Audio Wasn't Stored

Your Twilio calls are currently using **Twilio's Gather with speech recognition**, which means:
- Twilio processes the audio on their servers
- Only the **transcription text** is sent to your application
- The **raw audio never reaches your code**, so it can't be stored

## How Audio Storage Works

Audio storage only works when using **Twilio Media Streams**, which streams raw audio data to your server in real-time. This is different from using Twilio's built-in speech recognition.

## Solution Options

### Option 1: Enable Media Streams (Recommended for Debugging)

To store audio, you need to enable Twilio Media Streams. This requires:
1. Modifying the TwiML to include `<Stream>` instead of `<Gather>`
2. Processing audio chunks in real-time via the `/media/{call_sid}` endpoint

### Option 2: Check Current Setup

Your code already has support for media streams via:
- `/media/{call_sid}` endpoint in `twilio_voice.py`
- `process_audio_stream()` method
- Audio storage integration in `orchestrator.handle_audio_chunk()`

However, your current TwiML uses `<Gather>` which bypasses this path.

## Testing Audio Storage

To verify audio storage works, you can run:
```bash
python test_audio_storage.py
```

This will create a test audio file in `audio_logs/test_call_123/`.

## Current Configuration

- **Storage Enabled**: `True` (via `VOCA_DEBUG_AUDIO_STORAGE=true`)
- **Storage Directory**: `audio_logs/`
- **Test Files**: 1 test call found (`test_call_123`)

## Next Steps

If you want to store audio from Twilio calls:
1. Modify your TwiML to use Media Streams instead of Gather
2. Or enable Media Streams in addition to Gather for debugging
3. Audio files will be stored in `audio_logs/{call_sid}/` when streaming is active

