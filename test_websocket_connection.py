#!/usr/bin/env python3
"""
Test script to verify WebSocket connection to /twilio endpoint.
This simulates what Twilio Media Streams does when connecting.
"""

import asyncio
import json
import websockets
import ssl
import sys
from datetime import datetime


async def test_websocket_connection(url: str, use_ssl: bool = True):
    """
    Test WebSocket connection to the /twilio endpoint.
    
    Args:
        url: WebSocket URL (e.g., wss://voca2.duckdns.org/twilio)
        use_ssl: Whether to verify SSL certificate
    """
    print(f"\n{'='*60}")
    print(f"Testing WebSocket Connection")
    print(f"{'='*60}")
    print(f"URL: {url}")
    
    # Detect if URL uses wss:// (secure) or ws:// (non-secure)
    is_secure = url.startswith('wss://')
    print(f"Protocol: {'WSS (Secure)' if is_secure else 'WS (Non-secure)'}")
    print(f"SSL Verification: {'Enabled' if (use_ssl and is_secure) else 'Disabled'}")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"{'='*60}\n")
    
    # SSL context - only use for wss:// URLs
    ssl_context = None
    if is_secure and use_ssl:
        ssl_context = ssl.create_default_context()
        # For testing, you might want to disable verification if using self-signed certs
        # ssl_context.check_hostname = False
        # ssl_context.verify_mode = ssl.CERT_NONE
    elif is_secure and not use_ssl:
        # Create SSL context but disable verification
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
    
    try:
        print("1. Attempting to connect to WebSocket...")
        async with websockets.connect(
            url,
            ssl=ssl_context,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=10,
            open_timeout=10  # Add timeout for connection
        ) as websocket:
            print("   ✓ WebSocket connection established!")
            print(f"   Connection state: {websocket.state}")
            print(f"   Remote address: {websocket.remote_address}")
            
            # Send a test message similar to what Twilio sends
            print("\n2. Sending test 'connected' event (simulating Twilio)...")
            connected_message = {
                "event": "connected",
                "protocol": "Call",
                "version": "1.0.0",
                "sequenceNumber": 1
            }
            await websocket.send(json.dumps(connected_message))
            print(f"   ✓ Sent: {json.dumps(connected_message)}")
            
            # Send a test 'start' event (simulating Twilio Media Streams)
            print("\n3. Sending test 'start' event (simulating Twilio Media Streams)...")
            start_message = {
                "event": "start",
                "sequenceNumber": 2,
                "start": {
                    "accountSid": "test_account",
                    "callSid": "test_call_sid",
                    "tracks": ["inbound", "outbound"],
                    "mediaFormat": {
                        "encoding": "audio/x-mulaw",
                        "sampleRate": 8000,
                        "channels": 1
                    },
                    "streamSid": "test_stream_sid"
                }
            }
            await websocket.send(json.dumps(start_message))
            print(f"   ✓ Sent: {json.dumps(start_message)}")
            
            # Wait for response
            print("\n4. Waiting for response from server (5 seconds)...")
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"   ✓ Received response: {response[:200]}...")
            except asyncio.TimeoutError:
                print("   ⚠ No response received within 5 seconds (this is OK if server is just listening)")
            
            # Send a test media event
            print("\n5. Sending test 'media' event (simulating audio data)...")
            import base64
            # Create dummy audio data (silence in mulaw)
            dummy_audio = b'\x7f' * 160  # 160 bytes of silence
            media_message = {
                "event": "media",
                "sequenceNumber": 3,
                "media": {
                    "track": "inbound",
                    "chunk": "1",
                    "timestamp": "1234567890",
                    "payload": base64.b64encode(dummy_audio).decode('ascii')
                }
            }
            await websocket.send(json.dumps(media_message))
            print(f"   ✓ Sent media event with {len(dummy_audio)} bytes of audio data")
            
            # Wait a bit more
            print("\n6. Waiting for any additional responses (3 seconds)...")
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=3.0)
                print(f"   ✓ Received: {response[:200]}...")
            except asyncio.TimeoutError:
                print("   ⚠ No additional response (this is OK)")
            
            print("\n" + "="*60)
            print("✓ WebSocket connection test completed successfully!")
            print("="*60 + "\n")
            
    except websockets.exceptions.InvalidStatus as e:
        status_code = getattr(e, 'status_code', getattr(e, 'status', 'unknown'))
        headers = getattr(e, 'headers', {})
        print(f"\n✗ Connection failed with HTTP status: {status_code}")
        if headers:
            print(f"  Response headers: {headers}")
        if status_code == 401:
            print("  → This indicates authentication/authorization issue")
        elif status_code == 404:
            print("  → WebSocket endpoint not found - check the URL path")
        elif status_code == 403:
            print("  → Access forbidden - check nginx/firewall configuration")
        return False
    except websockets.exceptions.InvalidURI as e:
        print(f"\n✗ Invalid WebSocket URL: {e}")
        print("  → Check that the URL starts with 'wss://' or 'ws://'")
        return False
    except websockets.exceptions.ConnectionClosed as e:
        print(f"\n✗ Connection closed by server: {e.code} - {e.reason}")
        return False
    except ssl.SSLError as e:
        print(f"\n✗ SSL/TLS error: {e}")
        print("  → SSL certificate issue - check certificate validity")
        return False
    except OSError as e:
        print(f"\n✗ Network error: {e}")
        print("  → Cannot reach the server - check network/firewall/DNS")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {type(e).__name__}: {e}")
        import traceback
        print(f"\nTraceback:\n{traceback.format_exc()}")
        return False
    
    return True


async def main():
    """Main function to run WebSocket connection tests."""
    # Default URL - can be overridden via command line argument
    default_url = "wss://voca2.duckdns.org/twilio"
    
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = default_url
    
    # Check if SSL verification should be disabled
    disable_ssl = "--no-ssl-verify" in sys.argv
    
    print("\n" + "="*60)
    print("WebSocket Connection Test Tool")
    print("="*60)
    print("\nThis script tests the WebSocket connection to /twilio endpoint")
    print("to verify that Twilio Media Streams can connect.\n")
    
    success = await test_websocket_connection(url, use_ssl=not disable_ssl)
    
    if success:
        print("\n✓ Test PASSED - WebSocket endpoint is accessible")
        print("\nNext steps:")
        print("  1. If Twilio still can't connect, check Twilio Console logs")
        print("  2. Verify TwiML Bin URL is exactly: wss://voca2.duckdns.org/twilio")
        print("  3. Check nginx logs: sudo tail -f /var/log/nginx/error.log")
        sys.exit(0)
    else:
        print("\n✗ Test FAILED - WebSocket endpoint is not accessible")
        print("\nTroubleshooting:")
        print("  1. Check if the server is running: python main.py")
        print("  2. Check nginx configuration: sudo nginx -t")
        print("  3. Check nginx logs: sudo tail -f /var/log/nginx/error.log")
        print("  4. Verify SSL certificate: openssl s_client -connect voca2.duckdns.org:443")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)

