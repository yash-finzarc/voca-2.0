#!/usr/bin/env python3
"""
Simple script to test if the WebSocket endpoint is accessible.
Tests DNS, SSL, and HTTP endpoint accessibility.
"""

import requests
import ssl
import socket
from urllib.parse import urlparse

def test_endpoint():
    """Test endpoint accessibility."""
    url = "https://voca-2.duckdns.org/twilio"
    
    print("=" * 80)
    print("Testing Endpoint Accessibility")
    print("=" * 80)
    print(f"URL: {url}")
    print("")
    
    # Test 1: DNS Resolution
    print("1. Testing DNS Resolution...")
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        ip = socket.gethostbyname(hostname)
        print(f"   ✓ DNS resolved: {hostname} -> {ip}")
    except Exception as e:
        print(f"   ✗ DNS resolution failed: {e}")
        return
    
    # Test 2: SSL Certificate
    print("\n2. Testing SSL Certificate...")
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                print(f"   ✓ SSL Certificate valid")
                print(f"   ✓ Valid until: {cert.get('notAfter', 'N/A')}")
    except Exception as e:
        print(f"   ✗ SSL certificate check failed: {e}")
        return
    
    # Test 3: HTTP Endpoint
    print("\n3. Testing HTTP Endpoint...")
    try:
        response = requests.get(url, timeout=10, verify=True)
        print(f"   ✓ HTTP endpoint accessible")
        print(f"   ✓ Status code: {response.status_code}")
        print(f"   ✓ Response: {response.text[:200]}")
    except requests.exceptions.SSLError as e:
        print(f"   ✗ SSL Error: {e}")
        return
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return
    
    print("\n" + "=" * 80)
    print("✓ All basic tests passed!")
    print("=" * 80)
    print("\nIf Twilio still shows Error 11100, check:")
    print("1. Twilio Console -> Monitor -> Logs for detailed error")
    print("2. Nginx error logs: sudo tail -f /var/log/nginx/error.log")
    print("3. Server logs for [WEBSOCKET_DEBUG] messages")

if __name__ == "__main__":
    test_endpoint()

