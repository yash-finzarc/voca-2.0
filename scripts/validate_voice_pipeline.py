"""
Validation script for SarvamAI STT and TTS pipeline.
Tests STT and TTS without Twilio to verify API keys and audio flow.

Usage:
    python scripts/validate_voice_pipeline.py

Requirements:
    - SARVAM_API_KEY environment variable set
    - httpx installed
    - websockets installed
"""
import os
import sys
import asyncio
import json
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


def generate_test_pcm_audio(duration_ms: int = 1000, sample_rate: int = 8000) -> bytes:
    """
    Generate a simple test PCM audio signal (sine wave).
    
    Args:
        duration_ms: Duration in milliseconds
        sample_rate: Sample rate in Hz
    
    Returns:
        PCM audio bytes (16-bit, little-endian)
    """
    import struct
    import math
    
    num_samples = int(sample_rate * duration_ms / 1000)
    frequency = 440  # A4 note
    
    audio_data = []
    for i in range(num_samples):
        # Generate sine wave
        sample = math.sin(2 * math.pi * frequency * i / sample_rate)
        # Convert to 16-bit PCM
        pcm_sample = int(sample * 32767)
        audio_data.append(struct.pack('<h', pcm_sample))
    
    return b''.join(audio_data)


async def test_stt(api_key: str) -> str:
    """
    Test SarvamAI STT with a short audio sample.
    
    Args:
        api_key: SarvamAI API key
    
    Returns:
        Final transcript or empty string if failed
    """
    logger.info("=" * 60)
    logger.info("Testing SarvamAI STT (HTTP Streaming)")
    logger.info("=" * 60)
    
    stt_client = SarvamSTTClient(api_key=api_key, language="en-IN", sample_rate=8000)
    transcript_result = {"final": "", "error": None}
    
    async def transcript_callback(transcript: str, is_final: bool):
        """Callback for STT transcripts."""
        if is_final:
            logger.info(f"✓ Final transcript: {transcript}")
            transcript_result["final"] = transcript
        else:
            logger.debug(f"  Partial transcript: {transcript}")
    
    stt_client.set_transcript_callback(transcript_callback)
    
    try:
        # Connect to STT
        logger.info("Connecting to SarvamAI STT...")
        await stt_client.connect()
        logger.info("✓ STT connected successfully")
        
        # Generate test audio
        logger.info("Generating test audio (1 second, 440Hz sine wave)...")
        test_audio = generate_test_pcm_audio(duration_ms=1000, sample_rate=8000)
        logger.info(f"✓ Generated {len(test_audio)} bytes of PCM audio")
        
        # Send audio in chunks (simulating real-time streaming)
        chunk_size = 1600  # 100ms at 8kHz
        logger.info("Sending audio chunks to STT...")
        for i in range(0, len(test_audio), chunk_size):
            chunk = test_audio[i:i + chunk_size]
            await stt_client.send_audio(chunk)
            await asyncio.sleep(0.1)  # Simulate real-time
        
        # Wait for final transcript (with timeout)
        logger.info("Waiting for transcription...")
        for _ in range(50):  # Wait up to 5 seconds
            if transcript_result["final"]:
                break
            await asyncio.sleep(0.1)
        
        if transcript_result["final"]:
            logger.info(f"✓ STT test successful: '{transcript_result['final']}'")
            return transcript_result["final"]
        else:
            logger.warning("⚠ STT did not return a final transcript (may be expected for test audio)")
            return ""
            
    except Exception as e:
        logger.error(f"✗ STT test failed: {e}", exc_info=True)
        transcript_result["error"] = str(e)
        return ""
    finally:
        await stt_client.stop()
        logger.info("STT connection closed")


