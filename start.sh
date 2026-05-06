#!/bin/bash

# Запускаем PO Token provider сервер в фоне
echo "Starting PO Token provider server..."
cd /opt/bgutil-ytdlp-pot-provider/server
node build/main.js &
POT_PID=$!

# Ждём пока сервер запустится
sleep 3
echo "PO Token provider server started (PID: $POT_PID)"

# Запускаем основного бота
cd /app
echo "Starting Telegram bot..."
python app.py

# Если бот упал, убиваем сервер
kill $POT_PID 2>/dev/null
