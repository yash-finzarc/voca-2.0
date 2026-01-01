# WebSocket Connectivity Test

This script tests the WebSocket endpoint for Twilio Media Streams to verify it's accessible and working correctly.

## Installation

Install the required library:

```bash
pip install websockets
```

Optional (for HTTP upgrade test):
```bash
pip install aiohttp
```

## Usage

### Basic test (uses default URL):
```bash
python testing/test_websocket_connection.py
```

### Test with custom URL:
```bash
python testing/test_websocket_connection.py wss://voca-2.duckdns.org
```

### Test with custom URL and call SID:
```bash
python testing/test_websocket_connection.py wss://voca-2.duckdns.org CA1234567890abcdef
```

### Test against local server (for development):
```bash
python testing/test_websocket_connection.py ws://127.0.0.1:8000
```

## What it tests

1. **Direct WebSocket Connection**: Tests if the WebSocket endpoint accepts connections
2. **HTTP to WebSocket Upgrade**: Tests if nginx properly upgrades HTTP connections to WebSocket
3. **Message Reception**: Tests if the endpoint can receive WebSocket messages

## Expected Output

If successful, you should see:
- ✅ WebSocket connection established
- ✅ Received messages (if any)
- ✅ Test passed

If failed, check:
1. Is the FastAPI server running?
2. Is nginx configured correctly?
3. Are firewall rules allowing WebSocket connections?
4. Is the SSL certificate valid?

## Notes

- The script will connect but won't receive real Twilio messages (Twilio needs to be the one connecting)
- This test verifies the endpoint is accessible and accepts connections
- For a real test, make an actual Twilio call and watch the server logs

