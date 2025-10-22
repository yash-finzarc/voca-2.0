#!/usr/bin/env python3
"""
Alternative tunneling setup using localtunnel
"""
import subprocess
import sys
import time
import requests
import json

def setup_localtunnel():
    """Set up localtunnel as an alternative to ngrok."""
    print("🚀 Setting up localtunnel (ngrok alternative)...")
    
    try:
        # Install localtunnel if not available
        try:
            subprocess.run(["npx", "--version"], check=True, capture_output=True)
        except:
            print("❌ npm/npx not found. Please install Node.js first.")
            print("Download from: https://nodejs.org/")
            return 1
        
        print("📦 Installing localtunnel...")
        subprocess.run(["npm", "install", "-g", "localtunnel"], check=True)
        
        print("🚀 Starting localtunnel...")
        process = subprocess.Popen(
            ["npx", "localtunnel", "--port", "5000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for tunnel to start
        time.sleep(5)
        
        # Try to get the URL from localtunnel output
        try:
            stdout, stderr = process.communicate(timeout=2)
            if stdout:
                for line in stdout.split('\n'):
                    if 'https://' in line:
                        public_url = line.strip()
                        print(f"✅ localtunnel started: {public_url}")
                        
                        # Update .env file
                        webhook_url = f"{public_url}/webhook/voice"
                        update_env_file(webhook_url)
                        
                        print(f"\n🎉 Setup complete!")
                        print(f"Your webhook URL is: {webhook_url}")
                        print("\nNext steps:")
                        print("1. Update your Twilio phone number webhook URL in the Twilio Console")
                        print("2. Run: python src/main.py")
                        print("3. Test by calling +1XXXXXXXXXX")
                        
                        return 0
        except:
            pass
        
        print("⚠️  localtunnel started but URL not detected")
        print("Please check the terminal output for the URL")
        return 1
        
    except Exception as e:
        print(f"❌ Failed to setup localtunnel: {e}")
        return 1

def update_env_file(webhook_url):
    """Update .env file with webhook URL."""
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

if __name__ == "__main__":
    sys.exit(setup_localtunnel())
