#!/bin/bash
# Script to check the server file for the exact issues
FILE="/root/voca-2.0/src/voca/api.py"

echo "Checking for client.transcriptions.list(call_sid=...) issues:"
grep -n "client.transcriptions.list.*call_sid" "$FILE" | head -10

echo ""
echo "Checking for start.xml = ET.tostring issues:"
grep -n "start.xml.*ET.tostring" "$FILE" | head -10

echo ""
echo "Checking lines 11900-11905:"
sed -n '11900,11905p' "$FILE"

echo ""
echo "Checking lines 11972-11976:"
sed -n '11972,11976p' "$FILE"

