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
    """Configuration class for VOCA application."""
    
    # Supabase
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")
    default_organization_id: str = os.getenv("VOCA_DEFAULT_ORGANIZATION_ID", "")
    
    # SarvamAI
    sarvam_api_key: str = os.getenv("SARVAM_API_KEY", "")
    # SarvamAI language code (default: en-IN)
    sarvam_language: str = os.getenv("SARVAM_LANGUAGE", "en-IN")
    # SarvamAI TTS voice (default: anushka)
    sarvam_voice: str = os.getenv("SARVAM_VOICE", "anushka")

