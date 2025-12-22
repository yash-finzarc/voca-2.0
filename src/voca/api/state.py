import asyncio
import logging
import os
import threading
from datetime import datetime
from queue import Queue, Empty
from typing import Optional, List, Dict, Any

from fastapi import WebSocket

from src.voca.config import Config
from src.voca.deepgram_twilio_handler import DeepgramCallManager
from src.voca.orchestrator import VocaOrchestrator
from src.voca.twilio_config import get_twilio_config
from src.voca.twilio_voice import TwilioCallManager


class AppState:
    def __init__(self):
        self.orchestrator: Optional[VocaOrchestrator] = None
        self.twilio_manager: Optional[TwilioCallManager] = None
        self.log_queue: Queue = Queue()
        self.is_twilio_server_running: bool = False
        self.is_continuous_call_running: bool = False
        self.continuous_call_thread: Optional[threading.Thread] = None

    def get_orchestrator(self) -> VocaOrchestrator:
        if self.orchestrator is None:
            self.orchestrator = VocaOrchestrator(on_log=self._log_callback)
        return self.orchestrator

    def get_twilio_manager(self):
        """Get Twilio call manager, preferring Deepgram if API key is configured."""
        if self.twilio_manager is None:
            config = get_twilio_config()
            if not config.validate():
                return None

            logger = logging.getLogger(__name__)

            # Diagnostic: Check if Deepgram API key is configured
            deepgram_key_env = os.getenv("DEEPGRAM_API_KEY", "")
            deepgram_key_config = Config.deepgram_api_key
            deepgram_key = deepgram_key_config or deepgram_key_env

            logger.info("=" * 80)
            logger.info("🔍 Checking Deepgram Configuration...")
            logger.info(f"   - os.getenv('DEEPGRAM_API_KEY'): {'YES' if deepgram_key_env else 'NO'} ({len(deepgram_key_env)} chars)")
            logger.info(f"   - Config.deepgram_api_key: {'YES' if deepgram_key_config else 'NO'} ({len(deepgram_key_config)} chars)")
            logger.info(f"   - Using key: {'YES' if deepgram_key else 'NO'}")

            if deepgram_key:
                logger.info(f"   - Key length: {len(deepgram_key)} characters")
                logger.info(f"   - Key preview: {'*' * 20}...{deepgram_key[-4:] if len(deepgram_key) > 4 else '****'}")
            else:
                logger.warning("   ⚠️  DEEPGRAM_API_KEY is empty or not set in .env file")
                logger.warning("   💡 Make sure .env file is in the project root directory")
                logger.warning("   💡 Check that the variable name is exactly: DEEPGRAM_API_KEY")
                # Check if .env file exists
                import pathlib

                project_root = pathlib.Path(__file__).parent.parent.parent
                env_file = project_root / ".env"
                if env_file.exists():
                    logger.info(f"   ✓ Found .env file at: {env_file}")
                    # Check if DEEPGRAM_API_KEY is in the file
                    try:
                        with open(env_file, "r") as f:
                            content = f.read()
                            if "DEEPGRAM_API_KEY" in content:
                                logger.warning("   ⚠️  DEEPGRAM_API_KEY found in .env but value is empty or has spaces")
                                logger.warning("   💡 Make sure the format is: DEEPGRAM_API_KEY=your_key_here (no spaces around =)")
                            else:
                                logger.warning("   ⚠️  DEEPGRAM_API_KEY not found in .env file")
                                logger.warning("   💡 Add this line to .env: DEEPGRAM_API_KEY=your_deepgram_api_key")
                    except Exception as e:
                        logger.error(f"   ❌ Error reading .env file: {e}")
                else:
                    logger.warning(f"   ⚠️  .env file not found at: {env_file}")
                    logger.warning("   💡 Create a .env file in the project root with: DEEPGRAM_API_KEY=your_key")
            logger.info("=" * 80)

            # Check if Deepgram API key is configured (use the combined value)
            if deepgram_key and deepgram_key.strip():
                # Update Config if we found it in environment but not in Config
                if not Config.deepgram_api_key and deepgram_key_env:
                    Config.deepgram_api_key = deepgram_key_env
                    logger.info("   ✓ Loaded DEEPGRAM_API_KEY from environment")

                try:
                    logger.info("=" * 80)
                    logger.info("🔵 DEEPGRAM MODE: Using Deepgram STT and TTS")
                    logger.info(f"   - Deepgram API Key: {'*' * 20}...{deepgram_key[-4:] if len(deepgram_key) > 4 else '****'}")
                    if Config.deepgram_keyterms:
                        keyterms_list = [k.strip() for k in Config.deepgram_keyterms.split(",") if k.strip()]
                        logger.info(f"   - Keyterms configured: {len(keyterms_list)} terms")
                        logger.info(f"   - Keyterms: {', '.join(keyterms_list[:5])}{'...' if len(keyterms_list) > 5 else ''}")
                    else:
                        logger.info("   - No keyterms configured")
                    logger.info("=" * 80)
                    self.twilio_manager = DeepgramCallManager(self.get_orchestrator())
                except Exception as e:
                    logger.error("=" * 80)
                    logger.error(f"❌ Failed to create DeepgramCallManager: {e}")
                    logger.warning("⚠️  Falling back to Twilio STT/TTS")
                    logger.info("=" * 80)
                    try:
                        self.twilio_manager = TwilioCallManager(self.get_orchestrator())
                    except Exception as e2:
                        logger.error(f"Failed to create TwilioCallManager: {e2}")
                        return None
            else:
                # No Deepgram API key, use Twilio STT/TTS
                try:
                    logger.info("=" * 80)
                    logger.info("🟡 TWILIO MODE: Using Twilio STT and TTS")
                    logger.info("   - No Deepgram API key found in environment")
                    logger.info("   - To use Deepgram, set DEEPGRAM_API_KEY in .env file")
                    logger.info("=" * 80)
                    self.twilio_manager = TwilioCallManager(self.get_orchestrator())
                except Exception as e:
                    logger.error(f"Failed to create TwilioCallManager: {e}")
                    return None
        else:
            # Manager already exists, log which type it is
            logger = logging.getLogger(__name__)
            manager_type = type(self.twilio_manager).__name__
            if manager_type == "DeepgramCallManager":
                logger.debug("🔵 Using existing DeepgramCallManager (Deepgram STT/TTS)")
            else:
                logger.debug("🟡 Using existing TwilioCallManager (Twilio STT/TTS)")

        return self.twilio_manager

    def _log_callback(self, message: str):
        """Callback for log messages."""
        log_entry = {"timestamp": datetime.now().isoformat(), "message": message}
        self.log_queue.put(log_entry)


app_state = AppState()

# WebSocket connections for real-time logs
active_websockets: List[WebSocket] = []


async def broadcast_log(log_entry: Dict[str, str]):
    """Broadcast log entry to all connected WebSocket clients."""
    if active_websockets:
        disconnected = []
        for ws in active_websockets:
            try:
                await ws.send_json(log_entry)
            except Exception:
                disconnected.append(ws)

        # Remove disconnected clients
        for ws in disconnected:
            active_websockets.remove(ws)


async def log_broadcaster():
    """Background task to broadcast logs to WebSocket clients."""
    while True:
        try:
            await asyncio.sleep(0.1)
            if not app_state.log_queue.empty():
                log_entry = app_state.log_queue.get_nowait()
                await broadcast_log(log_entry)
        except Exception as e:
            logging.getLogger(__name__).error(f"Log broadcaster error: {e}")
            await asyncio.sleep(0.5)

