#!/usr/bin/env python3
"""
Test script for Ultravox realtime speech-to-speech model.
Tests the Ultravox client without Twilio integration.

Usage:
    python test_ultravox_speech_to_speech.py

Requirements:
    - ULTRAVOX_API_KEY in .env file
    - Optional: sounddevice for microphone/speaker access
    - Optional: pyaudio for audio I/O
"""

import asyncio
import sys
import os
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

# Explicitly load .env file from project root
env_path = Path(project_root) / '.env'
if env_path.exists():
    # Load with override to ensure it takes precedence
    load_dotenv(dotenv_path=env_path, override=True)
    print(f"✅ Loaded .env file from: {env_path}")
    
    # Debug: Read and show relevant lines from .env file
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            print(f"📄 Reading .env file (total lines: {len(lines)})")
            ultravox_lines = []
            for i, line in enumerate(lines, 1):
                line_stripped = line.strip()
                # Check if line contains ULTRAVOX (case-insensitive)
                if line_stripped and 'ultravox' in line_stripped.lower():
                    ultravox_lines.append((i, line_stripped))
            
            if ultravox_lines:
                print(f"📄 Found {len(ultravox_lines)} ULTRAVOX line(s) in .env:")
                for line_num, line in ultravox_lines:
                    # Mask the actual key for security
                    if '=' in line:
                        key, value = line.split('=', 1)
                        value = value.strip().strip('"').strip("'")
                        masked_value = value[:10] + '...' + value[-4:] if len(value) > 14 else '***'
                        print(f"   Line {line_num}: {key.strip()}={masked_value}")
                    else:
                        print(f"   Line {line_num}: {line[:50]}...")
            else:
                print(f"⚠️  No ULTRAVOX line found in .env file")
                # Show all lines for debugging
                print(f"   All {len(lines)} lines of .env:")
                for i, line in enumerate(lines, 1):
                    line_stripped = line.strip()
                    # Highlight lines that might be relevant
                    if 'API' in line_stripped.upper() or 'KEY' in line_stripped.upper():
                        print(f"   Line {i}: {line_stripped[:100]}")
                    elif line_stripped and not line_stripped.startswith('#'):
                        print(f"   Line {i}: {line_stripped[:100]}")
    except Exception as e:
        print(f"⚠️  Could not read .env file: {e}")
else:
    # Try loading from current directory
    load_dotenv(override=True)
    print(f"⚠️  .env file not found at {env_path}, trying current directory")

from src.voca.services.ultravox import UltravoxClient
from src.voca.services.ultravox import create_ultravox_call
from src.voca.config import Config

try:
    import websockets
except ImportError:
    websockets = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import audio libraries
try:
    import sounddevice as sd
    import numpy as np
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    logger.warning("sounddevice not available. Microphone/speaker testing disabled.")

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False


