# Twilio Setup Guide for VOCA

## 1. Environment Variables Setup

Create a `.env` file in your project root with the following variables:

```env
# Twilio Configuration
# Get these from your Twilio Console (https://console.twilio.com/)
TWILIO_ACCOUNT_SID=your_account_sid_here
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
TWILIO_WEBHOOK_URL=http://your-ngrok-url.ngrok.io/webhook/voice

# Optional: For advanced features
TWILIO_API_KEY_SID=your_api_key_sid_here
TWILIO_API_KEY_SECRET=your_api_key_secret_here
```

## 2. How to Get Your Twilio Credentials

### Step 1: Create Twilio Account
1. Go to [Twilio Console](https://console.twilio.com/)
2. Sign up for a free account
3. Verify your phone number

### Step 2: Get Account SID and Auth Token
1. In Twilio Console, go to **Account Info** section
2. Copy your **Account SID** and **Auth Token**
3. Add these to your `.env` file

### Step 3: Get Your Phone Number
1. Go to **Phone Numbers > Manage > Active numbers**
2. Copy your Twilio phone number (starts with +1)
3. Add this to your `.env` file

### Step 4: Set Up Webhook URL (for incoming calls)
1. Install ngrok: `pip install pyngrok` or download from [ngrok.com](https://ngrok.com/)
2. Run: `ngrok http 5000` (this exposes your local server)
3. Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`)
4. Add this URL + `/webhook/voice` to your `.env` file

> 📖 For more details about ngrok and why it's needed, see [NGROK_EXPLANATION.md](NGROK_EXPLANATION.md)

## 3. Configure Twilio Phone Number
1. In Twilio Console, go to **Phone Numbers > Manage > Active numbers**
2. Click on your phone number
3. In the **Voice** section:
   - Set **Webhook** to: `http://your-ngrok-url.ngrok.io/webhook/voice`
   - Set **HTTP Method** to: `POST`
4. Save configuration

## 4. Testing Your Setup
1. Run: `python -m pip install -r requirements.txt`
2. Run: `python src/main.py`
3. Test by calling your Twilio number from any phone
4. The call should be answered by your VOCA assistant
