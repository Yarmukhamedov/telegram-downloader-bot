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
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InlineQueryResultArticle, InputTextMessageContent
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from database import (
    init_db, get_or_create_user, update_user_quality, record_download,
    check_daily_limit, get_setting, get_admin_stats, register_user_with_referral,
    get_user_referrals, grant_premium, get_user_coins, add_user_coins,
    get_user_language, set_user_language, get_referral_stats, verify_referral_activity,
    create_redeem_code, redeem_code, get_user_total_downloads
)
from downloader import (
    detect_platform_and_url, download_media, get_video_metadata,
    ensure_h264_codec, convert_to_mp3, create_video_thumbnail,
    compress_video_to_target_size
)
from keyboards import (
    get_main_keyboard, get_settings_keyboard, get_force_sub_keyboard,
    get_quality_selector_keyboard, get_profile_keyboard, get_profile_reply_keyboard,
    get_shop_reply_keyboard, get_buy_prem_stars_keyboard, get_use_coins_keyboard,
    get_payment_receipt_keyboard, get_language_keyboard, get_invite_center_keyboard, get_shop_keyboard,
    get_invite_center_reply_keyboard, get_settings_reply_keyboard
)
from locales import get_text, get_all_button_texts, get_all_registered_buttons
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
    lang = user.get('language', 'uz')

    if is_new:
        await message.answer(get_text("lang_select_prompt", lang), reply_markup=get_language_keyboard())

    admin_ids = get_admin_ids()
    is_admin = message.from_user.id in admin_ids

    bot_info = await bot.get_me()
    welcome_text = get_text("welcome", lang, name=message.from_user.first_name, bot_name=bot_info.first_name)
    await message.answer(welcome_text, reply_markup=get_main_keyboard(is_admin, lang), parse_mode="Markdown")

async def delete_menu_and_user_msg(callback: types.CallbackQuery, user_msg_id: int):
    try:
        await callback.message.delete()
    except Exception:
        pass
    if user_msg_id > 0:
        try:
            await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=user_msg_id)
        except Exception:
            pass

@dp.message(Command("lang"))
@dp.message(F.text.in_(get_all_button_texts("btn_language")))
@dp.callback_query(F.data == "change_lang_menu")
async def cmd_change_lang(event: types.Message | types.CallbackQuery):
    msg = event.message if isinstance(event, types.CallbackQuery) else event
    user_id = event.from_user.id
    lang = await get_user_language(user_id)
    user_msg_id = event.message_id if isinstance(event, types.Message) else 0
    await msg.answer(get_text("lang_select_prompt", lang), reply_markup=get_language_keyboard(user_msg_id))
    if isinstance(event, types.CallbackQuery):
        await event.answer()

