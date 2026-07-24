import os
import re
import sys
import json
import shutil
import asyncio
import logging
import subprocess
import yt_dlp
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.client.session.aiohttp import AiohttpSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

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

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOCAL_FFMPEG = os.path.join(PROJECT_ROOT, "bin", "ffmpeg")

def get_ffmpeg_path():
    if os.path.exists(LOCAL_FFMPEG):
        return LOCAL_FFMPEG
    return shutil.which("ffmpeg") or "ffmpeg"

def get_ffprobe_path():
    ffmpeg_p = get_ffmpeg_path()
    if ffmpeg_p and "ffmpeg" in ffmpeg_p:
        candidate = ffmpeg_p.replace("ffmpeg", "ffprobe")
        if os.path.exists(candidate):
            return candidate
    return shutil.which("ffprobe") or "ffprobe"

def get_video_metadata(file_path: str):
    ffprobe_path = get_ffprobe_path()
    cmd = [
        ffprobe_path,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        file_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(result.stdout)
        
        width = None
        height = None
        duration = None
        
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = int(stream.get("width", 0)) or None
                height = int(stream.get("height", 0)) or None
                
                rotation = 0
                for side_data in stream.get("side_data_list", []):
                    if "rotation" in side_data:
                        rotation = abs(int(side_data["rotation"]))
                if "tags" in stream and "rotate" in stream.get("tags", {}):
                    try:
                        rotation = abs(int(stream["tags"]["rotate"]))
                    except ValueError:
                        pass
                        
                if rotation in (90, 270) and width and height:
                    width, height = height, width
                break
                
        if "format" in data and "duration" in data["format"]:
            try:
                duration = int(float(data["format"]["duration"]))
            except (ValueError, TypeError):
                pass
                
        return width, height, duration
    except Exception as e:
        logger.error(f"Metadata error via ffprobe: {e}")
        return None, None, None

def create_video_thumbnail(file_path: str, output_thumb_path: str):
    ffmpeg_path = get_ffmpeg_path()
    cmd = [
        ffmpeg_path,
        "-y",
        "-ss", "00:00:01",
        "-i", file_path,
        "-vframes", "1",
        "-q:v", "2",
        output_thumb_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if os.path.exists(output_thumb_path) and os.path.getsize(output_thumb_path) > 0:
            return output_thumb_path
    except Exception as e:
        logger.error(f"Thumbnail error: {e}")
    return None

async def progress_hook(d, message: types.Message, last_update_time):
    if d["status"] == "downloading":
        p = d.get("_percent_str", "0%")
        speed = d.get("_speed_str", "N/A")
        eta = d.get("_eta_str", "N/A")
        
        current_time = asyncio.get_event_loop().time()
        if current_time - last_update_time[0] > 3:
            try:
                text = f"⏳ Скачивание: {p}\n🚀 Скорость: {speed}\n⏱ ETA: {eta}"
                await message.edit_text(text)
                last_update_time[0] = current_time
            except Exception:
                pass

def get_video_info(url):
    ydl_opts = {
        "noplaylist": True,
        "quiet": True,
        "ffmpeg_location": get_ffmpeg_path(),
        "cachedir": os.path.join(PROJECT_ROOT, ".cache"),
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "android", "mweb", "web"],
            }
        },
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def download_video(url, message: types.Message, loop):
    last_update_time = [loop.time()]
    ffmpeg_path = get_ffmpeg_path()

    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "logger": MyLogger(),
        "progress_hooks": [lambda d: asyncio.run_coroutine_threadsafe(progress_hook(d, message, last_update_time), loop)],
        "merge_output_format": "mp4",
        "noplaylist": True,
        "ffmpeg_location": ffmpeg_path,
        "cachedir": os.path.join(PROJECT_ROOT, ".cache"),
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "android", "mweb", "web"],
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        },
        "postprocessor_args": {
            "ffmpeg": ["-movflags", "+faststart"]
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        mp4_path = os.path.splitext(filename)[0] + ".mp4"
        final_file = mp4_path if os.path.exists(mp4_path) else filename
        return final_file, info

def extract_url(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r"(https?://[^\s]+)", text)
    if match:
        return match.group(1)
    if "youtu" in text:
        match = re.search(r"((?:youtu\.be/|youtube\.com/)[^\s]+)", text)
        if match:
            return "https://" + match.group(1)
    return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    logger.info(f"Received /start from user {message.from_user.id}")
    await message.answer("👋 Привет! Я скачиваю видео из YouTube в максимальном оригинальном качестве без сжатия.\nПросто пришли мне ссылку на видео!")

@dp.message(F.text)
async def handle_text_message(message: types.Message):
    url = extract_url(message.text)
    logger.info(f"Received message from user {message.from_user.id}: {message.text}")
    
    if not url:
        await message.answer("ℹ️ Пожалуйста, отправьте мне ссылку на видео из YouTube (например: https://youtu.be/...)")
        return

    status_msg = await message.answer("🔍 Проверяю ссылку...")
    loop = asyncio.get_event_loop()
    
    try:
        os.makedirs("downloads", exist_ok=True)
        await status_msg.edit_text("⏳ Начинаю скачивание в 100% оригинальном качестве (без сжатия)...")
        
        file_path, video_info = await loop.run_in_executor(None, download_video, url, status_msg, loop)

        await status_msg.edit_text("✅ Готово! Подготавливаю и отправляю видео...")
        
        width, height, duration = await loop.run_in_executor(None, get_video_metadata, file_path)
        
        if not width or not height:
            width = video_info.get("width")
            height = video_info.get("height")
        if not duration:
            duration = video_info.get("duration")
            
        title = video_info.get("title", "Видео")

        thumb_file_path = os.path.splitext(file_path)[0] + "_thumb.jpg"
        thumb_result = await loop.run_in_executor(None, create_video_thumbnail, file_path, thumb_file_path)

        video = FSInputFile(file_path)
        thumbnail = FSInputFile(thumb_result) if thumb_result else None

        await message.answer_video(
            video,
            caption=f"🎬 {title}",
            width=width,
            height=height,
            duration=int(duration) if duration else None,
            thumbnail=thumbnail,
            supports_streaming=True
        )
        await status_msg.delete()
        
        if os.path.exists(file_path):
            os.remove(file_path)
        if thumb_result and os.path.exists(thumb_result):
            os.remove(thumb_result)
            
    except Exception as e:
        logger.error(f"Error processing URL {url}: {e}")
        await status_msg.edit_text(f"❌ Произошла ошибка при скачивании: {str(e)}")

async def main():
    logger.info("Bot is starting...")
    proxy_url = os.getenv("TELEGRAM_PROXY")
    
    if proxy_url:
        logger.info(f"Using Telegram Proxy: {proxy_url}")
        session = AiohttpSession(proxy=proxy_url)
        bot = Bot(token=BOT_TOKEN, session=session)
    else:
        bot = Bot(token=BOT_TOKEN)
        
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")
