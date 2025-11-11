#!/usr/bin/env python3
"""
Quick test to verify FastAPI server is working correctly
"""
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

try:
    from fastapi import FastAPI
    from src.voca.twilio_voice import TwilioVoiceHandler
    from src.voca.orchestrator import VocaOrchestrator
    import uvicorn
    
    print("✅ FastAPI import successful")
    print("✅ TwilioVoiceHandler import successful")
    
    # Test creating a FastAPI app
    app = FastAPI(title="Test Server")
    
    @app.get("/test")
    async def test_endpoint():
        return {"status": "FastAPI is working!"}
    
    print("✅ FastAPI app created successfully")
    print("\n🎉 FastAPI migration is working correctly!")
    print("\nTo start the server, run:")
    print("  python -m src.voca.twilio_app")
    print("\nOr use the startup script:")
    print("  python start_twilio_voca.py")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("\nPlease install dependencies:")
    print("  pip install -r requirements.txt")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)



