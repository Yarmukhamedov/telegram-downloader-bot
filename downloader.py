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
    elif "threads.net" in url or "threads.com" in url:
        return "Threads", "🧵", url
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
    elif quality == '1080p':
        format_spec = (
            "bestvideo[height<=1080]+bestaudio"
            "/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
            "/best[height<=1080][ext=mp4]"
            "/best[height<=1080]"
            "/best"
        )
    elif quality in ['2k', '1440p']:
        format_spec = (
            "bestvideo[height<=1440]+bestaudio"
            "/bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]"
            "/best[height<=1440][ext=mp4]"
            "/best[height<=1440]"
            "/best"
        )
    elif quality == 'mp3':
        format_spec = "bestaudio[ext=m4a]/bestaudio/best"
    else:
        # Best quality — prioritize highest resolution (4K/8K/VP9/AV1/H264)
        format_spec = (
            "bestvideo+bestaudio"
            "/bestvideo[ext=mp4]+bestaudio[ext=m4a]"
            "/best[ext=mp4]"
            "/best"
        )

    # IMPORTANT: Only 'web' and 'mweb' clients support cookies.
    # 'android' and 'ios' silently SKIP cookies — never include them in cookie-based calls.
    if not player_clients:
        player_clients = ["web", "mweb"]

    ydl_opts = {
        "format": format_spec,
        "format_sort": ["res", "codec:h264:aac", "ext:mp4:m4a"],
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
    vq = "1440" if quality in ["2k", "1440p"] else ("1080" if quality in ["best", "1080p"] else ("720" if quality == "720p" else "480"))
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

def clean_title(title: str) -> str:
    """Decodes raw JSON unicode escapes (e.g. \\ud83e\\udd23), HTML entities, and surrogate pairs into clean emojis"""
    if not title:
        return ""
    import html as html_lib

    # 1. Unescape HTML entities (&amp;, &quot;, etc.)
    title = html_lib.unescape(title)

    # 2. Decode \\uXXXX unicode escapes into actual characters
    def replace_u(match):
        hex_code = match.group(1)
        try:
            return chr(int(hex_code, 16))
        except ValueError:
            return match.group(0)

    decoded = re.sub(r"\\u([0-9a-fa-f]{4})", replace_u, title)

    # 3. Combine UTF-16 surrogate pairs into real Unicode Emojis
    try:
        title = decoded.encode("utf-16", "surrogatepass").decode("utf-16")
    except Exception:
        title = decoded

    # 4. Clean up escaped newlines and extra quotes
    title = title.replace(r"\n", " ").replace(r"\"", '"').strip()
    return title

def download_threads_media(url: str, quality: str = 'best', progress_fn=None) -> tuple[str, dict]:
    """Custom high-speed media downloader for Threads.net / Threads.com posts (supports 18+ & restricted content via cookies and quality selection)"""
    logger.info(f"🧵 Attempting custom Threads downloader for: {url} (Quality: {quality})")
    import urllib.request
    import http.cookiejar

    # Load cookies first for authenticated share redirects & restricted 18+ content
    opener = None
    if os.path.exists(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 0:
        try:
            cj = http.cookiejar.MozillaCookieJar(COOKIES_PATH)
            cj.load(ignore_discard=True, ignore_expires=True)
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        except Exception as cookie_err:
            logger.warning(f"Could not load cookies.txt for Threads: {cookie_err}")

    # 1. Resolve redirect if share URL or threads.com
    if "/share/" in url or "threads.com" in url:
        try:
            req_init = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            if opener:
                with opener.open(req_init) as resp:
                    url = resp.geturl()
            else:
                with urllib.request.urlopen(req_init) as resp:
                    url = resp.geturl()
        except Exception as e:
            logger.warning(f"Threads redirect resolve warning: {e}")
            
    url = url.replace("threads.com", "threads.net")

    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Sec-Fetch-Site': 'same-origin'
    }

    req = urllib.request.Request(url, headers=headers)
    if opener:
        resp = opener.open(req)
    else:
        resp = urllib.request.urlopen(req)
        
    html = resp.read().decode('utf-8', errors='ignore')

    def clean(s):
        return s.replace(chr(92) + '/', '/').replace(chr(92) + 'u0026', '&')

    v_urls = []
    matches = re.findall(r'\"video_versions\":\[(.*?)\]', html)
    if matches:
        for m in matches:
            urls = re.findall(r'\"url\":\"([^\"]+)\"', m)
            for u in urls:
                cu = clean(u)
                if cu not in v_urls:
                    v_urls.append(cu)

    v_url = None
    if v_urls:
        if quality in ['720p'] and len(v_urls) > 1:
            v_url = v_urls[1]
        elif quality in ['480p'] and len(v_urls) > 2:
            v_url = v_urls[-1]
        else:
            v_url = v_urls[0]

    if not v_url:
        mp4s = re.findall(r'\"(https://[^\"]+?\.mp4[^\"]*?)\"', html)
        if mp4s:
            v_url = clean(mp4s[0])

    is_video = False
    if v_url:
        is_video = True
        media_url = v_url
    else:
        img_matches = re.findall(r'\"image_versions2\":\{\"candidates\":\[\{\"height\":\d+,\"url\":\"([^\"]+)\"', html)
        if not img_matches:
            img_matches = re.findall(r'\"display_resources\":\[\{\"src\":\"([^\"]+)\"', html)
        if img_matches:
            media_url = clean(img_matches[0])
        else:
            raise Exception("Threads video or photo URL not found in post HTML")

    import html as html_lib

    title = ""
    GENERIC_FALLBACKS = ["join threads", "log in", "home", "threads • log in", "log in with your instagram", "see photos and videos"]

    # 1. Try extracting caption from JSON payload
    captions = re.findall(r'\"caption\":\{\"text\":\"([^\"]+)\"', html)
    if not captions:
        captions = re.findall(r'\"text\":\"([^\"]+)\"', html)

    for c in captions:
        t = clean_title(c)
        if t and not any(bad in t.lower() for bad in GENERIC_FALLBACKS):
            title = t
            break

    # 2. If no valid caption in JSON, try OpenGraph description
    if not title:
        og_desc = re.findall(r'<meta[^>]+property=[\"\']og:description[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']', html, re.IGNORECASE)
        if not og_desc:
            og_desc = re.findall(r'<meta[^>]+name=[\"\']twitter:description[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']', html, re.IGNORECASE)
        
        if og_desc:
            t = clean_title(og_desc[0])
            if t and not any(bad in t.lower() for bad in GENERIC_FALLBACKS):
                title = t

    # 3. Fallback to post author username if caption is missing/generic
    if not title:
        user_match = re.search(r'/@([A-Za-z0-9_.-]+)', url)
        if user_match:
            title = f"Threads Post by @{user_match.group(1)}"
        else:
            title = "Threads Post"

    os.makedirs("downloads", exist_ok=True)
    ext = ".mp4" if is_video else ".jpg"
    out_file = f"downloads/threads_{abs(hash(url))}{ext}"
    
    if progress_fn:
        try:
            progress_fn({'status': 'downloading', '_percent_str': ' 50.0%', '_speed_str': 'Fast', '_eta_str': '00:01'})
        except Exception:
            pass

    v_req = urllib.request.Request(media_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(v_req) as v_resp:
        data = v_resp.read()
        with open(out_file, 'wb') as f:
            f.write(data)

    if progress_fn:
        try:
            progress_fn({'status': 'finished'})
        except Exception:
            pass

    width, height, duration = 1080, 1080, 30
    if is_video:
        # Scale to requested quality if 720p or 480p requested
        if quality in ['720p', '480p']:
            target_h = 720 if quality == '720p' else 480
            w, h, d = get_video_metadata(out_file)
            if h and h > target_h:
                scaled_file = f"downloads/threads_{abs(hash(url))}_{quality}.mp4"
                ffmpeg = get_ffmpeg_path()
                cmd = [
                    ffmpeg, "-y", "-i", out_file,
                    "-vf", f"scale=-2:{target_h}",
                    "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                    "-c:a", "copy", scaled_file
                ]
                try:
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                    if os.path.exists(scaled_file):
                        os.remove(out_file)
                        out_file = scaled_file
                        logger.info(f"⚡️ Threads video scaled to exact {quality} ({target_h}p)")
                except Exception as scale_err:
                    logger.warning(f"Threads quality scaling warning: {scale_err}")

        w, h, d = get_video_metadata(out_file)
        if w: width = w
        if h: height = h
        if d: duration = d

    logger.info(f"🚀 ✅ Threads media ({'Video ' + quality if is_video else 'Photo'}) downloaded successfully to {out_file}")
    return out_file, {"title": title, "width": width, "height": height, "duration": duration, "is_photo": not is_video}

def download_instagram_media(url: str, quality: str = 'best', progress_fn=None) -> tuple[str, dict]:
    """Custom high-speed media downloader for Instagram posts, reels, and photos"""
    logger.info(f"📸 Attempting custom Instagram downloader for: {url}")
    import urllib.request
    import urllib.parse
    import http.cookiejar

    shortcode_match = re.search(r'/(?:p|reel|reels)/([A-Za-z0-9_-]+)', url)
    if not shortcode_match:
        raise Exception("Invalid Instagram post URL")
    shortcode = shortcode_match.group(1)

    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'X-IG-App-ID': '936619743392459',
        'Accept': '*/*',
        'Sec-Fetch-Site': 'same-origin'
    }

    opener = None
    if os.path.exists(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 0:
        try:
            cj = http.cookiejar.MozillaCookieJar(COOKIES_PATH)
            cj.load(ignore_discard=True, ignore_expires=True)
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        except Exception as e:
            logger.warning(f"Cookies load warning for Instagram: {e}")

    # Query Instagram GraphQL doc_ids
    doc_ids = ['10015901848480474', '17991233853477142', '8833687760075322']
    var = json.dumps({'shortcode': shortcode})

    media_data = None
    for did in doc_ids:
        gql_url = f"https://www.instagram.com/graphql/query/?doc_id={did}&variables={urllib.parse.quote(var)}"
        req = urllib.request.Request(gql_url, headers=headers)
        try:
            if opener:
                resp = opener.open(req)
            else:
                resp = urllib.request.urlopen(req)
            data = json.loads(resp.read().decode('utf-8', errors='ignore'))
            xdt = data.get('data', {}).get('xdt_shortcode_media') or data.get('data', {}).get('shortcode_media')
            if xdt:
                media_data = xdt
                break
        except Exception as err:
            logger.warning(f"Instagram GQL doc_id {did} warning: {err}")

    if media_data:
        is_video = media_data.get('is_video', False)
        media_url = media_data.get('video_url') if is_video else media_data.get('display_url')
        caption = "Instagram Post"
        try:
            caption = media_data.get('edge_media_to_caption', {}).get('edges', [{}])[0].get('node', {}).get('text') or caption
        except Exception:
            pass

        if media_url:
            os.makedirs("downloads", exist_ok=True)
            ext = ".mp4" if is_video else ".jpg"
            out_file = f"downloads/ig_{abs(hash(url))}{ext}"
            
            v_req = urllib.request.Request(media_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(v_req) as v_resp:
                img_bytes = v_resp.read()
                with open(out_file, "wb") as f:
                    f.write(img_bytes)
            logger.info(f"🚀 ✅ Instagram custom downloader successfully saved to {out_file}")
            return out_file, {"title": caption[:100], "is_photo": not is_video}

    raise Exception("Instagram custom downloader found no media URL")

def download_media(url: str, quality: str, progress_fn=None) -> tuple[str, dict]:
    url = url.replace("threads.com", "threads.net")

    if "threads.net" in url:
        try:
            return download_threads_media(url, quality=quality, progress_fn=progress_fn)
        except Exception as err:
            logger.warning(f"Custom Threads downloader failed: {err}")
            raise Exception(f"Threads post media unavailable or link expired ({err})")

    if "instagram.com" in url:
        try:
            return download_instagram_media(url, quality=quality, progress_fn=progress_fn)
        except Exception as err:
            logger.warning(f"Custom Instagram downloader failed ({err}). Falling back to yt-dlp...")

    is_youtube = "youtube.com" in url or "youtu.be" in url
    is_instagram = "instagram.com" in url

    # Download strategy requested by user for Beta:
    # Stage 1: web+cookies (official). If resolution < 1080p on 'best', try Stage 2.
    # Stage 2: PO Token & Advanced clients (web_creator, tv_embedded) for Full HD/4K.
    # Stage 3: Fallback back to web+cookies if Stage 2 fails.
    # Stage 4: no-cookies fallback for Instagram (if cookies file is stale/missing CSRF token).
    stages = [
        {"clients": ["web", "mweb"], "use_cookies": True, "label": "Stage 1 [web+cookies (official)]", "check_hd": True},
        {"clients": ["web_creator", "tv_embedded", "web_safari", "web", "mweb"], "use_cookies": True, "label": "Stage 2 [PO Token & Advanced Clients (Full HD/4K)]", "check_hd": False},
        {"clients": ["web", "mweb"], "use_cookies": True, "label": "Stage 3 [web+cookies fallback]", "check_hd": False}
    ]

    if is_instagram:
        stages.append({"clients": ["web", "mweb"], "use_cookies": False, "label": "Stage 4 [no-cookies Instagram fallback]", "check_hd": False})

    last_exception = None
    for idx, stage in enumerate(stages, start=1):
        try:
            logger.info(f"⏳ Attempting {stage['label']}...")
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
                if stage["check_hd"] and is_youtube and quality == 'best':
                    try:
                        info_preview = ydl.extract_info(url, download=False)
                        height = info_preview.get("height", 0) or 0
                        if not height and "requested_formats" in info_preview:
                            for rf in info_preview["requested_formats"]:
                                if rf.get("vcodec") != "none" and rf.get("height"):
                                    height = rf.get("height")
                                    break
                        if not height and "formats" in info_preview:
                            for f in reversed(info_preview["formats"]):
                                if f.get("vcodec") != "none" and f.get("height"):
                                    height = f.get("height")
                                    break
                        if 0 < height < 1080:
                            has_higher = any((f.get("height", 0) or 0) >= 1080 for f in info_preview.get("formats", []))
                            if has_higher:
                                logger.warning(f"⚠️ Stage 1 max resolution is only {height}p (< 1080p). Escalating to Stage 2 for Full HD/4K...")
                                continue
                            else:
                                logger.info(f"ℹ️ Stage 1 resolution is {height}p (no 1080p+ formats available for this video). Proceeding with Stage 1 download...")
                    except Exception as prev_err:
                        logger.warning(f"Preview check failed: {prev_err}. Proceeding with Stage 1 download...")

                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                mp4_path = os.path.splitext(filename)[0] + ".mp4"
                final_file = mp4_path if os.path.exists(mp4_path) else filename
                dl_height = info.get("height") or 0
                if not dl_height and "requested_formats" in info:
                    for rf in info["requested_formats"]:
                        if rf.get("vcodec") != "none" and rf.get("height"):
                            dl_height = rf.get("height")
                            break
                logger.info(f"✅ Download SUCCESS at {stage['label']}: {final_file} (Resolution: {dl_height}p)")
                return final_file, info
        except Exception as e:
            logger.warning(f"{stage['label']} failed: {e}")
            last_exception = e

    # Stage 5: Instagram Photo & Post Fallback Extractor
    if is_instagram:
        logger.info("📸 Attempting Instagram photo/post fallback extraction...")
        try:
            photo_opts = {
                "extract_flat": True,
                "no_check_certificates": True,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                }
            }
            if os.path.exists(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 0:
                photo_opts["cookiefile"] = COOKIES_PATH

            info_p = None
            with yt_dlp.YoutubeDL(photo_opts) as ydl_photo:
                try:
                    info_p = ydl_photo.extract_info(url, download=False)
                except Exception as ex_err:
                    info_p = getattr(ex_err, "info_dict", None)

                if info_p:
                    img_url = info_p.get("thumbnail") or info_p.get("url")
                    if not img_url and info_p.get("thumbnails"):
                        img_url = info_p["thumbnails"][-1].get("url")
                    if img_url:
                        os.makedirs("downloads", exist_ok=True)
                        out_photo = f"downloads/ig_{abs(hash(url))}.jpg"
                        r_img = requests.get(img_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                        if r_img.status_code == 200:
                            with open(out_photo, "wb") as f:
                                f.write(r_img.content)
                            title = info_p.get("title") or "Instagram Photo"
                            logger.info(f"✅ Instagram photo downloaded successfully: {out_photo}")
                            return out_photo, {"title": title, "is_photo": True}
        except Exception as photo_err:
            logger.warning(f"Instagram photo fallback error: {photo_err}")

    # Stage 6: Cobalt API fallback for YouTube
    if is_youtube:
        try:
            return download_via_cobalt_fallback(url, quality)
        except Exception as cob_err:
            logger.error(f"Cobalt fallback failed: {cob_err}")

    if last_exception:
        raise last_exception
    else:
        raise Exception("Media download failed: Unable to extract media from provided link")

