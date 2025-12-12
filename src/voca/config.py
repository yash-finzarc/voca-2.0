import os
from dotenv import load_dotenv


load_dotenv()


class Config:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    llm_temperature: float = float(os.getenv("VOCA_LLM_TEMPERATURE", "0.7"))
    llm_max_tokens: int = int(os.getenv("VOCA_LLM_MAX_TOKENS", "256"))
    openai_base_url: str = os.getenv("VOCA_OPENAI_BASE_URL", "")
    openai_extra_headers: str = os.getenv("VOCA_OPENAI_EXTRA_HEADERS", "")  # JSON string of headers
    llm_timeout_sec: float = float(os.getenv("VOCA_LLM_TIMEOUT", "30"))
    llm_retries: int = int(os.getenv("VOCA_LLM_RETRIES", "3"))
    openai_insecure: bool = os.getenv("VOCA_OPENAI_INSECURE", "0") in ("1", "true", "TRUE", "yes", "Yes")
    device: str = os.getenv("VOCA_DEVICE", "cpu")
    sample_rate: int = int(os.getenv("VOCA_SAMPLE_RATE", "16000"))

    # STT
    stt_model_path: str = os.getenv("VOCA_STT_MODEL_PATH", "models/stt/model.tflite")
    stt_scorer_path: str = os.getenv("VOCA_STT_SCORER_PATH", "models/stt/kenlm.scorer")

    # TTS
    tts_model_name: str = os.getenv("VOCA_TTS_MODEL_NAME", "tts_models/en/ljspeech/tacotron2-DDC")

    # Supabase
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")
    default_organization_id: str = os.getenv("VOCA_DEFAULT_ORGANIZATION_ID", "")

    # Audio Debug Storage
    audio_storage_enabled: bool = os.getenv("VOCA_DEBUG_AUDIO_STORAGE", "false").lower() in ("1", "true", "yes")
    audio_storage_dir: str = os.getenv("VOCA_AUDIO_LOG_DIR", "audio_logs")
    
    # Deepgram STT (via Twilio)
    deepgram_api_key: str = os.getenv("DEEPGRAM_API_KEY", "")
    twilio_stt_model: str = os.getenv("TWILIO_STT_MODEL", "deepgram_nova-3")  # Options: deepgram_nova-3, deepgram_nova-2, etc.
    twilio_stt_language: str = os.getenv("TWILIO_STT_LANGUAGE", "hi-IN")  # Language code for STT (e.g., hi-IN for Hindi, en-US for English, or "multi" for auto-detection)




