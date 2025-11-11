#!/usr/bin/env python3
"""
Debug webhook to test TwiML responses without AI complexity
"""

from fastapi import FastAPI, Request, Response
import logging
import uvicorn
import json

app = FastAPI(title="Debug Twilio Webhook")
logging.basicConfig(level=logging.DEBUG)

@app.post('/debug')
@app.get('/debug')
async def debug_webhook(request: Request):
    print("\n=== DEBUG WEBHOOK CALLED ===")
    print(f"Method: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    
    # Handle form data
    try:
        form_data = await request.form()
        form_dict = dict(form_data)
        print(f"Form Data: {form_dict}")
    except Exception:
        form_dict = {}
        print("No form data")
    
    # Handle JSON data
    try:
        json_data = await request.json()
        print(f"JSON data received: {json_data}")
    except Exception:
        print("No JSON data")
    
    # Get raw body
    try:
        raw_data = await request.body()
        print(f"Raw Data: {raw_data}")
    except Exception:
        print("No raw data")
    
    # Create simple TwiML response
    twiml = '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Hello! This is a debug test. If you hear this, the webhook is working correctly.</Say>
    <Say>Testing one, two, three. This should work without any errors.</Say>
    <Hangup/>
</Response>'''
    
    print(f"Response TwiML:\n{twiml}")
    return Response(content=twiml, media_type='text/xml')

@app.post('/test')
@app.get('/test')
async def test_webhook():
    """Even simpler test"""
    twiml = '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Test successful</Say>
    <Hangup/>
</Response>'''
    return Response(content=twiml, media_type='text/xml')

if __name__ == '__main__':
    print("🐛 Starting Debug Webhook Server...")
    print("Test URLs:")
    print("  - http://localhost:5001/debug")
    print("  - http://localhost:5001/test")
    uvicorn.run(app, host='0.0.0.0', port=5001, log_level="info")