import os
import asyncio
import logging
import yt_dlp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Путь к куки
COOKIES_PATH = "cookies.txt"

class MyLogger:
    def debug(self, msg):
        pass
    def warning(self, msg):
        logger.warning(msg)
    def error(self, msg):
        logger.error(msg)

async def progress_hook(d, message: types.Message, last_update_time):
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%')
        speed = d.get('_speed_str', 'N/A')
        eta = d.get('_eta_str', 'N/A')
        
        current_time = asyncio.get_event_loop().time()
        # Обновляем сообщение раз в 2 секунды, чтобы избежать флуда
        if current_time - last_update_time[0] > 2:
            try:
                text = f"⏳ Скачивание: {p}\n🚀 Скорость: {speed}\n⏱ Оставшееся время: {eta}"
                await message.edit_text(text)
                last_update_time[0] = current_time
            except Exception as e:
                logger.debug(f"Update error: {e}")

def download_video(url, message: types.Message, loop):
    last_update_time = [loop.time()]
    
    ydl_opts = {
        'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'logger': MyLogger(),
        'progress_hooks': [lambda d: asyncio.run_coroutine_threadsafe(progress_hook(d, message, last_update_time), loop)],
        'cookiefile': COOKIES_PATH if os.path.exists(COOKIES_PATH) else None,
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'web'],
            }
        },
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        # After merge/conversion the file is .mp4, but prepare_filename may return original ext
        mp4_path = os.path.splitext(filename)[0] + '.mp4'
        if os.path.exists(mp4_path):
            return mp4_path
        return filename

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Пришли мне ссылку на видео из YouTube, и я его скачаю.")

@dp.message(F.text.regexp(r'^(https?://)'))
async def handle_link(message: types.Message):
    url = message.text
    status_msg = await message.answer("⏳ Анализирую ссылку...")
    
    loop = asyncio.get_event_loop()
    
    try:
        # Создаем папку для загрузок, если её нет
        os.makedirs("downloads", exist_ok=True)
        
        # Скачиваем видео в отдельном потоке, чтобы не блокировать бота
        file_path = await loop.run_in_executor(None, download_video, url, status_msg, loop)
        
        await status_msg.edit_text("✅ Скачивание завершено! Начинаю выгрузку в Telegram...")
        
        # Отправляем видео
        video = FSInputFile(file_path)
        await message.answer_video(video, caption="Ваше видео готово!")
        
        await status_msg.delete()
        
        # Удаляем файл после отправки
        if os.path.exists(file_path):
            os.remove(file_path)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text(f"❌ Произошла ошибка: {str(e)}")
        # Попытка очистки при ошибке
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

async def main():
    logger.info("Bot is starting...")
    
    # Проверка наличия node.js для yt-dlp
    import subprocess
    try:
        node_version = subprocess.check_output(["node", "--version"]).decode().strip()
        logger.info(f"Node.js found: {node_version}")
    except Exception as e:
        logger.warning(f"Node.js NOT found: {e}")

    # Удаляем вебхук, если он был установлен ранее (решает ошибку Conflict)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")
