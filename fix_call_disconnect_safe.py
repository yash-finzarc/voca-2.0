#!/usr/bin/env python3
"""
Safe fix for call disconnection - fixes start.xml issue and adds error handling
"""
import sys
import re

file_path = sys.argv[1] if len(sys.argv) > 1 else "/root/voca-2.0/src/voca/api.py"

print(f"Fixing call disconnection in {file_path}...")

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

fixes = 0
i = 0
while i < len(lines):
    line = lines[i]
    
    # Find start.xml = ET.tostring(...) lines
    if 'start.xml' in line and 'ET.tostring' in line:
        line_num = i + 1
        print(f"Found issue at line {line_num}")
        
        # Find the comment before it
        if i > 0 and 'Add to Start element' in lines[i-1]:
            # Replace the comment
            lines[i-1] = "        # Add Transcription element to Start's children using _verbs\n"
            # Replace the problematic line
            lines[i] = "        # The Start class uses _verbs list to store child elements\n"
            # Insert new lines
            lines.insert(i+1, "        if not hasattr(start, '_verbs'):\n")
            lines.insert(i+2, "            start._verbs = []\n")
            lines.insert(i+3, "        start._verbs.append(transcription_elem)\n")
            # Skip the inserted lines
            i += 4
            fixes += 1
        else:
            # Just comment out the problematic line and add fix
            lines[i] = "        # FIXED: start.xml assignment removed - using _verbs instead\n"
            # Insert fix after
            lines.insert(i+1, "        if not hasattr(start, '_verbs'):\n")
            lines.insert(i+2, "            start._verbs = []\n")
            lines.insert(i+3, "        start._verbs.append(transcription_elem)\n")
            i += 4
            fixes += 1
        continue
    
    # Also add error handling around TwiML generation
    if 'return Response(content=str(response), media_type=\'text/xml\')' in line:
        # Add try/except around TwiML generation
        indent = len(line) - len(line.lstrip())
        indent_str = ' ' * indent
        
        # Insert try block before return
        lines.insert(i, f"{indent_str}try:\n")
        lines.insert(i+1, f"{indent_str}    twiml_str = str(response)\n")
        lines.insert(i+2, f"{indent_str}    logger.debug(f'Generated TwiML for call {{call_sid}}: {{twiml_str[:200]}}...')\n")
        lines.insert(i+3, f"{indent_str}except Exception as e:\n")
        lines.insert(i+4, f"{indent_str}    logger.error(f'Error generating TwiML: {{e}}', exc_info=True)\n")
        lines.insert(i+5, f"{indent_str}    # Return minimal valid TwiML to prevent disconnection\n")
        lines.insert(i+6, f"{indent_str}    response = VoiceResponse()\n")
        lines.insert(i+7, f"{indent_str}    response.say('Sorry, there was an error. Please try again later.')\n")
        lines.insert(i+8, f"{indent_str}    twiml_str = str(response)\n")
        lines.insert(i+9, f"{indent_str}\n")
        # Update the return line
        lines[i+10] = f"{indent_str}return Response(content=twiml_str, media_type='text/xml')\n"
        i += 11
        fixes += 1
        continue
    
    i += 1

if fixes > 0:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f"✓ Fixed {fixes} issue(s)! Please restart the server.")
else:
    print("No issues found. The file might already be correct.")

