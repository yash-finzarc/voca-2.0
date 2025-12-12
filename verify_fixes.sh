#!/bin/bash
# Verify that the fixes are in place on the server

FILE="/root/voca-2.0/src/voca/api.py"

echo "=== Checking for client.transcriptions.list(call_sid=...) issues ==="
grep -n "client.transcriptions.list.*call_sid" "$FILE" || echo "✓ No issues found"

echo ""
echo "=== Checking for start.xml = ET.tostring issues ==="
grep -n "start.xml.*ET.tostring" "$FILE" || echo "✓ No issues found"

echo ""
echo "=== Checking if _verbs approach is being used ==="
grep -n "start._verbs.append" "$FILE" | head -3 || echo "⚠ _verbs approach not found"

echo ""
echo "=== Checking for Start/Transcription setup ==="
grep -n "Start real-time transcription" "$FILE" | head -3

echo ""
echo "=== Sample of transcription setup code ==="
grep -A 5 "Start real-time transcription" "$FILE" | head -10

