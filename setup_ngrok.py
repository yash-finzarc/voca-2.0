#!/usr/bin/env python3
"""
Setup script to help configure ngrok for Twilio webhooks.
"""
import subprocess
import sys
import time
import requests
import json
from urllib.parse import urlparse


def check_ngrok_installed():
    """Check if ngrok is installed."""
    try:
        result = subprocess.run(['ngrok', 'version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ ngrok is installed: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    
    print("❌ ngrok is not installed")
    print("Please install ngrok from: https://ngrok.com/download")
    return False


def start_ngrok_tunnel(port=5000):
    """Start ngrok tunnel for the specified port."""
    print(f"🚀 Starting ngrok tunnel on port {port}...")
    
    try:
        # Start ngrok in background
        process = subprocess.Popen(
            ['ngrok', 'http', str(port), '--log=stdout'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait a moment for ngrok to start
        time.sleep(3)
        
        # Get the public URL
        try:
            response = requests.get('http://localhost:4040/api/tunnels')
            if response.status_code == 200:
                tunnels = response.json()
                for tunnel in tunnels.get('tunnels', []):
                    if tunnel.get('proto') == 'https':
                        public_url = tunnel.get('public_url')
                        if public_url:
                            print(f"✅ ngrok tunnel started: {public_url}")
                            return public_url, process
        except Exception as e:
            print(f"⚠️  Could not get ngrok URL automatically: {e}")
        
        print("⚠️  ngrok started but URL not detected automatically")
        print("Please check ngrok web interface at: http://localhost:4040")
        return None, process
        
    except Exception as e:
        print(f"❌ Failed to start ngrok: {e}")
        return None, None


def update_env_file(webhook_url):
    """Update .env file with webhook URL."""
    env_file = '.env'
    webhook_url_with_path = f"{webhook_url}/webhook/voice"
    
    try:
        # Read existing .env file
        env_content = ""
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                env_content = f.read()
        
        # Update or add webhook URL
        lines = env_content.split('\n')
        updated = False
        
        for i, line in enumerate(lines):
            if line.startswith('TWILIO_WEBHOOK_URL='):
                lines[i] = f'TWILIO_WEBHOOK_URL={webhook_url_with_path}'
                updated = True
                break
        
        if not updated:
            lines.append(f'TWILIO_WEBHOOK_URL={webhook_url_with_path}')
        
        # Write back to file
        with open(env_file, 'w') as f:
            f.write('\n'.join(lines))
        
        print(f"✅ Updated .env file with webhook URL: {webhook_url_with_path}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to update .env file: {e}")
        return False


def main():
    """Main setup function."""
    print("🔧 ngrok Setup for Twilio Webhooks\n")
    
    # Check if ngrok is installed
    if not check_ngrok_installed():
        return 1
    
    # Start ngrok tunnel
    public_url, ngrok_process = start_ngrok_tunnel()
    
    if not public_url:
        print("❌ Failed to start ngrok tunnel")
        return 1
    
    # Update .env file
    if update_env_file(public_url):
        print("\n🎉 Setup complete!")
        print(f"Your webhook URL is: {public_url}/webhook/voice")
        print("\nNext steps:")
        print("1. Update your Twilio phone number webhook URL in the Twilio Console")
        print("2. Run: python src/main.py")
        print("3. Test by calling your Twilio number")
        print("\nPress Ctrl+C to stop ngrok when done testing")
        
        try:
            # Keep ngrok running
            ngrok_process.wait()
        except KeyboardInterrupt:
            print("\n🛑 Stopping ngrok...")
            ngrok_process.terminate()
            ngrok_process.wait()
            print("✅ ngrok stopped")
    
    return 0


if __name__ == "__main__":
    import os
    sys.exit(main())
