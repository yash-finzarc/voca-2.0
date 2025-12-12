#!/usr/bin/env python3
"""
Fix errors that are occurring on the server:
1. Fix transcription API call: client.transcriptions.list(call_sid=call_sid, limit=10) -> call.transcriptions.list(limit=10)
2. Fix Start/Transcription XML: start.xml = ET.tostring(...) -> use _verbs approach
"""
import sys
import re

file_path = sys.argv[1] if len(sys.argv) > 1 else "src/voca/api.py"

print(f"Fixing errors in {file_path}...")

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

original_content = content

# Fix 1: Replace all instances of client.transcriptions.list(call_sid=call_sid, limit=10)
content = content.replace(
    'client.transcriptions.list(call_sid=call_sid, limit=10)',
    'call.transcriptions.list(limit=10)'
)

# Fix 2: Replace start.xml = ET.tostring(...) pattern
# Find the pattern and replace with proper _verbs approach
pattern = r'(\s+# Add to Start element by converting to string and appending\n\s+start\.xml = ET\.tostring\(transcription_elem, encoding=\'unicode\'\)\n\s+response\.append\(start\))'

def replace_start_xml(match):
    indent = '        '
    return f'''{indent}# Add Transcription element to Start's children using the library's internal structure
{indent}# The Start class uses _verbs list to store child elements
{indent}if not hasattr(start, '_verbs'):
{indent}    start._verbs = []
{indent}start._verbs.append(transcription_elem)
{indent}response.append(start)'''

content = re.sub(pattern, replace_start_xml, content)

# Count changes
changes1 = original_content.count('client.transcriptions.list(call_sid=call_sid, limit=10)')
changes2 = original_content.count('start.xml = ET.tostring(transcription_elem, encoding=\'unicode\')')

print(f"Found {changes1} instances of client.transcriptions.list(call_sid=...)")
print(f"Found {changes2} instances of start.xml = ET.tostring(...)")

if content != original_content:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✓ Fixed errors in file!")
else:
    print("No changes needed.")

