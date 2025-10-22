#!/usr/bin/env python3
"""
Quick test to verify VOCA components are working
"""
import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """Test if all modules can be imported."""
    print("🧪 Testing module imports...")
    
    try:
        from voca.twilio_config import get_twilio_config
        print("✅ Twilio config imported")
        
        from voca.twilio_voice import TwilioCallManager
        print("✅ Twilio voice imported")
        
        from voca.orchestrator import VocaOrchestrator
        print("✅ Orchestrator imported")
        
        from voca.stt import build_stt
        print("✅ STT module imported")
        
        from voca.tts import CoquiTTS
        print("✅ TTS module imported")
        
        return True
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

def test_stt():
    """Test STT functionality."""
    print("\n🧪 Testing STT...")
    
    try:
        from voca.stt import build_stt
        stt = build_stt()
        print("✅ STT model loaded successfully")
        return True
        
    except Exception as e:
        print(f"❌ STT failed: {e}")
        return False

def test_twilio_config():
    """Test Twilio configuration."""
    print("\n🧪 Testing Twilio configuration...")
    
    try:
        from voca.twilio_config import get_twilio_config
        config = get_twilio_config()
        
        if config.validate():
            print("✅ Twilio configuration is valid")
            print(f"   Account SID: {config.account_sid[:8]}...")
            print(f"   Phone Number: {config.phone_number}")
            return True
        else:
            print("❌ Twilio configuration is invalid")
            return False
            
    except Exception as e:
        print(f"❌ Twilio config failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 VOCA Component Test\n")
    
    tests = [
        test_imports,
        test_stt,
        test_twilio_config
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All components are working!")
        print("\nYour VOCA application is ready to use!")
        print("The GUI should be running - check for the VOCA window.")
    else:
        print("❌ Some components failed. Please check the errors above.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
