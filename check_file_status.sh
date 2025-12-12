#!/bin/bash
# Check the actual status of the api.py file on the server

FILE="/root/voca-2.0/src/voca/api.py"

echo "=== File size and line count ==="
wc -l "$FILE"
ls -lh "$FILE"

echo ""
echo "=== Checking for any /outbound references ==="
grep -n "outbound" "$FILE" | head -5

echo ""
echo "=== Checking for @app.post endpoints ==="
grep -n "@app.post" "$FILE" | head -10

echo ""
echo "=== Checking for VoiceResponse ==="
grep -n "VoiceResponse" "$FILE" | head -5

echo ""
echo "=== First 50 lines of the file ==="
head -50 "$FILE"

echo ""
echo "=== Last 50 lines of the file ==="
tail -50 "$FILE"