@dp.callback_query(F.data.startswith("set_lang:"))
async def cb_set_lang(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    new_lang = parts[1]
    user_msg_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    await set_user_language(callback.from_user.id, new_lang)
    admin_ids = get_admin_ids()
    is_admin = callback.from_user.id in admin_ids
    
    await delete_menu_and_user_msg(callback, user_msg_id)
    await callback.message.answer(get_text("lang_changed", new_lang), reply_markup=get_main_keyboard(is_admin, new_lang), parse_mode="Markdown")
    await callback.answer()

@dp.message(Command("settings"))
@dp.message(F.text.in_(get_all_button_texts("btn_settings")))
async def cmd_settings_menu(message: types.Message):
    lang = await get_user_language(message.from_user.id)
    text = get_text("settings_title", lang)
    await message.answer(text, reply_markup=get_settings_reply_keyboard(lang), parse_mode="Markdown")

@dp.message(Command("quality"))
@dp.message(F.text.in_(get_all_button_texts("btn_quality")))
async def cmd_quality_settings(message: types.Message):
    logger.info(f">>> Sifat/Quality clicked by user_id: {message.from_user.id}")
    user = await get_or_create_user(message.from_user.id)
    is_admin = message.from_user.id in get_admin_ids()
    is_premium = user['is_premium'] or is_admin
    quality = user['preferred_quality']
    if quality == 'best' and not is_premium:
        quality = '720p'
    lang = user.get('language', 'uz')
    
    text = (
        "🎬 *Video Sifatini Tanlash*\n\nVideolar qaysi sifatda yuklab olinishini tanlang:" if lang == 'uz' else (
        "🎬 *Выбор качества видео*\n\nВыберите качество для загрузки видео:" if lang == 'ru' else
        "🎬 *Select Video Quality*\n\nSelect preferred video download quality:")
    )
    await message.answer(text, reply_markup=get_settings_keyboard(quality, lang, message.message_id, is_premium=is_premium), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("set_quality:"))
async def cb_set_quality(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    quality = parts[1]
    user_msg_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    user = await get_or_create_user(callback.from_user.id)
    is_admin = callback.from_user.id in get_admin_ids()
    is_premium = user['is_premium'] or is_admin
    if quality == 'best' and not is_premium:
        lang = await get_user_language(callback.from_user.id)
        alert_msg = (
            "🔒 1080p Full HD va 4K Ultra HD yuklab olish faqat Premium foydalanuvchilar uchun mavjud!\n\n🛍 Quyidagi menyudan Premium obunani xarid qilib, cheksiz yuklash va eng yuqori sifatni oching!" if lang == 'uz' else (
            "🔒 Загрузка в 1080p Full HD и 4K Ultra HD доступна только для Premium пользователей!\n\n🛍 Оформите Premium ниже для безлимита и максимального качества!" if lang == 'ru' else
            "🔒 1080p Full HD and 4K Ultra HD downloading is available exclusively for Premium users!\n\n🛍 Upgrade to Premium below for unlimited downloads and highest quality!")
        )
        await callback.answer(alert_msg, show_alert=True)
        await delete_menu_and_user_msg(callback, user_msg_id)
        text = get_text("buy_premium_text", lang)
        await callback.message.answer(text, reply_markup=get_buy_prem_stars_keyboard(lang, user_msg_id), parse_mode="Markdown")
        return
    await update_user_quality(callback.from_user.id, quality)
    
    await delete_menu_and_user_msg(callback, user_msg_id)

    lang = await get_user_language(callback.from_user.id)
    q_map = {'best': "1080p / 4K", '720p': "720p HD", '480p': "480p SD", 'mp3': "MP3 Audio", 'ask': "❓ Ask"}
    q_str = q_map.get(quality, quality)
    msg_text = f"✅ Video yuklash sifati sozlangan: *{q_str}*" if lang == 'uz' else (
        f"✅ Качество загрузки видео установлено на: *{q_str}*" if lang == 'ru' else
        f"✅ Video download quality set to: *{q_str}*"
    )
    await callback.message.answer(msg_text, reply_markup=get_main_keyboard(is_admin, lang), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("close_quality:"))
async def cb_close_quality(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    user_msg_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    await delete_menu_and_user_msg(callback, user_msg_id)
    is_admin = callback.from_user.id in get_admin_ids()
    lang = await get_user_language(callback.from_user.id)
    text = get_text("back_main_menu", lang)
    await callback.message.answer(text, reply_markup=get_main_keyboard(is_admin, lang), parse_mode="Markdown")
    await callback.answer()

@dp.message(F.text.in_(get_all_button_texts("btn_profile")))
async def cmd_profile(message: types.Message, state: FSMContext):
    await state.set_state("in_profile")
    logger.info(f">>> Profil clicked by user_id: {message.from_user.id}")
    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    lang = user.get('language', 'uz')
    
    is_admin = message.from_user.id in get_admin_ids()
    if is_admin:
        status_str = "⭐ Premium (Cheksiz)" if lang == 'uz' else ("⭐ Premium (Безлимит)" if lang == 'ru' else "⭐ Premium (Unlimited)")
        daily_limit = "Cheksiz" if lang == 'uz' else ("Безлимит" if lang == 'ru' else "Unlimited")
    elif user['is_premium']:
        status_str = f"⭐ Premium ({user['premium_until'][:10]})" if user['premium_until'] and user['premium_until'] != "9999-12-31T23:59:59" else "⭐ Premium"
        daily_limit = "Cheksiz" if lang == 'uz' else ("Безлимит" if lang == 'ru' else "Unlimited")
    else:
        status_str = "🆓 Bepul (Free)" if lang == 'uz' else ("🆓 Бесплатный" if lang == 'ru' else "🆓 Free")
        daily_limit = "15"
    
    q_map = {
        'best': "🎬 1080p / 4K",
        '720p': "📺 720p HD",
        '480p': "📱 480p SD",
        'mp3': "🎵 MP3 Audio",
        'ask': "❓ Ask"
    }
    pref_q = q_map.get(user['preferred_quality'], "📺 720p HD")
    user_fname = message.from_user.full_name or user.get('full_name') or message.from_user.first_name or "Foydalanuvchi"
    joined_at = user['joined_at'][:10] if user.get('joined_at') else "N/A"
    total_downloads = await get_user_total_downloads(user['user_id'])

    text = get_text("profile_text", lang,
                    user_id=user['user_id'],
                    full_name=user_fname,
                    status_str=status_str,
                    coins=user.get('coins', 0),
                    daily_downloads=user['daily_downloads'],
                    daily_limit=daily_limit,
                    pref_q=pref_q,
                    joined_at=joined_at,
                    total_downloads=total_downloads)
    await message.answer(text, reply_markup=get_profile_reply_keyboard(lang), parse_mode="Markdown")

@dp.message(F.text.in_(get_all_button_texts("btn_balance")))
async def cmd_balance(message: types.Message):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    coins = await get_user_coins(user_id)
    text = get_text("balance_text", lang, coins=coins)
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text.in_(get_all_button_texts("btn_back")))
async def cmd_back_main(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    current_state = await state.get_state()
    if current_state in ["in_shop", "in_invite_center"]:
        await state.set_state("in_profile")
        user = await get_or_create_user(user_id, message.from_user.username, message.from_user.full_name)
        is_admin = user_id in get_admin_ids()
        if is_admin:
            status_str = "⭐ Premium (Cheksiz)" if lang == 'uz' else ("⭐ Premium (Безлимит)" if lang == 'ru' else "⭐ Premium (Unlimited)")
            daily_limit = "Cheksiz" if lang == 'uz' else ("Безлимит" if lang == 'ru' else "Unlimited")
        elif user['is_premium']:
            status_str = f"⭐ Premium ({user['premium_until'][:10]})" if user['premium_until'] and user['premium_until'] != "9999-12-31T23:59:59" else "⭐ Premium"
            daily_limit = "Cheksiz" if lang == 'uz' else ("Безлимит" if lang == 'ru' else "Unlimited")
        else:
            status_str = "🆓 Bepul (Free)" if lang == 'uz' else ("🆓 Бесплатный" if lang == 'ru' else "🆓 Free")
            daily_limit = "15"
        q_map = {'best': "🎬 1080p / 4K", '720p': "📺 720p HD", '480p': "📱 480p SD", 'mp3': "🎵 MP3 Audio", 'ask': "❓ Ask"}
        pref_q = q_map.get(user['preferred_quality'], "📺 720p HD")
        user_fname = message.from_user.full_name or user.get('full_name') or message.from_user.first_name or "Foydalanuvchi"
        joined_at = user['joined_at'][:10] if user.get('joined_at') else "N/A"
        total_downloads = await get_user_total_downloads(user['user_id'])
        text = get_text("profile_text", lang, user_id=user['user_id'], full_name=user_fname, status_str=status_str, coins=user.get('coins', 0), daily_downloads=user['daily_downloads'], daily_limit=daily_limit, pref_q=pref_q, joined_at=joined_at, total_downloads=total_downloads)
        await message.answer(text, reply_markup=get_profile_reply_keyboard(lang), parse_mode="Markdown")
    else:
        await state.clear()
        is_admin = user_id in get_admin_ids()
        text = get_text("back_main_menu", lang)
        await message.answer(text, reply_markup=get_main_keyboard(is_admin, lang), parse_mode="Markdown")

@dp.message(F.text.in_(get_all_button_texts("btn_main_menu")))
async def cmd_home_main(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    is_admin = user_id in get_admin_ids()
    text = get_text("back_main_menu", lang)
    await message.answer(text, reply_markup=get_main_keyboard(is_admin, lang), parse_mode="Markdown")

@dp.message(F.text.in_(get_all_button_texts("btn_invite_center")))
@dp.callback_query(F.data == "invite_center_menu")
async def cmd_invite_center(event: types.Message | types.CallbackQuery, state: FSMContext, bot: Bot):
    await state.set_state("in_invite_center")
    msg = event.message if isinstance(event, types.CallbackQuery) else event
    user_id = event.from_user.id
    lang = await get_user_language(user_id)
    
    text = get_text("invite_center_welcome", lang)
    await msg.answer(text, reply_markup=get_invite_center_reply_keyboard(lang), parse_mode="Markdown")
    if isinstance(event, types.CallbackQuery):
        await event.answer()

@dp.message(F.text.in_(get_all_button_texts("btn_invite_link")))
@dp.callback_query(F.data == "show_invite_link")
async def cmd_invite_link_menu(event: types.Message | types.CallbackQuery, bot: Bot):
    msg = event.message if isinstance(event, types.CallbackQuery) else event
    user_id = event.from_user.id
    lang = await get_user_language(user_id)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    
    text = get_text("invite_link_text", lang, ref_link=ref_link)
    await msg.answer(text, reply_markup=get_invite_center_keyboard(ref_link, lang), parse_mode="Markdown")
    if isinstance(event, types.CallbackQuery):
        await event.answer()

@dp.message(F.text.in_(get_all_button_texts("btn_invite_stats")))
@dp.callback_query(F.data == "show_invite_stats")
async def cmd_invite_stats_menu(event: types.Message | types.CallbackQuery, bot: Bot):
    msg = event.message if isinstance(event, types.CallbackQuery) else event
    user_id = event.from_user.id
    lang = await get_user_language(user_id)
    
    stats = await get_referral_stats(user_id)
    text = get_text("invite_stats_text", lang,
                    total_ref=stats['total'],
                    active_ref=stats['active'],
                    earned_coins=stats['earned_coins'])
    await msg.answer(text, parse_mode="Markdown")
    if isinstance(event, types.CallbackQuery):
        await event.answer()

@dp.message(F.text.in_(get_all_button_texts("btn_shop_redeem")))
@dp.callback_query(F.data == "shop_menu")
async def cmd_shop(event: types.Message | types.CallbackQuery, state: FSMContext):
    await state.set_state("in_shop")
    msg = event.message if isinstance(event, types.CallbackQuery) else event
    user_id = event.from_user.id
    lang = await get_user_language(user_id)
    coins = await get_user_coins(user_id)
    
    text = get_text("shop_text", lang, coins=coins)
    await msg.answer(text, reply_markup=get_shop_reply_keyboard(lang), parse_mode="Markdown")
    if isinstance(event, types.CallbackQuery):
        await event.answer()

@dp.message(F.text.in_(get_all_button_texts("btn_buy_prem_menu")))
async def cmd_buy_premium_menu(message: types.Message):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    text = get_text("buy_premium_text", lang)
    await message.answer(text, reply_markup=get_buy_prem_stars_keyboard(lang, message.message_id), parse_mode="Markdown")

@dp.message(F.text.in_(get_all_button_texts("btn_use_coins")))
async def cmd_use_coins_menu(message: types.Message):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    coins = await get_user_coins(user_id)
    text = get_text("use_coins_text", lang, coins=coins)
    await message.answer(text, reply_markup=get_use_coins_keyboard(lang, message.message_id), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("buy_shop:"))
async def cb_buy_shop(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    item = parts[1]
    user_msg_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    user_id = callback.from_user.id
    coins = await get_user_coins(user_id)
    lang = await get_user_language(user_id)
    
    costs = {"vip7": 300, "vip30": 1000, "limit": 50}
    cost = costs.get(item, 999999)
    
    if coins < cost:
        msg = "❌ Coin yetarli emas! Invite Center orqali do'stlaringizni taklif qilib Coin yig'ing." if lang == 'uz' else (
            "❌ Недостаточно монет! Приглашайте друзей в Invite Center, чтобы заработать." if lang == 'ru' else
            "❌ Not enough Coins! Invite friends via Invite Center to earn Coins.")
        await callback.answer(msg, show_alert=True)
        return
        
    await delete_menu_and_user_msg(callback, user_msg_id)
    await add_user_coins(user_id, -cost)
    if item == "vip7":
        await grant_premium(user_id, 7)
        succ = "🎉 Tabriklaymiz! 300 Coin evaziga 7 kunlik Premium sotib oldingiz!" if lang == 'uz' else (
            "🎉 Поздравляем! Вы приобрели 7 дней Premium за 300 монет!" if lang == 'ru' else
            "🎉 Congratulations! You purchased 7 Days Premium for 300 Coins!")
    elif item == "vip30":
        await grant_premium(user_id, 30)
        succ = "🎉 Tabriklaymiz! 1000 Coin evaziga 30 kunlik Premium sotib oldingiz!" if lang == 'uz' else (
            "🎉 Поздравляем! Вы приобрели 30 дней Premium за 1000 монет!" if lang == 'ru' else
            "🎉 Congratulations! You purchased 30 Days Premium for 1000 Coins!")
    elif item == "limit":
        from database import DB_PATH
        import aiosqlite
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET daily_downloads = MAX(0, daily_downloads - 20) WHERE user_id = ?", (user_id,))
            await db.commit()
        succ = "⚡️ Bugungi yuklash limitingiz +20 taga oshirildi!" if lang == 'uz' else (
            "⚡️ Ваш лимит скачиваний на сегодня увеличен на +20!" if lang == 'ru' else
            "⚡️ Your download limit for today has been increased by +20!")
            
    await callback.message.answer(succ)
    await callback.answer()

@dp.message(Command("redeem"))
@dp.message(F.text.in_(get_all_button_texts("btn_redeem_code")))
@dp.callback_query(F.data == "redeem_code_prompt")
async def cmd_redeem_prompt(event: types.Message | types.CallbackQuery):
    msg = event.message if isinstance(event, types.CallbackQuery) else event
    user_id = event.from_user.id
    lang = await get_user_language(user_id)
    
    args = msg.text.split() if isinstance(event, types.Message) and msg.text.startswith("/redeem") else []
    if len(args) > 1:
        code = args[1]
        success, r_type, r_val = await redeem_code(user_id, code)
        if success:
            res_text = f"🎉 *Promokod qabul qilindi!*\n🎁 Sizga *+{r_val} {'🪙 Coin' if r_type=='coins' else 'kunlik Premium'}* taqdim etildi!"
        else:
            err_map = {"NOT_FOUND": "❌ Bunday promokod mavjud emas.", "EXPIRED": "❌ Bu promokodning muddati yoki limiti tuggan.", "ALREADY_USED": "❌ Siz bu promokoddan avval foydalangansiz."}
            res_text = err_map.get(r_type, "❌ Xatolik yuz berdi.")
        await msg.answer(res_text, parse_mode="Markdown")
        return
        
    prompt = (
        "🎟 *Promokodni yozib yuboring:*\n\nMisol uchun: `/redeem NAVROZ2026`" if lang == 'uz' else (
        "🎟 *Введите промокод:*\n\nПример: `/redeem NAVROZ2026`" if lang == 'ru' else
        "🎟 *Enter your Promo Code:*\n\nExample: `/redeem NAVROZ2026`")
    )
    await msg.answer(prompt, parse_mode="Markdown")
    if isinstance(event, types.CallbackQuery):
        await event.answer()

@dp.message(F.text.in_(get_all_button_texts("btn_help")))
async def cmd_help(message: types.Message):
    logger.info(f">>> Help clicked by user_id: {message.from_user.id}")
    lang = await get_user_language(message.from_user.id)
    await message.answer(get_text("help_text", lang), parse_mode="Markdown")

@dp.message(F.text.in_(get_all_button_texts("btn_admin")))
async def cmd_admin_panel_direct(message: types.Message):
    from admin import cmd_admin_panel
    await cmd_admin_panel(message)

@dp.callback_query(F.data == "check_subscription")
async def cb_check_sub(callback: types.CallbackQuery, bot: Bot):
    is_sub, ch_id, ch_link = await check_channel_subscription(callback.from_user.id, bot)
    if is_sub:
        await callback.message.edit_text("✅ Rahmat! Obuna tasdiqlandi. Endi botdan to'liq foydalanishingiz mumkin! 🚀")
        await callback.answer()
    else:
        lang = await get_user_language(callback.from_user.id)
        await callback.answer(get_text("not_subscribed_alert", lang), show_alert=True)

from aiogram.filters import StateFilter

IGNORED_BUTTONS = get_all_registered_buttons()

@dp.message(StateFilter(None), F.text, ~F.text.startswith("/"), ~F.text.in_(IGNORED_BUTTONS))
async def handle_media_download(message: types.Message, bot: Bot):
    logger.info(f">>> Text message received from user_id: {message.from_user.id}: {message.text}")

    if message.text.startswith("/redeem"):
        await cmd_redeem_prompt(message)
        return

    is_sub, ch_id, ch_link = await check_channel_subscription(message.from_user.id, bot)
    if not is_sub:
        lang = await get_user_language(message.from_user.id)
        text = (
            "⚠️ *Botdan foydalanish uchun kanalimizga obuna bo'ling!*\n\nObuna bo'lgach, *✅ Obunani tekshirish* tugmasini bosing:" if lang == 'uz' else (
            "⚠️ *Подпишитесь на наш канал, чтобы использовать бота!*\n\nПосле подписки нажмите *✅ Проверить подписку*:" if lang == 'ru' else
            "⚠️ *Please subscribe to our channel to use the bot!*\n\nAfter subscribing, click *✅ Check Subscription*:")
        )
        await message.answer(text, reply_markup=get_force_sub_keyboard(ch_link, lang), parse_mode="Markdown")
        return

    platform, icon, url = detect_platform_and_url(message.text)
    if not url:
        lang = await get_user_language(message.from_user.id)
        msg = "ℹ️ Iltimos, menga YouTube, TikTok, Instagram, Pinterest yoki Twitter havolasini yuboring!" if lang == 'uz' else (
            "ℹ️ Пожалуйста, отправьте мне ссылку на YouTube, TikTok, Instagram, Pinterest или Twitter!" if lang == 'ru' else
            "ℹ️ Please send me a link from YouTube, TikTok, Instagram, Pinterest, or Twitter!")
        await message.answer(msg)
        return

    can_download, current_usage = await check_daily_limit(message.from_user.id, free_limit=15)
    if not can_download:
        lang = await get_user_language(message.from_user.id)
        await message.answer(get_text("limit_exceeded", lang), parse_mode="Markdown")
        return

    user = await get_or_create_user(message.from_user.id)
    is_admin = message.from_user.id in get_admin_ids()
    is_premium = user['is_premium'] or is_admin
    pref_quality = user['preferred_quality']
    if pref_quality == 'best' and not is_premium:
        pref_quality = '720p'

    if pref_quality == 'ask':
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
        url_cache[url_hash] = url
        
        await message.answer(
            get_text("ask_quality_title", lang, icon=icon, platform=platform),
            reply_markup=get_quality_selector_keyboard(url, is_premium=is_premium, lang=lang, user_msg_id=message.message_id),
            parse_mode="Markdown"
        )
        return

    await process_and_send_media(message, url, platform, icon, pref_quality, bot)

@dp.callback_query(F.data.startswith("download_q:"))
async def cb_download_quality(callback: types.CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    url_hash = parts[1]
    quality = parts[2]
    user_msg_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0

    user = await get_or_create_user(callback.from_user.id)
    is_admin = callback.from_user.id in get_admin_ids()
    is_premium = user['is_premium'] or is_admin
    if quality == 'best' and not is_premium:
        lang = await get_user_language(callback.from_user.id)
        alert_msg = (
            "🔒 1080p Full HD va 4K Ultra HD yuklab olish faqat Premium foydalanuvchilar uchun mavjud!\n\n🛍 Quyidagi menyudan Premium obunani xarid qilib, cheksiz yuklash va eng yuqori sifatni oching!" if lang == 'uz' else (
            "🔒 Загрузка в 1080p Full HD и 4K Ultra HD доступна только для Premium пользователей!\n\n🛍 Оформите Premium ниже для безлимита и максимального качества!" if lang == 'ru' else
            "🔒 1080p Full HD and 4K Ultra HD downloading is available exclusively for Premium users!\n\n🛍 Upgrade to Premium below for unlimited downloads and highest quality!")
        )
        await callback.answer(alert_msg, show_alert=True)
        await delete_menu_and_user_msg(callback, user_msg_id)
        text = get_text("buy_premium_text", lang)
        await callback.message.answer(text, reply_markup=get_buy_prem_stars_keyboard(lang, user_msg_id), parse_mode="Markdown")
        return

    url = url_cache.get(url_hash)
    if not url:
        lang = await get_user_language(callback.from_user.id)
        await callback.answer(get_text("link_expired_alert", lang), show_alert=True)
        return

    platform, icon, _ = detect_platform_and_url(url)
    await delete_menu_and_user_msg(callback, user_msg_id)
    await process_and_send_media(callback.message, url, platform or "Media", icon or "📹", quality, bot)
    await callback.answer()

async def check_and_notify_referral(user_id: int, bot_inst: Bot):
    ref_id, coins_awarded = await verify_referral_activity(user_id)
    if ref_id > 0:
        try:
            ref_lang = await get_user_language(ref_id)
            ref_coins = await get_user_coins(ref_id)
            await bot_inst.send_message(ref_id, get_text("ref_success_notice", ref_lang, coins=ref_coins), parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Could not notify referrer {ref_id}: {e}")

async def process_and_send_media(message: types.Message, url: str, platform: str, icon: str, quality: str, bot_inst: Bot):
    user = await get_or_create_user(message.from_user.id)
    is_vip = user['is_premium']

    lang = user.get('language', 'uz')
    status_msg = await message.answer(get_text("processing_link", lang, icon=icon, platform=platform), parse_mode="Markdown")
    loop = asyncio.get_event_loop()
    
    last_update_time = [loop.time()]

    def progress_hook(d):
        if d['status'] == 'downloading':
            p = re.sub(r'\x1b\[[0-9;]*m', '', str(d.get('_percent_str', '0%'))).strip()
            speed = re.sub(r'\x1b\[[0-9;]*m', '', str(d.get('_speed_str', 'N/A'))).strip()
            eta = re.sub(r'\x1b\[[0-9;]*m', '', str(d.get('_eta_str', 'N/A'))).strip()
            
            current_time = loop.time()
            if current_time - last_update_time[0] >= 2.5:
                last_update_time[0] = current_time
                try:
                    text = get_text("downloading_progress", lang, platform=platform, p=p, speed=speed, eta=eta)
                    asyncio.run_coroutine_threadsafe(status_msg.edit_text(text, parse_mode="Markdown"), loop)
                except Exception:
                    pass

    if not is_vip and download_semaphore.locked():
        await status_msg.edit_text("⏳ *Serverda yuklash navbati:* Siz navbatda turibsiz. Video tez orada yuklanishni boshlaydi...\n\n💎 *Premium obunachilar navbatsiz tezkor yuklaydi!*", parse_mode="Markdown")

    async with download_semaphore:
        try:
            os.makedirs("downloads", exist_ok=True)
            await status_msg.edit_text(get_text("downloading_start", lang, platform=platform), parse_mode="Markdown")
            
            file_path, video_info = await loop.run_in_executor(None, download_media, url, quality, progress_hook)
            title = video_info.get("title", f"{platform} Video")

            bot_info = await bot_inst.get_me()

            if quality == 'mp3' or file_path.endswith(".mp3"):
                await status_msg.edit_text(get_text("mp3_preparing", lang), parse_mode="Markdown")
                mp3_file = await loop.run_in_executor(None, convert_to_mp3, file_path)
                
                audio = FSInputFile(mp3_file)
                await message.answer_audio(
                    audio,
                    caption=f"🎵 {title}\n\n🤖 @{bot_info.username}",
                    title=title
                )
                await record_download(message.from_user.id, url, platform, "MP3")
                await check_and_notify_referral(message.from_user.id, bot_inst)
                if os.path.exists(mp3_file):
                    os.remove(mp3_file)

            else:
                file_path = await loop.run_in_executor(None, ensure_h264_codec, file_path)
                
                is_local_api = getattr(bot_inst, "_is_local_api", False) or (hasattr(bot_inst.session, "api") and bot_inst.session.api.is_local)
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                
                if not is_local_api and file_size_mb > 49.0:
                    await status_msg.edit_text(get_text("compressing_video", lang), parse_mode="Markdown")
                    file_path = await loop.run_in_executor(None, compress_video_to_target_size, file_path, 48.0)

                await status_msg.edit_text(get_text("sending_telegram", lang), parse_mode="Markdown")
                
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

                res_str = get_text("quality_str_part", lang, height=height) if height else ""
                caption_text = get_text("video_caption", lang, icon=icon, title=title, size=file_size_mb, res_str=res_str, username=bot_info.username)
                await message.answer_video(
                    video,
                    caption=caption_text,
                    width=width,
                    height=height,
                    duration=int(duration) if duration else None,
                    thumbnail=thumbnail,
                    supports_streaming=True,
                    parse_mode="Markdown"
                )
                await record_download(message.from_user.id, url, platform, quality)
                await check_and_notify_referral(message.from_user.id, bot_inst)
                
                if os.path.exists(file_path):
                    os.remove(file_path)
                if thumb_result and os.path.exists(thumb_result):
                    os.remove(thumb_result)

            await status_msg.delete()

        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            await status_msg.edit_text(get_text("download_error", lang, error=str(e)))

@dp.callback_query(F.data == "ref_info")
async def cb_ref_info(callback: types.CallbackQuery, bot: Bot):
    await cmd_invite_center(callback, bot)

@dp.callback_query(F.data.in_(["buy_prem_stars"]) | F.data.startswith("buy_stars:"))
async def cb_buy_stars(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    option = parts[1] if len(parts) > 1 else "1m"
    user_msg_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    lang = await get_user_language(callback.from_user.id)
    if option == "1m":
        amount, days, label = 50, 30, ("⭐ 1 oy Premium" if lang == 'uz' else ("⭐ 1 месяц Premium" if lang == 'ru' else "⭐ 1 Month Premium"))
        payload = "prem_30_days"
    elif option == "2m":
        amount, days, label = 90, 60, ("⭐ 2 oy Premium (-10%)" if lang == 'uz' else ("⭐ 2 месяца Premium (-10%)" if lang == 'ru' else "⭐ 2 Months Premium (-10%)"))
        payload = "prem_60_days"
    elif option == "3m":
        amount, days, label = 130, 90, ("⭐ 3 oy Premium (-15%)" if lang == 'uz' else ("⭐ 3 месяца Premium (-15%)" if lang == 'ru' else "⭐ 3 Months Premium (-15%)"))
        payload = "prem_90_days"
    else:
        return

    prices = [types.LabeledPrice(label=label, amount=amount)]
    desc = "Cheksiz yuklash, 1080p/4K sifat, navbatsiz super-tezkor yuklash va hech qanday reklamasiz!" if lang == 'uz' else (
        "Безлимитные скачивания, 1080p/4K качество, загрузка без очереди и рекламы!" if lang == 'ru' else
        "Unlimited downloads, 1080p/4K quality, priority high-speed downloads without ads!"
    )
    await delete_menu_and_user_msg(callback, user_msg_id)
    await callback.message.answer_invoice(
        title=label,
        description=desc,
        payload=payload,
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
    payload = message.successful_payment.invoice_payload
    days = 30
    if payload == "prem_60_days":
        days = 60
    elif payload == "prem_90_days":
        days = 90
    await grant_premium(user_id, days)
    lang = await get_user_language(user_id)
    await message.answer(
        get_text("successful_payment_notice", lang, days=days),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "buy_prem_card")
async def cb_buy_card(callback: types.CallbackQuery):
    lang = await get_user_language(callback.from_user.id)
    text = get_text("card_payment_info", lang)
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

    lang = await get_user_language(user_id)
    await message.answer(get_text("receipt_received_user", lang))

    caption = (
        "💳 *Yangi to'lov cheki (Karta / Click)*\n\n"
        f"👤 *Foydalanuvchi:* {username} (`{user_id}`)\n"
        f"🆔 *ID:* `{user_id}`\n\n"
        "To'lovni tasdiqlab, 30 kunlik Premium berishni xohlaysizmi?"
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
        caption=f"✅ *Tasdiqlandi!* `{target_user_id}` foydalanuvchiga {days} kunlik Premium berildi.",
        parse_mode="Markdown"
    )
    await callback.answer("✅ Premium berildi!")
    
    try:
        target_lang = await get_user_language(target_user_id)
        await bot.send_message(
            target_user_id,
            get_text("receipt_verified_notice", target_lang, days=days),
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
        caption=f"❌ *Rad etildi!* `{target_user_id}` foydalanuvchi cheki qabul qilinmadi.",
        parse_mode="Markdown"
    )
    await callback.answer("❌ Rad etildi!")
    
    try:
        target_lang = await get_user_language(target_user_id)
        await bot.send_message(
            target_user_id,
            get_text("receipt_rejected_notice", target_lang),
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
        session = AiohttpSession(api=api, timeout=600)
        bot_inst = Bot(token=BOT_TOKEN, session=session)
        bot_inst._is_local_api = True
        return bot_inst
    else:
        logger.info("🌐 Using Standard Telegram API")
        session = AiohttpSession(timeout=600)
        bot_inst = Bot(token=BOT_TOKEN, session=session)
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
