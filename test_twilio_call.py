#!/usr/bin/env python3
"""
Simple test script to make Twilio calls directly
This bypasses the GUI import issues and tests the core functionality
"""

import os
import sys
from twilio.rest import Client
from src.voca.twilio_config import get_twilio_config

def make_test_call():
    """Make a test call to verify the integration is working"""
    print("🚀 Making Test Twilio Call...")
    
    try:
        # Get Twilio configuration
        config = get_twilio_config()
        client = Client(config.account_sid, config.auth_token)
        
        # Get phone number from user
        phone_number = input("Enter your phone number (with country code, e.g., +91xxxxxxxxxx): ")
        
        # Ensure phone number has country code
        if not phone_number.startswith('+'):
            if phone_number.startswith('91'):
                phone_number = '+' + phone_number
            else:
                phone_number = '+91' + phone_number
        
        print(f"📞 Calling {phone_number}...")
        
        # Make the call
        call = client.calls.create(
            to=phone_number,
            from_=config.phone_number,
            url=f"https://erectly-cigarless-lionel.ngrok-free.dev/outbound",
            method='POST'
        )
        
        print(f"✅ Call initiated successfully!")
        print(f"   Call SID: {call.sid}")
        print(f"   Status: {call.status}")
        print(f"   From: {config.phone_number}")
        print(f"   To: {phone_number}")
        
        print("\n🎯 What should happen:")
        print("1. Your phone should ring")
        print("2. Answer the call")
        print("3. You should hear: 'Hello! This is VOCA calling. How can I help you today?'")
        print("4. Speak to the AI and get responses")
        
        return call.sid
        
    except Exception as e:
        print(f"❌ Error making call: {e}")
        return None

def check_call_status(call_sid):
    """Check the status of a call"""
    try:
        config = get_twilio_config()
        client = Client(config.account_sid, config.auth_token)
        
        call = client.calls(call_sid).fetch()
        print(f"📊 Call Status: {call.status}")
        print(f"   Duration: {call.duration} seconds")
        print(f"   Direction: {call.direction}")
        
        return call.status
        
    except Exception as e:
        print(f"❌ Error checking call status: {e}")
        return None

if __name__ == "__main__":
    print("🎯 Twilio VOCA Call Test")
    print("=" * 40)
    
    # Make a test call
    call_sid = make_test_call()
    
    if call_sid:
        print(f"\n📋 Call SID: {call_sid}")
        print("\n🔍 To check call status later, run:")
        print(f"python test_twilio_call.py --status {call_sid}")
        
        # Check status immediately
        print("\n📊 Checking initial status...")
        check_call_status(call_sid)
    
    print("\n" + "=" * 40)
    print("🎉 Test completed!")
