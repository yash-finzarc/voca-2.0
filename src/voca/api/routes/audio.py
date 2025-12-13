"""
Audio recording endpoints for testing and debugging captured audio.
Note: These endpoints are registered with the Twilio webhook server,
not the main API server.
"""
import logging
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from fastapi import HTTPException
from fastapi.routing import APIRouter
from fastapi.responses import JSONResponse, FileResponse

from src.voca.config import Config

logger = logging.getLogger(__name__)

# Note: This router needs to be registered with the Twilio webhook server's FastAPI app
# The audio storage directory and handlers are managed by TwilioVoiceHandler
router = APIRouter(prefix="/audio", tags=["audio"])


def get_audio_storage_dir() -> Path:
    """Get audio storage directory."""
    return Path(Config.audio_storage_dir)


def get_audio_chunk_counts() -> Dict[str, int]:
    """Get audio chunk counts from TwilioVoiceHandler.
    This needs to be imported from the handler instance."""
    # This will be set when router is initialized with handler reference
    return getattr(router, '_audio_chunk_counts', {})


def set_handler_references(handler):
    """Set handler references for accessing audio storage."""
    router._handler = handler
    router._audio_chunk_counts = handler.audio_chunk_counts
    router._audio_storage_dir = handler.audio_storage_dir


@router.get("/calls")
async def list_recorded_calls():
    """List all calls that have recorded audio."""
    try:
        handler = getattr(router, '_handler', None)
        if handler is None:
            raise HTTPException(status_code=503, detail="Audio handler not available")
        
        audio_dir = handler.audio_storage_dir
        if not audio_dir.exists():
            return JSONResponse({"calls": []})
        
        calls = []
        for call_dir in audio_dir.iterdir():
            if call_dir.is_dir():
                audio_file = call_dir / f"audio_{call_dir.name}.wav"
                if audio_file.exists():
                    file_size = audio_file.stat().st_size
                    file_mtime = datetime.fromtimestamp(audio_file.stat().st_mtime, tz=timezone.utc)
                    chunk_count = handler.audio_chunk_counts.get(call_dir.name, 0)
                    calls.append({
                        "call_sid": call_dir.name,
                        "audio_file": str(audio_file.name),
                        "file_size": file_size,
                        "file_size_mb": round(file_size / (1024 * 1024), 2),
                        "modified_time": file_mtime.isoformat(),
                        "chunk_count": chunk_count,
                        "download_url": f"/audio/download/{call_dir.name}"
                    })
        
        # Sort by modified time, most recent first
        calls.sort(key=lambda x: x["modified_time"], reverse=True)
        return JSONResponse({"calls": calls})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing recorded calls: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{call_sid}")
async def download_audio(call_sid: str):
    """Download recorded audio file for a specific call."""
    try:
        handler = getattr(router, '_handler', None)
        if handler is None:
            raise HTTPException(status_code=503, detail="Audio handler not available")
        
        call_dir = handler.audio_storage_dir / call_sid
        audio_file = call_dir / f"audio_{call_sid}.wav"
        
        if not audio_file.exists():
            raise HTTPException(status_code=404, detail=f"Audio file not found for call {call_sid}")
        
        return FileResponse(
            path=str(audio_file),
            filename=f"audio_{call_sid}.wav",
            media_type="audio/wav"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading audio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/info/{call_sid}")
async def get_audio_info(call_sid: str):
    """Get information about recorded audio for a specific call."""
    try:
        handler = getattr(router, '_handler', None)
        if handler is None:
            raise HTTPException(status_code=503, detail="Audio handler not available")
        
        call_dir = handler.audio_storage_dir / call_sid
        audio_file = call_dir / f"audio_{call_sid}.wav"
        
        if not audio_file.exists():
            raise HTTPException(status_code=404, detail=f"Audio file not found for call {call_sid}")
        
        file_size = audio_file.stat().st_size
        file_mtime = datetime.fromtimestamp(audio_file.stat().st_mtime, tz=timezone.utc)
        chunk_count = handler.audio_chunk_counts.get(call_sid, 0)
        
        # Try to read WAV file info
        with wave.open(str(audio_file), 'rb') as wav_file:
            n_frames = wav_file.getnframes()
            sample_rate = wav_file.getframerate()
            n_channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            duration = n_frames / sample_rate if sample_rate > 0 else 0
        
        return JSONResponse({
            "call_sid": call_sid,
            "audio_file": str(audio_file.name),
            "file_size": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "modified_time": file_mtime.isoformat(),
            "chunk_count": chunk_count,
            "audio_info": {
                "sample_rate": sample_rate,
                "channels": n_channels,
                "sample_width": sample_width,
                "frames": n_frames,
                "duration_seconds": round(duration, 2),
                "duration_formatted": f"{int(duration // 60)}m {int(duration % 60)}s"
            },
            "download_url": f"/audio/download/{call_sid}"
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting audio info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

