#!/usr/bin/env python3
"""
Startup script for Twilio VOCA integration.
This script provides an easy way to start the VOCA application with Twilio voice calls.
"""
import os
import sys
import subprocess
import time
import logging
from pathlib import Path

def setup_logging():
    """Setup logging for the startup script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def check_environment():
    """Check if the environment is properly set up."""
    logger = logging.getLogger(__name__)
    
    # Check if .env file exists
    env_file = Path('.env')
    if not env_file.exists():
        logger.error("❌ .env file not found!")
        logger.error("Please create a .env file with your credentials.")
        logger.error("See docs/TWILIO_VOCA_SETUP.md for details.")
        return False
    
    # Check if required directories exist
    src_dir = Path('src')
    if not src_dir.exists():
        logger.error("❌ src directory not found!")
        logger.error("Please run this script from the project root directory.")
        return False
    
    logger.info("✅ Environment check passed")
    return True

def check_dependencies():
    """Check if required dependencies are installed."""
    logger = logging.getLogger(__name__)
    
    try:
        import fastapi
        import uvicorn
        import twilio
        import google.generativeai
        import numpy
        import sounddevice
        logger.info("✅ All required dependencies are installed")
        return True
    except ImportError as e:
        logger.error(f"❌ Missing dependency: {e}")
        logger.error("Please run: pip install -r requirements.txt")
        return False

def start_ngrok():
    """Start ngrok in the background."""
    logger = logging.getLogger(__name__)
    
    try:
        # Check if ngrok is already running
        result = subprocess.run(['ngrok', 'version'], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("✅ ngrok is available")
            
            # Start ngrok in background
            logger.info("🚀 Starting ngrok...")
            subprocess.Popen(['ngrok', 'http', '5000'], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
            time.sleep(3)  # Give ngrok time to start
            logger.info("✅ ngrok started on port 5000")
            return True
        else:
            logger.warning("⚠️ ngrok not found, you'll need to set up webhooks manually")
            return False
    except FileNotFoundError:
        logger.warning("⚠️ ngrok not found, you'll need to set up webhooks manually")
        return False

def start_voca_application():
    """Start the VOCA application."""
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 Starting Twilio VOCA Application...")
    
    try:
        # Run the test script with --start flag
        result = subprocess.run([
            sys.executable, 'testing/test_twilio_voca_integration.py', '--start'
        ], cwd=os.getcwd())
        
        if result.returncode == 0:
            logger.info("✅ Application started successfully")
            return True
        else:
            logger.error("❌ Application failed to start")
            return False
            
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        return True
    except Exception as e:
        logger.error(f"❌ Error starting application: {e}")
        return False

def main():
    """Main function."""
    logger = setup_logging()
    
    logger.info("🎯 Twilio VOCA Integration Startup Script")
    logger.info("=" * 50)
    
    # Step 1: Check environment
    if not check_environment():
        return False
    
    # Step 2: Check dependencies
    if not check_dependencies():
        return False
    
    # Step 3: Start ngrok (optional)
    start_ngrok()
    
    # Step 4: Start VOCA application
    logger.info("")
    logger.info("🚀 Starting VOCA Application...")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 50)
    
    return start_voca_application()

if __name__ == "__main__":
    try:
        success = main()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
