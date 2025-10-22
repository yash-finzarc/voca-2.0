#!/usr/bin/env python3
"""
Test script for Twilio VOCA integration.
Tests the complete integration of VOCA AI with Twilio voice calls.
"""
import os
import sys
import time
import logging
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from voca.twilio_app import TwilioVocaApp
from voca.config import Config

# Load environment variables
load_dotenv()

def setup_logging():
    """Setup logging for the test."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def test_configuration():
    """Test that all required configuration is present."""
    logger = logging.getLogger(__name__)
    
    logger.info("Testing configuration...")
    
    # Check Gemini API key
    if not Config.gemini_api_key:
        logger.error("❌ GEMINI_API_KEY not found!")
        return False
    else:
        logger.info("✅ GEMINI_API_KEY found")
    
    # Check Twilio configuration
    from voca.twilio_config import get_twilio_config
    twilio_config = get_twilio_config()
    
    if not twilio_config.validate():
        logger.error("❌ Twilio configuration incomplete!")
        logger.error("Required: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER")
        return False
    else:
        logger.info("✅ Twilio configuration found")
    
    return True

def test_voca_models():
    """Test that VOCA models can be loaded."""
    logger = logging.getLogger(__name__)
    
    logger.info("Testing VOCA models...")
    
    try:
        from voca.orchestrator import VocaOrchestrator
        
        # Create orchestrator
        orchestrator = VocaOrchestrator()
        
        # Test model loading
        logger.info("Loading VOCA models...")
        orchestrator.ensure_models_loaded()
        
        if orchestrator.models_ready():
            logger.info("✅ VOCA models loaded successfully")
            return True
        else:
            logger.error("❌ VOCA models not ready")
            return False
            
    except Exception as e:
        logger.error(f"❌ Failed to load VOCA models: {e}")
        return False

def test_twilio_integration():
    """Test Twilio integration."""
    logger = logging.getLogger(__name__)
    
    logger.info("Testing Twilio integration...")
    
    try:
        from voca.twilio_voice import TwilioCallManager
        from voca.orchestrator import VocaOrchestrator
        
        # Create orchestrator
        orchestrator = VocaOrchestrator()
        
        # Create call manager
        call_manager = TwilioCallManager(orchestrator)
        
        logger.info("✅ Twilio integration components created successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Twilio integration failed: {e}")
        return False

def run_integration_test():
    """Run the complete integration test."""
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 Starting Twilio VOCA Integration Test")
    logger.info("=" * 50)
    
    # Test 1: Configuration
    if not test_configuration():
        logger.error("❌ Configuration test failed!")
        return False
    
    # Test 2: VOCA Models
    if not test_voca_models():
        logger.error("❌ VOCA models test failed!")
        return False
    
    # Test 3: Twilio Integration
    if not test_twilio_integration():
        logger.error("❌ Twilio integration test failed!")
        return False
    
    logger.info("=" * 50)
    logger.info("✅ All tests passed! Twilio VOCA integration is ready!")
    logger.info("")
    logger.info("To start the application, run:")
    logger.info("python -m src.voca.twilio_app")
    logger.info("")
    logger.info("Or use the main entry point:")
    logger.info("python test_twilio_voca_integration.py --start")
    
    return True

def start_application():
    """Start the Twilio VOCA application."""
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 Starting Twilio VOCA Application...")
    
    try:
        app = TwilioVocaApp()
        app.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Application error: {e}")
        return False
    
    return True

def main():
    """Main function."""
    logger = setup_logging()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--start':
        # Start the application
        if run_integration_test():
            start_application()
    else:
        # Just run tests
        run_integration_test()

if __name__ == "__main__":
    main()
