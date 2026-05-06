#!/bin/bash

echo "--- Starting PO Token provider server ---"
cd /opt/bgutil-ytdlp-pot-provider/server
# Запускаем и перенаправляем логи сервера в stdout, чтобы видеть их в Railway
node build/main.js > /tmp/pot_server.log 2>&1 &
POT_PID=$!

# Даем время на запуск
sleep 5

if ps -p $POT_PID > /dev/null
then
   echo "PO Token server started successfully on PID $POT_PID"
else
   echo "ERROR: PO Token server failed to start! Last logs:"
   cat /tmp/pot_server.log
fi

echo "--- Starting Telegram Bot ---"
cd /app
# Используем exec чтобы сигналы (Stop/Restart) доходили до python
exec python3 app.py
