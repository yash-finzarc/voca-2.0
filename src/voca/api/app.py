import asyncio
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.voca.api.routes import routers
from src.voca.api.state import app_state, log_broadcaster
from src.voca.config import Config

app = FastAPI(title="VOCA API", description="API for VOCA AI Voice Assistant", version="1.0.0")

_cors_origins_env = os.getenv("CORS_ORIGINS", "")
if _cors_origins_env:
    _cors_origins = [origin.strip() for origin in _cors_origins_env.split(",")]
else:
    _cors_origins = [
        "https://voca-frontend-self.vercel.app",
        "http://localhost:3000",
        "http://localhost:3001",
    ]

logger = logging.getLogger(__name__)
logger.info(f"CORS allowed origins: {_cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

for router in routers:
    app.include_router(router)


async def model_info_logger():
    """Background task to periodically log real-time model information."""
    logger = logging.getLogger(__name__)
    while True:
        try:
            await asyncio.sleep(30)  # Log every 30 seconds
            model_info = app_state.get_model_info()
            
            # Log STT model info (only if connection is active)
            if model_info.get("stt"):
                stt_info = model_info["stt"]
                if stt_info.get("model") and stt_info.get("is_ready"):
                    logger.info(f"STT Model: {stt_info.get('model')} (Language: {stt_info.get('language', 'N/A')}, Ready: {stt_info.get('is_ready', False)})")
            
            # Log TTS model info
            if model_info.get("tts"):
                tts_info = model_info["tts"]
                if tts_info.get("model"):
                    logger.info(f"TTS Model: {tts_info.get('model')} (Format: {tts_info.get('output_format', 'N/A')}, Ready: {tts_info.get('is_ready', False)})")
            
            # Log LLM model info
            if model_info.get("llm"):
                llm_info = model_info["llm"]
                if llm_info.get("model"):
                    logger.info(f"LLM Model: {llm_info.get('model')}")
                    
        except Exception as e:
            logger.error(f"Error in model info logger: {e}")
            await asyncio.sleep(60)  # Wait longer on error


@app.on_event("startup")
async def startup_event():
    """Initialize components on startup."""
    logger = logging.getLogger(__name__)
    logger.info("VOCA API server starting up")

    try:
        # Get orchestrator - don't load STT at startup (it will be created during calls)
        # Only load TTS if available since it doesn't need a persistent connection
        orchestrator = app_state.get_orchestrator()
        if Config.deepgram_api_key:
            try:
                # Only load TTS at startup, STT will be created lazily during calls
                if not orchestrator.tts:
                    from src.voca.deepgramtts import DeepgramTTS
                    orchestrator.tts = DeepgramTTS()
                    orchestrator.tts.load()
                    logger.debug("TTS loaded at startup")
            except Exception as e:
                logger.debug(f"Could not load TTS at startup: {e}")
        
        twilio_manager = app_state.get_twilio_manager()
        if not twilio_manager:
            logger.warning("Twilio manager not available (Twilio not configured)")
    except Exception as e:
        logger.error(f"Error initializing components: {e}")

    asyncio.create_task(log_broadcaster())
    asyncio.create_task(model_info_logger())
    
    # Log initial model info after a short delay to allow models to initialize
    async def log_initial_models():
        await asyncio.sleep(1)  # Give models time to initialize
        try:
            model_info = app_state.get_model_info()
            # Only log STT if it's actually connected (will be created during calls)
            if model_info.get("stt") and model_info["stt"].get("model") and model_info["stt"].get("is_connected"):
                logger.info(f"Active STT: {model_info['stt']['model']} (Language: {model_info['stt'].get('language', 'N/A')})")
            if model_info.get("tts") and model_info["tts"].get("model"):
                logger.info(f"Active TTS: {model_info['tts']['model']} (Format: {model_info['tts'].get('output_format', 'N/A')})")
            if model_info.get("llm") and model_info["llm"].get("model"):
                logger.info(f"Active LLM: {model_info['llm']['model']}")
        except Exception as e:
            logger.debug(f"Could not get initial model info: {e}")
    
    asyncio.create_task(log_initial_models())


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger = logging.getLogger(__name__)
    logger.info("VOCA API server shutting down...")

