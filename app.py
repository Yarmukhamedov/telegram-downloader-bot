import os
import asyncio
import logging
import yt_dlp
import sys
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

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN is not set!")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

COOKIES_PATH = "cookies.txt"

class MyLogger:
    def debug(self, msg):
        if "[pot]" in msg or "Signature" in msg:
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

def download_video(url, message: types.Message, loop):
    last_update_time = [loop.time()]
    
    ydl_opts = {
        # Используем формат как в твоем Shortcut
        'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'logger': MyLogger(),
        'progress_hooks': [lambda d: asyncio.run_coroutine_threadsafe(progress_hook(d, message, last_update_time), loop)],
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['mweb', 'web', 'tv'],
                'po_token': 'mweb' # Подсказка плагину использовать mweb токен
            }
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
        return mp4_path if os.path.exists(mp4_path) else filename

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Пришли ссылку на YouTube, и я скачаю её в 1080p (если доступно).")

@dp.message(F.text.regexp(r'^(https?://)'))
async def handle_link(message: types.Message):
    url = message.text
    status_msg = await message.answer("⏳ Анализирую...")
    
    loop = asyncio.get_event_loop()
    
    try:
        os.makedirs("downloads", exist_ok=True)
        file_path = await loop.run_in_executor(None, download_video, url, status_msg, loop)
        
        await status_msg.edit_text("✅ Загружено! Отправляю...")
        
        video = FSInputFile(file_path)
        await message.answer_video(video, caption="Готово!")
        await status_msg.delete()
        
        if os.path.exists(file_path):
            os.remove(file_path)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")

async def main():
    logger.info("Bot is starting...")
    
    # Проверка PO Token сервера
    import urllib.request
    await asyncio.sleep(2) # Даем фору start.sh
    try:
        urllib.request.urlopen("http://127.0.0.1:4416/", timeout=5)
        logger.info("✅ PO Token Provider is ONLINE")
    except Exception as e:
        logger.error(f"❌ PO Token Provider is OFFLINE: {e}")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")
