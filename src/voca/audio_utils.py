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
    
    Args:
        pcm_audio: PCM audio bytes (16-bit, little-endian)
        sample_width: Sample width in bytes (2 for 16-bit PCM)
    
    Returns:
        μ-law encoded audio bytes
    """
    try:
        mulaw_audio = audioop.lin2ulaw(pcm_audio, sample_width)
        return mulaw_audio
    except Exception as e:
        logger.error(f"Error converting PCM to μ-law: {e}")
        raise


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

