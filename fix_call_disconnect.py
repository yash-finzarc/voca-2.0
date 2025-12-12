#!/usr/bin/env python3
"""
Fix call disconnection issue by properly constructing Start/Transcription TwiML.
The problem: start.xml = ET.tostring(...) breaks Twilio's XML generation.
Solution: Use _verbs list to add Transcription element properly.
"""
import sys
import re

file_path = sys.argv[1] if len(sys.argv) > 1 else "/root/voca-2.0/src/voca/api.py"

print(f"Fixing call disconnection in {file_path}...")

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

original = content
fixes = 0

# Fix 1: Replace start.xml = ET.tostring(...) with _verbs approach
# Find the pattern: start.xml = ET.tostring(transcription_elem, encoding='unicode')
pattern1 = r'(\s+)# Add to Start element by converting to string and appending\n\s+start\.xml\s*=\s*ET\.tostring\(transcription_elem,\s*encoding=\'unicode\'\)\n\s+response\.append\(start\)'

def replace_with_verbs(match):
    indent = match.group(1)
    return f'''{indent}# Add Transcription element to Start's children using _verbs
{indent}if not hasattr(start, '_verbs'):
{indent}    start._verbs = []
{indent}start._verbs.append(transcription_elem)
{indent}response.append(start)'''

content = re.sub(pattern1, replace_with_verbs, content)

# Count fixes
if content != original:
    fixes += content.count('start._verbs.append(transcription_elem)')

# Also try a simpler pattern match
if 'start.xml = ET.tostring' in content:
    print("Found start.xml = ET.tostring pattern(s)")
    # Replace all variations
    content = re.sub(
        r'start\.xml\s*=\s*ET\.tostring\([^)]+\)',
        '''# Fixed: using _verbs (see lines above)
        if not hasattr(start, '_verbs'):
            start._verbs = []
        start._verbs.append(transcription_elem)''',
        content
    )
    fixes += 1

if content != original:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✓ Fixed {fixes} issue(s)! Restart the server.")
else:
    print("No issues found. Checking if _verbs approach is already used...")
    if 'start._verbs.append' in content:
        print("✓ _verbs approach is already in use.")
    else:
        print("⚠ Could not find the pattern. The issue might be elsewhere.")
        print("\nTo debug, add this logging before returning the response:")
        print("  try:")
        print("      twiml_str = str(response)")
        print("      logger.info(f'Generated TwiML: {twiml_str[:500]}')")
        print("  except Exception as e:")
        print("      logger.error(f'TwiML generation error: {e}')")

