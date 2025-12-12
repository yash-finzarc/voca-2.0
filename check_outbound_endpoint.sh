#!/bin/bash
# Check what the /outbound endpoint actually does

FILE="/root/voca-2.0/src/voca/api.py"

echo "=== Finding /outbound endpoint ==="
grep -n "@app.post(\"/outbound\")" "$FILE" | head -1

echo ""
echo "=== Checking what happens after response.say(greeting) ==="
LINE=$(grep -n "response.say(greeting)" "$FILE" | head -1 | cut -d: -f1)
if [ ! -z "$LINE" ]; then
    echo "Found at line $LINE, showing next 30 lines:"
    START=$LINE
    END=$((LINE + 30))
    sed -n "${START},${END}p" "$FILE"
else
    echo "No 'response.say(greeting)' found"
fi

echo ""
echo "=== Checking for Gather or Start after greeting ==="
grep -A 10 "response.say(greeting)" "$FILE" | head -15

echo ""
echo "=== Checking for return statement in /outbound ==="
# Find the /outbound function and see what it returns
OUTBOUND_LINE=$(grep -n "@app.post(\"/outbound\")" "$FILE" | head -1 | cut -d: -f1)
if [ ! -z "$OUTBOUND_LINE" ]; then
    echo "Found /outbound at line $OUTBOUND_LINE, showing function:"
    sed -n "${OUTBOUND_LINE},$((OUTBOUND_LINE + 200))p" "$FILE" | grep -A 200 "async def handle_outbound_call" | head -100
fi

