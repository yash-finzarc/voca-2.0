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

# Supabase
supabase_url: str = os.getenv("SUPABASE_URL", "")
supabase_key: str = os.getenv("SUPABASE_KEY", "")
default_organization_id: str = os.getenv("VOCA_DEFAULT_ORGANIZATION_ID", "")

# Deepgram
deepgram_api_key: str = os.getenv("DEEPGRAM_API_KEY", "")
# Deepgram keyterms for better accuracy (comma-separated list)
# Example: "Yash Verma,vermayash849,John Doe,johndoe@example.com"
deepgram_keyterms: str = os.getenv("DEEPGRAM_KEYTERMS", "")

# Optional: Gemini/LLM config (for future use)
gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "8192"))


class Config:
    """Configuration class containing all environment variables."""
    # Supabase
    supabase_url: str = supabase_url
    supabase_key: str = supabase_key
    default_organization_id: str = default_organization_id
    
    # Deepgram
    deepgram_api_key: str = deepgram_api_key
    deepgram_keyterms: str = deepgram_keyterms
    
    # Optional: Gemini/LLM config
    gemini_api_key: str = gemini_api_key
    llm_temperature: float = llm_temperature
    llm_max_tokens: int = llm_max_tokens

