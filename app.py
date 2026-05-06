import os
import asyncio
import logging
import yt_dlp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Состояния для выбора качества
class DownloadStates(StatesGroup):
    choosing_quality = State()

def get_quality_keyboard(url: str):
    # Как в вашем Shortcut на macOS
    buttons = [
        [InlineKeyboardButton(text="🎬 Best Quality", callback_data=f"q:best|{url}")],
        [InlineKeyboardButton(text="📺 1080p (mp4)", callback_data=f"q:1080|{url}")],
        [InlineKeyboardButton(text="📺 720p (mp4)", callback_data=f"q:720|{url}")],
        [InlineKeyboardButton(text="🎵 Audio Only (mp3)", callback_data=f"q:audio|{url}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def download_video_sync(url, format_type, status_msg_id, chat_id, loop):
    # Форматы как в вашем Shortcut
    if format_type == "best":
        ydl_format = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    elif format_type == "1080":
        ydl_format = "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best"
    elif format_type == "720":
        ydl_format = "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best"
    else: # audio
        ydl_format = "bestaudio/best"

    ydl_opts = {
        'format': ydl_format,
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                # Используем клиентов, которые меньше всего требуют PO Token
                'player_client': ['tv', 'web_creator', 'mweb'],
                'skip': ['hls', 'dash'] 
            }
        },
        # Автоматический PO Token через наш сервер в Docker
        'enable_remote_components': True,
    }

    if format_type == "audio":
        ydl_opts.update({
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        
        # Корректировка расширения
        if format_type == "audio":
            return os.path.splitext(filename)[0] + '.mp3'
        
        mp4_path = os.path.splitext(filename)[0] + '.mp4'
        if os.path.exists(mp4_path):
            return mp4_path
        return filename

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Пришли мне ссылку на YouTube, и выбери качество, как в macOS Shortcuts.")

@dp.message(F.text.regexp(r'^(https?://)'))
async def handle_link(message: types.Message):
    url = message.text
    await message.answer("Выберите формат загрузки:", reply_markup=get_quality_keyboard(url))

@dp.callback_query(F.data.startswith("q:"))
async def process_quality_choice(callback: types.Callback_query):
    data = callback.data.replace("q:", "").split("|")
    quality = data[0]
    url = data[1]
    
    await callback.answer()
    status_msg = await callback.message.edit_text(f"⏳ Начинаю загрузку ({quality})...")
    
    loop = asyncio.get_event_loop()
    try:
        os.makedirs("downloads", exist_ok=True)
        
        file_path = await loop.run_in_executor(None, download_video_sync, url, quality, status_msg.message_id, callback.message.chat.id, loop)
        
        await status_msg.edit_text("✅ Готово! Отправляю файл...")
        
        if quality == "audio":
            await callback.message.answer_audio(FSInputFile(file_path))
        else:
            await callback.message.answer_video(FSInputFile(file_path))
            
        await status_msg.delete()
        if os.path.exists(file_path):
            os.remove(file_path)
            
    except Exception as e:
        logger.error(f"Download error: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}...")

async def main():
    # Проверка PO Token сервера
    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:4416/", timeout=5)
        logger.info("✅ PO Token Provider запущен")
    except:
        logger.warning("⚠️ PO Token Provider не отвечает, возможны ошибки 403")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
