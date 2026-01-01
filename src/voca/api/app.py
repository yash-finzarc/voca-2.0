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

# Add middleware to log WebSocket connection attempts
@app.middleware("http")
async def log_websocket_attempts(request, call_next):
    """Log WebSocket upgrade attempts for debugging."""
    if request.url.path.startswith("/media/") or request.url.path.startswith("/webrtc/") or request.url.path == "/twilio":
        logger.info(f"[WEBSOCKET_DEBUG] ===== WebSocket upgrade attempt =====")
        logger.info(f"[WEBSOCKET_DEBUG] Method: {request.method}")
        logger.info(f"[WEBSOCKET_DEBUG] Path: {request.url.path}")
        logger.info(f"[WEBSOCKET_DEBUG] Client: {request.client}")
        logger.info(f"[WEBSOCKET_DEBUG] Headers: {dict(request.headers)}")
    response = await call_next(request)
    if request.url.path.startswith("/media/") or request.url.path.startswith("/webrtc/") or request.url.path == "/twilio":
        logger.info(f"[WEBSOCKET_DEBUG] Response status: {response.status_code}")
    return response

for router in routers:
    app.include_router(router)



# Model info logger removed - get_model_info() function has been deleted
# async def model_info_logger():
#     """Background task to periodically log real-time model information."""
#     logger = logging.getLogger(__name__)
#     while True:
#         try:
#             await asyncio.sleep(30)  # Log every 30 seconds
#             model_info = app_state.get_model_info()
#             
#             # Log STT model info (only if connection is active)
#             if model_info.get("stt"):
#                 stt_info = model_info["stt"]
#                 if stt_info.get("model") and stt_info.get("is_ready"):
#                     logger.info(f"STT Model: {stt_info.get('model')} (Language: {stt_info.get('language', 'N/A')}, Ready: {stt_info.get('is_ready', False)})")
#             
#             # Log TTS model info
#             if model_info.get("tts"):
#                 tts_info = model_info["tts"]
#                 if tts_info.get("model"):
#                     logger.info(f"TTS Model: {tts_info.get('model')} (Format: {tts_info.get('output_format', 'N/A')}, Ready: {tts_info.get('is_ready', False)})")
#             
#             # Log LLM model info
#             if model_info.get("llm"):
#                 llm_info = model_info["llm"]
#                 if llm_info.get("model"):
#                     logger.info(f"LLM Model: {llm_info.get('model')}")
#                     
#         except Exception as e:
#             logger.error(f"Error in model info logger: {e}")
#             await asyncio.sleep(60)  # Wait longer on error


@app.on_event("startup")
async def startup_event():
    """Initialize components on startup."""
    logger = logging.getLogger(__name__)
    logger.info("VOCA API server starting up")
    
    # Log Media Streams and WebRTC WebSocket routes for debugging
    logger.info("[ROUTE_DEBUG] Checking for Media Streams and WebRTC WebSocket routes:")
    for route in app.routes:
        if hasattr(route, 'path') and ('/media/' in route.path or '/webrtc/' in route.path or route.path == '/twilio'):
            route_type = "WebSocket" if hasattr(route, 'endpoint') and 'websocket' in str(type(route)).lower() else "HTTP"
            logger.info(f"[ROUTE_DEBUG] Found route: {route.path} ({route_type})")
    
    # Disable Twilio HTTP client logging to reduce log noise
    logging.getLogger("twilio.http_client").setLevel(logging.WARNING)
    logging.getLogger("twilio.rest").setLevel(logging.WARNING)
    logging.getLogger("twilio").setLevel(logging.WARNING)
    
    # Suppress Google/gRPC/absl warnings and errors
    logging.getLogger("absl").setLevel(logging.ERROR)
    logging.getLogger("grpc").setLevel(logging.ERROR)
    import os
    os.environ["GRPC_VERBOSITY"] = "ERROR"
    os.environ["GLOG_minloglevel"] = "2"

    try:
        # Verify Twilio is configured (custom LLM pipeline handles everything via WebSocket)
        twilio_config = app_state.get_twilio_manager()
        if not twilio_config:
            logger.warning("Twilio not configured (check environment variables)")
        else:
            logger.info("Twilio configuration verified - using custom LLM pipeline")
    except Exception as e:
        logger.error(f"Error initializing components: {e}")

    asyncio.create_task(log_broadcaster())
    # asyncio.create_task(model_info_logger())  # Commented out - model_info_logger removed
    
    # Log initial model info removed - get_model_info() function has been deleted
    # async def log_initial_models():
    #     await asyncio.sleep(2)  # Give models time to fully initialize connections
    #     try:
    #         model_info = app_state.get_model_info()
    #         # Log STT model info
    #         if model_info.get("stt") and model_info["stt"].get("model"):
    #             logger.info(f"Active STT: {model_info['stt']['model']} (Language: {model_info['stt'].get('language', 'N/A')}, Connected: {model_info['stt'].get('is_connected', False)})")
    #         if model_info.get("tts") and model_info["tts"].get("model"):
    #             logger.info(f"Active TTS: {model_info['tts']['model']} (Format: {model_info['tts'].get('output_format', 'N/A')})")
    #         if model_info.get("llm") and model_info["llm"].get("model"):
    #             logger.info(f"Active LLM: {model_info['llm']['model']}")
    #     except Exception as e:
    #         logger.debug(f"Could not get initial model info: {e}")
    # 
    # asyncio.create_task(log_initial_models())


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger = logging.getLogger(__name__)
    logger.info("VOCA API server shutting down...")

