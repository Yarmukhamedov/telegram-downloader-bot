import os
import re
import sys
import json
import time
import shutil
import asyncio
import logging
import subprocess
import aiohttp
import yt_dlp
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineQueryResultArticle, InputTextMessageContent
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from database import (
    init_db, get_or_create_user, update_user_quality, record_download,
    check_daily_limit, get_setting, get_admin_stats, register_user_with_referral,
    get_user_referrals, grant_premium
)
from downloader import (
    detect_platform_and_url, download_media, get_video_metadata,
    ensure_h264_codec, convert_to_mp3, create_video_thumbnail,
    compress_video_to_target_size
)
from keyboards import (
    get_main_keyboard, get_settings_keyboard, get_force_sub_keyboard,
    get_quality_selector_keyboard, get_profile_keyboard, get_payment_receipt_keyboard
)
from admin import admin_router, get_admin_ids

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN is not set!")
    sys.exit(1)

dp = Dispatcher()
dp.include_router(admin_router)
url_cache = {}
download_semaphore = asyncio.Semaphore(4)

async def check_channel_subscription(user_id: int, bot_inst: Bot) -> tuple[bool, str, str]:
    admin_ids = get_admin_ids()
    if user_id in admin_ids:
        return True, "", ""

    ch_id = await get_setting("force_channel_id", os.getenv("REQUIRED_CHANNEL_ID", ""))
    ch_link = await get_setting("force_channel_link", os.getenv("REQUIRED_CHANNEL_LINK", "https://t.me"))

    if not ch_id or ch_id == "off":
        return True, "", ""

    try:
        member = await bot_inst.get_chat_member(chat_id=ch_id, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            return True, ch_id, ch_link
    except Exception as e:
        logger.warning(f"Failed to check channel subscription for user {user_id}: {e}")
        return True, "", ""

    return False, ch_id, ch_link

@dp.message(Command("start"))
async def cmd_start(message: types.Message, bot: Bot):
    logger.info(f">>> /start command received from user_id: {message.from_user.id} ({message.from_user.full_name})")
    args = message.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1].replace("ref_", ""))
        except ValueError:
            pass

    user, is_new, referrer_got_bonus = await register_user_with_referral(message.from_user.id, message.from_user.username, message.from_user.full_name, ref_id)
    
    if referrer_got_bonus > 0:
        try:
            await bot.send_message(
                referrer_got_bonus,
                "🎉 **Tabriklaymiz!**\n\n"
                "Sizning referal havolangiz orqali **3 nafar** do'stingiz botga qo'shildi!\n"
                "🎁 Sizga avtomatik ravishda **7 kunlik ⭐ VIP Premium** obuna taqdim etildi!\n\n"
                "Cheksiz, navbatsiz va super sifatli yuklashdan rohatlaning! 🚀",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not notify referrer {referrer_got_bonus}: {e}")
    elif is_new and ref_id and ref_id != message.from_user.id:
        try:
            ref_count = await get_user_referrals(ref_id)
            await bot.send_message(
                ref_id,
                f"👤 Sizning havolangiz orqali yangi do'stingiz ({message.from_user.first_name}) botga qo'shildi!\n"
                f"📊 **Jami taklif qilinganlar:** {ref_count} ta.\n"
                f"🎁 Yana {3 - (ref_count % 3)} kishi qo'shilsa, 7 kunlik VIP Premium olasiz!",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not notify referrer {ref_id}: {e}")

    admin_ids = get_admin_ids()
    is_admin = message.from_user.id in admin_ids

    welcome_text = (
        f"👋 **Xush kelibsiz, {message.from_user.first_name}!**\n\n"
        f"Men YouTube, TikTok, Instagram, Pinterest va Twitter/X platformalaridan "
        f"videolarni 100% original hajmda hamda yuqori sifatda yuklab beruvchi botman! 🚀\n\n"
        f"⚡️ Shunchaki video havolasini menga yuboring!\n"
        f"🎁 Bepul VIP olish yoki Tariflar bilan tanishish uchun **👤 Profil / Tarif** bo'limiga o'ting."
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(is_admin), parse_mode="Markdown")

@dp.message(Command("settings"))
@dp.message(F.text == "⚙️ Sozlamalar")
async def cmd_settings(message: types.Message):
    logger.info(f">>> Sozlamalar clicked by user_id: {message.from_user.id}")
    user = await get_or_create_user(message.from_user.id)
    quality = user['preferred_quality']
    
    text = (
        "⚙️ **Yuklash Sozlamalari**\n\n"
        "Videolar qaysi sifatda yuklab olinishini tanlang.\n"
        "Tanlangan sifat barcha kelgusi yuklashlaringizga avtomatik qo'llaniladi:"
    )
    await message.answer(text, reply_markup=get_settings_keyboard(quality), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("set_quality:"))
async def cb_set_quality(callback: types.CallbackQuery):
    quality = callback.data.split(":")[1]
    await update_user_quality(callback.from_user.id, quality)
    
    q_labels = {
        'best': "🎬 Eng yuqori (1080p / 4K)",
        '720p': "📺 O'rtacha HD (720p)",
        '480p': "📱 Tejamkor (480p)",
        'mp3': "🎵 Faqat MP3 Audio",
        'ask': "❓ Har safar so'rash"
    }

    selected_label = q_labels.get(quality, quality)
    await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(quality))
    await callback.answer(f"✅ Sozlama saqlandi: {selected_label}", show_alert=True)

@dp.message(F.text == "👤 Profil / Tarif")
async def cmd_profile(message: types.Message):
    logger.info(f">>> Profil clicked by user_id: {message.from_user.id}")
    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    ref_count = await get_user_referrals(message.from_user.id)
    
    status_str = f"⭐ VIP Premium (gacha: {user['premium_until'][:10]})" if (user['is_premium'] and user['premium_until']) else ("⭐ VIP Premium (Cheksiz)" if user['is_premium'] else "🆓 Bepul (Free)")
    daily_limit = "Cheksiz (Priority Navbat)" if user['is_premium'] else "15 ta / kun"
    
    q_map = {
        'best': "🎬 Eng yuqori (1080p / 4K)",
        '720p': "📺 O'rtacha HD (720p)",
        '480p': "📱 Tejamkor (480p)",
        'mp3': "🎵 Faqat MP3 Audio",
        'ask': "❓ Har safar so'rash"
    }
    pref_q = q_map.get(user['preferred_quality'], "🎬 Eng yuqori")

    text = (
        "👤 **Sizning Profilingiz va Tarif**\n\n"
        f"🆔 **ID:** `{user['user_id']}`\n"
        f"👤 **Ism:** {user['full_name']}\n"
        f"👑 **Tarifingiz:** {status_str}\n"
        f"📥 **Bugungi yuklashlar:** {user['daily_downloads']} / {daily_limit}\n"
        f"⚙️ **Tanlangan sifat:** {pref_q}\n"
        f"👥 **Taklif qilgan do'stlaringiz:** {ref_count} ta\n\n"
        "💎 *VIP Premium imtiyozlari:* Cheksiz yuklash, 1080p/4K sifat, navbatsiz super-tezkor yuklash va hech qanday reklamasiz!"
    )
    await message.answer(text, reply_markup=get_profile_keyboard(), parse_mode="Markdown")

@dp.message(F.text == "ℹ️ Yordam")
async def cmd_help(message: types.Message):
    logger.info(f">>> Help clicked by user_id: {message.from_user.id}")
    text = (
        "ℹ️ **Botdan foydalanish yordami**\n\n"
        "1. **Qo'llab-quvvatlanadigan platformalar:**\n"
        "   • 🎬 YouTube (Videolar va Shorts)\n"
        "   • 🎵 TikTok (Suv belgisiz - No Watermark)\n"
        "   • 📸 Instagram (Reels va Videolar)\n"
        "   • 📌 Pinterest (Videolar va GIF)\n"
        "   • 🐦 Twitter / X (Videolar)\n\n"
        "2. **Qanday yuklanadi?**\n"
        "   Shunchaki istalgan video havolasini botga yuboring!\n\n"
        "3. **Sifatni o'zgartirish:**\n"
        "   **⚙️ Sozlamalar** tugmasi orqali MP3 audio yoki boshqa sifatlarni tanlashingiz mumkin."
    )
    await message.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data == "check_subscription")
