#!/usr/bin/env python3
"""
ngrok setup using pyngrok package
"""
import sys
import time
from pyngrok import ngrok

def setup_ngrok():
    """Set up ngrok tunnel using pyngrok."""
    print("🚀 Setting up ngrok tunnel using pyngrok...")
    
    try:
        # Create tunnel
        tunnel = ngrok.connect(5000)
        public_url = tunnel.public_url
        
        print(f"✅ ngrok tunnel created: {public_url}")
        
        # Update .env file
        webhook_url = f"{public_url}/webhook/voice"
        
        try:
            with open('.env', 'r') as f:
                lines = f.readlines()
            
            # Update webhook URL
            updated = False
            for i, line in enumerate(lines):
                if line.startswith('TWILIO_WEBHOOK_URL='):
                    lines[i] = f'TWILIO_WEBHOOK_URL={webhook_url}\n'
                    updated = True
                    break
            
            if not updated:
                lines.append(f'TWILIO_WEBHOOK_URL={webhook_url}\n')
            
            # Write back to file
            with open('.env', 'w') as f:
                f.writelines(lines)
            
            print(f"✅ Updated .env file with webhook URL: {webhook_url}")
            
        except Exception as e:
            print(f"⚠️  Could not update .env file: {e}")
            print(f"Please manually add: TWILIO_WEBHOOK_URL={webhook_url}")
        
        print("\n🎉 Setup complete!")
        print(f"Your webhook URL is: {webhook_url}")
        print("\nNext steps:")
        print("1. Update your Twilio phone number webhook URL in the Twilio Console")
        print("2. Run: python src/main.py")
        print("3. Test by calling +1XXXXXXXXXX")
        print("\nPress Ctrl+C to stop ngrok when done testing")
        
        try:
            # Keep tunnel alive
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping ngrok...")
            ngrok.disconnect(tunnel.public_url)
            ngrok.kill()
            print("✅ ngrok stopped")
        
        return 0
        
    except Exception as e:
        print(f"❌ Failed to create ngrok tunnel: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(setup_ngrok())
