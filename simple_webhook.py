#!/usr/bin/env python3
"""
Simple webhook that works without AI processing to test the basic flow
"""

from flask import Flask, request, Response
import logging
from twilio.twiml.voice_response import VoiceResponse

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

@app.route('/webhook/voice', methods=['POST'])
def handle_incoming_call():
    """Handle incoming calls with simple responses"""
    print("\n=== INCOMING CALL ===")
    print(f"Form data: {dict(request.form)}")
    
    call_sid = request.form.get('CallSid', 'unknown')
    from_number = request.form.get('From', 'unknown')
    
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
    return Response(twiml, mimetype='text/xml')

@app.route('/process_speech/<call_sid>', methods=['POST'])
def handle_speech(call_sid):
    """Handle speech input with simple responses"""
    print(f"\n=== SPEECH PROCESSING FOR {call_sid} ===")
    print(f"Form data: {dict(request.form)}")
    
    speech_result = request.form.get('SpeechResult', '')
    confidence = request.form.get('Confidence', '0')
    
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
            return Response(str(response), mimetype='text/xml')
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
    return Response(twiml, mimetype='text/xml')

@app.route('/outbound', methods=['POST'])
def handle_outbound_call():
    """Handle outbound calls"""
    print("\n=== OUTBOUND CALL ===")
    print(f"Form data: {dict(request.form)}")
    
    call_sid = request.form.get('CallSid', 'unknown')
    to_number = request.form.get('To', 'unknown')
    
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
    return Response(twiml, mimetype='text/xml')

@app.route('/call/status', methods=['POST'])
def handle_call_status():
    """Handle call status updates"""
    print(f"\n=== CALL STATUS ===")
    print(f"Form data: {dict(request.form)}")
    return Response("OK", status=200)

if __name__ == '__main__':
    print("🚀 Starting Simple Webhook Server...")
    print("This webhook works without AI processing to test basic functionality")
    app.run(host='0.0.0.0', port=5002, debug=True)
