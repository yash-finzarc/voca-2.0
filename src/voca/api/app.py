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


@app.on_event("startup")
async def startup_event():
    """Initialize components on startup."""
    logger = logging.getLogger(__name__)
    logger.info("=" * 80)
    logger.info("🚀 VOCA API Server Startup")
    logger.info("=" * 80)

    try:
        twilio_manager = app_state.get_twilio_manager()
        if twilio_manager:
            manager_type = type(twilio_manager).__name__
            if manager_type == "DeepgramCallManager":
                logger.info("✅ Service Mode: DEEPGRAM STT/TTS")
                logger.info("   📊 Service Details:")
                logger.info("      - Speech-to-Text: Deepgram Nova-3 (Multilingual: English India + Hindi)")
                logger.info("      - Text-to-Speech: Deepgram Aura")
                if Config.deepgram_keyterms:
                    keyterms_list = [k.strip() for k in Config.deepgram_keyterms.split(",") if k.strip()]
                    logger.info(f"      - Keyterms: {len(keyterms_list)} configured")
            else:
                logger.info("✅ Service Mode: TWILIO STT/TTS")
                logger.info("   📊 Service Details:")
                logger.info("      - Speech-to-Text: Twilio Speech Recognition (TwiML)")
                logger.info("      - Text-to-Speech: Twilio Text-to-Speech (TwiML)")
        else:
            logger.warning("⚠️  Twilio manager not available (Twilio not configured)")
    except Exception as e:
        logger.error(f"❌ Error checking service mode: {e}")

    logger.info("=" * 80)
    logger.info("VOCA API server starting up...")

    asyncio.create_task(log_broadcaster())

    logger.info("Server running on Linode: http://172.105.50.83:8000")
    app_state._log_callback("Server running on Linode: http://172.105.50.83:8000")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger = logging.getLogger(__name__)
    logger.info("VOCA API server shutting down...")

