#!/bin/bash
# Check what's actually in the Start/Transcription setup

FILE="/root/voca-2.0/src/voca/api.py"

echo "=== Finding Start/Transcription setup ==="
grep -n "Start real-time transcription" "$FILE" | head -3

echo ""
echo "=== Checking lines around Start/Transcription (first occurrence) ==="
LINE=$(grep -n "Start real-time transcription" "$FILE" | head -1 | cut -d: -f1)
if [ ! -z "$LINE" ]; then
    echo "Found at line $LINE, showing context:"
    START=$((LINE - 2))
    END=$((LINE + 25))
    sed -n "${START},${END}p" "$FILE"
else
    echo "No 'Start real-time transcription' found"
fi

echo ""
echo "=== Checking for Start() usage ==="
grep -n "from twilio.twiml.voice_response import Start" "$FILE" | head -3
grep -n "start = Start()" "$FILE" | head -3

echo ""
echo "=== Checking how Start is added to response ==="
grep -n "response.append(start)" "$FILE" | head -3

echo ""
echo "=== Checking for any XML/ET usage in transcription context ==="
grep -B 2 -A 2 "transcription_elem" "$FILE" | head -15

