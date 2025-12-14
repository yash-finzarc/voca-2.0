#!/usr/bin/env python3
"""
Script to pull audio files from the server to local machine.
"""
import os
import subprocess
import sys
from pathlib import Path

# Server details
SERVER_HOST = "172.105.50.83"
SERVER_USER = "root"
SERVER_AUDIO_DIR = "/root/voca-2.0/audio_logs"
LOCAL_AUDIO_DIR = "audio_logs"

def pull_audio_files(call_sid=None):
    """
    Pull audio files from server to local machine.
    
    Args:
        call_sid: Specific call SID to pull (optional). If None, pulls all calls.
    """
    # Create local directory
    local_dir = Path(LOCAL_AUDIO_DIR)
    local_dir.mkdir(exist_ok=True)
    
    # Build SCP command
    if call_sid:
        # Pull specific call
        remote_path = f"{SERVER_USER}@{SERVER_HOST}:{SERVER_AUDIO_DIR}/{call_sid}/"
        local_path = str(local_dir / call_sid)
        print(f"📥 Pulling audio files for call: {call_sid}")
    else:
        # Pull all calls
        remote_path = f"{SERVER_USER}@{SERVER_HOST}:{SERVER_AUDIO_DIR}/"
        local_path = str(local_dir)
        print(f"📥 Pulling all audio files from server...")
    
    # Use scp to copy files
    # On Windows, you might need to use pscp (PuTTY) or WSL scp
    if sys.platform == "win32":
        # Try using scp from Git Bash or WSL
        scp_cmd = ["scp", "-r", remote_path, local_path]
    else:
        scp_cmd = ["scp", "-r", remote_path, local_path]
    
    print(f"🔧 Running: {' '.join(scp_cmd)}")
    print(f"📁 Local destination: {os.path.abspath(local_path)}")
    print()
    
    try:
        result = subprocess.run(scp_cmd, check=True)
        print("✅ Successfully pulled audio files!")
        print(f"📂 Files are in: {os.path.abspath(local_path)}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error pulling files: {e}")
        print()
        print("💡 Alternative methods:")
        print("1. Use WinSCP (GUI tool for Windows)")
        print("2. Use PuTTY's pscp.exe:")
        print(f"   pscp -r {remote_path} {local_path}")
        print("3. Use Git Bash or WSL:")
        print(f"   scp -r {remote_path} {local_path}")
        return False
    except FileNotFoundError:
        print("❌ 'scp' command not found!")
        print()
        print("💡 Please use one of these methods:")
        print()
        print("Option 1: Use WinSCP (GUI)")
        print("  - Download from: https://winscp.net/")
        print(f"  - Connect to: {SERVER_HOST}")
        print(f"  - Navigate to: {SERVER_AUDIO_DIR}")
        print()
        print("Option 2: Use PuTTY pscp")
        print("  - Download PuTTY from: https://www.putty.org/")
        print(f"  - Run: pscp -r {SERVER_USER}@{SERVER_HOST}:{SERVER_AUDIO_DIR}/ {LOCAL_AUDIO_DIR}/")
        print()
        print("Option 3: Use Git Bash or WSL")
        print(f"  - Run: scp -r {SERVER_USER}@{SERVER_HOST}:{SERVER_AUDIO_DIR}/ {LOCAL_AUDIO_DIR}/")
        return False
    
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Pull audio files from server")
    parser.add_argument(
        "--call-sid",
        type=str,
        help="Specific call SID to pull (optional, pulls all if not specified)"
    )
    
    args = parser.parse_args()
    
    pull_audio_files(call_sid=args.call_sid)






