"""
Main FastAPI server entry point for VOCA frontend integration.
Run this file to start the API server for the web frontend.
"""
import logging
import uvicorn

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the API server."""
    logger.info("Starting VOCA API Server...")
    logger.info("API will be available at http://localhost:8000")
    logger.info("API Documentation at http://localhost:8000/docs")
    logger.info("Access API docs at http://localhost:8000/docs")
    
    # Run the FastAPI app with uvicorn using import string format for reload
    uvicorn.run(
        "src.voca.api:app",  # Use import string format for reload support
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=True  # Enable auto-reload for development
    )


if __name__ == "__main__":
    main()

