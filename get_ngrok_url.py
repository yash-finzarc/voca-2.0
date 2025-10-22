#!/usr/bin/env python3
"""
Get the current ngrok URL for Twilio webhook configuration
"""

import subprocess
import json
import time

def start_ngrok():
    """Start ngrok tunnel"""
    print("🚀 Starting ngrok tunnel...")
    try:
        # Start ngrok in background
        subprocess.Popen(['ngrok', 'http', '5000'], 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL)
        
        # Wait for ngrok to start
        time.sleep(3)
        
        # Get the tunnel URL
        import requests
        response = requests.get('http://localhost:4040/api/tunnels')
        data = response.json()
        
        if data['tunnels']:
            public_url = data['tunnels'][0]['public_url']
            print(f"✅ ngrok URL: {public_url}")
            return public_url
        else:
            print("❌ No tunnels found")
            return None
            
    except Exception as e:
        print(f"❌ Error starting ngrok: {e}")
        return None

def get_current_ngrok_url():
    """Get current ngrok URL"""
    try:
        import requests
        response = requests.get('http://localhost:4040/api/tunnels')
        data = response.json()
        
        if data['tunnels']:
            public_url = data['tunnels'][0]['public_url']
            print(f"✅ Current ngrok URL: {public_url}")
            return public_url
        else:
            print("❌ No active tunnels found")
            return None
            
    except Exception as e:
        print(f"❌ Error getting ngrok URL: {e}")
        return None

if __name__ == "__main__":
    print("🔍 Checking ngrok status...")
    
    # Try to get existing URL first
    url = get_current_ngrok_url()
    
    if not url:
        # Start new tunnel if none exists
        url = start_ngrok()
    
    if url:
        print(f"\n🎯 Use this URL in Twilio Console:")
        print(f"Webhook URL: {url}/webhook/voice")
        print(f"\n📋 Update your Twilio Console with:")
        print(f"- A call comes in: {url}/webhook/voice")
        print(f"- Primary handler fails: {url}/webhook/voice") 
        print(f"- Call status changes: {url}/call/status")
    else:
        print("❌ Could not get ngrok URL")
