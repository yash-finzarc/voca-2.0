"""
Configuration management for VOCA project.
Loads settings from environment variables with sensible defaults.
"""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class for VOCA application settings."""
    
    # Organization settings
    default_organization_id: Optional[str] = os.getenv('VOCA_DEFAULT_ORGANIZATION_ID')
    
    # LLM settings (Gemini)
    gemini_api_key: Optional[str] = os.getenv('GEMINI_API_KEY')
    llm_temperature: float = float(os.getenv('LLM_TEMPERATURE', '0.7'))
    llm_max_tokens: int = int(os.getenv('LLM_MAX_TOKENS', '2048'))
    llm_retries: int = int(os.getenv('LLM_RETRIES', '3'))
    
    # Audio settings
    audio_storage_enabled: bool = os.getenv('AUDIO_STORAGE_ENABLED', 'false').lower() == 'true'
    audio_storage_dir: str = os.getenv('AUDIO_STORAGE_DIR', 'audio_storage')
    sample_rate: int = int(os.getenv('SAMPLE_RATE', '16000'))
    
    # STT settings
    stt_model_path: Optional[str] = os.getenv('STT_MODEL_PATH')
    stt_scorer_path: Optional[str] = os.getenv('STT_SCORER_PATH')
    
    # TTS settings
    tts_model_name: Optional[str] = os.getenv('TTS_MODEL_NAME')
    device: str = os.getenv('DEVICE', 'cpu')  # 'cpu' or 'cuda'
    
    # Sarvam TTS settings
    sarvam_api_key: Optional[str] = os.getenv('SARVAM_API_KEY')
    
    # Supabase settings
    supabase_url: Optional[str] = os.getenv('SUPABASE_URL')
    supabase_key: Optional[str] = os.getenv('SUPABASE_KEY')
