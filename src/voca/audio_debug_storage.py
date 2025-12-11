"""
Audio Debug Storage Module

Stores audio chunks sent to STT for debugging and echo analysis.
This module handles all audio file storage logic separately from the main processing.
"""
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)


class AudioDebugStorage:
    """
    Handles storage of audio chunks for debugging and echo analysis.
    Stores audio files and metadata separately from main processing logic.
    """
    
    def __init__(self, base_dir: str = "audio_logs", enabled: bool = False):
        """
        Initialize audio debug storage.
        
        Args:
            base_dir: Base directory for storing audio logs
            enabled: Whether audio storage is enabled
        """
        self.base_dir = Path(base_dir)
        self.enabled = enabled
        self._ensure_base_dir()
    
    def _ensure_base_dir(self):
        """Create base directory if it doesn't exist."""
        if self.enabled:
            try:
                self.base_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"[AUDIO_DEBUG] Audio storage enabled - base directory: {self.base_dir.absolute()}")
            except Exception as e:
                logger.error(f"[AUDIO_DEBUG] Failed to create base directory: {e}")
                self.enabled = False
    
    def _get_call_dir(self, call_sid: str) -> Path:
        """Get or create directory for a specific call."""
        call_dir = self.base_dir / call_sid
        if self.enabled:
            call_dir.mkdir(parents=True, exist_ok=True)
        return call_dir
    
    def _generate_filename(self, timestamp: datetime, chunk_number: int) -> str:
        """Generate filename for audio chunk."""
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Include milliseconds
        return f"{timestamp_str}_chunk_{chunk_number}.wav"
    
    def _save_wav_file(self, audio_array: np.ndarray, filepath: Path, sample_rate: int = 8000):
        """
        Save audio array as WAV file.
        
        Args:
            audio_array: PCM16 audio data as numpy array (int16)
            filepath: Path to save WAV file
            sample_rate: Sample rate (default: 8000 Hz)
        """
        try:
            # Try scipy first (more common)
            try:
                from scipy.io import wavfile
                wavfile.write(str(filepath), sample_rate, audio_array)
            except ImportError:
                # Fallback to soundfile
                import soundfile as sf
                sf.write(str(filepath), audio_array, sample_rate, subtype='PCM_16')
            
            logger.debug(f"[AUDIO_DEBUG] Saved WAV file: {filepath.name}")
        except Exception as e:
            logger.error(f"[AUDIO_DEBUG] Failed to save WAV file {filepath}: {e}")
            raise
    
    def _convert_to_json_serializable(self, obj):
        """Recursively convert numpy types and other non-serializable types to JSON-compatible types."""
        if isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        elif isinstance(obj, dict):
            return {key: self._convert_to_json_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._convert_to_json_serializable(item) for item in obj]
        else:
            return obj
    
    def _save_metadata(self, call_dir: Path, metadata: Dict[str, Any]):
        """Save metadata JSON file for a chunk."""
        try:
            chunk_number = metadata.get('chunk_number', 0)
            metadata_file = call_dir / f"metadata_chunk_{chunk_number}.json"
            
            # Convert numpy types and other non-serializable types to JSON-compatible types
            serializable_metadata = self._convert_to_json_serializable(metadata)
            
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_metadata, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"[AUDIO_DEBUG] Saved metadata: {metadata_file.name}")
        except Exception as e:
            logger.warning(f"[AUDIO_DEBUG] Failed to save metadata: {e}")
    
    def _update_index(self, call_dir: Path, metadata: Dict[str, Any]):
        """Update index.json file with chunk information."""
        try:
            index_file = call_dir / "index.json"
            
            # Load existing index or create new
            if index_file.exists():
                with open(index_file, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
            else:
                index_data = {
                    "call_sid": metadata.get('call_sid'),
                    "chunks": []
                }
            
            # Add chunk info to index
            chunk_info = {
                "chunk_number": metadata.get('chunk_number'),
                "timestamp": metadata.get('timestamp'),
                "audio_file": metadata.get('audio_file'),
                "transcript": metadata.get('transcript'),
                "transcript_accepted": metadata.get('transcript_accepted'),
                "rejection_reason": metadata.get('rejection_reason')
            }
            
            # Convert to JSON-serializable format
            chunk_info = self._convert_to_json_serializable(chunk_info)
            index_data["chunks"].append(chunk_info)
            
            # Save updated index
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.warning(f"[AUDIO_DEBUG] Failed to update index: {e}")
    
    def store_audio_chunk(
        self,
        call_sid: str,
        audio_array: np.ndarray,
        chunk_number: int,
        metadata: Optional[Dict[str, Any]] = None,
        sample_rate: int = 8000
    ) -> Optional[str]:
        """
        Store an audio chunk for debugging.
        
        Args:
            call_sid: Call SID identifier
            audio_array: PCM16 audio data as numpy array (int16)
            chunk_number: Sequential chunk number
            metadata: Optional metadata dictionary
            sample_rate: Audio sample rate (default: 8000 Hz)
        
        Returns:
            Path to saved audio file if successful, None otherwise
        """
        if not self.enabled:
            return None
        
        try:
            # Get call directory
            call_dir = self._get_call_dir(call_sid)
            
            # Generate filename
            timestamp = datetime.now()
            filename = self._generate_filename(timestamp, chunk_number)
            audio_filepath = call_dir / filename
            
            # Save WAV file
            self._save_wav_file(audio_array, audio_filepath, sample_rate)
            
            # Prepare metadata
            audio_duration = len(audio_array) / sample_rate
            full_metadata = {
                "call_sid": call_sid,
                "chunk_number": chunk_number,
                "timestamp": timestamp.isoformat(),
                "audio_file": filename,
                "audio_duration_sec": round(audio_duration, 2),
                "sample_rate": sample_rate,
                "audio_samples": len(audio_array),
                **(metadata or {})
            }
            
            # Save metadata
            self._save_metadata(call_dir, full_metadata)
            
            # Update index
            self._update_index(call_dir, full_metadata)
            
            logger.info(f"[AUDIO_DEBUG] Stored audio chunk #{chunk_number} for call {call_sid}: {filename}")
            return str(audio_filepath)
            
        except Exception as e:
            logger.error(f"[AUDIO_DEBUG] Failed to store audio chunk: {e}")
            return None
    
    def is_enabled(self) -> bool:
        """Check if audio storage is enabled."""
        return self.enabled
    
    def get_storage_path(self) -> Path:
        """Get the base storage path."""
        return self.base_dir
    
    def update_chunk_metadata(
        self,
        call_sid: str,
        chunk_number: int,
        transcript: Optional[str] = None,
        transcript_accepted: Optional[bool] = None,
        rejection_reason: Optional[str] = None
    ) -> bool:
        """
        Update metadata for an already-stored audio chunk with transcript information.
        
        Args:
            call_sid: Call SID identifier
            chunk_number: Chunk number to update
            transcript: Transcript text (if available)
            transcript_accepted: Whether transcript was accepted
            rejection_reason: Reason for rejection (if rejected)
        
        Returns:
            True if update was successful, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            call_dir = self._get_call_dir(call_sid)
            metadata_file = call_dir / f"metadata_chunk_{chunk_number}.json"
            
            if not metadata_file.exists():
                logger.warning(f"[AUDIO_DEBUG] Metadata file not found: {metadata_file}")
                return False
            
            # Load existing metadata
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # Update with transcript info
            if transcript is not None:
                metadata['transcript'] = transcript
            if transcript_accepted is not None:
                metadata['transcript_accepted'] = transcript_accepted
            if rejection_reason is not None:
                metadata['rejection_reason'] = rejection_reason
            
            # Save updated metadata
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            # Also update index.json
            self._update_index_with_transcript(call_dir, chunk_number, transcript, transcript_accepted, rejection_reason)
            
            logger.debug(f"[AUDIO_DEBUG] Updated metadata for chunk #{chunk_number}")
            return True
            
        except Exception as e:
            logger.warning(f"[AUDIO_DEBUG] Failed to update chunk metadata: {e}")
            return False
    
    def _update_index_with_transcript(
        self,
        call_dir: Path,
        chunk_number: int,
        transcript: Optional[str],
        transcript_accepted: Optional[bool],
        rejection_reason: Optional[str]
    ):
        """Update index.json with transcript information for a specific chunk."""
        try:
            index_file = call_dir / "index.json"
            
            if not index_file.exists():
                return
            
            # Load existing index
            with open(index_file, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            
            # Find and update the chunk
            for chunk in index_data.get('chunks', []):
                if chunk.get('chunk_number') == chunk_number:
                    if transcript is not None:
                        chunk['transcript'] = transcript
                    if transcript_accepted is not None:
                        chunk['transcript_accepted'] = transcript_accepted
                    if rejection_reason is not None:
                        chunk['rejection_reason'] = rejection_reason
                    break
            
            # Save updated index
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.warning(f"[AUDIO_DEBUG] Failed to update index with transcript: {e}")


# Global instance (can be configured via environment variables)
_audio_storage_instance: Optional[AudioDebugStorage] = None


def get_audio_storage() -> AudioDebugStorage:
    """
    Get the global audio storage instance.
    Creates instance on first call based on Config or environment variables.
    """
    global _audio_storage_instance
    
    if _audio_storage_instance is None:
        try:
            from src.voca.config import Config
            enabled = Config.audio_storage_enabled
            base_dir = Config.audio_storage_dir
        except Exception:
            # Fallback to environment variables if Config not available
            import os
            enabled = os.getenv('VOCA_DEBUG_AUDIO_STORAGE', 'false').lower() == 'true'
            base_dir = os.getenv('VOCA_AUDIO_LOG_DIR', 'audio_logs')
        _audio_storage_instance = AudioDebugStorage(base_dir=base_dir, enabled=enabled)
    
    return _audio_storage_instance


def store_stt_audio(
    call_sid: str,
    audio_array: np.ndarray,
    chunk_number: int,
    metadata: Optional[Dict[str, Any]] = None,
    sample_rate: int = 8000
) -> Optional[str]:
    """
    Convenience function to store STT audio chunk.
    
    This is the main entry point for storing audio from STT processing.
    Usage: store_stt_audio(call_sid, audio_array, chunk_num, {...metadata...})
    
    Args:
        call_sid: Call SID identifier
        audio_array: PCM16 audio data as numpy array (int16)
        chunk_number: Sequential chunk number
        metadata: Optional metadata (rms_energy, has_voice, transcript, etc.)
        sample_rate: Audio sample rate (default: 8000 Hz)
    
    Returns:
        Path to saved audio file if successful, None otherwise
    """
    storage = get_audio_storage()
    return storage.store_audio_chunk(
        call_sid=call_sid,
        audio_array=audio_array,
        chunk_number=chunk_number,
        metadata=metadata,
        sample_rate=sample_rate
    )


def update_stt_metadata(
    call_sid: str,
    chunk_number: int,
    transcript: Optional[str] = None,
    transcript_accepted: Optional[bool] = None,
    rejection_reason: Optional[str] = None
) -> bool:
    """
    Convenience function to update metadata for a stored audio chunk with transcript information.
    
    Call this after STT processing to update the metadata with transcript results.
    
    Args:
        call_sid: Call SID identifier
        chunk_number: Chunk number to update
        transcript: Transcript text (if available)
        transcript_accepted: Whether transcript was accepted
        rejection_reason: Reason for rejection (if rejected)
    
    Returns:
        True if update was successful, False otherwise
    """
    storage = get_audio_storage()
    return storage.update_chunk_metadata(
        call_sid=call_sid,
        chunk_number=chunk_number,
        transcript=transcript,
        transcript_accepted=transcript_accepted,
        rejection_reason=rejection_reason
    )

