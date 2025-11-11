#!/usr/bin/env python3
"""
Simple webhook that works without AI processing to test the basic flow
"""

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
import logging
import uvicorn
from twilio.twiml.voice_response import VoiceResponse

app = FastAPI(title="Simple Twilio Webhook")
logging.basicConfig(level=logging.DEBUG)

@app.post('/webhook/voice')
async def handle_incoming_call(request: Request):
    """Handle incoming calls with simple responses"""
    form_data = await request.form()
    form_dict = dict(form_data)
    
    print("\n=== INCOMING CALL ===")
    print(f"Form data: {form_dict}")
    
    call_sid = form_data.get('CallSid', 'unknown')
    from_number = form_data.get('From', 'unknown')
    
    print(f"Call SID: {call_sid}")
    print(f"From: {from_number}")
    
    # Create simple TwiML response
    response = VoiceResponse()
    response.say("Hello! This is VOCA calling. How can I help you today?")
    
    # Gather user input
    gather = response.gather(
        input='speech',
        timeout=10,
        speech_timeout='auto',
        action=f'/process_speech/{call_sid}',
        method='POST'
    )
    gather.say("I'm listening...")
    
    # If no input, redirect
    response.redirect(f'/process_speech/{call_sid}')
    
    twiml = str(response)
    print(f"TwiML Response:\n{twiml}")
    return Response(content=twiml, media_type='text/xml')

@app.post('/process_speech/{call_sid}')
async def handle_speech(call_sid: str, request: Request):
    """Handle speech input with simple responses"""
    form_data = await request.form()
    form_dict = dict(form_data)
    
    print(f"\n=== SPEECH PROCESSING FOR {call_sid} ===")
    print(f"Form data: {form_dict}")
    
    speech_result = form_data.get('SpeechResult', '')
    confidence = form_data.get('Confidence', '0')
    
    print(f"Speech: {speech_result}")
    print(f"Confidence: {confidence}")
    
    # Create simple response without AI
    response = VoiceResponse()
    
    if speech_result and float(confidence) > 0.5:
        # Simple response based on keywords
        if 'hello' in speech_result.lower():
            response.say("Hello! Nice to meet you. How are you doing today?")
        elif 'help' in speech_result.lower():
            response.say("I'm here to help! What would you like to know?")
        elif 'bye' in speech_result.lower() or 'goodbye' in speech_result.lower():
            response.say("Goodbye! Have a great day!")
            response.hangup()
            return Response(content=str(response), media_type='text/xml')
        else:
            response.say(f"I heard you say: {speech_result}. That's interesting! Tell me more.")
        
        # Continue conversation
        gather = response.gather(
            input='speech',
            timeout=10,
            speech_timeout='auto',
            action=f'/process_speech/{call_sid}',
            method='POST'
        )
        gather.say("I'm listening...")
        response.redirect(f'/process_speech/{call_sid}')
    else:
        response.say("I didn't catch that. Please try speaking again.")
        response.redirect(f'/process_speech/{call_sid}')
    
    twiml = str(response)
    print(f"TwiML Response:\n{twiml}")
    return Response(content=twiml, media_type='text/xml')

@app.post('/outbound')
async def handle_outbound_call(request: Request):
    """Handle outbound calls"""
    form_data = await request.form()
    form_dict = dict(form_data)
    
    print("\n=== OUTBOUND CALL ===")
    print(f"Form data: {form_dict}")
    
    call_sid = form_data.get('CallSid', 'unknown')
    to_number = form_data.get('To', 'unknown')
    
    print(f"Call SID: {call_sid}")
    print(f"To: {to_number}")
    
    # Create simple TwiML response
    response = VoiceResponse()
    response.say("Hello! This is VOCA calling. How can I help you today?")
    
    # Gather user input
    gather = response.gather(
        input='speech',
        timeout=10,
        speech_timeout='auto',
        action=f'/process_speech/{call_sid}',
        method='POST'
    )
    gather.say("I'm listening...")
    
    # If no input, redirect
    response.redirect(f'/process_speech/{call_sid}')
    
    twiml = str(response)
    print(f"TwiML Response:\n{twiml}")
    return Response(content=twiml, media_type='text/xml')

@app.post('/call/status')
async def handle_call_status(request: Request):
    """Handle call status updates"""
    form_data = await request.form()
    form_dict = dict(form_data)
    
    print(f"\n=== CALL STATUS ===")
    print(f"Form data: {form_dict}")
    return PlainTextResponse("OK", status_code=200)

if __name__ == '__main__':
    print("🚀 Starting Simple Webhook Server...")
    print("This webhook works without AI processing to test basic functionality")
    uvicorn.run(app, host='0.0.0.0', port=5002, log_level="info")
