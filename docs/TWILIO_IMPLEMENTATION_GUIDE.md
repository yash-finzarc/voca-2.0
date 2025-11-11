# Complete Twilio Integration Guide for VOCA

## Overview

This guide will help you integrate Twilio Voice with your VOCA project to enable phone call functionality. The integration includes:

- **SIP to WebRTC Bridge**: Twilio handles the SIP trunk connection
- **Real-time Audio Processing**: Incoming calls are processed by your VOCA AI assistant
- **Outbound Calling**: Make calls from the application
- **Webhook Management**: Handle incoming call events

## Architecture

```
Phone Call → Twilio SIP → Twilio Voice API → Your Webhook Server → VOCA Orchestrator
                                                                    ↓
Phone Call ← Twilio SIP ← Twilio Voice API ← Your Webhook Server ← TTS Response
```

## Prerequisites

1. **Twilio Account** (Free tier available)
2. **Python 3.8+**
3. **ngrok** (for webhook testing)
4. **Your existing VOCA project**

## Step-by-Step Implementation

### Step 1: Twilio Account Setup

1. **Create Twilio Account**
   - Go to [Twilio Console](https://console.twilio.com/)
   - Sign up for free account
   - Verify your phone number

2. **Get Credentials**
   - Account SID: Found in Account Info
   - Auth Token: Found in Account Info
   - Phone Number: Go to Phone Numbers > Manage > Active numbers

3. **Configure Phone Number**
   - Click on your phone number
   - Enable Voice
   - Set webhook URL (we'll configure this later)

### Step 2: Environment Setup

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create .env File**
   ```env
   # Twilio Configuration
   TWILIO_ACCOUNT_SID=your_account_sid_here
   TWILIO_AUTH_TOKEN=your_auth_token_here
   TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
   TWILIO_WEBHOOK_URL=http://your-ngrok-url.ngrok.io/webhook/voice
   ```

3. **Test Configuration**
   ```bash
   python test_twilio_setup.py
   ```

### Step 3: Set Up ngrok (for webhook testing)

1. **Install ngrok**
   - Download from [ngrok.com](https://ngrok.com/download)
   - Or use: `pip install pyngrok`

2. **Run Setup Script**
   ```bash
   python setup_ngrok.py
   ```

3. **Update Twilio Webhook**
   - Copy the ngrok URL from the script output
   - In Twilio Console, update your phone number's webhook URL
   - Set HTTP method to POST

### Step 4: Run the Application

1. **Start VOCA with Twilio**
   ```bash
   python src/main.py
   ```

2. **Using the GUI**
   - Go to "Twilio Calls" tab
   - Click "Start Twilio Server"
   - Test by calling your Twilio number

## Key Features Implemented

### 1. Twilio Voice Handler (`src/voca/twilio_voice.py`)
- **Incoming Call Processing**: Handles Twilio webhooks
- **Outbound Calling**: Make calls programmatically
- **Call Management**: Track active calls, hang up calls
- **Audio Streaming**: Bridge between Twilio and VOCA

### 2. Enhanced WebRTC Client (`src/voca/webrtc.py`)
- **TwilioWebRTCClient**: Specialized for Twilio integration
- **Audio Processing**: Real-time audio handling
- **SDP Negotiation**: WebRTC connection management

### 3. Configuration Management (`src/voca/twilio_config.py`)
- **Environment Variables**: Secure credential management
- **Validation**: Check configuration completeness
- **Webhook URLs**: Dynamic URL generation

### 4. GUI Integration (`src/voca/gui/app.py`)
- **Tabbed Interface**: Separate local and Twilio controls
- **Call Controls**: Start server, make calls, hang up
- **Status Monitoring**: Real-time call status display
- **Error Handling**: User-friendly error messages

## How It Works

### Incoming Calls
1. Someone calls your Twilio number
2. Twilio sends webhook to your server
3. Your server responds with TwiML to start audio streaming
4. Audio is processed by VOCA orchestrator
5. AI response is sent back through Twilio

### Outbound Calls
1. User enters phone number in GUI
2. Application calls Twilio API to initiate call
3. Twilio calls the target number
4. When answered, audio is streamed to your server
5. VOCA processes the conversation

### Audio Processing Flow
```
Twilio Audio → WebRTC → AudioSinkTrack → VOCA Orchestrator
                                                      ↓
Twilio Audio ← WebRTC ← TTS Output ← VOCA Orchestrator
```

## Testing Your Setup

### 1. Validate Configuration
```bash
python test_twilio_setup.py
```

### 2. Test Incoming Calls
1. Start the application
2. Start Twilio server
3. Call your Twilio number from any phone
4. Speak to test the AI assistant

### 3. Test Outbound Calls
1. Enter a phone number in the GUI
2. Click "Make Call"
3. Answer the call to test the conversation

## Troubleshooting

### Common Issues

1. **"Twilio not configured" Error**
   - Check your .env file
   - Ensure all required variables are set
   - Run the test script to validate

2. **Webhook Not Receiving Calls**
   - Check ngrok is running
   - Verify webhook URL in Twilio Console
   - Check firewall settings

3. **Audio Not Working**
   - Ensure microphone permissions
   - Check audio device settings
   - Verify VOSK model is loaded

4. **Call Drops Immediately**
   - Check TwiML response format
   - Verify webhook server is running
   - Check Twilio logs in console

### Debug Mode
Enable detailed logging by modifying the logging level in `src/main.py`:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Advanced Configuration

### Custom TwiML Responses
Modify the TwiML in `twilio_voice.py` to customize call behavior:
- Add custom greetings
- Implement call routing
- Add hold music
- Customize voice settings

### Audio Quality Settings
Adjust audio processing parameters in `webrtc.py`:
- Sample rate (default: 16000 Hz)
- Audio format (default: 16-bit PCM)
- Buffer sizes

### Call Timeout Settings
Modify call duration limits in `twilio_voice.py`:
- Maximum call length
- Silence detection timeouts
- Connection timeouts

## Security Considerations

1. **Environment Variables**: Never commit .env file
2. **Webhook Security**: Validate Twilio signatures
3. **Rate Limiting**: Implement call rate limits
4. **Authentication**: Add user authentication if needed

## Production Deployment

### 1. Use HTTPS
- Replace ngrok with proper HTTPS endpoint
- Use services like Heroku, AWS, or DigitalOcean

### 2. Database Integration
- Store call logs
- Track usage statistics
- Implement user management

### 3. Monitoring
- Add logging and monitoring
- Set up alerts for failures
- Monitor call quality

## Next Steps

1. **Test the basic integration**
2. **Customize the AI responses**
3. **Add call recording features**
4. **Implement call analytics**
5. **Add multi-language support**

## Support

If you encounter issues:
1. Check the logs in the application
2. Run the test script
3. Verify Twilio Console logs
4. Check ngrok status

The integration is now complete and ready for testing!
