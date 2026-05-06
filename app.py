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

# Путь к куки
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

def download_video(url, message: types.Message, loop):
    last_update_time = [loop.time()]
    
    ydl_opts = {
        # Формат как в Shortcut (1080p mp4 preference)
        'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'logger': MyLogger(),
        'progress_hooks': [lambda d: asyncio.run_coroutine_threadsafe(progress_hook(d, message, last_update_time), loop)],
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'enable_remote_components': True,
        'extractor_args': {
            'youtube': {
                # Используем android и ios — они меньше всего подвержены 429 ошибке
                'player_client': ['android', 'ios', 'mweb'],
                'skip': ['web', 'web_embedded'] # Пропускаем веб-клиенты, они заблокированы на Railway
            }
        },
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        # Добавляем заголовки, чтобы имитировать браузер
        'http_headers': {
            'User-Agent': 'com.google.android.youtube/19.16.36 (Linux; U; Android 14; en_US; Pixel 8 Pro) gzip',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        }
    }

    # ПРОВЕРКА КУКИ: Это критически важно для обхода 429 ошибки на Railway
    if os.path.exists(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 0:
        logger.info(f"Using cookies from {COOKIES_PATH}")
        ydl_opts['cookiefile'] = COOKIES_PATH
    else:
        logger.warning("COOKIES_PATH not found or empty! This will likely lead to 429 error on Railway.")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        mp4_path = os.path.splitext(filename)[0] + '.mp4'
        return mp4_path if os.path.exists(mp4_path) else filename

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Пришли ссылку на YouTube. (Использую Android/iOS клиенты для обхода блокировок)")

@dp.message(F.text.regexp(r'^(https?://)'))
async def handle_link(message: types.Message):
    url = message.text
    status_msg = await message.answer("⏳ Анализирую (имитация Android)...")
    
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
        logger.error(f"Download error: {e}")
        # Если это 429, даем совет пользователю
        error_text = str(e)
        if "429" in error_text:
            error_text = "❌ Ошибка 429 (Too Many Requests). YouTube заблокировал IP сервера. Нужно обновить cookies.txt."
        await status_msg.edit_text(error_text)

async def main():
    logger.info("Bot is starting...")
    await asyncio.sleep(5)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")
