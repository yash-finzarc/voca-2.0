#!/usr/bin/env python3
"""
Simple ngrok setup script for Windows
"""
import subprocess
import time
import requests
import json
import sys
import os

def start_ngrok():
    """Start ngrok and return the public URL."""
    print("🚀 Starting ngrok tunnel...")
    
    try:
        # Start ngrok in background
        process = subprocess.Popen(
            ["./ngrok.exe", "http", "5000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        print("⏳ Waiting for ngrok to start...")
        time.sleep(5)  # Wait for ngrok to start
        
        # Try to get the URL from ngrok API
        try:
            response = requests.get("http://localhost:4040/api/tunnels", timeout=5)
            if response.status_code == 200:
                tunnels = response.json()
                for tunnel in tunnels.get('tunnels', []):
                    if tunnel.get('proto') == 'https':
                        public_url = tunnel.get('public_url')
                        if public_url:
                            print(f"✅ ngrok tunnel started: {public_url}")
                            return public_url, process
        except Exception as e:
            print(f"⚠️  Could not get URL from API: {e}")
        
        # Alternative: try to parse ngrok output
        print("🔍 Trying to get URL from ngrok output...")
        time.sleep(2)
        
        # Check if ngrok is running
        try:
            response = requests.get("http://localhost:4040", timeout=2)
            if response.status_code == 200:
                print("✅ ngrok is running!")
                print("📋 Please:")
                print("1. Open http://localhost:4040 in your browser")
                print("2. Copy the HTTPS URL (starts with https://)")
                print("3. Update your .env file with: TWILIO_WEBHOOK_URL=https://your-url.ngrok.io/webhook/voice")
                return None, process
        except:
            pass
        
        print("❌ Could not start ngrok properly")
        return None, None
        
    except Exception as e:
        print(f"❌ Failed to start ngrok: {e}")
        return None, None

def update_env_file(webhook_url):
    """Update .env file with webhook URL."""
    if not webhook_url:
        return False
    
    webhook_url_with_path = f"{webhook_url}/webhook/voice"
    
    try:
        # Read existing .env file
        with open('.env', 'r') as f:
            lines = f.readlines()
        
        # Update webhook URL
        updated = False
        for i, line in enumerate(lines):
            if line.startswith('TWILIO_WEBHOOK_URL='):
                lines[i] = f'TWILIO_WEBHOOK_URL={webhook_url_with_path}\n'
                updated = True
                break
        
        if not updated:
            lines.append(f'TWILIO_WEBHOOK_URL={webhook_url_with_path}\n')
        
        # Write back to file
        with open('.env', 'w') as f:
            f.writelines(lines)
        
        print(f"✅ Updated .env file with webhook URL: {webhook_url_with_path}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to update .env file: {e}")
        return False

def main():
    """Main setup function."""
    print("🔧 Simple ngrok Setup for Twilio Webhooks\n")
    
    # Check if ngrok exists
    if not os.path.exists("ngrok.exe"):
        print("❌ ngrok.exe not found in current directory")
        print("Please run: python install_ngrok_windows.py")
        return 1
    
    # Start ngrok
    public_url, ngrok_process = start_ngrok()
    
    if public_url:
        # Update .env file
        if update_env_file(public_url):
            print("\n🎉 Setup complete!")
            print(f"Your webhook URL is: {public_url}/webhook/voice")
            print("\nNext steps:")
            print("1. Update your Twilio phone number webhook URL in the Twilio Console")
            print("2. Run: python src/main.py")
            print("3. Test by calling +1XXXXXXXXXX")
        
        print("\nPress Ctrl+C to stop ngrok when done testing")
        try:
            # Keep ngrok running
            ngrok_process.wait()
        except KeyboardInterrupt:
            print("\n🛑 Stopping ngrok...")
            ngrok_process.terminate()
            ngrok_process.wait()
            print("✅ ngrok stopped")
    else:
        print("\n⚠️  ngrok started but URL not detected")
        print("Please check http://localhost:4040 for the URL")
        print("Then update your .env file manually")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
