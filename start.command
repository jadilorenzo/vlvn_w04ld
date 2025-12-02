#!/usr/bin/env bash
cd "$(dirname "$0")"

# Start Playit tunnel in background
if [ -x "../playit-agent" ]; then
  echo "🌐 Starting Playit tunnel..."
  ./playit > playit.log 2>&1 &
  PLAYIT_PID=$!
else
  echo "ℹ️  Playit not found or not executable; skipping tunnel."
  PLAYIT_PID=""
fi

# Launch NeoForge server
bash ./run.sh nogui

# Stop Playit when server stops
if [ -n "$PLAYIT_PID" ]; then
  echo "🛑 Stopping Playit tunnel..."
  kill "$PLAYIT_PID" 2>/dev/null
fi