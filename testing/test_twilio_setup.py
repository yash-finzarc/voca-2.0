#!/usr/bin/env python3
"""
Test script to validate Twilio setup and configuration.
"""
import os
import sys
from dotenv import load_dotenv

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from voca.twilio_config import get_twilio_config
from voca.twilio_voice import TwilioCallManager
from voca.orchestrator import VocaOrchestrator


def test_environment_setup():
    """Test if environment variables are properly set."""
    print("🔍 Testing environment setup...")
    
    load_dotenv()
    
    required_vars = [
        'TWILIO_ACCOUNT_SID',
        'TWILIO_AUTH_TOKEN', 
        'TWILIO_PHONE_NUMBER'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("Please create a .env file with the required variables.")
        return False
    else:
        print("✅ All required environment variables found")
        return True


def test_twilio_config():
    """Test Twilio configuration validation."""
    print("\n🔍 Testing Twilio configuration...")
    
    config = get_twilio_config()
    if config.validate():
        print("✅ Twilio configuration is valid")
        print(f"   Account SID: {config.account_sid[:8]}...")
        print(f"   Phone Number: {config.phone_number}")
        return True
    else:
        print("❌ Twilio configuration is invalid")
        return False


def test_twilio_connection():
    """Test connection to Twilio API."""
    print("\n🔍 Testing Twilio API connection...")
    
    try:
        from twilio.rest import Client
        config = get_twilio_config()
        client = Client(config.account_sid, config.auth_token)
        
        # Test API connection by fetching account info
        account = client.api.accounts(config.account_sid).fetch()
        print(f"✅ Connected to Twilio API")
        print(f"   Account Name: {account.friendly_name}")
        print(f"   Account Status: {account.status}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to connect to Twilio API: {e}")
        return False


def test_webhook_url():
    """Test webhook URL configuration."""
    print("\n🔍 Testing webhook URL...")
    
    config = get_twilio_config()
    webhook_url = config.get_webhook_url()
    print(f"Webhook URL: {webhook_url}")
    
    if webhook_url.startswith('http://localhost'):
        print("⚠️  Warning: Using localhost URL. You'll need ngrok for external access.")
        print("   Install ngrok: https://ngrok.com/")
        print("   Run: ngrok http 5000")
        print("   Update TWILIO_WEBHOOK_URL in your .env file")
    
    return True


def test_voca_integration():
    """Test VOCA orchestrator integration."""
    print("\n🔍 Testing VOCA integration...")
    
    try:
        orchestrator = VocaOrchestrator()
        print("✅ VOCA orchestrator created successfully")
        
        # Test Twilio manager creation
        twilio_manager = TwilioCallManager(orchestrator)
        print("✅ Twilio call manager created successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ VOCA integration failed: {e}")
        return False


def main():
    """Run all tests."""
    print("🚀 Twilio Setup Validation for VOCA\n")
    
    tests = [
        test_environment_setup,
        test_twilio_config,
        test_twilio_connection,
        test_webhook_url,
        test_voca_integration
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Your Twilio setup is ready.")
        print("\nNext steps:")
        print("1. Run: python src/main.py")
        print("2. Go to 'Twilio Calls' tab")
        print("3. Click 'Start Twilio Server'")
        print("4. Test by calling your Twilio number")
    else:
        print("❌ Some tests failed. Please fix the issues above.")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


