#!/usr/bin/env python3
"""
Fix the Start/Transcription TwiML construction to prevent call disconnections.
The issue is that start.xml = ET.tostring(...) breaks Twilio's XML generation.
We'll manually construct the XML string instead.
"""
import sys
import re

file_path = sys.argv[1] if len(sys.argv) > 1 else "src/voca/api.py"

print(f"Fixing TwiML Transcription construction in {file_path}...")

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

original_content = content

# Pattern to find the problematic Start/Transcription block
# This matches from "Start real-time transcription" through the response.append(start)
pattern = r'''(    # Start real-time transcription with Deepgram Nova-3 for Hindi
    if call_sid:
        # Get base URL for transcription callback
        config = get_twilio_config\(\)
        base_url = config\.get_webhook_url\(\)\.replace\('/webhook/voice', ''\)\.replace\('/outbound', ''\)
        transcription_callback = f"{base_url}/transcription/\{call_sid\}"
        
        # Start real-time transcription
        # The Twilio Python library's Start class can accept child elements
        # We'll construct the Transcription element and add it to Start
        from twilio\.twiml\.voice_response import Start
        start = Start\(\)
        # Add Transcription element with Deepgram settings
        # Using the Start class's internal method to add child elements
        # Add Transcription element with Deepgram settings
        # The Twilio Python library doesn't have a Transcription class, so we construct it manually
        # We'll add the Transcription XML directly to the Start element
        import xml\.etree\.ElementTree as ET
        transcription_elem = ET\.Element\('Transcription'\)
        transcription_elem\.set\('statusCallbackUrl', transcription_callback\)
        transcription_elem\.set\('statusCallbackMethod', 'POST'\)
        transcription_elem\.set\('transcriptionEngine', 'deepgram'\)
        transcription_elem\.set\('speechModel', 'nova-3'\)
        transcription_elem\.set\('languageCode', 'hi-IN'\)
        # Add to Start element by converting to string and appending
        start\.xml = ET\.tostring\(transcription_elem, encoding='unicode'\)
        response\.append\(start\)
        
        logger\.info\(f"\[TRANSCRIPTION\] Started real-time transcription for call \{call_sid\} with Deepgram Nova-3 \(hi-IN\)"\)
        logger\.info\(f"\[TRANSCRIPTION\] Callback URL: \{transcription_callback\}"\)'''

# Replacement: Manually construct the XML string
replacement = '''    # Start real-time transcription with Deepgram Nova-3 for Hindi
    if call_sid:
        # Get base URL for transcription callback
        config = get_twilio_config()
        base_url = config.get_webhook_url().replace('/webhook/voice', '').replace('/outbound', '')
        transcription_callback = f"{base_url}/transcription/{call_sid}"
        
        # Manually construct Start/Transcription XML since Twilio library doesn't support it
        # We'll inject the XML directly into the response
        transcription_xml = f'''<Start>
    <Transcription statusCallbackUrl="{transcription_callback}" statusCallbackMethod="POST" transcriptionEngine="deepgram" speechModel="nova-3" languageCode="hi-IN" />
</Start>'''
        
        # Parse the XML and add it to the response manually
        import xml.etree.ElementTree as ET
        start_elem = ET.fromstring(transcription_xml)
        # Convert back to string and inject into response
        # Since VoiceResponse doesn't support raw XML injection easily, we'll modify the response after creation
        # Actually, the best approach is to construct the entire response as XML for this part
        # But that's complex. Instead, let's use a workaround: add Start without Transcription first, then modify
        
        # Workaround: Use Start with a dummy child, then replace the XML
        from twilio.twiml.voice_response import Start
        start = Start()
        # Manually set the XML content by modifying the internal structure
        # The Start class stores children in _verbs
        transcription_child = ET.Element('Transcription')
        transcription_child.set('statusCallbackUrl', transcription_callback)
        transcription_child.set('statusCallbackMethod', 'POST')
        transcription_child.set('transcriptionEngine', 'deepgram')
        transcription_child.set('speechModel', 'nova-3')
        transcription_child.set('languageCode', 'hi-IN')
        
        # Add to Start's internal _verbs list
        if not hasattr(start, '_verbs'):
            start._verbs = []
        start._verbs.append(transcription_child)
        response.append(start)
        
        logger.info(f"[TRANSCRIPTION] Started real-time transcription for call {call_sid} with Deepgram Nova-3 (hi-IN)")
        logger.info(f"[TRANSCRIPTION] Callback URL: {transcription_callback}")'''

# Try to replace
new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)

if new_content == content:
    # Try a simpler pattern - just find and replace the problematic line
    simple_pattern = r'start\.xml\s*=\s*ET\.tostring\(transcription_elem, encoding=\'unicode\'\)'
    if re.search(simple_pattern, content):
        print("Found start.xml = ET.tostring pattern, fixing...")
        # Find the context and replace
        def fix_start_xml(match):
            return '''# Fixed: using _verbs approach
        if not hasattr(start, '_verbs'):
            start._verbs = []
        start._verbs.append(transcription_elem)'''
        
        new_content = re.sub(
            r'(\s+)# Add to Start element by converting to string and appending\n\s+start\.xml\s*=\s*ET\.tostring\([^)]+\)',
            r'\1# Fixed: using _verbs approach\n\1if not hasattr(start, \'_verbs\'):\n\1    start._verbs = []\n\1start._verbs.append(transcription_elem)',
            new_content
        )
    else:
        print("Could not find the problematic pattern. File might already be fixed or pattern is different.")
        print("Searching for variations...")
        # Search for any start.xml assignments
        if 'start.xml' in content:
            print("Found 'start.xml' in file - manual inspection needed")
        else:
            print("No 'start.xml' found - issue might be elsewhere")

if new_content != original_content:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("✓ Fixed TwiML Transcription construction!")
    print("The call should no longer disconnect after the welcome message.")
else:
    print("No changes made. The file might already be correct or the pattern is different.")
    print("\nTo debug, check the TwiML response in Twilio logs or add logging:")
    print("  logger.info(f'Generated TwiML: {str(response)}')")

