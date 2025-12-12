#!/usr/bin/env python3
"""
Robust fix for errors on the server - uses regex to find variations
"""
import sys
import re

file_path = sys.argv[1] if len(sys.argv) > 1 else "src/voca/api.py"

print(f"Checking {file_path} for errors...")

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

fixes_applied = 0
line_numbers_fixed = []

# Fix 1: Find client.transcriptions.list(call_sid=...) patterns
for i, line in enumerate(lines):
    if 'client.transcriptions.list' in line and 'call_sid' in line:
        # Find the line number in the original content
        line_num = i + 1
        print(f"Found issue at line {line_num}: {line.strip()}")
        # Replace with call.transcriptions.list(limit=10)
        lines[i] = re.sub(
            r'client\.transcriptions\.list\([^)]*call_sid[^)]*\)',
            'call.transcriptions.list(limit=10)',
            line
        )
        fixes_applied += 1
        line_numbers_fixed.append(line_num)

# Fix 2: Find start.xml = ET.tostring(...) patterns
for i, line in enumerate(lines):
    if 'start.xml' in line and 'ET.tostring' in line:
        line_num = i + 1
        print(f"Found issue at line {line_num}: {line.strip()}")
        
        # Find the comment line before it
        if i > 0 and 'Add to Start element' in lines[i-1]:
            # Replace the comment
            lines[i-1] = "        # Add Transcription element to Start's children using the library's internal structure\n"
            # Replace the problematic line
            lines[i] = "        # The Start class uses _verbs list to store child elements\n"
            # Insert new lines
            lines.insert(i+1, "        if not hasattr(start, '_verbs'):\n")
            lines.insert(i+2, "            start._verbs = []\n")
            lines.insert(i+3, "        start._verbs.append(transcription_elem)\n")
            # Check if response.append(start) is on the next line
            if i+4 < len(lines) and 'response.append(start)' in lines[i+4]:
                # Keep it, it's already there
                pass
            else:
                # Add it
                lines.insert(i+4, "        response.append(start)\n")
            fixes_applied += 1
            line_numbers_fixed.append(line_num)
        else:
            # Just replace the line directly
            lines[i] = re.sub(
                r'start\.xml\s*=\s*ET\.tostring\([^)]+\)',
                "# Fixed: using _verbs approach (see lines above)",
                line
            )
            fixes_applied += 1
            line_numbers_fixed.append(line_num)

if fixes_applied > 0:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f"\n✓ Fixed {fixes_applied} issues at lines: {line_numbers_fixed}")
    print("Please restart the server to apply changes.")
else:
    print("\n✓ No issues found - file appears to be correct.")
    print("\nIf errors persist, please check:")
    print("  1. The exact line numbers from the error traceback")
    print("  2. Whether the file was recently modified")
    print("  3. Run: grep -n 'client.transcriptions.list' " + file_path)
    print("  4. Run: grep -n 'start.xml' " + file_path)
