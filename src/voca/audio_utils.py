"""
Audio conversion utilities for μ-law ↔ PCM conversion.
Twilio uses μ-law encoding (8kHz, mono), while SarvamAI STT/TTS uses PCM.
"""
import audioop
import logging

logger = logging.getLogger(__name__)


def mulaw_to_pcm(mulaw_audio: bytes, sample_width: int = 2) -> bytes:
    """
    Convert μ-law encoded audio to 16-bit PCM.
    
    Args:
        mulaw_audio: μ-law encoded audio bytes
        sample_width: Sample width in bytes (2 for 16-bit PCM)
    
    Returns:
        PCM audio bytes (16-bit, little-endian)
    """
    try:
        pcm_audio = audioop.ulaw2lin(mulaw_audio, sample_width)
        return pcm_audio
    except Exception as e:
        logger.error(f"Error converting μ-law to PCM: {e}")
        raise


def pcm_to_mulaw(pcm_audio: bytes, sample_width: int = 2) -> bytes:
    """
    Convert 16-bit PCM audio to μ-law encoding.
    
    CRITICAL: Twilio Media Streams REQUIRES μ-law encoding at 8000Hz, mono.
    This function converts linear PCM to μ-law using audioop.lin2ulaw.
    
    Args:
        pcm_audio: PCM audio bytes (16-bit signed, little-endian)
        sample_width: Sample width in bytes (2 for 16-bit PCM, REQUIRED)
    
    Returns:
        μ-law encoded audio bytes (ready for Twilio)
    
    Raises:
        ValueError: If audio format is invalid or conversion fails
    """
    if not pcm_audio:
        raise ValueError("PCM audio data is empty")
    
    if sample_width != 2:
        raise ValueError(f"Sample width must be 2 for 16-bit PCM, got {sample_width}")
    
    # Verify PCM length is multiple of sample width
    if len(pcm_audio) % sample_width != 0:
        logger.warning(f"PCM audio length ({len(pcm_audio)}) is not a multiple of sample width ({sample_width}), truncating")
        pcm_audio = pcm_audio[:-(len(pcm_audio) % sample_width)]
    
    try:
        # audioop.lin2ulaw converts linear PCM to μ-law
        # Input: 16-bit signed PCM (little-endian)
        # Output: 8-bit μ-law encoded audio
        # Ratio: ~2:1 (PCM bytes : μ-law bytes)
        mulaw_audio = audioop.lin2ulaw(pcm_audio, sample_width)
        
        # Verify conversion ratio is approximately correct
        expected_mulaw_len = len(pcm_audio) // sample_width
        if len(mulaw_audio) != expected_mulaw_len:
            logger.warning(f"Unexpected μ-law length: got {len(mulaw_audio)}, expected {expected_mulaw_len} (PCM: {len(pcm_audio)})")
        
        return mulaw_audio
    except Exception as e:
        logger.error(f"Error converting PCM to μ-law: {e}, PCM length: {len(pcm_audio)}, sample_width: {sample_width}")
        raise ValueError(f"PCM to μ-law conversion failed: {e}") from e


def chunk_audio(audio_data: bytes, chunk_size_ms: int = 20, sample_rate: int = 8000, sample_width: int = 2) -> list[bytes]:
    """
    Split audio into chunks of specified duration.
    
    Args:
        audio_data: Audio bytes to chunk
        chunk_size_ms: Chunk size in milliseconds (default 20ms for low latency)
        sample_rate: Sample rate in Hz (default 8000 for Twilio)
        sample_width: Sample width in bytes (2 for 16-bit)
    
    Returns:
        List of audio chunks
    """
    # Calculate bytes per chunk: (sample_rate * sample_width * chunk_size_ms) / 1000
    bytes_per_chunk = (sample_rate * sample_width * chunk_size_ms) // 1000
    
    chunks = []
    for i in range(0, len(audio_data), bytes_per_chunk):
        chunk = audio_data[i:i + bytes_per_chunk]
        if chunk:
            chunks.append(chunk)
    
    return chunks

