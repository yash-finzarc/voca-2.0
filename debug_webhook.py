#!/usr/bin/env python3
"""
Debug webhook to test TwiML responses without AI complexity
"""

from flask import Flask, request, Response
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

@app.route('/debug', methods=['POST', 'GET'])
def debug_webhook():
    print("\n=== DEBUG WEBHOOK CALLED ===")
    print(f"Method: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Form Data: {dict(request.form)}")
    print(f"Raw Data: {request.get_data()}")
    
    # Handle both form and JSON data
    if request.form:
        print(f"Form data received: {dict(request.form)}")
    if request.get_json():
        print(f"JSON data received: {request.get_json()}")
    
    # Create simple TwiML response
    twiml = '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Hello! This is a debug test. If you hear this, the webhook is working correctly.</Say>
    <Say>Testing one, two, three. This should work without any errors.</Say>
    <Hangup/>
</Response>'''
    
    print(f"Response TwiML:\n{twiml}")
    return Response(twiml, mimetype='text/xml')

@app.route('/test', methods=['POST', 'GET'])
def test_webhook():
    """Even simpler test"""
    twiml = '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Test successful</Say>
    <Hangup/>
</Response>'''
    return Response(twiml, mimetype='text/xml')

if __name__ == '__main__':
    print("🐛 Starting Debug Webhook Server...")
    print("Test URLs:")
    print("  - http://localhost:5001/debug")
    print("  - http://localhost:5001/test")
    app.run(host='0.0.0.0', port=5001, debug=True)