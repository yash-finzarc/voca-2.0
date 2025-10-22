#!/usr/bin/env python3
"""
Install ngrok for Windows - Downloads and sets up ngrok binary
"""
import os
import sys
import requests
import zipfile
import shutil
from pathlib import Path

def download_ngrok():
    """Download ngrok for Windows."""
    print("📥 Downloading ngrok for Windows...")
    
    # ngrok download URL for Windows
    ngrok_url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
    
    try:
        response = requests.get(ngrok_url, stream=True)
        response.raise_for_status()
        
        # Save to temporary file
        with open("ngrok.zip", "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print("✅ ngrok downloaded successfully")
        return True
        
    except Exception as e:
        print(f"❌ Failed to download ngrok: {e}")
        return False

def extract_ngrok():
    """Extract ngrok from zip file."""
    print("📦 Extracting ngrok...")
    
    try:
        with zipfile.ZipFile("ngrok.zip", 'r') as zip_ref:
            zip_ref.extractall(".")
        
        # Find the ngrok.exe file
        ngrok_exe = None
        for root, dirs, files in os.walk("."):
            for file in files:
                if file == "ngrok.exe":
                    ngrok_exe = os.path.join(root, file)
                    break
            if ngrok_exe:
                break
        
        if ngrok_exe:
            # Move to current directory
            shutil.move(ngrok_exe, "ngrok.exe")
            print("✅ ngrok extracted successfully")
            return True
        else:
            print("❌ ngrok.exe not found in extracted files")
            return False
            
    except Exception as e:
        print(f"❌ Failed to extract ngrok: {e}")
        return False

def cleanup():
    """Clean up temporary files."""
    try:
        if os.path.exists("ngrok.zip"):
            os.remove("ngrok.zip")
        print("🧹 Cleaned up temporary files")
    except Exception as e:
        print(f"⚠️  Could not clean up: {e}")

def test_ngrok():
    """Test if ngrok is working."""
    print("🧪 Testing ngrok installation...")
    
    try:
        import subprocess
        result = subprocess.run(["./ngrok.exe", "version"], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✅ ngrok is working: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ ngrok test failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ ngrok test error: {e}")
        return False

def main():
    """Main installation function."""
    print("🚀 Installing ngrok for Windows\n")
    
    # Check if ngrok is already installed
    if os.path.exists("ngrok.exe"):
        print("✅ ngrok.exe already exists")
        if test_ngrok():
            print("🎉 ngrok is ready to use!")
            return 0
    
    # Download ngrok
    if not download_ngrok():
        return 1
    
    # Extract ngrok
    if not extract_ngrok():
        cleanup()
        return 1
    
    # Test installation
    if not test_ngrok():
        cleanup()
        return 1
    
    # Cleanup
    cleanup()
    
    print("\n🎉 ngrok installation complete!")
    print("📋 Next steps:")
    print("1. Run: python setup_ngrok.py")
    print("2. Or manually: ./ngrok.exe http 5000")
    print("3. Update Twilio webhook URL with the ngrok URL")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
