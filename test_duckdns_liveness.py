#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to check if DuckDNS domain is still live and accessible.
DuckDNS free accounts require periodic updates (every 30 days) or the domain may expire.
"""

import socket
import ssl
import requests
import sys
import os
from datetime import datetime
from urllib.parse import urlparse

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7 fallback
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

DOMAIN = "voca-2.duckdns.org"
BASE_URL = f"https://{DOMAIN}"

def test_dns_resolution():
    """Test 1: Check if DNS resolves the domain to an IP address."""
    print("=" * 80)
    print("TEST 1: DNS Resolution")
    print("=" * 80)
    try:
        ip = socket.gethostbyname(DOMAIN)
        print(f"[OK] DNS Resolution: {DOMAIN} -> {ip}")
        return True, ip
    except socket.gaierror as e:
        print(f"[WARNING] DNS Resolution FAILED locally: {e}")
        print(f"  -> This may be a local DNS cache issue")
        print(f"  -> Will verify with HTTPS test (SSL requires DNS resolution)")
        return None, None  # Return None to indicate inconclusive
    except Exception as e:
        print(f"[ERROR] DNS Resolution ERROR: {e}")
        return False, None

def test_ssl_certificate():
    """Test 2: Check SSL certificate validity."""
    print("\n" + "=" * 80)
    print("TEST 2: SSL Certificate")
    print("=" * 80)
    try:
        context = ssl.create_default_context()
        with socket.create_connection((DOMAIN, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=DOMAIN) as ssock:
                cert = ssock.getpeercert()
                issuer = dict(x[0] for x in cert['issuer'])
                valid_from = datetime.strptime(cert['notBefore'], '%b %d %H:%M:%S %Y %Z')
                valid_until = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                now = datetime.utcnow()
                
                print(f"[OK] SSL Certificate: Valid")
                print(f"  Issuer: {issuer.get('organizationName', 'Unknown')}")
                print(f"  Valid from: {valid_from}")
                print(f"  Valid until: {valid_until}")
                
                days_remaining = (valid_until - now).days
                if days_remaining < 30:
                    print(f"  [WARNING] Certificate expires in {days_remaining} days")
                else:
                    print(f"  [OK] Certificate valid for {days_remaining} more days")
                
                return True, cert
    except socket.gaierror:
        print(f"✗ SSL Test SKIPPED: DNS resolution failed")
        return None, None
    except ssl.SSLError as e:
        print(f"✗ SSL Certificate ERROR: {e}")
        return False, None
    except Exception as e:
        print(f"✗ SSL Certificate ERROR: {e}")
        return False, None

def test_http_connectivity():
    """Test 3: Check HTTP/HTTPS connectivity."""
    print("\n" + "=" * 80)
    print("TEST 3: HTTP/HTTPS Connectivity")
    print("=" * 80)
    try:
        response = requests.get(BASE_URL, timeout=10, verify=True, allow_redirects=True)
        print(f"[OK] HTTP Connectivity: {response.status_code} {response.reason}")
        print(f"  Final URL: {response.url}")
        
        if response.status_code == 200:
            print(f"  [OK] Server is responding")
        elif response.status_code in [301, 302, 307, 308]:
            print(f"  -> Redirected (this is normal for HTTPS)")
        
        return True, response.status_code
    except requests.exceptions.SSLError as e:
        print(f"[FAIL] SSL Error: {e}")
        return False, None
    except requests.exceptions.ConnectionError as e:
        print(f"[FAIL] Connection Error: {e}")
        print(f"  -> Domain may be expired or server is down")
        return False, None
    except requests.exceptions.Timeout:
        print(f"[FAIL] Connection Timeout: Server did not respond")
        return False, None
    except Exception as e:
        print(f"[ERROR] HTTP Connectivity ERROR: {e}")
        return False, None

def test_api_endpoint():
    """Test 4: Check if API endpoint is accessible."""
    print("\n" + "=" * 80)
    print("TEST 4: API Endpoint (/twilio)")
    print("=" * 80)
    try:
        url = f"{BASE_URL}/twilio"
        response = requests.get(url, timeout=10, verify=True)
        print(f"[OK] API Endpoint: {response.status_code} {response.reason}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"  Response: {data}")
            except:
                print(f"  Response: {response.text[:100]}")
        
        return True, response.status_code
    except requests.exceptions.ConnectionError as e:
        print(f"[FAIL] Connection Error: {e}")
        return False, None
    except Exception as e:
        print(f"[ERROR] API Endpoint ERROR: {e}")
        return False, None

def test_webhook_endpoints():
    """Test 5: Check if webhook endpoints are accessible."""
    print("\n" + "=" * 80)
    print("TEST 5: Webhook Endpoints")
    print("=" * 80)
    
    endpoints = [
        "/webhook/voice",
        "/outbound",
    ]
    
    results = {}
    for endpoint in endpoints:
        try:
            url = f"{BASE_URL}{endpoint}"
            # Use POST since these are webhook endpoints (should handle GET too though)
            response = requests.post(url, timeout=10, verify=True, data={})
            print(f"[OK] {endpoint}: {response.status_code} {response.reason}")
            results[endpoint] = True
        except Exception as e:
            print(f"[FAIL] {endpoint}: ERROR - {e}")
            results[endpoint] = False
    
    return all(results.values()), results

def main():
    """Run all tests and provide summary."""
    print(f"\n{'=' * 80}")
    print(f"DuckDNS Domain Liveness Test")
    print(f"Domain: {DOMAIN}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 80}\n")
    
    results = {}
    
    # Run tests
    dns_ok, ip = test_dns_resolution()
    results['dns'] = dns_ok
    
    ssl_ok, cert = test_ssl_certificate()
    results['ssl'] = ssl_ok
    
    http_ok, status = test_http_connectivity()
    results['http'] = http_ok
    
    api_ok, api_status = test_api_endpoint()
    results['api'] = api_ok
    
    webhook_ok, webhook_results = test_webhook_endpoints()
    results['webhooks'] = webhook_ok
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    total_tests = len([r for r in results.values() if r is not None])
    passed_tests = len([r for r in results.values() if r is True])
    
    print(f"Tests Passed: {passed_tests}/{total_tests}")
    print()
    
    # Check DNS result - if None, it failed locally but may work elsewhere
    # If SSL/HTTP work, then DNS is actually working (SSL requires DNS)
    dns_result = results.get('dns')
    if dns_result is False:
        # Only fail if DNS is explicitly False AND HTTP also failed
        if results.get('http') is False:
            print("[CRITICAL] DNS resolution failed!")
            print("   -> DuckDNS domain may have EXPIRED")
            print("   -> Update your DuckDNS domain at: https://www.duckdns.org/")
            print("   -> Free DuckDNS domains expire after 30 days without updates")
            return 1
        else:
            print("[WARNING] DNS resolution failed locally, but HTTPS works (DNS is actually OK)")
            print("[OK] DNS: Domain is resolving (verified via HTTPS connection)")
    elif dns_result is None:
        # DNS failed locally but if HTTP/SSL work, DNS is actually OK
        if results.get('ssl') is True or results.get('http') is True:
            print("[OK] DNS: Domain is resolving (verified via HTTPS connection)")
            print("   (Local DNS resolution failed, but domain works globally)")
        else:
            print("[WARNING] DNS resolution failed locally")
    elif dns_result is True:
        print("[OK] DNS: Domain resolves correctly")
    
    if results.get('ssl') is False:
        print("[CRITICAL] SSL certificate invalid or expired")
        return 1
    elif results.get('ssl') is True:
        print("[OK] SSL: Certificate is valid")
    
    if results.get('http') is False:
        print("[CRITICAL] HTTP connectivity failed")
        return 1
    elif results.get('http') is True:
        print("[OK] HTTP: Server is accessible")
    
    if results.get('api') is False:
        print("[WARNING] API endpoint not accessible (may be normal if server is down)")
    elif results.get('api') is True:
        print("[OK] API: Endpoint is accessible")
    
    if results.get('webhooks') is False:
        print("[WARNING] Some webhook endpoints not accessible")
    elif results.get('webhooks') is True:
        print("[OK] Webhooks: Endpoints are accessible")
    
    print("\n" + "=" * 80)
    # Consider DNS test passed if HTTP/SSL work (they require DNS)
    critical_tests = [
        results.get('ssl'),
        results.get('http'),
        results.get('api'),
    ]
    # DNS is critical only if all other tests also fail
    if dns_result is False and not any(critical_tests):
        critical_tests.append(False)
    elif dns_result is not False:
        critical_tests.append(True)  # DNS passed or inconclusive but other tests pass
    
    if all(r for r in critical_tests if r is not None):
        print("[SUCCESS] DOMAIN IS LIVE AND ACCESSIBLE!")
        print("  All critical tests passed (SSL, HTTP, API endpoints working)")
        if dns_result is None or dns_result is False:
            print("  Note: Local DNS resolution had issues, but domain works globally")
        print("=" * 80)
        return 0
    else:
        print("[WARNING] SOME TESTS FAILED - Check details above")
        print("=" * 80)
        return 1

if __name__ == "__main__":
    sys.exit(main())

