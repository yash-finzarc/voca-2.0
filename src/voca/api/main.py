"""
Main FastAPI application for VOCA API.
Imports and registers all route modules.
"""
import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.voca.api.app_state import app_state
from src.voca.api.routes import (
    health,
    local_voice,
    twilio,
    logs,
    webhooks,
    system_prompt,
    organizations,
)

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="VOCA API",
    description="API for VOCA voice AI system",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://voca-frontend-self.vercel.app",  # Vercel production deployment
        "http://localhost:3000",  # Local development
        "http://localhost:3001",  # Alternative local port
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Register routers
app.include_router(health.router)
app.include_router(local_voice.router)
app.include_router(twilio.router)
app.include_router(logs.router)
app.include_router(webhooks.router)
app.include_router(system_prompt.router)
app.include_router(organizations.router)


@app.on_event("startup")
async def startup_event():
    """Initialize components on startup."""
    logger.info("VOCA API server starting up...")
    
    # Start log broadcaster task
    asyncio.create_task(logs.log_broadcaster())
    
    logger.info("VOCA API server started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("VOCA API server shutting down...")
    
    # Stop Twilio server if running
    if app_state.is_twilio_server_running and app_state.twilio_manager:
        try:
            app_state.twilio_manager.stop()
        except Exception as e:
            logger.error(f"Error stopping Twilio server: {e}")
    
    logger.info("VOCA API server shut down")

