"""
Diagnostic script to test backend API server connectivity.
Run this to verify your backend is accessible.
"""
import requests
import sys
import time

def test_backend_connection(base_url="http://localhost:8000", timeout=5):
    """Test if backend API server is accessible."""
    print(f"🔍 Testing backend connection to {base_url}...")
    print("-" * 60)
    
    endpoints = [
        ("/", "Root endpoint"),
        ("/health", "Health check"),
        ("/api/twilio/configured", "Twilio config check"),
        ("/api/ngrok/status", "Ngrok status"),
    ]
    
    results = []
    
    for endpoint, description in endpoints:
        url = f"{base_url}{endpoint}"
        try:
            print(f"\n📡 Testing {description} ({endpoint})...")
            response = requests.get(url, timeout=timeout)
            
            if response.status_code == 200:
                print(f"✅ SUCCESS: {description}")
                print(f"   Response: {response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text[:100]}")
                results.append((endpoint, True, response.status_code))
            else:
                print(f"⚠️  WARNING: {description} returned status {response.status_code}")
                results.append((endpoint, False, response.status_code))
                
        except requests.exceptions.ConnectionError:
            print(f"❌ CONNECTION ERROR: Cannot connect to {url}")
            print(f"   → Is the backend server running?")
            print(f"   → Try: python main_api_server.py")
            results.append((endpoint, False, "ConnectionError"))
        except requests.exceptions.Timeout:
            print(f"⏱️  TIMEOUT: Request to {url} timed out")
            results.append((endpoint, False, "Timeout"))
        except Exception as e:
            print(f"❌ ERROR: {type(e).__name__}: {e}")
            results.append((endpoint, False, str(e)))
    
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    
    successful = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for endpoint, success, status in results:
        status_icon = "✅" if success else "❌"
        print(f"{status_icon} {endpoint}: {status}")
    
    print(f"\n{'✅' if successful == total else '⚠️'} {successful}/{total} endpoints accessible")
    
    if successful == 0:
        print("\n💡 TROUBLESHOOTING:")
        print("   1. Make sure the backend server is running:")
        print("      python main_api_server.py")
        print("   2. Check if port 8000 is already in use:")
        print("      netstat -ano | findstr :8000  (Windows)")
        print("   3. Try accessing http://localhost:8000/docs in your browser")
        print("   4. Check firewall settings")
        return False
    elif successful < total:
        print("\n⚠️  Some endpoints are not accessible. Check server logs.")
        return False
    else:
        print("\n✅ Backend is fully accessible!")
        return True

if __name__ == "__main__":
    # Allow custom URL via command line argument
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    print("=" * 60)
    print("VOCA Backend Connection Diagnostic Tool")
    print("=" * 60)
    
    success = test_backend_connection(base_url)
    
    sys.exit(0 if success else 1)

