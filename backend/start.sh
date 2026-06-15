#!/bin/bash
# Render.com के लिए start script

echo "🚀 Starting YouTube Downloader Backend..."

# yt-dlp install करें
pip install yt-dlp

# ffmpeg install करें
apt-get update -qq
apt-get install -y -qq ffmpeg

# Download directory बनाएं
mkdir -p /var/data/downloads

# गुनिकॉर्न से app start करें
gunicorn app:app --bind 0.0.0.0:5000 --workers 2
