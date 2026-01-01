#!/usr/bin/env python3
"""
Test script to verify WebSocket endpoint accessibility from external perspective.
This helps diagnose why Twilio cannot connect (Error 11100 Invalid URL).
"""

import ssl
import socket
import requests
import dns.resolver
import json
from datetime import datetime

LOG_PATH = r"c:\Users\Yash\Desktop\voca-2.0\.cursor\debug.log"

def log_debug(hypothesis_id, location, message, data=None):
    """Write debug log entry."""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            entry = {
                "sessionId": "debug-session",
                "runId": "endpoint-test",
                "hypothesisId": hypothesis_id,
                "location": location,
                "message": message,
                "timestamp": int(datetime.now().timestamp() * 1000),
                "data": data or {}
            }
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"Failed to write log: {e}")

def test_dns_resolution():
    """Test A: DNS resolution for voca-2.duckdns.org"""
    log_debug("A", "test_dns_resolution:1", "Testing DNS resolution")
    try:
        result = dns.resolver.resolve("voca-2.duckdns.org", "A")
        ip_addresses = [str(ip) for ip in result]
        log_debug("A", "test_dns_resolution:2", "DNS resolution successful", {"ips": ip_addresses})
        print(f"✓ DNS Resolution: {ip_addresses}")
        return True, ip_addresses
    except Exception as e:
        log_debug("A", "test_dns_resolution:3", "DNS resolution failed", {"error": str(e)})
        print(f"✗ DNS Resolution Failed: {e}")
        return False, None

def test_ssl_certificate():
    """Test A: SSL certificate validation"""
    log_debug("A", "test_ssl_certificate:1", "Testing SSL certificate")
    try:
        context = ssl.create_default_context()
        with socket.create_connection(("voca-2.duckdns.org", 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname="voca-2.duckdns.org") as ssock:
                cert = ssock.getpeercert()
                log_debug("A", "test_ssl_certificate:2", "SSL certificate valid", {
                    "subject": dict(x[0] for x in cert.get("subject", [])),
                    "issuer": dict(x[0] for x in cert.get("issuer", [])),
                    "notAfter": cert.get("notAfter")
                })
                print(f"✓ SSL Certificate: Valid")
                print(f"  Subject: {dict(x[0] for x in cert.get('subject', []))}")
                print(f"  Valid Until: {cert.get('notAfter')}")
                return True
    except Exception as e:
        log_debug("A", "test_ssl_certificate:3", "SSL certificate check failed", {"error": str(e)})
        print(f"✗ SSL Certificate Check Failed: {e}")
        return False

def test_http_endpoint():
    """Test C: HTTP endpoint accessibility"""
    log_debug("C", "test_http_endpoint:1", "Testing HTTP endpoint")
    try:
        response = requests.get("https://voca-2.duckdns.org/twilio", timeout=10, verify=True)
        log_debug("C", "test_http_endpoint:2", "HTTP endpoint accessible", {
            "status_code": response.status_code,
            "headers": dict(response.headers)
        })
        print(f"✓ HTTP Endpoint: Accessible (Status: {response.status_code})")
        return True, response.status_code
    except requests.exceptions.SSLError as e:
        log_debug("C", "test_http_endpoint:3", "HTTP endpoint SSL error", {"error": str(e)})
        print(f"✗ HTTP Endpoint SSL Error: {e}")
        return False, None
    except Exception as e:
        log_debug("C", "test_http_endpoint:4", "HTTP endpoint error", {"error": str(e)})
        print(f"✗ HTTP Endpoint Error: {e}")
        return False, None

def test_websocket_handshake():
    """Test C, E: WebSocket handshake (simulated)"""
    log_debug("C", "test_websocket_handshake:1", "Testing WebSocket handshake")
    try:
        import websocket
        ws = websocket.create_connection(
            "wss://voca-2.duckdns.org/twilio",
            timeout=10,
            sslopt={"cert_reqs": ssl.CERT_REQUIRED}
        )
        log_debug("C", "test_websocket_handshake:2", "WebSocket connection successful")
        print("✓ WebSocket: Connection successful")
        ws.close()
        return True
    except websocket.WebSocketException as e:
        log_debug("C", "test_websocket_handshake:3", "WebSocket connection failed", {"error": str(e)})
        print(f"✗ WebSocket Connection Failed: {e}")
        return False
    except Exception as e:
        log_debug("C", "test_websocket_handshake:4", "WebSocket error", {"error": str(e)})
        print(f"✗ WebSocket Error: {e}")
        return False

def main():
    print("=" * 80)
    print("WebSocket Endpoint Accessibility Test")
    print("=" * 80)
    print("Testing: wss://voca-2.duckdns.org/twilio")
    print("")
    
    # Test DNS (Hypothesis A, B)
    dns_ok, ips = test_dns_resolution()
    print("")
    
    # Test SSL (Hypothesis A)
    ssl_ok = test_ssl_certificate()
    print("")
    
    # Test HTTP endpoint (Hypothesis C)
    http_ok, status = test_http_endpoint()
    print("")
    
    # Test WebSocket (Hypothesis C, E)
    try:
        ws_ok = test_websocket_handshake()
    except ImportError:
        print("⚠ WebSocket test skipped (websocket-client not installed)")
        ws_ok = None
    print("")
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"DNS Resolution: {'✓' if dns_ok else '✗'}")
    print(f"SSL Certificate: {'✓' if ssl_ok else '✗'}")
    print(f"HTTP Endpoint: {'✓' if http_ok else '✗'} ({status if status else 'N/A'})")
    print(f"WebSocket: {'✓' if ws_ok else '✗' if ws_ok is not None else '⚠ Skipped'}")
    print("")

if __name__ == "__main__":
    main()

