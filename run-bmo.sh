#!/bin/bash

echo "🧠 Starting BMO..."

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

# 🚀 Start BMO brain
echo "🎤 Launching BMO..."
python3 bmo-brain.py

echo "👋 BMO stopped"