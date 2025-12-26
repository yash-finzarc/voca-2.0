"""
Basic Voice Workflow Validation
Validates STT and TTS authentication and basic functionality without LLM or Twilio.

Usage:
    python scripts/validate_voice_workflow_basic.py

Requirements:
    - SARVAM_API_KEY environment variable set
    - httpx installed
    - websockets installed
"""
import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.voca.services.sarvam_stt import SarvamSTTClient
from src.voca.services.sarvam_tts import SarvamTTSClient

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TEST_TEXT = "Hello, this is a Sarvam TTS validation test."


async def test_stt_auth(api_key: str) -> bool:
    """
    Test STT authentication and connection.
    Sends silence audio - STT should accept it even if no transcript is returned.
    
    Args:
        api_key: SarvamAI API key
    
    Returns:
        True if connection successful, False otherwise
    """
    logger.info("=" * 60)
    logger.info("Testing STT Authentication")
    logger.info("=" * 60)
    
    stt = SarvamSTTClient(api_key=api_key, language="en-IN", sample_rate=8000)
    
    try:
        logger.info("Connecting to SarvamAI STT...")
        await stt.connect()
        logger.info("✓ STT connected successfully")
        
        # Send silence (1 second of zeros at 8kHz = 16000 bytes for 16-bit PCM)
        silence_audio = b"\x00" * 16000
        logger.info(f"Sending {len(silence_audio)} bytes of silence audio...")
        await stt.send_audio(silence_audio)
        
        # Wait a moment for any response
        await asyncio.sleep(1)
        
        logger.info("✓ STT auth & connection OK")
        return True
        
    except Exception as e:
        logger.error(f"✗ STT test failed: {e}", exc_info=True)
        return False
    finally:
        await stt.stop()
        logger.info("STT connection closed")


async def test_tts_auth(api_key: str) -> bool:
    """
    Test TTS authentication and basic synthesis.
    
    Args:
        api_key: SarvamAI API key
    
    Returns:
        True if audio received, False otherwise
    """
    logger.info("=" * 60)
    logger.info("Testing TTS Authentication")
    logger.info("=" * 60)
    
    tts = SarvamTTSClient(api_key=api_key, language="en-IN", voice="anushka", sample_rate=8000)
    audio_chunks = []
    audio_received = asyncio.Event()
    
    async def audio_callback(pcm_audio: bytes):
        """Callback for TTS audio output."""
        audio_chunks.append(pcm_audio)
        if len(audio_chunks) > 0:
            audio_received.set()
    
    tts.set_audio_callback(audio_callback)
    
    try:
        logger.info("Connecting to SarvamAI TTS WebSocket...")
        await tts.connect()
        logger.info("✓ TTS WebSocket connected successfully")
        
        logger.info(f"Sending text to TTS: '{TEST_TEXT}'")
        await tts.send_text(TEST_TEXT, is_final=True)
        
        # Wait for audio (with timeout)
        logger.info("Waiting for audio generation...")
        try:
            await asyncio.wait_for(audio_received.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for audio - checking if any audio was received...")
        
        # Give it a moment to finish
        await asyncio.sleep(1)
        
        total_audio = b''.join(audio_chunks)
        
        if total_audio and len(total_audio) > 0:
            logger.info(f"✓ TTS audio received: {len(total_audio)} bytes")
            return True
        else:
            logger.error("✗ TTS returned no audio")
            return False
            
    except Exception as e:
        logger.error(f"✗ TTS test failed: {e}", exc_info=True)
        return False
    finally:
        await tts.stop()
        logger.info("TTS connection closed")


async def main():
    """Main validation function."""
    logger.info("=" * 60)
    logger.info("BASIC VOICE WORKFLOW CHECK")
    logger.info("=" * 60)
    
    # Check API key
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        logger.error("✗ SARVAM_API_KEY not found in environment variables")
        logger.error("Please set SARVAM_API_KEY in your .env file or environment")
        sys.exit(1)
    
    api_key_preview = api_key[:10] + "..." if len(api_key) > 10 else api_key
    logger.info(f"Using API key: {api_key_preview} (length: {len(api_key)})")
    logger.info("")
    
    # Test STT
    stt_ok = await test_stt_auth(api_key)
    logger.info("")
    
    # Test TTS
    tts_ok = await test_tts_auth(api_key)
    logger.info("")
    
    # Summary
    logger.info("=" * 60)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 60)
    
    logger.info(f"STT Auth & Connection: {'✓ PASS' if stt_ok else '✗ FAIL'}")
    logger.info(f"TTS Auth & Audio: {'✓ PASS' if tts_ok else '✗ FAIL'}")
    logger.info("")
    
    if stt_ok and tts_ok:
        logger.info("✓ BASIC WORKFLOW PASSED")
        sys.exit(0)
    else:
        logger.error("✗ BASIC WORKFLOW FAILED")
        if not stt_ok:
            logger.error("  - STT authentication or connection failed")
        if not tts_ok:
            logger.error("  - TTS authentication or audio generation failed")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nValidation interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Validation failed with error: {e}", exc_info=True)
        sys.exit(1)

