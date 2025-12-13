#!/bin/bash
# Script to pull audio files from server

SERVER_HOST="172.105.50.83"
SERVER_USER="root"
SERVER_AUDIO_DIR="/root/voca-2.0/audio_logs"
LOCAL_AUDIO_DIR="audio_logs"

# Create local directory
mkdir -p "$LOCAL_AUDIO_DIR"

# Check if call SID is provided
if [ -z "$1" ]; then
    echo "📥 Pulling ALL audio files from server..."
    scp -r "${SERVER_USER}@${SERVER_HOST}:${SERVER_AUDIO_DIR}/" "$LOCAL_AUDIO_DIR/"
else
    echo "📥 Pulling audio files for call: $1"
    scp -r "${SERVER_USER}@${SERVER_HOST}:${SERVER_AUDIO_DIR}/$1/" "$LOCAL_AUDIO_DIR/$1/"
fi

if [ $? -eq 0 ]; then
    echo "✅ Successfully pulled audio files!"
    echo "📂 Files are in: $(pwd)/$LOCAL_AUDIO_DIR"
else
    echo "❌ Error pulling files. Make sure you have SSH access configured."
fi