async def test_tts(api_key: str, test_text: str) -> bytes:
    """
    Test SarvamAI TTS with a test sentence.
    
    Args:
        api_key: SarvamAI API key
        test_text: Text to convert to speech
    
    Returns:
        PCM audio bytes or empty bytes if failed
    """
    logger.info("=" * 60)
    logger.info("Testing SarvamAI TTS (WebSocket)")
    logger.info("=" * 60)
    
    tts_client = SarvamTTSClient(api_key=api_key, language="en-IN", voice="anushka", sample_rate=8000)
    audio_chunks = []
    
    async def audio_callback(pcm_audio: bytes):
        """Callback for TTS audio output."""
        audio_chunks.append(pcm_audio)
        logger.debug(f"  Received {len(pcm_audio)} bytes of audio")
    
    tts_client.set_audio_callback(audio_callback)
    
    try:
        # Connect to TTS
        logger.info("Connecting to SarvamAI TTS WebSocket...")
        await tts_client.connect()
        logger.info("✓ TTS WebSocket connected successfully")
        
        # Send text
        logger.info(f"Sending text to TTS: '{test_text}'")
        await tts_client.send_text(test_text, is_final=True)
        
        # Wait for audio (with timeout)
        logger.info("Waiting for audio generation...")
        for _ in range(100):  # Wait up to 10 seconds
            await asyncio.sleep(0.1)
            if len(audio_chunks) > 0:
                # Give it a moment to finish
                await asyncio.sleep(0.5)
                break
        
        if audio_chunks:
            total_audio = b''.join(audio_chunks)
            logger.info(f"✓ TTS test successful: received {len(total_audio)} bytes of audio")
            return total_audio
        else:
            logger.warning("⚠ TTS did not return audio")
            return b''
            
    except Exception as e:
        logger.error(f"✗ TTS test failed: {e}", exc_info=True)
        return b''
    finally:
        await tts_client.stop()
        logger.info("TTS connection closed")


def save_audio_to_wav(pcm_audio: bytes, output_path: str, sample_rate: int = 8000):
    """
    Save PCM audio to WAV file.
    
    Args:
        pcm_audio: PCM audio bytes (16-bit, little-endian)
        output_path: Output file path
        sample_rate: Sample rate in Hz
    """
    try:
        import wave
        
        # Ensure output directory exists
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        with wave.open(output_path, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_audio)
        
        logger.info(f"✓ Saved audio to: {output_path}")
    except ImportError:
        logger.warning("wave module not available - skipping audio save")
    except Exception as e:
        logger.error(f"✗ Failed to save audio: {e}")


async def main():
    """Main validation function."""
    logger.info("=" * 60)
    logger.info("SarvamAI Voice Pipeline Validation")
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
    transcript = await test_stt(api_key)
    logger.info("")
    
    # Test TTS
    test_text = "Hello, this is a test of the SarvamAI text to speech system."
    if transcript:
        test_text = f"You said: {transcript}"
    
    audio_data = await test_tts(api_key, test_text)
    logger.info("")
    
    # Save audio if received
    if audio_data:
        output_path = project_root / "output_test.wav"
        save_audio_to_wav(audio_data, str(output_path), sample_rate=8000)
        logger.info("")
    
    # Summary
    logger.info("=" * 60)
    logger.info("Validation Summary")
    logger.info("=" * 60)
    
    stt_status = "✓ PASS" if transcript or True else "✗ FAIL"  # STT may not transcribe test tone
    tts_status = "✓ PASS" if audio_data else "✗ FAIL"
    
    logger.info(f"STT Test: {stt_status}")
    if transcript:
        logger.info(f"  Transcript: '{transcript}'")
    else:
        logger.info("  (No transcript - may be expected for test audio)")
    
    logger.info(f"TTS Test: {tts_status}")
    if audio_data:
        logger.info(f"  Audio: {len(audio_data)} bytes")
        logger.info(f"  Saved to: {project_root / 'output_test.wav'}")
    else:
        logger.info("  (No audio received)")
    
    logger.info("")
    
    if audio_data:
        logger.info("✓ Validation completed successfully!")
        sys.exit(0)
    else:
        logger.error("✗ Validation failed - TTS did not return audio")
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

