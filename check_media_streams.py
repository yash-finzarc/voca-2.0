"""
Diagnostic script to check Media Streams configuration and test audio storage.
"""
import os
import sys
from pathlib import Path

print("=== Media Streams & Audio Storage Diagnostic ===\n")

# 1. Check audio storage config
print("1. Audio Storage Configuration:")
from src.voca.config import Config
print(f"   Storage Enabled: {Config.audio_storage_enabled}")
print(f"   Storage Directory: {Config.audio_storage_dir}")
print(f"   Directory Exists: {Path(Config.audio_storage_dir).exists()}")

# 2. Check Twilio config
print("\n2. Twilio Configuration:")
try:
    from src.voca.twilio_config import get_twilio_config
    config = get_twilio_config()
    webhook_url = config.get_webhook_url()
    print(f"   Webhook URL: {webhook_url}")
    
    # Check if it supports WebSocket
    base_url = webhook_url.replace('/webhook/voice', '')
    wss_url = base_url.replace('http://', 'wss://').replace('https://', 'wss://')
    print(f"   Media Stream URL (wss://): {wss_url}/media/{{call_sid}}")
    
    if not wss_url.startswith('wss://'):
        print("   ⚠️  WARNING: Webhook URL doesn't use wss:// - Media Streams require WebSocket!")
    else:
        print("   ✓ WebSocket URL format looks correct")
        
except Exception as e:
    print(f"   ✗ Error loading Twilio config: {e}")

# 3. Test audio storage
print("\n3. Testing Audio Storage:")
try:
    from src.voca.audio_debug_storage import store_stt_audio
    import numpy as np
    
    test_audio = np.zeros(16000, dtype=np.int16)  # 1 second of silence
    result = store_stt_audio(
        call_sid="diagnostic_test",
        audio_array=test_audio,
        chunk_number=1,
        metadata={"test": True},
        sample_rate=16000
    )
    
    if result:
        print(f"   ✓ Audio storage works! Test file: {result}")
        print(f"   File exists: {Path(result).exists()}")
    else:
        print("   ✗ Audio storage returned None (might be disabled)")
        
except Exception as e:
    print(f"   ✗ Error testing audio storage: {e}")

# 4. Check for existing audio files
print("\n4. Existing Audio Files:")
audio_logs = Path("audio_logs")
if audio_logs.exists():
    call_dirs = [d for d in audio_logs.iterdir() if d.is_dir()]
    print(f"   Found {len(call_dirs)} call directories:")
    for call_dir in sorted(call_dirs, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
        wav_files = list(call_dir.glob("*.wav"))
        print(f"   - {call_dir.name}: {len(wav_files)} WAV files")
else:
    print("   No audio_logs directory found")

# 5. Recommendations
print("\n5. Recommendations:")
if not Config.audio_storage_enabled:
    print("   ⚠️  Enable audio storage: Set VOCA_DEBUG_AUDIO_STORAGE=true")
    
webhook_url = get_twilio_config().get_webhook_url() if 'config' in locals() else None
if webhook_url and not webhook_url.startswith('wss://'):
    print("   ⚠️  Media Streams require WebSocket (wss://)")
    print("   ⚠️  If using ngrok, ensure WebSocket support is enabled")
    print("   ⚠️  Check Twilio console for Media Stream connection errors")

print("\n=== Diagnostic Complete ===")

