import os
import asyncio
import logging
import yt_dlp
import sys
import subprocess
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

import socket
from aiohttp import TCPConnector
from aiogram.client.session.aiohttp import AiohttpSession

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN is not set!")
    sys.exit(1)

dp = Dispatcher()

COOKIES_PATH = "cookies.txt"

class MyLogger:
    def debug(self, msg):
        if any(x in msg for x in ["[pot]", "Signature", "n-parameter", "EJS", "ejs"]):
            logger.info(f"DEBUG: {msg}")
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
        if current_time - last_update_time[0] > 3:
            try:
                text = f"⏳ Скачивание: {p}\n🚀 Скорость: {speed}\n⏱ ETA: {eta}"
                await message.edit_text(text)
                last_update_time[0] = current_time
            except Exception:
                pass

# Путь к локальному FFmpeg (для Alwaysdata)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOCAL_FFMPEG = os.path.join(PROJECT_ROOT, "bin", "ffmpeg")

def get_ffmpeg_path():
    if os.path.exists(LOCAL_FFMPEG):
        return LOCAL_FFMPEG
    return "ffmpeg" # Используем системный, если локального нет

def get_video_info(url):
    """Получает информацию о видео без скачивания"""
    ydl_opts = {
        'cookiefile': COOKIES_PATH if os.path.exists(COOKIES_PATH) else None,
        'noplaylist': True,
        'quiet': True,
        'enable_remote_components': 'ejs:github',
        'ffmpeg_location': get_ffmpeg_path(),
        'js_runtimes': {'node': {}},
        'cachedir': os.path.join(PROJECT_ROOT, '.cache'),
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'tv'],
            }
        },
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def download_video(url, message: types.Message, loop):
    last_update_time = [loop.time()]
    
    ffmpeg_path = get_ffmpeg_path()
    
    try:
        # Проверка версии с учетом пути к ffmpeg
        subprocess.run([ffmpeg_path, "-version"], capture_output=True)
    except:
        logger.warning(f"FFmpeg not found at {ffmpeg_path}")

    ydl_opts = {
        'format': 'bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/best[height<=1080][vcodec^=avc1]/best[ext=mp4]/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'logger': MyLogger(),
        'progress_hooks': [lambda d: asyncio.run_coroutine_threadsafe(progress_hook(d, message, last_update_time), loop)],
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'enable_remote_components': 'ejs:github',
        'ffmpeg_location': ffmpeg_path,
        'js_runtimes': {'node': {}},
        'cachedir': os.path.join(PROJECT_ROOT, '.cache'),
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'tv'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        },
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
    }

    if os.path.exists(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 0:
        ydl_opts['cookiefile'] = COOKIES_PATH

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        mp4_path = os.path.splitext(filename)[0] + '.mp4'
        if os.path.exists(mp4_path):
            return mp4_path
        return filename

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Я скачиваю видео в лучшем качестве (до 50 МБ).\nПросто пришли мне ссылку!")

@dp.message(F.text.regexp(r'^(https?://)'))
async def handle_link(message: types.Message):
    url = message.text
    status_msg = await message.answer("🔍 Проверяю размер файла...")
    
    loop = asyncio.get_event_loop()
    
    try:
        # Сначала проверяем информацию о файле
        info = await loop.run_in_executor(None, get_video_info, url)
        
        # Пытаемся определить размер (в байтах)
        filesize = info.get('filesize') or info.get('filesize_approx')
        
        if filesize and filesize > 50 * 1024 * 1024:
            size_mb = round(filesize / (1024 * 1024), 1)
            await status_msg.edit_text(
                f"⚠️ К сожалению, это видео весит около {size_mb} МБ.\n\n"
                "На данный момент скачивание файлов больше 50 МБ невозможно, "
                "но это временное ограничение. Попробуйте видео покороче! 😊"
            )
            return

        await status_msg.edit_text("⏳ Размер подходит. Начинаю скачивание...")
        
        os.makedirs("downloads", exist_ok=True)
        file_path = await loop.run_in_executor(None, download_video, url, status_msg, loop)
        
        # Дополнительная проверка реального размера после скачивания
        real_size = os.path.getsize(file_path)
        if real_size > 50 * 1024 * 1024:
            os.remove(file_path)
            await status_msg.edit_text("❌ Упс! После обработки файл превысил 50 МБ. Пока не могу его отправить.")
            return

        await status_msg.edit_text("✅ Готово! Отправляю видео...")
        
        video = FSInputFile(file_path)
        await message.answer_video(video, caption=f"🎬 {info.get('title', 'Видео')}")
        await status_msg.delete()
        
        if os.path.exists(file_path):
            os.remove(file_path)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text(f"❌ Произошла ошибка: {str(e)}")

async def main():
    logger.info("Bot is starting...")
    proxy_url = os.getenv("TELEGRAM_PROXY", "socks5://127.0.0.1:4001")
    logger.info(f"Using Telegram Proxy: {proxy_url}")
    
    session = AiohttpSession(proxy=proxy_url)
    bot = Bot(token=BOT_TOKEN, session=session)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")
