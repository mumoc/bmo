#!/bin/bash

echo "🧠 Starting BMO..."

# 📦 Install Python dependencies
echo "📦 Checking Python dependencies..."
pip3 install -q -r requirements.txt

# 🍺 Ensure portaudio is installed (required by sounddevice)
if ! brew list portaudio &>/dev/null; then
  echo "🍺 Installing portaudio via Homebrew..."
  brew install portaudio
fi

# 🔍 Check if Ollama is running
if ! pgrep -x "ollama" > /dev/null
then
  echo "🚀 Starting Ollama..."
  ollama serve > /dev/null 2>&1 &
  sleep 2
else
  echo "✅ Ollama already running"
fi

# 🔍 Check if model is available (optional)
echo "🤖 Ensuring model is ready..."
ollama list | grep llama3 > /dev/null || ollama pull llama3

# 🌐 Start static file server for the face UI
echo "🌐 Starting face server on http://localhost:8080 ..."
python3 -m http.server 8080 --bind 127.0.0.1 > /dev/null 2>&1 &
HTTP_PID=$!

# 🚀 Start BMO brain
echo "🎤 Launching BMO..."
python3 bmo-brain.py

echo "👋 BMO stopped"
kill $HTTP_PID 2>/dev/null