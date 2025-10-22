#!/usr/bin/env python3
"""
Quick setup script for your Twilio number: +1XXXXXXXXXX
"""
import os
import subprocess
import sys

def create_env_file():
    """Create .env file with your Twilio number."""
    env_content = """# Twilio Configuration for +1XXXXXXXXXX
# Get these from your Twilio Console (https://console.twilio.com/)
TWILIO_ACCOUNT_SID=your_account_sid_here
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
TWILIO_WEBHOOK_URL=http://your-ngrok-url.ngrok.io/webhook/voice

# Optional: For advanced features
TWILIO_API_KEY_SID=your_api_key_sid_here
TWILIO_API_KEY_SECRET=your_api_key_secret_here

# OpenAI Configuration (if using OpenAI)
OPENAI_API_KEY=your_openai_api_key_here

# Google AI Configuration (if using Gemini)
GOOGLE_AI_API_KEY=your_google_ai_api_key_here
"""
    
    with open('.env', 'w') as f:
        f.write(env_content)
    
    print("✅ Created .env file with your Twilio number: +1XXXXXXXXXX")
    print("📝 Please edit .env file and add your actual credentials")

def install_dependencies():
    """Install required dependencies."""
    print("📦 Installing dependencies...")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], check=True)
        print("✅ Dependencies installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False
    return True

def main():
    """Main setup function."""
    print("🚀 Quick Setup for Twilio Number: +1XXXXXXXXXX\n")
    
    # Create .env file
    create_env_file()
    
    # Install dependencies
    if not install_dependencies():
        return 1
    
    print("\n🎯 Next Steps:")
    print("1. Edit .env file and add your Twilio credentials:")
    print("   - TWILIO_ACCOUNT_SID (from Twilio Console)")
    print("   - TWILIO_AUTH_TOKEN (from Twilio Console)")
    print("   - TWILIO_WEBHOOK_URL (will be set when you run ngrok)")
    
    print("\n2. Set up ngrok for webhooks:")
    print("   python setup_ngrok.py")
    
    print("\n3. Test your configuration:")
    print("   python test_twilio_setup.py")
    
    print("\n4. Run the application:")
    print("   python src/main.py")
    
    print("\n5. Configure your Twilio phone number webhook:")
    print("   - Go to Twilio Console > Phone Numbers > Manage > Active numbers")
    print("   - Click on +1XXXXXXXXXX")
    print("   - Set Voice webhook URL to your ngrok URL + '/webhook/voice'")
    print("   - Set HTTP method to POST")
    
    print("\n6. Test by calling +1XXXXXXXXXX from any phone!")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
