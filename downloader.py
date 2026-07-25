import os
import re
import sys
import json
import shutil
import logging
import subprocess
import requests
import yt_dlp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
COOKIES_PATH = os.path.join(PROJECT_ROOT, "cookies.txt")

def get_ffmpeg_path():
    p = shutil.which("ffmpeg")
    return p if p else "ffmpeg"

def get_ffprobe_path():
    p = shutil.which("ffprobe")
    return p if p else "ffprobe"

def detect_platform_and_url(text: str) -> tuple[str, str, str]:
    url_match = re.search(r'https?://[^\s]+', text)
    if not url_match:
        return None, None, None

    url = url_match.group(0)

    if "youtube.com" in url or "youtu.be" in url:
        return "YouTube", "🎬", url
    elif "tiktok.com" in url:
        return "TikTok", "🎵", url
    elif "instagram.com" in url:
        return "Instagram", "📸", url
    elif "pinterest.com" in url or "pin.it" in url:
        return "Pinterest", "📌", url
    elif "twitter.com" in url or "x.com" in url:
        return "Twitter/X", "🐦", url
    else:
        return "Media", "📹", url

class MyLogger:
    def debug(self, msg):
        if any(x in msg for x in ["[pot]", "Signature", "n-parameter", "EJS", "ejs"]):
            logger.info(f"DEBUG: {msg}")
    def warning(self, msg):
        logger.warning(msg)
    def error(self, msg):
        logger.error(msg)

