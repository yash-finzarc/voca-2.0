#!/usr/bin/env python3
"""
Test Twilio integration without webhooks
"""
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from voca.twilio_config import get_twilio_config
from twilio.rest import Client

def test_outbound_call():
    """Test making an outbound call."""
    print("🧪 Testing Twilio Outbound Call\n")
    
    config = get_twilio_config()
    
    if not config.validate():
        print("❌ Twilio configuration is invalid")
        return 1
    
    try:
        client = Client(config.account_sid, config.auth_token)
        
        # Get phone number to call
        phone_number = input("Enter phone number to call (e.g., +1234567890): ").strip()
        
        if not phone_number:
            print("❌ No phone number provided")
            return 1
        
        print(f"📞 Making call to {phone_number}...")
        
        # Make the call
        call = client.calls.create(
            to=phone_number,
            from_=config.phone_number,
            twiml='<Response><Say>Hello! This is a test call from VOCA AI assistant. The integration is working!</Say></Response>'
        )
        
        print(f"✅ Call initiated successfully!")
        print(f"Call SID: {call.sid}")
        print(f"Status: {call.status}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Failed to make call: {e}")
        return 1

def test_account_info():
    """Test Twilio account connection."""
    print("🧪 Testing Twilio Account Connection\n")
    
    config = get_twilio_config()
    
    if not config.validate():
        print("❌ Twilio configuration is invalid")
        return 1
    
    try:
        client = Client(config.account_sid, config.auth_token)
        
        # Get account info
        account = client.api.accounts(config.account_sid).fetch()
        
        print(f"✅ Connected to Twilio successfully!")
        print(f"Account Name: {account.friendly_name}")
        print(f"Account Status: {account.status}")
        print(f"Account Type: {account.type}")
        
        # Get phone numbers
        incoming_phone_numbers = client.incoming_phone_numbers.list()
        print(f"\n📱 Phone Numbers:")
        for number in incoming_phone_numbers:
            print(f"  - {number.phone_number} (SID: {number.sid})")
        
        return 0
        
    except Exception as e:
        print(f"❌ Failed to connect to Twilio: {e}")
        return 1

def main():
    """Main test function."""
    print("🚀 Twilio Integration Test (Without Webhooks)\n")
    
    print("Choose test:")
    print("1. Test account connection")
    print("2. Test outbound call")
    print("3. Both")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        return test_account_info()
    elif choice == "2":
        return test_outbound_call()
    elif choice == "3":
        if test_account_info() == 0:
            print("\n" + "="*50 + "\n")
            return test_outbound_call()
        return 1
    else:
        print("❌ Invalid choice")
        return 1
    
if __name__ == "__main__":
    sys.exit(main())


