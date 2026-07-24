import os
import re
import sys
import json
import shutil
import asyncio
import logging
import subprocess
import yt_dlp

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOCAL_FFMPEG = os.path.join(PROJECT_ROOT, "bin", "ffmpeg")
COOKIES_PATH = "cookies.txt"

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

def detect_platform_and_url(text: str) -> tuple[str | None, str | None, str | None]:
    """
    Detects platform, returns (platform_name, platform_icon, clean_url)
    """
    if not text:
        return None, None, None

    match = re.search(r'(https?://[^\s]+)', text)
    if not match:
        if 'youtu' in text:
            m = re.search(r'((?:youtu\.be/|youtube\.com/)[^\s]+)', text)
            if m:
                return "YouTube", "🎬", "https://" + m.group(1)
        return None, None, None

    url = match.group(1)
    
    if "youtube.com" in url or "youtu.be" in url:
        return "YouTube", "🎬", url
    elif "tiktok.com" in url or "vt.tiktok.com" in url:
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

def get_base_ydl_opts(quality: str = 'best', use_cookies: bool = True):
    ffmpeg_path = get_ffmpeg_path()
    
    if quality == '720p':
        format_spec = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
    elif quality == '480p':
        format_spec = "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
    elif quality == 'mp3':
        format_spec = "bestaudio/best"
    else:
        format_spec = "bestvideo+bestaudio/bestvideo/best/bv*+ba/b"

    ydl_opts = {
        "format": format_spec,
        "format_sort": ["vcodec:h264", "res", "ext:mp4:m4a"],
        "merge_output_format": "mp4",
        "noplaylist": True,
        "ffmpeg_location": ffmpeg_path,
        "cachedir": os.path.join(PROJECT_ROOT, ".cache"),
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        },
        "postprocessor_args": {
            "ffmpeg": ["-movflags", "+faststart"]
        }
    }

    if use_cookies and os.path.exists(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 0:
        ydl_opts["cookiefile"] = COOKIES_PATH

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
    """
    Checks if video codec is H.264. If AV1 or VP9, converts to H.264 (CRF 18 ultrafast)
    for seamless playback in Telegram player.
    """
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

def convert_to_mp3(file_path: str) -> str:
    """
    Converts video/audio file to MP3 format using ffmpeg.
    """
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

def download_media(url: str, quality: str, progress_fn=None) -> tuple[str, dict]:
    """
    Downloads media file according to specified quality.
    Returns (final_file_path, video_info)
    """
    # 1. Primary try with cookies
    try:
        ydl_opts = get_base_ydl_opts(quality=quality, use_cookies=True)
        ydl_opts["logger"] = MyLogger()
        ydl_opts["outtmpl"] = "downloads/%(id)s.%(ext)s"
        if progress_fn:
            ydl_opts["progress_hooks"] = [progress_fn]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            mp4_path = os.path.splitext(filename)[0] + ".mp4"
            final_file = mp4_path if os.path.exists(mp4_path) else filename
            return final_file, info
    except Exception as e:
        logger.warning(f"Primary download with cookies failed: {e}. Trying fallback without cookies...")
        
        ydl_opts_fallback = get_base_ydl_opts(quality=quality, use_cookies=False)
        ydl_opts_fallback["logger"] = MyLogger()
        ydl_opts_fallback["outtmpl"] = "downloads/%(id)s.%(ext)s"
        if progress_fn:
            ydl_opts_fallback["progress_hooks"] = [progress_fn]

        with yt_dlp.YoutubeDL(ydl_opts_fallback) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            mp4_path = os.path.splitext(filename)[0] + ".mp4"
            final_file = mp4_path if os.path.exists(mp4_path) else filename
            return final_file, info