class UltravoxTester:
    """Test harness for Ultravox speech-to-speech model."""
    
    def __init__(self):
        self.client = None
        self.audio_output_queue = asyncio.Queue()
        self.transcript_log = []
        self.is_running = False
        
    async def setup_client(self, api_key: str = None, endpoint: str = None):
        """Initialize and connect Ultravox client."""
        logger.info("Initializing Ultravox client...")
        
        # Get API key from parameter, environment, or Config
        if api_key:
            api_key_to_use = api_key
        else:
            api_key_to_use = os.getenv("ULTRAVOX_API_KEY") or Config.ultravox_api_key
        
        # Check API key
        if not api_key_to_use:
            raise ValueError(
                "ULTRAVOX_API_KEY not found in environment. "
                "Please set it in your .env file or pass via --api-key argument."
            )
        
        # Create client with explicit API key
        self.client = UltravoxClient(api_key=api_key_to_use)
        
        # Override endpoint if provided
        if endpoint:
            from src.voca.services import ultravox
            # Convert https:// to wss:// and http:// to ws:// if needed (WebSocket requires ws/wss protocol)
            ws_endpoint = endpoint
            if endpoint.startswith("https://"):
                ws_endpoint = endpoint.replace("https://", "wss://", 1)
                logger.debug(f"Converted https:// to wss://: {ws_endpoint}")
            elif endpoint.startswith("http://"):
                ws_endpoint = endpoint.replace("http://", "ws://", 1)
                logger.debug(f"Converted http:// to ws://: {ws_endpoint}")
            ultravox.ULTRAVOX_WS_ENDPOINT = ws_endpoint
            logger.info(f"Using custom endpoint: {endpoint} → {ws_endpoint}")
        
        # Set up callbacks
        self.client.set_audio_output_callback(self._on_audio_output)
        self.client.set_transcript_callback(self._on_transcript)
        
        # Connect
        logger.info("Connecting to Ultravox...")
        await self.client.connect()
        logger.info("✅ Connected to Ultravox successfully!")
        
    async def _on_audio_output(self, audio_bytes: bytes):
        """Callback for audio output from Ultravox."""
        logger.debug(f"Received audio output: {len(audio_bytes)} bytes")
        await self.audio_output_queue.put(audio_bytes)
        
    async def _on_transcript(self, transcript: str, is_final: bool):
        """Callback for transcript updates."""
        status = "FINAL" if is_final else "INTERIM"
        logger.info(f"[TRANSCRIPT {status}]: {transcript}")
        self.transcript_log.append({"text": transcript, "is_final": is_final})
        
    async def send_audio_chunk(self, audio_data: bytes):
        """Send audio chunk to Ultravox."""
        if self.client and self.client.is_connected:
            await self.client.send_audio(audio_data)
        else:
            logger.warning("Client not connected, cannot send audio")
    
    async def test_with_microphone(self, duration: int = 30):
        """Test with microphone input and speaker output."""
        if not SOUNDDEVICE_AVAILABLE:
            logger.error("sounddevice not available. Cannot test with microphone.")
            logger.info("Install with: pip install sounddevice")
            return
        
        logger.info(f"🎤 Starting microphone test (duration: {duration}s)")
        logger.info("Speak into your microphone. Press Ctrl+C to stop.")
        
        sample_rate = 16000
        chunk_size = 3200  # 200ms at 16kHz
        
        self.is_running = True
        
        # Start audio output handler
        output_task = asyncio.create_task(self._handle_audio_output(sample_rate))
        
        try:
            # Record and send audio
            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype='int16',
                blocksize=chunk_size,
                callback=self._audio_input_callback
            ):
                await asyncio.sleep(duration)
                
        except KeyboardInterrupt:
            logger.info("\n⏹️  Stopping test...")
        finally:
            self.is_running = False
            output_task.cancel()
            try:
                await output_task
            except asyncio.CancelledError:
                pass
    
    def _audio_input_callback(self, indata, frames, time, status):
        """Callback for audio input from microphone."""
        if status:
            logger.warning(f"Audio input status: {status}")
        
        if self.is_running and self.client and self.client.is_connected:
            # Convert numpy array to bytes
            audio_bytes = indata.tobytes()
            # Send asynchronously
            asyncio.create_task(self.send_audio_chunk(audio_bytes))
    
    async def _handle_audio_output(self, sample_rate: int):
        """Handle audio output from Ultravox and play through speaker."""
        if not SOUNDDEVICE_AVAILABLE:
            return
            
        logger.info("🔊 Audio output handler started")
        audio_buffer = []
        
        try:
            while self.is_running or not self.audio_output_queue.empty():
                try:
                    # Get audio with timeout
                    audio_bytes = await asyncio.wait_for(
                        self.audio_output_queue.get(),
                        timeout=0.1
                    )
                    
                    # Convert bytes to numpy array
                    audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
                    audio_buffer.extend(audio_array)
                    
                    # Play when we have enough data (e.g., 100ms)
                    min_samples = sample_rate // 10
                    if len(audio_buffer) >= min_samples:
                        play_data = np.array(audio_buffer[:min_samples], dtype=np.int16)
                        sd.play(play_data, samplerate=sample_rate)
                        audio_buffer = audio_buffer[min_samples:]
                        
                except asyncio.TimeoutError:
                    # Play remaining buffer if any
                    if audio_buffer:
                        play_data = np.array(audio_buffer, dtype=np.int16)
                        sd.play(play_data, samplerate=sample_rate)
                        audio_buffer = []
                    continue
                    
        except asyncio.CancelledError:
            # Play remaining buffer
            if audio_buffer:
                play_data = np.array(audio_buffer, dtype=np.int16)
                sd.play(play_data, samplerate=sample_rate)
            logger.info("Audio output handler stopped")
    
    async def test_with_file(self, input_file: str, output_file: str = None):
        """Test with audio file input."""
        logger.info(f"📁 Testing with audio file: {input_file}")
        
        try:
            import wave
            
            # Read input audio file
            with wave.open(input_file, 'rb') as wf:
                sample_rate = wf.getframerate()
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                
                logger.info(f"Audio file: {sample_rate}Hz, {channels} channels, {sample_width} bytes/sample")
                
                # Read all frames
                audio_data = wf.readframes(wf.getnframes())
                
                # Convert to mono if stereo
                if channels == 2:
                    import struct
                    samples = struct.unpack(f'<{len(audio_data)//2}h', audio_data)
                    mono_samples = []
                    for i in range(0, len(samples), 2):
                        mono_samples.append((samples[i] + samples[i+1]) // 2)
                    audio_data = struct.pack(f'<{len(mono_samples)}h', *mono_samples)
                
                # Send in chunks
                chunk_size = sample_rate * 2 * sample_width // 10  # 100ms chunks
                logger.info("Sending audio to Ultravox...")
                
                for i in range(0, len(audio_data), chunk_size):
                    chunk = audio_data[i:i+chunk_size]
                    await self.send_audio_chunk(chunk)
                    await asyncio.sleep(0.1)  # Small delay between chunks
                
                # Wait for responses
                logger.info("Waiting for responses...")
                await asyncio.sleep(5)
                
                # Save output if requested
                if output_file:
                    await self._save_output_audio(output_file, sample_rate)
                    
        except FileNotFoundError:
            logger.error(f"Audio file not found: {input_file}")
        except Exception as e:
            logger.error(f"Error processing audio file: {e}", exc_info=True)
    
    async def _save_output_audio(self, output_file: str, sample_rate: int):
        """Save audio output to file."""
        import wave
        
        logger.info(f"Saving output audio to: {output_file}")
        audio_chunks = []
        
        # Collect all audio output
        while not self.audio_output_queue.empty():
            try:
                chunk = await asyncio.wait_for(
                    self.audio_output_queue.get(),
                    timeout=0.1
                )
                audio_chunks.append(chunk)
            except asyncio.TimeoutError:
                break
        
        if audio_chunks:
            # Combine all chunks
            combined_audio = b''.join(audio_chunks)
            
            # Save as WAV file
            with wave.open(output_file, 'wb') as wf:
                wf.setnchannels(1)  # Mono
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(combined_audio)
            
            logger.info(f"✅ Saved {len(combined_audio)} bytes to {output_file}")
        else:
            logger.warning("No audio output received to save")
    
    async def test_connection_only(self, api_key: str = None, endpoint: str = None):
        """Test only the connection without audio."""
        logger.info("🔌 Testing connection only...")
        await self.setup_client(api_key=api_key, endpoint=endpoint)
        logger.info("✅ Connection test successful!")
        logger.info("Waiting 5 seconds, then disconnecting...")
        await asyncio.sleep(5)
        await self.cleanup()
    
    async def cleanup(self):
        """Clean up resources."""
        if self.client:
            logger.info("Disconnecting from Ultravox...")
            await self.client.stop()
            logger.info("✅ Disconnected")


async def main(args=None):
    """Main test function."""
    if args is None:
        parser = argparse.ArgumentParser(description="Test Ultravox speech-to-speech model")
        parser.add_argument(
            '--mode',
            choices=['mic', 'file', 'connection', 'create-call'],
            default='connection',
            help='Test mode: mic (microphone), file (audio file), connection (connection only), or create-call (HTTP POST to create Ultravox call and get joinUrl)'
        )
        parser.add_argument(
            '--input-file',
            type=str,
            help='Input audio file (WAV format) for file mode'
        )
        parser.add_argument(
            '--output-file',
            type=str,
            help='Output audio file to save response (for file mode)'
        )
        parser.add_argument(
            '--duration',
            type=int,
            default=30,
            help='Duration in seconds for microphone test (default: 30)'
        )
        parser.add_argument(
            '--api-key',
            type=str,
            help='Ultravox API key (overrides .env file)'
        )
        parser.add_argument(
            '--endpoint',
            type=str,
            help='Ultravox WebSocket endpoint URL (overrides default)'
        )
        parser.add_argument(
            '--organization-id',
            type=str,
            default=None,
            help='Organization ID used to fetch system prompt from Supabase (defaults to Config.default_organization_id)'
        )
        parser.add_argument(
            '--discover-endpoint',
            action='store_true',
            help='Try multiple endpoint patterns to find the correct one'
        )
        args = parser.parse_args()
    
    # Get API key and endpoint from args or environment
    api_key = args.api_key if args and args.api_key else None
    if not api_key:
        api_key = os.getenv("ULTRAVOX_API_KEY") or Config.ultravox_api_key
    
    endpoint = args.endpoint if args and args.endpoint else None
    if not endpoint:
        endpoint = os.getenv("ULTRAVOX_WS_ENDPOINT")
    
    # Convert https:// to wss:// if endpoint is provided (for convenience)
    if endpoint:
        if endpoint.startswith("https://"):
            endpoint = endpoint.replace("https://", "wss://", 1)
        elif endpoint.startswith("http://"):
            endpoint = endpoint.replace("http://", "ws://", 1)
    
    # If discover endpoint flag is set, try multiple endpoints
    if args.discover_endpoint:
        discovered_endpoint = await try_multiple_endpoints(api_key)
        if discovered_endpoint:
            print(f"\n✅ Found working endpoint: {discovered_endpoint}")
            print(f"Add this to your .env file:")
            print(f"ULTRAVOX_WS_ENDPOINT={discovered_endpoint}")
        return
    
    tester = UltravoxTester()
    
    try:
        if args.mode == 'connection':
            await tester.test_connection_only(api_key=api_key, endpoint=endpoint)
            
        elif args.mode == 'mic':
            await tester.setup_client(api_key=api_key, endpoint=endpoint)
            await tester.test_with_microphone(duration=args.duration)
            await tester.cleanup()
            
        elif args.mode == 'file':
            if not args.input_file:
                logger.error("--input-file is required for file mode")
                return
            
            await tester.setup_client(api_key=api_key, endpoint=endpoint)
            await tester.test_with_file(args.input_file, args.output_file)
            await tester.cleanup()
        
        elif args.mode == 'create-call':
            # HTTP POST create-call test: print joinUrl
            org_id = args.organization_id or Config.default_organization_id or None
            logger.info("Creating Ultravox call (HTTP POST) to obtain joinUrl...")
            try:
                call_info = await create_ultravox_call(api_key=api_key, organization_id=org_id)
            except Exception as e:
                logger.error(f"Failed to create Ultravox call: {e}", exc_info=True)
                return
            join_url = call_info.get("joinUrl")
            if join_url:
                print("============================================================")
                print("✅ Ultravox call created successfully")
                print(f"joinUrl: {join_url}")
                print(f"keys: {list(call_info.keys())}")
                print("============================================================")
            else:
                logger.error(f"Ultravox call creation did not return joinUrl. Keys: {list(call_info.keys())}")
            
    except KeyboardInterrupt:
        logger.info("\n⏹️  Test interrupted by user")
        if args.mode != 'create-call' and 'tester' in locals():
            await tester.cleanup()
    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        if args.mode != 'create-call' and 'tester' in locals():
            await tester.cleanup()
        sys.exit(1)


async def try_multiple_endpoints(api_key: str):
    """Try multiple common endpoint patterns to find the correct one."""
    if not websockets:
        print("❌ websockets library not available. Cannot discover endpoints.")
        return None
        
    endpoints_to_try = [
        "wss://api.ultravox.ai/realtime",
        "wss://api.ultravox.ai/v1/realtime",
        "wss://api.ultravox.ai/v1/ws",
        "wss://api.ultravox.ai/ws/realtime",
        "wss://api.ultravox.ai/ws",
        "wss://realtime.ultravox.ai",
        "wss://realtime.ultravox.ai/ws",
        "wss://api.fixie.ai/ultravox/realtime",
        "wss://api.fixie.ai/v1/ultravox/realtime",
        "wss://api.fixie.ai/ultravox/ws",
        "wss://api.fixie.ai/realtime",
        "wss://api.fixie.ai/ws",
    ]
    
    print("\n🔍 Trying multiple endpoint patterns to find the correct one...")
    print("=" * 60)
    
    for endpoint in endpoints_to_try:
        print(f"\nTrying: {endpoint}")
        try:
            tester = UltravoxTester()
            await tester.setup_client(api_key=api_key, endpoint=endpoint)
            await asyncio.sleep(2)  # Wait a bit to see if connection works
            await tester.cleanup()
            print(f"✅ SUCCESS! Endpoint {endpoint} appears to work!")
            return endpoint
        except (websockets.exceptions.InvalidStatusCode, websockets.InvalidStatusCode) as e:
            if e.status_code == 404:
                print(f"   ❌ 404 - Not found")
            elif e.status_code == 401:
                print(f"   ⚠️  401 - Unauthorized (endpoint might be correct, check API key)")
                return endpoint
            else:
                print(f"   ❌ {e.status_code} - {e}")
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)[:100] if str(e) else ""
            print(f"   ❌ Error: {error_type} - {error_msg}")
    
    print("\n" + "=" * 60)
    print("❌ None of the common endpoints worked.")
    print("Please check your Ultravox account dashboard for the correct endpoint.")
    return None


