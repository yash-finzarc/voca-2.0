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


