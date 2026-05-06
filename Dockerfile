# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем системные зависимости (FFmpeg и Node.js)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Скачиваем EJS challenge solver скрипты для yt-dlp
RUN yt-dlp --remote-components ejs:github --skip-download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" || true

# Копируем остальные файлы проекта
COPY . .

# Команда для запуска
CMD ["python", "app.py"]
