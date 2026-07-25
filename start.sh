#!/bin/bash

echo "--- Starting PO Token provider server ---"
cd /opt/bgutil-ytdlp-pot-provider/server
# Start PO token server in background
node build/main.js > /tmp/pot_server.log 2>&1 &
POT_PID=$!

# Give server time to initialize
sleep 3

if ps -p $POT_PID > /dev/null; then
   echo "✅ PO Token server started successfully on PID $POT_PID"
else
   echo "❌ ERROR: PO Token server failed to start! Last logs:"
   cat /tmp/pot_server.log
   exit 1
fi

echo "--- Starting Telegram Downloader Bot ---"
cd /app
# Use exec so OS signals (SIGTERM/SIGINT) pass directly to Python for graceful shutdown
exec python3 app.py
