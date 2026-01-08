#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv
from twilio.rest import Client
import httpx

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'src'))

env_path = project_root / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)

from src.voca.config import Config
from src.voca.Twilio.twilio_config import get_twilio_config

PHONE_NUMBER = "+919540465263"

async def test_ultravox_call():
    print(f"Testing Ultravox with Twilio - Calling {PHONE_NUMBER}...")
    print(f"⚠️  Make sure your FastAPI server is running to handle WebSocket connections\n")
    
    twilio_config = get_twilio_config()
    if not twilio_config.validate():
        print("❌ Twilio credentials missing or invalid")
        print(f"   Account SID: {'✅' if twilio_config.account_sid else '❌'}")
        print(f"   Auth Token: {'✅' if twilio_config.auth_token else '❌'}")
        print(f"   Phone Number: {'✅' if twilio_config.phone_number else '❌'}")
        return
    
    print("✅ Twilio credentials validated")
    
    api_key = Config.ultravox_api_key
    if not api_key:
        print("❌ ULTRAVOX_API_KEY not found in .env")
        return
    
    print(f"✅ Ultravox API Key: {api_key[:10]}...")
    
    try:
        client = Client(twilio_config.account_sid, twilio_config.auth_token)
        
        webhook_url = twilio_config.get_webhook_url()
        base_url = webhook_url.replace('/webhook/voice', '').replace('/outbound', '')
        outbound_url = f"{base_url}/outbound"
        method = 'POST'
        
        print(f"📞 Initiating call to {PHONE_NUMBER}...")
        print(f"   From: {twilio_config.phone_number}")
        print(f"   Webhook URL: {outbound_url} (using direct webhook, not TwiML Bin)")
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as http_client:
                response = await http_client.get(f"{base_url}/server-info")
                if response.status_code == 200:
                    print(f"✅ Server is accessible at {base_url}")
                else:
                    print(f"⚠️  Server returned status {response.status_code}")
        except Exception as e:
            print(f"⚠️  Could not verify server accessibility: {e}")
            print(f"   Proceeding anyway - make sure server is running at {base_url}")
        
        print()
        
        call = client.calls.create(
            to=PHONE_NUMBER,
            from_=twilio_config.phone_number,
            url=outbound_url,
            method=method
        )
        
        print(f"✅ Call initiated successfully!")
        print(f"   Call SID: {call.sid}")
        print(f"   Status: {call.status}")
        print(f"\n📱 The call will connect to Ultravox via WebSocket")
        print(f"   Answer the phone to test the AI assistant")
        print(f"\n⏳ Monitoring call status (Press Ctrl+C to exit)...\n")
        
        call_sid = call.sid
        last_status = call.status
        
        while True:
            await asyncio.sleep(2)
            
            try:
                call = client.calls(call_sid).fetch()
                current_status = call.status
                
                if current_status != last_status:
                    print(f"📞 Call status: {last_status} → {current_status}")
                    last_status = current_status
                
                if current_status in ['completed', 'busy', 'no-answer', 'failed', 'canceled']:
                    print(f"\n✅ Call ended with status: {current_status}")
                    if hasattr(call, 'duration') and call.duration:
                        print(f"   Duration: {call.duration} seconds")
                    break
                    
            except KeyboardInterrupt:
                print(f"\n\n⚠️  Monitoring stopped by user")
                print(f"   Call SID: {call_sid}")
                print(f"   Call may still be active - check Twilio console")
                break
            except Exception as e:
                print(f"⚠️  Error checking call status: {e}")
                await asyncio.sleep(5)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ultravox_call())