if __name__ == "__main__":
    print("=" * 60)
    print("Ultravox Speech-to-Speech Test Script")
    print("=" * 60)
    print()
    
    # Reload .env one more time to be sure
    load_dotenv(dotenv_path=env_path, override=True)
    
    # Fallback: Read .env file directly if dotenv doesn't work
    api_key_from_file = None
    if env_path.exists():
        try:
            with open(env_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    original_line = line
                    line = line.strip()
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                    
                    # Try multiple patterns
                    patterns = ['ultravox_api_key', 'ULTRAVOX_API_KEY', 'ultravox', 'ULTRAVOX']
                    found_pattern = None
                    for pattern in patterns:
                        if pattern in line:
                            found_pattern = pattern
                            break
                    
                    if found_pattern:
                        print(f"🔍 Found potential match on line {line_num} with pattern '{found_pattern}': {line[:80]}")
                        if '=' in line:
                            # Split on first = only
                            parts = line.split('=', 1)
                            if len(parts) == 2:
                                key = parts[0].strip()
                                value = parts[1].strip()
                                # Remove quotes if present
                                value = value.strip('"').strip("'").strip()
                                # Check if key matches (case-insensitive)
                                if 'ultravox' in key.lower() and 'api' in key.lower() and 'key' in key.lower():
                                    api_key_from_file = value
                                    # Set it in environment
                                    os.environ['ULTRAVOX_API_KEY'] = value
                                    print(f"✅ Found and set ULTRAVOX_API_KEY from line {line_num}: {key}={value[:10]}...{value[-4:]}")
                                    break
        except Exception as e:
            print(f"⚠️  Could not read .env file directly: {e}")
    
    # Debug: Check environment variable directly
    api_key_from_env = os.getenv("ULTRAVOX_API_KEY", "").strip()
    api_key_from_config = Config.ultravox_api_key.strip() if Config.ultravox_api_key else ""
    
    print(f"🔍 Debug Info:")
    print(f"   Project root: {project_root}")
    print(f"   .env file exists: {env_path.exists()}")
    print(f"   ULTRAVOX_API_KEY from os.getenv(): {'✅ Found' if api_key_from_env else '❌ Not found'}")
    print(f"   ULTRAVOX_API_KEY from Config: {'✅ Found' if api_key_from_config else '❌ Not found'}")
    print(f"   ULTRAVOX_API_KEY from file read: {'✅ Found' if api_key_from_file else '❌ Not found'}")
    
    # Show all environment variables with ULTRAVOX in the name
    all_env_vars = {k: v for k, v in os.environ.items() if 'ULTRAVOX' in k.upper()}
    if all_env_vars:
        print(f"   Environment variables with 'ULTRAVOX': {list(all_env_vars.keys())}")
    
    if api_key_from_env:
        print(f"   API Key (from env): {api_key_from_env[:10]}...{api_key_from_env[-4:]}")
    if api_key_from_config:
        print(f"   API Key (from Config): {api_key_from_config[:10]}...{api_key_from_config[-4:]}")
    if api_key_from_file:
        print(f"   API Key (from file): {api_key_from_file[:10]}...{api_key_from_file[-4:]}")
    print()
    
    # Check API key - try all sources
    api_key = api_key_from_config or api_key_from_env or api_key_from_file
    
    # Parse command line args to check for --api-key, --endpoint, and --discover-endpoint
    parser = argparse.ArgumentParser(description="Test Ultravox speech-to-speech model", add_help=False)
    parser.add_argument('--mode', choices=['mic', 'file', 'connection', 'create-call'], default='connection')
    parser.add_argument('--input-file', type=str)
    parser.add_argument('--output-file', type=str)
    parser.add_argument('--duration', type=int, default=30)
    parser.add_argument('--api-key', type=str, help='Ultravox API key (overrides .env file)')
    parser.add_argument('--endpoint', type=str, help='Ultravox WebSocket endpoint URL (overrides default)')
    parser.add_argument('--organization-id', type=str, default=None, help='Organization ID for fetching system prompt from Supabase')
    parser.add_argument('--discover-endpoint', action='store_true', help='Try multiple endpoint patterns to find the correct one')
    args, unknown = parser.parse_known_args()
    
    # Override with command line API key if provided
    if args.api_key:
        api_key = args.api_key
        os.environ['ULTRAVOX_API_KEY'] = api_key
        print(f"✅ Using API key from command line argument")
    
    if not api_key:
        print("❌ ERROR: ULTRAVOX_API_KEY not found in environment")
        print(f"   Checked .env file at: {env_path}")
        print("   Please ensure ULTRAVOX_API_KEY is set in your .env file")
        print("   Format: ULTRAVOX_API_KEY=your_api_key_here")
        print("   Or use --api-key argument: python test_ultravox_speech_to_speech.py --api-key YOUR_KEY")
        sys.exit(1)
    
    print(f"✅ API Key found: {api_key[:10]}...{api_key[-4:]}")
    if args.endpoint:
        print(f"✅ Using endpoint: {args.endpoint}")
    if args.discover_endpoint:
        print(f"🔍 Endpoint discovery mode enabled")
    print()
    
    # Run test with parsed args
    asyncio.run(main(args))

