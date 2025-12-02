"""
Main FastAPI server entry point for VOCA frontend integration.
Run this file to start the API server for the web frontend.
"""
import logging
import sys
import uvicorn

# Setup comprehensive logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Explicitly use stdout
    ],
    force=True  # Override any existing configuration
)

# Set log level for all VOCA modules
logging.getLogger("src.voca").setLevel(logging.INFO)
logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the API server."""
    logger.info("=" * 80)
    logger.info("Starting VOCA API Server...")
    logger.info("=" * 80)
    logger.info("API will be available at http://localhost:8000")
    logger.info("API Documentation at http://localhost:8000/docs")
    logger.info("Access API docs at http://localhost:8000/docs")
    logger.info("=" * 80)
    
    # Run the FastAPI app with uvicorn using import string format for reload
    uvicorn.run(
        "src.voca.api:app",  # Use import string format for reload support
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=True,  # Enable auto-reload for development
        log_config=None,  # Use our custom logging config
        use_colors=True  # Enable colored output
    )


if __name__ == "__main__":
    main()

