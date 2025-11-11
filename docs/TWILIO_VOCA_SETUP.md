# Twilio VOCA Integration Setup Guide

This guide will help you set up VOCA with Twilio for real-time voice AI calls.

## Prerequisites

1. **Python 3.8+** installed
2. **Twilio Account** with a phone number
3. **Gemini API Key** for AI responses
4. **ngrok** for local development (or a public server)

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

Create a `.env` file in your project root:

```env
# Gemini AI Configuration
GEMINI_API_KEY=your_gemini_api_key_here

# Twilio Configuration
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number
TWILIO_WEBHOOK_URL=https://your-ngrok-url.ngrok.io

# VOCA Configuration (optional)
VOCA_LLM_TEMPERATURE=0.7
VOCA_LLM_MAX_TOKENS=256
VOCA_SAMPLE_RATE=16000
```

### 3. Get Your Credentials

#### Gemini API Key
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create a new API key
3. Copy the key to your `.env` file

#### Twilio Credentials
1. Sign up at [Twilio Console](https://console.twilio.com/)
2. Get your Account SID and Auth Token from the dashboard
3. Purchase a phone number from Twilio
4. Add these to your `.env` file

## Running the Application

### Option 1: Test Integration First

```bash
python test_twilio_voca_integration.py
```

This will test all components and show you if everything is configured correctly.

### Option 2: Start the Application

```bash
python test_twilio_voca_integration.py --start
```

Or directly:

```bash
python -m src.voca.twilio_app
```

### Option 3: Using the Main Entry Point

```bash
python -m src.voca.twilio_app
```

## Setting Up ngrok for Local Development

### 1. Install ngrok

Download from [ngrok.com](https://ngrok.com/download) or use the provided installer:

```bash
python install_ngrok_windows.py
```

### 2. Start ngrok

```bash
ngrok http 5000
```

This will give you a public URL like `https://abc123.ngrok.io`

### 3. Update Your Webhook URL

Update your `.env` file with the ngrok URL:

```env
TWILIO_WEBHOOK_URL=https://abc123.ngrok.io
```

## Configuring Twilio Webhooks

### 1. Set Up Voice Webhook

1. Go to your Twilio Console
2. Navigate to Phone Numbers → Manage → Active Numbers
3. Click on your phone number
4. Set the webhook URL to: `https://your-ngrok-url.ngrok.io/webhook/voice`
5. Set HTTP method to `POST`
6. Save the configuration

### 2. Test the Setup

1. Start your VOCA application
2. Call your Twilio phone number
3. You should hear: "Hello! You've reached VOCA, your AI voice assistant. I'm listening..."
4. Speak to the AI and get real-time responses!

## Features

### Real-time Voice AI
- **Speech-to-Text**: Converts your speech to text using Vosk
- **AI Processing**: Uses Gemini 2.5 Flash for intelligent responses
- **Text-to-Speech**: Converts AI responses back to speech using Coqui TTS
- **Voice Activity Detection**: Automatically detects when you start/stop speaking

### Call Management
- **Incoming Calls**: Automatically answers and processes calls
- **Outgoing Calls**: Make AI-powered calls to any number
- **Call Status**: Monitor active calls and their status
- **Real-time Streaming**: Low-latency audio processing

## API Endpoints

The application exposes several endpoints:

- `POST /webhook/voice` - Handles incoming Twilio calls
- `POST /call/status` - Handles call status updates
- `POST /media/<call_sid>` - Handles media streams
- `GET /stream/<call_sid>` - WebSocket stream endpoint

## Troubleshooting

### Common Issues

1. **"GEMINI_API_KEY not found"**
   - Make sure your `.env` file is in the project root
   - Check that the API key is correctly set

2. **"Twilio configuration incomplete"**
   - Verify all Twilio credentials are correct
   - Check that your phone number is active

3. **"Models not loading"**
   - Ensure all dependencies are installed
   - Check that the Vosk model files are present

4. **"Webhook not receiving calls"**
   - Verify your ngrok URL is correct
   - Check that the webhook URL is set in Twilio Console
   - Make sure the application is running

### Logs

Check the application logs for detailed error information:

```bash
tail -f voca_twilio.log
```

### Testing Components

You can test individual components:

```bash
# Test VOCA models
python test_voca_components.py

# Test Twilio setup
python test_twilio_setup.py

# Test credentials
python test_your_credentials.py
```

## Production Deployment

For production deployment:

1. **Use a VPS/Cloud Server** instead of ngrok
2. **Set up SSL certificates** for HTTPS
3. **Configure proper logging** and monitoring
4. **Set up process management** (systemd, PM2, etc.)
5. **Use environment variables** for configuration

## Advanced Configuration

### Custom AI Prompts

You can customize the AI behavior by modifying the system prompt in `src/voca/orchestrator.py`:

```python
system_prompt = (
    "You are Voca, a helpful voice assistant. "
    "Respond concisely and naturally. "
    "If asked how you can help, say: 'I can assist you with the information that is available to me.' "
    "Keep responses brief and conversational."
)
```

### Audio Quality Settings

Adjust audio quality in `src/voca/config.py`:

```python
sample_rate: int = int(os.getenv("VOCA_SAMPLE_RATE", "16000"))
```

### LLM Settings

Customize AI behavior:

```env
VOCA_LLM_TEMPERATURE=0.7
VOCA_LLM_MAX_TOKENS=256
```

## Support

If you encounter issues:

1. Check the logs for error messages
2. Verify all credentials are correct
3. Test individual components
4. Check Twilio Console for call logs
5. Verify ngrok is running and accessible

## Next Steps

Once everything is working:

1. **Customize the AI personality** for your use case
2. **Add call recording** and analytics
3. **Implement call routing** for different scenarios
4. **Add multi-language support**
5. **Scale to handle multiple concurrent calls**

Happy coding! 🚀