def get_base_ydl_opts(quality: str = 'best', use_cookies: bool = True, player_clients: list = None):
    ffmpeg_path = get_ffmpeg_path()

    if quality == '720p':
        format_spec = (
            "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo[height<=720]+bestaudio"
            "/best[height<=720][ext=mp4]"
            "/best[height<=720]"
            "/best"
        )
    elif quality == '480p':
        format_spec = (
            "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo[height<=480]+bestaudio"
            "/best[height<=480][ext=mp4]"
            "/best[height<=480]"
            "/best"
        )
    elif quality == 'mp3':
        format_spec = "bestaudio[ext=m4a]/bestaudio/best"
    else:
        # Best quality — fallback chain from merged mp4 to any container
        format_spec = (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo+bestaudio"
            "/best[ext=mp4]"
            "/best"
        )

    # IMPORTANT: Only 'web' and 'mweb' clients support cookies.
    # 'android' and 'ios' silently SKIP cookies — never include them in cookie-based calls.
    if not player_clients:
        player_clients = ["default,-tv"]

    ydl_opts = {
        "format": format_spec,
        "format_sort": ["res", "ext:mp4:m4a", "codec:h264:aac"],
        "merge_output_format": "mp4",
        "noplaylist": True,
        "ffmpeg_location": ffmpeg_path,
        # Disable cache to avoid stale session conflicts
        "cachedir": False,
        "js_runtimes": {"node": {}},
        "remote_components": {"ejs:github", "ejs:npm"},
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        },
        "extractor_args": {
            "youtube": {
                "player_client": player_clients
            }
        },
        "postprocessor_args": {
            "ffmpeg": ["-movflags", "+faststart"]
        }
    }

    # Node.js is installed in PATH via Dockerfile (nodesource setup_20.x)
    # yt-dlp auto-detects it from PATH — no need to pass js_runtimes manually
    # yt-dlp-ejs package provides the EJS challenge solver scripts automatically

    if use_cookies and os.path.exists(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 0:
        c_size = os.path.getsize(COOKIES_PATH)
        logger.info(f"🍪 Active Cookies File Loaded: {COOKIES_PATH} (Size: {c_size} bytes)")
        ydl_opts["cookiefile"] = COOKIES_PATH
    else:
        logger.warning(f"⚠️ No cookies file found at {COOKIES_PATH} — downloads may be blocked by YouTube!")

    return ydl_opts

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

def ensure_h264_codec(file_path: str) -> str:
    ffprobe_path = get_ffprobe_path()
    cmd_probe = [
        ffprobe_path,
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        file_path
    ]
    try:
        res = subprocess.run(cmd_probe, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(res.stdout)
        codec_name = ""
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                codec_name = stream.get("codec_name", "").lower()
                break
                
        if "h264" in codec_name or "avc" in codec_name:
            return file_path
            
        logger.info(f"Converting codec {codec_name} to H.264...")
        converted_path = os.path.splitext(file_path)[0] + "_h264.mp4"
        ffmpeg_path = get_ffmpeg_path()
        cmd_convert = [
            ffmpeg_path,
            "-y",
            "-i", file_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "18",
            "-c:a", "copy",
            "-movflags", "+faststart",
            converted_path
        ]
        subprocess.run(cmd_convert, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if os.path.exists(converted_path) and os.path.getsize(converted_path) > 0:
            os.remove(file_path)
            return converted_path
    except Exception as e:
        logger.error(f"Error ensuring H264 codec: {e}")
        
    return file_path

def compress_video_to_target_size(file_path: str, target_mb: float = 48.0) -> str:
    if not os.path.exists(file_path):
        return file_path
    
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb <= target_mb:
        return file_path

    logger.info(f"File size is {file_size_mb:.2f} MB > {target_mb} MB limit. Auto-compressing video...")
    
    width, height, duration = get_video_metadata(file_path)
    if not duration or duration <= 0:
        duration = 60
        
    target_total_bitrate = (target_mb * 8 * 1024 * 1024 * 0.95) / duration
    audio_bitrate = 128 * 1024
    video_bitrate = max(int((target_total_bitrate - audio_bitrate) / 1000), 200)

    compressed_path = os.path.splitext(file_path)[0] + "_compressed.mp4"
    ffmpeg_path = get_ffmpeg_path()
    
    cmd = [
        ffmpeg_path,
        "-y",
        "-i", file_path,
        "-c:v", "libx264",
        "-b:v", f"{video_bitrate}k",
        "-maxrate", f"{int(video_bitrate * 1.5)}k",
        "-bufsize", f"{int(video_bitrate * 2)}k",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        compressed_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if os.path.exists(compressed_path) and os.path.getsize(compressed_path) > 0:
            os.remove(file_path)
            return compressed_path
    except Exception as e:
        logger.error(f"Error compressing video: {e}")
        
    return file_path

def convert_to_mp3(file_path: str) -> str:
    mp3_path = os.path.splitext(file_path)[0] + ".mp3"
    ffmpeg_path = get_ffmpeg_path()
    cmd = [
        ffmpeg_path,
        "-y",
        "-i", file_path,
        "-vn",
        "-acodec", "libmp3lame",
        "-q:a", "2",
        mp3_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
            if os.path.exists(file_path) and file_path != mp3_path:
                os.remove(file_path)
            return mp3_path
    except Exception as e:
        logger.error(f"Error converting to MP3: {e}")

    return file_path

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

def download_via_cobalt_fallback(url: str, quality: str) -> tuple[str, dict]:
    logger.info("⚡️ Trying Cobalt API fallback for YouTube video...")
    # Only use the main official cobalt API (others have DNS issues on VPS)
    api_urls = [
        "https://api.cobalt.tools/api/json",
    ]
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    vq = "1080" if quality == "best" else ("720" if quality == "720p" else "480")
    payload = {
        "url": url,
        "videoQuality": vq,
        "isAudioOnly": True if quality == "mp3" else False
    }

    for endpoint in api_urls:
        try:
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=15)
            if resp.status_code in (200, 201):
                data = resp.json()
                media_url = data.get("url")
                if media_url:
                    r = requests.get(media_url, stream=True, timeout=120)
                    if r.status_code == 200:
                        os.makedirs("downloads", exist_ok=True)
                        ext = ".mp3" if quality == "mp3" else ".mp4"
                        file_path = f"downloads/fallback_{abs(hash(url))}{ext}"
                        with open(file_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=1024*1024):
                                if chunk:
                                    f.write(chunk)
                        logger.info(f"🚀 ✅ Cobalt API fallback successfully downloaded to {file_path}")
                        return file_path, {"title": "YouTube Video"}
        except Exception as e:
            logger.warning(f"Cobalt endpoint {endpoint} failed: {e}")

    raise Exception("Cobalt API fallback failed")

def download_media(url: str, quality: str, progress_fn=None) -> tuple[str, dict]:
    is_youtube = "youtube.com" in url or "youtu.be" in url

    # Download strategy for 2026:
    # Stage 1: default client WITHOUT cookies (let yt-dlp pick default client + bgutil POT handles proof of origin for public videos)
    # Stage 2: mweb WITHOUT cookies (specifically use mweb + POT without attaching potentially expired cookies)
    # Stage 3: mweb WITH cookies (for age-restricted/members-only videos, if valid cookies exist)
    # Stage 4: web WITH cookies (fallback auth)
    # Stage 5: Cobalt API fallback

    stages = [
        {"clients": ["default,-tv"], "use_cookies": False, "label": "default (no cookies, POT enabled)"},
        {"clients": ["mweb"], "use_cookies": False, "label": "mweb (no cookies, POT enabled)"},
        {"clients": ["mweb"], "use_cookies": True, "label": "mweb+cookies+POT"},
        {"clients": ["web"], "use_cookies": True, "label": "web+cookies+POT"},
    ]

    last_exception = None
    for idx, stage in enumerate(stages, start=1):
        try:
            logger.info(f"⏳ Stage {idx} [{stage['label']}] download attempt...")
            ydl_opts = get_base_ydl_opts(
                quality=quality,
                use_cookies=stage["use_cookies"],
                player_clients=stage["clients"]
            )
            ydl_opts["logger"] = MyLogger()
            ydl_opts["outtmpl"] = "downloads/%(id)s.%(ext)s"
            if progress_fn:
                ydl_opts["progress_hooks"] = [progress_fn]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                mp4_path = os.path.splitext(filename)[0] + ".mp4"
                final_file = mp4_path if os.path.exists(mp4_path) else filename
                logger.info(f"✅ Download SUCCESS at stage {idx} [{stage['label']}]: {final_file}")
                return final_file, info
        except Exception as e:
            logger.warning(f"Stage {idx} [{stage['label']}] failed: {e}")
            last_exception = e

    # Stage 3: Cobalt API fallback for YouTube
    if is_youtube:
        try:
            return download_via_cobalt_fallback(url, quality)
        except Exception as cob_err:
            logger.error(f"Cobalt fallback failed: {cob_err}")

    raise last_exception

