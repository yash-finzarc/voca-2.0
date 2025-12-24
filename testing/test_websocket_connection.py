#!/usr/bin/env python3
"""
Test script to verify WebSocket connectivity for Twilio Media Streams.

This script tests the WebSocket endpoint to ensure it's accessible and working correctly.
It simulates what Twilio does when connecting to the Media Streams endpoint.
"""

import asyncio
import json
import sys
import os
import ssl
from datetime import datetime

try:
    import websockets
except ImportError:
    print("❌ Error: websockets library not installed")
    print("Install it with: pip install websockets")
    sys.exit(1)


async def test_websocket_connection(url: str, call_sid: str = "test123", timeout: int = 10):
    """
    Test WebSocket connection to the endpoint.
    
    Args:
        url: WebSocket URL (wss:// or ws://)
        call_sid: Call SID to use in the URL
        timeout: Connection timeout in seconds
    """
    # Construct full URL
    if not url.endswith('/'):
        url = url + '/'
    full_url = f"{url}webrtc/{call_sid}"
    
    print(f"🔌 Testing WebSocket connection...")
    print(f"   URL: {full_url}")
    print(f"   Call SID: {call_sid}")
    print(f"   Timeout: {timeout}s")
    print()
    
    try:
        # Create SSL context for wss:// connections
        ssl_context = None
        if url.startswith('wss://'):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE  # For testing only
        
        # Connect to WebSocket with timeout
        print("⏳ Attempting to connect...")
        async with websockets.connect(
            full_url,
            ssl=ssl_context,
            ping_interval=None,  # Disable ping for testing
            close_timeout=5
        ) as websocket:
            print("✅ WebSocket connection established!")
            print()
            
            # Wait for 'connected' event from Twilio (simulated)
            print("⏳ Waiting for messages...")
            try:
                # Wait for first message (Twilio sends 'connected' event)
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(message)
                print("✅ Received message:")
                print(f"   {json.dumps(data, indent=2)}")
                print()
                
                event = data.get('event')
                if event == 'connected':
                    print("✅ Received 'connected' event (expected)")
                elif event == 'start':
                    print("✅ Received 'start' event (good!)")
                    stream_sid = data.get('start', {}).get('streamSid')
                    if stream_sid:
                        print(f"   Stream SID: {stream_sid}")
                else:
                    print(f"⚠️  Received unexpected event: {event}")
                
                # Try to receive one more message (could be 'start' event)
                try:
                    message2 = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data2 = json.loads(message2)
                    print("✅ Received second message:")
                    print(f"   {json.dumps(data2, indent=2)}")
                except asyncio.TimeoutError:
                    print("⏳ No second message received (this is OK for testing)")
                
            except asyncio.TimeoutError:
                print("⏳ No messages received within timeout (this is OK - Twilio hasn't connected)")
            
            print()
            print("✅ WebSocket connection test completed successfully!")
            print("   The endpoint is accessible and accepting connections.")
            
            # Send a test message (Twilio format)
            print()
            print("📤 Sending test message (Twilio format)...")
            test_message = {
                "event": "media",
                "media": {
                    "track": "inbound",
                    "payload": "dGVzdA=="  # base64 for "test"
                }
            }
            await websocket.send(json.dumps(test_message))
            print("✅ Test message sent")
            
            return True
            
    except websockets.exceptions.InvalidURI:
        print(f"❌ Error: Invalid WebSocket URL: {full_url}")
        return False
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"❌ Error: WebSocket connection failed with status code {e.status_code}")
        print(f"   Headers: {e.headers}")
        return False
    except ConnectionRefusedError:
        print(f"❌ Error: Connection refused. Is the server running?")
        return False
    except OSError as e:
        print(f"❌ Error: Network error - {e}")
        return False
    except asyncio.TimeoutError:
        print(f"❌ Error: Connection timeout after {timeout}s")
        return False
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_http_to_websocket_upgrade(url: str):
    """
    Test HTTP to WebSocket upgrade by sending upgrade headers.
    This simulates what nginx does.
    """
    import aiohttp
    
    print("🔌 Testing HTTP to WebSocket upgrade...")
    ws_url = url.replace('https://', 'wss://').replace('http://', 'ws://')
    if not ws_url.endswith('/'):
        ws_url = ws_url + '/'
    ws_url = f"{ws_url}webrtc/test123"
    
    print(f"   URL: {ws_url}")
    print()
    
    try:
        # Create SSL context for wss://
        ssl_context = False
        if ws_url.startswith('wss://'):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                ws_url,
                ssl=ssl_context,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as ws:
                print("✅ WebSocket connection established via HTTP upgrade!")
                print()
                
                # Try to receive a message
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=5.0)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        print("✅ Received message:")
                        print(f"   {json.dumps(data, indent=2)}")
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"❌ WebSocket error: {ws.exception()}")
                except asyncio.TimeoutError:
                    print("⏳ No messages received (this is OK)")
                
                return True
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        return False


def main():
    """Main function to run WebSocket connectivity tests."""
    print("=" * 70)
    print("WebSocket Connectivity Test for Twilio Media Streams")
    print("=" * 70)
    print()
    
    # Get URL from command line or use default
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = "wss://voca2.duckdns.org"
        print(f"ℹ️  No URL provided, using default: {url}")
        print(f"   Usage: python {sys.argv[0]} <wss://your-domain.com>")
        print()
    
    # Get call SID from command line or use default
    call_sid = sys.argv[2] if len(sys.argv) > 2 else "test-websocket-connection"
    
    # Test 1: Direct WebSocket connection
    print("TEST 1: Direct WebSocket Connection")
    print("-" * 70)
    success1 = asyncio.run(test_websocket_connection(url, call_sid))
    print()
    
    # Test 2: HTTP to WebSocket upgrade (if aiohttp is available)
    try:
        import aiohttp
        print("TEST 2: HTTP to WebSocket Upgrade (via aiohttp)")
        print("-" * 70)
        success2 = asyncio.run(test_http_to_websocket_upgrade(url))
        print()
    except ImportError:
        print("⏭️  Skipping Test 2: aiohttp not installed")
        print("   Install it with: pip install aiohttp")
        success2 = None
        print()
    
    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Direct WebSocket Connection: {'✅ PASSED' if success1 else '❌ FAILED'}")
    if success2 is not None:
        print(f"HTTP Upgrade Connection:    {'✅ PASSED' if success2 else '❌ FAILED'}")
    print()
    
    if success1:
        print("✅ WebSocket endpoint is accessible and working!")
        print("   Twilio should be able to connect to this endpoint.")
    else:
        print("❌ WebSocket endpoint test failed!")
        print("   Check:")
        print("   1. Is the FastAPI server running?")
        print("   2. Is nginx configured correctly?")
        print("   3. Are firewall rules allowing WebSocket connections?")
        print("   4. Is the SSL certificate valid?")
    print()


if __name__ == "__main__":
    main()

