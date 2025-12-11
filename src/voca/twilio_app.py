"""
Main application for Twilio voice calls with VOCA AI integration.
This is the entry point for running VOCA with Twilio voice calls.
"""
import logging
import signal
import sys
import time
from typing import Optional

from .orchestrator import VocaOrchestrator
from .twilio_voice import TwilioCallManager
from .websocket_handler import TwilioWebSocketHandler, TwilioMediaStreamHandler
from .config import Config


class TwilioVocaApp:
    """Main application class for Twilio voice calls with VOCA AI."""
    
    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port
        self.logger = logging.getLogger(__name__)
        
        # Initialize VOCA orchestrator
        self.orchestrator = VocaOrchestrator(on_log=self._log_callback)
        
        # Initialize Twilio components
        self.call_manager = TwilioCallManager(self.orchestrator)
        self.websocket_handler = TwilioWebSocketHandler(self.orchestrator)
        self.media_handler = TwilioMediaStreamHandler(self.orchestrator)
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self._running = False
    
    def _log_callback(self, message: str):
        """Log callback for VOCA orchestrator."""
        self.logger.info(f"VOCA: {message}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)
    
    def start(self):
        """Start the Twilio VOCA application."""
        self.logger.info("Starting Twilio VOCA Application...")
        
        try:
            # Start the call manager (this loads models and starts webhook server)
            self.call_manager.start(self.host, self.port)
            
            self._running = True
            self.logger.info("Twilio VOCA Application started successfully!")
            self.logger.info(f"Webhook URL: http://{self.host}:{self.port}/webhook/voice")
            self.logger.info("Ready to receive calls with real-time AI processing!")
            
            # Keep the application running
            self._run_forever()
            
        except Exception as e:
            self.logger.error(f"Failed to start application: {e}")
            raise
    
    def _run_forever(self):
        """Keep the application running."""
        try:
            while self._running:
                time.sleep(1)
                
                # Log status every 30 seconds
                if int(time.time()) % 30 == 0:
                    status = self.call_manager.get_call_status()
                    self.logger.info(f"Status: {status['active_calls']} active calls, models ready: {status['models_ready']}")
                
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt, shutting down...")
            self.stop()
    
    def stop(self):
        """Stop the application."""
        if self._running:
            self.logger.info("Stopping Twilio VOCA Application...")
            self.call_manager.stop()
            self._running = False
            self.logger.info("Application stopped")
    
    def make_call(self, phone_number: str, message: str = None) -> Optional[str]:
        """Make an outbound call."""
        return self.call_manager.make_call(phone_number, message)
    
    def get_status(self):
        """Get application status."""
        return self.call_manager.get_call_status()


def main():
    """Main entry point for the Twilio VOCA application."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('voca_twilio.log')
        ]
    )
    
    logger = logging.getLogger(__name__)
    
    # Check configuration
    if not Config.gemini_api_key:
        logger.error("GEMINI_API_KEY not found in environment variables!")
        logger.error("Please set your Gemini API key in the environment or .env file")
        sys.exit(1)
    
    # Create and start application
    app = TwilioVocaApp()
    
    try:
        app.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)
    finally:
        app.stop()


if __name__ == "__main__":
    main()
