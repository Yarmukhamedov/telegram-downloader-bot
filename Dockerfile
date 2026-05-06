# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем системные зависимости (FFmpeg, Node.js, git, npm)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем PO Token плагин для yt-dlp
RUN pip install --no-cache-dir bgutil-ytdlp-pot-provider

# Клонируем и собираем bgutil PO Token provider server
RUN git clone https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil-ytdlp-pot-provider \
    && cd /opt/bgutil-ytdlp-pot-provider/server \
    && npm install \
    && npx tsc

# ПРЕДУСТАНОВКА EJS компонентов (Signature Solver)
RUN yt-dlp --remote-components ejs:github --version

# Копируем остальные файлы проекта
COPY . .

# Скрипт запуска
RUN chmod +x start.sh

CMD ["./start.sh"]
