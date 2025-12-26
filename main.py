"""
Main FastAPI server entry point for VOCA frontend integration.
Run this file to start the API server for the web frontend.

This module exports the FastAPI app instance so it can be used with:
- python main.py (runs via main() function)
- uvicorn main:app (direct uvicorn invocation for production/systemd)
"""
import logging
import sys
import uvicorn

# Suppress Google/gRPC/absl warnings before any imports
from dotenv import load_dotenv
import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"

load_dotenv()

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

# Disable Twilio HTTP client logging to reduce log noise
logging.getLogger("twilio.http_client").setLevel(logging.WARNING)
logging.getLogger("twilio.rest").setLevel(logging.WARNING)
logging.getLogger("twilio").setLevel(logging.WARNING)

# Suppress Google/gRPC/absl warnings and errors
logging.getLogger("absl").setLevel(logging.ERROR)
logging.getLogger("grpc").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# Import the FastAPI app instance so it can be used with uvicorn main:app
from src.voca.api.app import app

# Export app for uvicorn: uvicorn main:app
__all__ = ["app"]


def main():
    """Main entry point for the API server."""
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

