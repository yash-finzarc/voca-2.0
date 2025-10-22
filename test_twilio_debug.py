#!/usr/bin/env python3
"""
Debug script for Twilio VOCA integration issues
This script helps identify what's causing the "application error has occurred" message
"""

import requests
import json
from src.voca.twilio_config import get_twilio_config
from src.voca.llm_client import GeminiClient
from src.voca.config import Config

def test_twilio_endpoints():
    """Test all Twilio endpoints to verify they're working"""
    print("🔍 Testing Twilio Endpoints...")
    
    # Get the current ngrok URL (you'll need to update this)
    base_url = "https://erectly-cigarless-lionel.ngrok-free.dev"
    
    # Test endpoints
    endpoints = [
        "/webhook/voice",
        "/outbound", 
        "/call/status"
    ]
    
    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        print(f"\n📡 Testing {endpoint}...")
        
        # Test with sample Twilio webhook data
        test_data = {
            "CallSid": "test123",
            "From": "+1234567890",
            "To": "+1987654321",
            "CallStatus": "ringing"
        }
        
        try:
            response = requests.post(url, data=test_data, timeout=10)
            print(f"   Status: {response.status_code}")
            print(f"   Content-Type: {response.headers.get('content-type', 'unknown')}")
            print(f"   Response Length: {len(response.text)} chars")
            
            if response.status_code == 200:
                print("   ✅ Endpoint working")
                # Check if response is valid TwiML
                if 'xml' in response.headers.get('content-type', ''):
                    print("   ✅ Valid TwiML response")
                else:
                    print("   ⚠️  Response not TwiML")
                    print(f"   Response: {response.text[:200]}...")
            else:
                print(f"   ❌ Endpoint failed: {response.text[:200]}...")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")

def test_ai_components():
    """Test AI components separately"""
    print("\n🤖 Testing AI Components...")
    
    try:
        # Test LLM
        print("   Testing LLM...")
        llm = GeminiClient()
        response = llm.complete_chat([{"role": "user", "content": "Hello, say 'AI test successful'"}])
        print(f"   ✅ LLM Response: {response[:50]}...")
        
        # Test TTS
        print("   Testing TTS...")
        from src.voca.tts import CoquiTTS
        tts = CoquiTTS()
        print("   ✅ TTS loaded successfully")
        
        # Test STT
        print("   Testing STT...")
        from src.voca.stt import FasterWhisperSTT
        stt = FasterWhisperSTT()
        print("   ✅ STT loaded successfully")
        
    except Exception as e:
        print(f"   ❌ AI Component Error: {e}")

def create_simple_twiml():
    """Create a simple TwiML response for testing"""
    print("\n📝 Creating Simple TwiML Response...")
    
    # Simple TwiML without importing VoiceResponse
    twiml = '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Hello! This is a test message from VOCA.</Say>
    <Hangup/>
</Response>'''
    
    print(f"   TwiML: {twiml}")
    return twiml

def test_twilio_credentials():
    """Test Twilio credentials"""
    print("\n🔐 Testing Twilio Credentials...")
    
    try:
        config = get_twilio_config()
        print(f"   Account SID: {config.account_sid[:10]}...")
        print(f"   Phone Number: {config.phone_number}")
        print(f"   Webhook URL: {config.webhook_url}")
        print("   ✅ Credentials loaded")
        
        # Test Twilio client
        from twilio.rest import Client
        client = Client(config.account_sid, config.auth_token)
        
        # Try to get account info
        account = client.api.accounts(config.account_sid).fetch()
        print(f"   ✅ Twilio connection successful")
        print(f"   Account Status: {account.status}")
        
    except Exception as e:
        print(f"   ❌ Twilio Error: {e}")

def create_debug_webhook():
    """Create a debug webhook that logs everything"""
    print("\n🐛 Creating Debug Webhook...")
    
    debug_code = '''
from flask import Flask, request, Response
from twilio.twiml import VoiceResponse
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

@app.route('/debug/webhook', methods=['POST'])
def debug_webhook():
    print("\\n=== DEBUG WEBHOOK CALLED ===")
    print(f"Headers: {dict(request.headers)}")
    print(f"Form Data: {dict(request.form)}")
    print(f"JSON Data: {request.get_json()}")
    
    # Create simple TwiML
    response = VoiceResponse()
    response.say("Debug test successful. This should work.")
    response.hangup()
    
    return Response(str(response), mimetype='text/xml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
'''
    
    with open('debug_webhook.py', 'w') as f:
        f.write(debug_code)
    
    print("   ✅ Debug webhook created as 'debug_webhook.py'")
    print("   Run: python debug_webhook.py")
    print("   Test URL: http://localhost:5001/debug/webhook")

if __name__ == "__main__":
    print("🚀 Twilio VOCA Debug Script")
    print("=" * 50)
    
    # Run all tests
    test_twilio_credentials()
    test_ai_components()
    create_simple_twiml()
    test_twilio_endpoints()
    create_debug_webhook()
    
    print("\n" + "=" * 50)
    print("🎯 Debug Summary:")
    print("1. Check if all AI components load")
    print("2. Verify Twilio credentials")
    print("3. Test webhook endpoints")
    print("4. Use debug webhook for detailed logging")
    print("\nNext steps:")
    print("- Run: python debug_webhook.py")
    print("- Update Twilio webhook URL to: https://your-ngrok-url.ngrok-free.dev/debug/webhook")
    print("- Make a test call and check logs")