async def cb_check_sub(callback: types.CallbackQuery, bot: Bot):
    is_sub, ch_id, ch_link = await check_channel_subscription(callback.from_user.id, bot)
    if is_sub:
        await callback.message.edit_text("✅ Rahmat! Obuna tasdiqlandi. Endi botdan to'liq foydalanishingiz mumkin! 🚀")
        await callback.answer()
    else:
        await callback.answer("❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)

@dp.message(F.text)
async def handle_media_download(message: types.Message, bot: Bot):
    logger.info(f">>> Text message received from user_id: {message.from_user.id}: {message.text}")
    if message.text in ["⚙️ Sozlamalar", "👤 Profil / Tarif", "ℹ️ Yordam", "🛠 Admin Panel"]:
        return

    is_sub, ch_id, ch_link = await check_channel_subscription(message.from_user.id, bot)
    if not is_sub:
        text = (
            "⚠️ **Botdan foydalanish uchun kanalimizga obuna bo'ling!**\n\n"
            "Obuna bo'lgach, **✅ Obunani tekshirish** tugmasini bosing:"
        )
        await message.answer(text, reply_markup=get_force_sub_keyboard(ch_link), parse_mode="Markdown")
        return

    platform, icon, url = detect_platform_and_url(message.text)
    if not url:
        await message.answer("ℹ️ Iltimos, menga YouTube, TikTok, Instagram, Pinterest yoki Twitter havolasini yuboring!")
        return

    can_download, current_usage = await check_daily_limit(message.from_user.id, free_limit=15)
    if not can_download:
        await message.answer(
            "⚠️ **Kunlik tekin yuklab olish limitiga yetdingiz! (15/15)**\n\n"
            "Cheksiz yuklab olish uchun **Premium** tarifiga o'ting yoki ertagacha kuting. 😊",
            parse_mode="Markdown"
        )
        return

    user = await get_or_create_user(message.from_user.id)
    pref_quality = user['preferred_quality']

    if pref_quality == 'ask':
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
        url_cache[url_hash] = url
        
        await message.answer(
            f"{icon} **{platform} havolasi qabul qilindi!**\nSifat yoki formatni tanlang:",
            reply_markup=get_quality_selector_keyboard(url),
            parse_mode="Markdown"
        )
        return

    await process_and_send_media(message, url, platform, icon, pref_quality, bot)

@dp.callback_query(F.data.startswith("download_q:"))
async def cb_download_quality(callback: types.CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    url_hash = parts[1]
    quality = parts[2]

    url = url_cache.get(url_hash)
    if not url:
        await callback.answer("❌ Havola muddati o'tdi. Iltimos, havolani qayta yuboring.", show_alert=True)
        return

    platform, icon, _ = detect_platform_and_url(url)
    await callback.message.delete()
    await process_and_send_media(callback.message, url, platform or "Media", icon or "📹", quality, bot)
    await callback.answer()

async def process_and_send_media(message: types.Message, url: str, platform: str, icon: str, quality: str, bot_inst: Bot):
    user = await get_or_create_user(message.from_user.id)
    is_vip = user['is_premium']

    status_msg = await message.answer(f"{icon} **{platform}** havolasi ishlanmoqda...")
    loop = asyncio.get_event_loop()
    
    last_update_time = [loop.time()]

    def progress_hook(d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%')
            speed = d.get('_speed_str', 'N/A')
            eta = d.get('_eta_str', 'N/A')
            
            current_time = loop.time()
            if current_time - last_update_time[0] > 3:
                last_update_time[0] = current_time
                try:
                    text = f"⏳ **{platform}** yuklanmoqda: {p}\n🚀 Tezlik: {speed}\n⏱ Qolgan vaqt: {eta}"
                    asyncio.run_coroutine_threadsafe(status_msg.edit_text(text, parse_mode="Markdown"), loop)
                except Exception:
                    pass

    if not is_vip and download_semaphore.locked():
        await status_msg.edit_text("⏳ **Serverda yuklash navbati:** Siz navbatda turibsiz. Video tez orada yuklanishni boshlaydi...\n\n💎 *VIP Premium obunachilar navbatsiz tezkor yuklaydi!*", parse_mode="Markdown")

    async with download_semaphore:
        try:
            os.makedirs("downloads", exist_ok=True)
            await status_msg.edit_text(f"⏳ **{platform}** dan yuklab olinmoqda...")
            
            file_path, video_info = await loop.run_in_executor(None, download_media, url, quality, progress_hook)
            title = video_info.get("title", f"{platform} Video")

            bot_info = await bot_inst.get_me()

            if quality == 'mp3' or file_path.endswith(".mp3"):
                await status_msg.edit_text("🎵 MP3 audio fayl tayyorlanmoqda...")
                mp3_file = await loop.run_in_executor(None, convert_to_mp3, file_path)
                
                audio = FSInputFile(mp3_file)
                await message.answer_audio(
                    audio,
                    caption=f"🎵 {title}\n\n🤖 @{bot_info.username}",
                    title=title
                )
                await record_download(message.from_user.id, url, platform, "MP3")
                if os.path.exists(mp3_file):
                    os.remove(mp3_file)

            else:
                file_path = await loop.run_in_executor(None, ensure_h264_codec, file_path)
                
                is_local_api = getattr(bot_inst, "_is_local_api", False) or (hasattr(bot_inst.session, "api") and bot_inst.session.api.is_local)
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                
                if not is_local_api and file_size_mb > 49.0:
                    await status_msg.edit_text("⚡️ Video 50 MB dan katta. Telegram uchun sifatli siqilmoqda...")
                    file_path = await loop.run_in_executor(None, compress_video_to_target_size, file_path, 48.0)

                await status_msg.edit_text("✅ Tayyor! Telegram'ga yuborilmoqda...")
                
                width, height, duration = await loop.run_in_executor(None, get_video_metadata, file_path)
                if not width or not height:
                    width = video_info.get("width")
                    height = video_info.get("height")
                if not duration:
                    duration = video_info.get("duration")

                thumb_file_path = os.path.splitext(file_path)[0] + "_thumb.jpg"
                thumb_result = await loop.run_in_executor(None, create_video_thumbnail, file_path, thumb_file_path)

                video = FSInputFile(file_path)
                thumbnail = FSInputFile(thumb_result) if thumb_result else None

                await message.answer_video(
                    video,
                    caption=f"{icon} **{title}**\n\n🤖 @{bot_info.username}",
                    width=width,
                    height=height,
                    duration=int(duration) if duration else None,
                    thumbnail=thumbnail,
                    supports_streaming=True,
                    parse_mode="Markdown"
                )
                await record_download(message.from_user.id, url, platform, quality)
                
                if os.path.exists(file_path):
                    os.remove(file_path)
                if thumb_result and os.path.exists(thumb_result):
                    os.remove(thumb_result)

            await status_msg.delete()

        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            await status_msg.edit_text(f"❌ Yuklab olishda xatolik yuz berdi: {str(e)}")

@dp.callback_query(F.data == "ref_info")
async def cb_ref_info(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    ref_count = await get_user_referrals(user_id)
    
    text = (
        "🎁 **Bepul VIP Premium olish tizimi (Referal)**\n\n"
        "Quyidagi shaxsiy taklif havolangizni do'stlaringizga, guruhlarga yoki kanallarga yuboring!\n\n"
        f"🔗 **Sizning havolangiz:**\n`{ref_link}`\n\n"
        f"👥 **Hozircha taklif qilganlaringiz:** {ref_count} ta\n\n"
        "🎯 **Shart:** Har **3 nafar yangi do'stingiz** ushbu havola orqali botga kirganda, sizga avtomatik ravishda **7 kunlik ⭐ VIP Premium** taqdim etiladi (hech qanday limitsiz!)."
    )
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "buy_prem_stars")
async def cb_buy_stars(callback: types.CallbackQuery):
    prices = [types.LabeledPrice(label="⭐ 30 kun VIP Premium", amount=50)]
    await callback.message.answer_invoice(
        title="⭐ VIP Premium (30 kun)",
        description="Cheksiz yuklash, 1080p/4K sifat, navbatsiz super-tezkor yuklash va hech qanday reklamasiz!",
        payload="prem_30_days",
        provider_token="",
        currency="XTR",
        prices=prices
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: types.PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    user_id = message.from_user.id
    await grant_premium(user_id, 30)
    await message.answer(
        "🎉 **Tabriklaymiz! To'lov muvaffaqiyatli qabul qilindi.**\n\n"
        "Sizga **30 kunlik ⭐ VIP Premium** obuna taqdim etildi!\n"
        "Endi cheksiz, navbatsiz va super sifatli yuklashdan rohatlaning. 🚀",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "buy_prem_card")
async def cb_buy_card(callback: types.CallbackQuery):
    text = (
        "💳 **Karta orqali to'lov (Click / Payme / Uzcard / Humo)**\n\n"
        "⭐ 1 oy VIP Premium narxi: **15,000 so'm**\n"
        "💳 Karta raqam: `8600 0000 0000 0000` *(Palonchiyev P.)*\n\n"
        "📝 **To'lovni tasdiqlash uchun:** To'lovni amalga oshirgach, to'lov cheki rasmini (skrinshotini) darhol shu yerga yuboring! "
        "Adminlarimiz chekni tekshirib, bir necha daqiqada sizga VIP tarifni yoqib berishadi."
    )
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.message(F.photo)
async def handle_photo_receipt(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    admin_ids = get_admin_ids()
    
    if not admin_ids:
        await message.answer("⚠️ Hozircha adminlar tayinlanmagan.")
        return

    await message.answer("✅ To'lov chekingiz adminlarga yuborildi! Tekshirib tez orada VIP tarifni aktivlashtiramiz. Rahmat! 😊")

    caption = (
        "💳 **Yangi to'lov cheki (Karta / Click)**\n\n"
        f"👤 **Foydalanuvchi:** {username} (`{user_id}`)\n"
        f"🆔 **ID:** `{user_id}`\n\n"
        "To'lovni tasdiqlab, 30 kunlik VIP berishni xohlaysizmi?"
    )
    for admin_id in admin_ids:
        try:
            await bot.send_photo(
                chat_id=admin_id,
                photo=message.photo[-1].file_id,
                caption=caption,
                reply_markup=get_payment_receipt_keyboard(user_id),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not forward receipt to admin {admin_id}: {e}")

@dp.callback_query(F.data.startswith("verify_prem:"))
async def cb_verify_prem(callback: types.CallbackQuery, bot: Bot):
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Bu tugma faqat adminlar uchun!", show_alert=True)
        return
        
    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    days = int(parts[2]) if len(parts) > 2 else 30
    
    await grant_premium(target_user_id, days)
    await callback.message.edit_caption(
        caption=f"✅ **Tasdiqlandi!** `{target_user_id}` foydalanuvchiga {days} kunlik VIP Premium berildi.",
        parse_mode="Markdown"
    )
    await callback.answer("✅ VIP Premium berildi!")
    
    try:
        await bot.send_message(
            target_user_id,
            f"🎉 **Tabriklaymiz! To'lov chekingiz admin tomonidan tasdiqlandi!**\n\n"
            f"Sizga **{days} kunlik ⭐ VIP Premium** obuna yoqildi!\n"
            "Endi cheksiz va super sifatli yuklashdan rohatlaning. 🚀",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Could not notify user {target_user_id} of premium verification: {e}")

@dp.callback_query(F.data.startswith("reject_prem:"))
async def cb_reject_prem(callback: types.CallbackQuery, bot: Bot):
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Bu tugma faqat adminlar uchun!", show_alert=True)
        return
        
    target_user_id = int(callback.data.split(":")[1])
    await callback.message.edit_caption(
        caption=f"❌ **Rad etildi!** `{target_user_id}` foydalanuvchi cheki qabul qilinmadi.",
        parse_mode="Markdown"
    )
    await callback.answer("❌ Rad etildi!")
    
    try:
        await bot.send_message(
            target_user_id,
            "❌ **To'lov chekingiz tasdiqlanmadi.**\n\n"
            "Iltimos, to'g'ri chek yuborganingizga ishonch hosil qiling yoki savollar bo'yicha adminga murojaat qiling.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Could not notify user {target_user_id} of rejection: {e}")

@dp.inline_query()
async def inline_search_handler(inline_query: types.InlineQuery):
    query = inline_query.query.strip()
    if not query:
        return

    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "noplaylist": True,
        "max_downloads": 5
    }

    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = search_info.get("entries", [])
            
            for idx, entry in enumerate(entries):
                v_title = entry.get("title", "YouTube Video")
                v_url = entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}"
                v_duration = entry.get("duration")
                
                dur_str = f" ({int(v_duration)} sec)" if v_duration else ""
                
                results.append(
                    InlineQueryResultArticle(
                        id=str(idx),
                        title=f"🎬 {v_title}",
                        description=f"YouTube Video{dur_str}\n{v_url}",
                        input_message_content=InputTextMessageContent(
                            message_text=v_url
                        )
                    )
                )
        await inline_query.answer(results, cache_time=300)
    except Exception as e:
        logger.error(f"Inline search error: {e}")

async def create_bot_instance() -> Bot:
    bot_api_url = os.getenv("BOT_API_SERVER", "http://telegram-bot-api:8081")
    
    logger.info(f"⏳ Connecting to Local Telegram Bot API Server (2GB Mode) at: {bot_api_url}...")
    
    chosen_api_url = None
    for attempt in range(1, 16):
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{bot_api_url.rstrip('/')}/bot{BOT_TOKEN}/getMe"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    chosen_api_url = bot_api_url
                    break
        except Exception:
            pass
        await asyncio.sleep(1)

    if chosen_api_url:
        logger.info(f"🚀 ✅ SUCCESS: Connected to Local Telegram Bot API Server at: {chosen_api_url} (2GB Mode Active!)")
        api = TelegramAPIServer.from_base(chosen_api_url, is_local=True)
        session = AiohttpSession(api=api)
        bot_inst = Bot(token=BOT_TOKEN, session=session)
        bot_inst._is_local_api = True
        return bot_inst
    else:
        logger.info("🌐 Using Standard Telegram API")
        bot_inst = Bot(token=BOT_TOKEN)
        bot_inst._is_local_api = False
        return bot_inst

async def cleanup_old_downloads():
    while True:
        try:
            await asyncio.sleep(3600)  # Run every 1 hour
            if os.path.exists("downloads"):
                now = time.time()
                for fname in os.listdir("downloads"):
                    fpath = os.path.join("downloads", fname)
                    if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 3600:
                        try:
                            os.remove(fpath)
                            logger.info(f"🧹 Deleted stale temp file: {fpath}")
                        except Exception:
                            pass
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Error in cleanup task: {e}")

async def main():
    logger.info("Initializing database...")
    await init_db()
    
    bot_instance = await create_bot_instance()
    cleanup_task = asyncio.create_task(cleanup_old_downloads())
    try:
        await bot_instance.delete_webhook(drop_pending_updates=True)
        bot_info = await bot_instance.get_me()
        logger.info(f"🤖 Connected Bot Username: @{bot_info.username} (ID: {bot_info.id})")
        logger.info(f"🚀 Bot @{bot_info.username} is now online and active in 2GB Mode!")
        await dp.start_polling(bot_instance)
    except Exception as e:
        logger.error(f"❌ Error during bot polling startup: {e}")
        raise e
    finally:
        cleanup_task.cancel()

if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot manually stopped!")
            break
        except Exception as e:
            logger.error(f"Bot encountered unhandled exception: {e}. Auto-reconnecting in 5 seconds...")
            time.sleep(5)
