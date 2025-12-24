import os
from dotenv import load_dotenv
import logging

# Load .env file - try multiple locations
env_loaded = load_dotenv()  # Try current directory
if not env_loaded:
    # Try project root (one level up from src/voca)
    import pathlib
    project_root = pathlib.Path(__file__).parent.parent.parent
    env_path = project_root / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        env_loaded = True

logger = logging.getLogger(__name__)
if env_loaded:
    logger.debug("Environment variables loaded from .env file")
else:
    logger.warning("No .env file found - using system environment variables only")


class Config:
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    llm_temperature: float = float(os.getenv("VOCA_LLM_TEMPERATURE", "0.7"))
    llm_max_tokens: int = int(os.getenv("VOCA_LLM_MAX_TOKENS", "256"))
    llm_timeout_sec: float = float(os.getenv("VOCA_LLM_TIMEOUT", "30"))
    llm_retries: int = int(os.getenv("VOCA_LLM_RETRIES", "3"))
    device: str = os.getenv("VOCA_DEVICE", "cpu")
    sample_rate: int = int(os.getenv("VOCA_SAMPLE_RATE", "16000"))

    # Supabase
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")
    default_organization_id: str = os.getenv("VOCA_DEFAULT_ORGANIZATION_ID", "")
    
    # Deepgram
    deepgram_api_key: str = os.getenv("DEEPGRAM_API_KEY", "")
    # Deepgram keyterms for better accuracy (comma-separated list)
    # Example: "Yash Verma,vermayash849,John Doe,johndoe@example.com"
    deepgram_keyterms: str = os.getenv("DEEPGRAM_KEYTERMS", "")
    
    # Audio storage (for Media Streams recording only, not TTS)
    audio_storage_enabled: bool = os.getenv("VOCA_AUDIO_STORAGE_ENABLED", "0") in ("1", "true", "TRUE", "yes", "Yes")


