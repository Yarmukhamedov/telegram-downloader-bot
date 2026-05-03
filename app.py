import os
import yt_dlp
import requests
from flask import Flask, request

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)

@app.route('/', methods=['POST'])
def webhook():
    data = request.json
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text")

    if not text or not text.startswith("http"):
        return "ok"

    send_message(chat_id, "⏳ Скачиваю...")

    try:
        ydl_opts = {
            'format': 'best[filesize<50M]',
            'outtmpl': 'video.%(ext)s',
            'cookiefile': 'cookies.txt'
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(text, download=True)
            file_path = ydl.prepare_filename(info)

        send_video(chat_id, file_path)
        os.remove(file_path)

    except Exception as e:
        send_message(chat_id, f"Ошибка: {str(e)}")

    return "ok"

def send_message(chat_id, text):
    requests.post(f"{API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

def send_video(chat_id, file_path):
    with open(file_path, "rb") as f:
        requests.post(f"{API_URL}/sendVideo",
            data={"chat_id": chat_id},
            files={"video": f}
        )

port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
