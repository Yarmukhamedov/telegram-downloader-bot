from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import hashlib
from locales import get_text

def get_main_keyboard(is_admin: bool = False, lang: str = "uz") -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text=get_text("btn_settings", lang)),
            KeyboardButton(text=get_text("btn_profile", lang))
        ],
        [
            KeyboardButton(text=get_text("btn_help", lang)),
            KeyboardButton(text=get_text("btn_language", lang))
        ]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text=get_text("btn_admin", lang))])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_profile_reply_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text=get_text("btn_balance", lang))
        ],
        [
            KeyboardButton(text=get_text("btn_invite_center", lang)),
            KeyboardButton(text=get_text("btn_shop_redeem", lang))
        ],
        [
            KeyboardButton(text=get_text("btn_back", lang))
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_language_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="set_lang:uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang:ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang:en")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_settings_keyboard(current_quality: str = 'best', lang: str = "uz", user_msg_id: int = 0) -> InlineKeyboardMarkup:
    q_map = {
        'best': "🎬 Eng yuqori (1080p / 4K)" if lang == 'uz' else ("🎬 Максимальное (1080p / 4K)" if lang == 'ru' else "🎬 Highest (1080p / 4K)"),
        '720p': "📺 O'rtacha HD (720p)" if lang == 'uz' else ("📺 Среднее HD (720p)" if lang == 'ru' else "📺 Medium HD (720p)"),
        '480p': "📱 Tejamkor (480p)" if lang == 'uz' else ("📱 Экономное (480p)" if lang == 'ru' else "📱 Data Saver (480p)"),
        'mp3': "🎵 Faqat MP3 Audio" if lang == 'uz' else ("🎵 Только MP3 Аудио" if lang == 'ru' else "🎵 MP3 Audio Only"),
        'ask': "❓ Har safar so'rash" if lang == 'uz' else ("❓ Спрашивать каждый раз" if lang == 'ru' else "❓ Ask every time")
    }

    buttons = []
    for q_key, q_label in q_map.items():
        prefix = "✅ " if current_quality == q_key else ""
        buttons.append([InlineKeyboardButton(text=f"{prefix}{q_label}", callback_data=f"set_quality:{q_key}:{user_msg_id}")])
    
    buttons.append([InlineKeyboardButton(text=get_text("btn_back", lang), callback_data=f"close_quality:{user_msg_id}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_force_sub_keyboard(channel_link: str, lang: str = "uz") -> InlineKeyboardMarkup:
    sub_text = "📢 Kanalga obuna bo'lish" if lang == 'uz' else ("📢 Подписаться на канал" if lang == 'ru' else "📢 Subscribe to Channel")
    chk_text = "✅ Obunani tekshirish" if lang == 'uz' else ("✅ Проверить подписку" if lang == 'ru' else "✅ Check Subscription")
    buttons = [
        [InlineKeyboardButton(text=sub_text, url=channel_link)],
        [InlineKeyboardButton(text=chk_text, callback_data="check_subscription")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_quality_selector_keyboard(video_url: str) -> InlineKeyboardMarkup:
    url_hash = hashlib.md5(video_url.encode()).hexdigest()[:10]
    buttons = [
        [
            InlineKeyboardButton(text="🎬 1080p (Best)", callback_data=f"download_q:{url_hash}:best"),
            InlineKeyboardButton(text="📺 720p HD", callback_data=f"download_q:{url_hash}:720p")
        ],
        [
            InlineKeyboardButton(text="📱 480p SD", callback_data=f"download_q:{url_hash}:480p"),
            InlineKeyboardButton(text="🎵 MP3 Audio", callback_data=f"download_q:{url_hash}:mp3")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats"),
            InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton(text="⚙️ Obuna kanali", callback_data="admin_channel"),
            InlineKeyboardButton(text="👑 Premium berish", callback_data="admin_premium")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_profile_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=get_text("btn_invite_center", lang), callback_data="invite_center_menu")],
        [InlineKeyboardButton(text=get_text("btn_shop_redeem", lang), callback_data="shop_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_invite_center_keyboard(ref_link: str, lang: str = "uz") -> InlineKeyboardMarkup:
    share_text = "🚀 Eng zo'r video yuklovchi bot! Hech qanday suv belgisiz va super sifatda yuklaydi!" if lang == 'uz' else (
        "🚀 Лучший бот для скачивания видео! Без водяных знаков и в высоком качестве!" if lang == 'ru' else
        "🚀 Best video downloader bot! High quality without watermarks!"
    )
    btn_share = "📤 Havolani do'stlarga yuborish" if lang == 'uz' else ("📤 Поделиться ссылкой" if lang == 'ru' else "📤 Share Link with Friends")
    btn_shop = "🛍 Do'konga o'tish" if lang == 'uz' else ("🛍 Перейти в магазин" if lang == 'ru' else "🛍 Go to Shop")
    
    from urllib.parse import quote
    share_url = f"https://t.me/share/url?url={quote(ref_link)}&text={quote(share_text)}"
    
    buttons = [
        [InlineKeyboardButton(text=btn_share, url=share_url)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_shop_reply_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text=get_text("btn_buy_prem_menu", lang)),
            KeyboardButton(text=get_text("btn_use_coins", lang))
        ],
        [
            KeyboardButton(text=get_text("btn_redeem_code", lang))
        ],
        [
            KeyboardButton(text=get_text("btn_back", lang))
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_shop_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=get_text("btn_shop_vip7", lang), callback_data="buy_shop:vip7")],
        [InlineKeyboardButton(text=get_text("btn_shop_vip30", lang), callback_data="buy_shop:vip30")],
        [InlineKeyboardButton(text=get_text("btn_shop_limit", lang), callback_data="buy_shop:limit")],
        [InlineKeyboardButton(text=get_text("btn_redeem_code", lang), callback_data="redeem_code_prompt")],
        [InlineKeyboardButton(text=get_text("btn_buy_stars", lang), callback_data="buy_prem_stars")],
        [InlineKeyboardButton(text=get_text("btn_buy_card", lang), callback_data="buy_prem_card")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_buy_prem_stars_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    t1 = "1 oy — 50 ⭐" if lang == 'uz' else ("1 месяц — 50 ⭐" if lang == 'ru' else "1 Month — 50 ⭐")
    t2 = "2 oy — 90 ⭐ (-10%)" if lang == 'uz' else ("2 месяца — 90 ⭐ (-10%)" if lang == 'ru' else "2 Months — 90 ⭐ (-10%)")
    t3 = "3 oy — 130 ⭐ (-15%)" if lang == 'uz' else ("3 месяца — 130 ⭐ (-15%)" if lang == 'ru' else "3 Months — 130 ⭐ (-15%)")
    buttons = [
        [InlineKeyboardButton(text=t1, callback_data="buy_stars:1m")],
        [InlineKeyboardButton(text=t2, callback_data="buy_stars:2m")],
        [InlineKeyboardButton(text=t3, callback_data="buy_stars:3m")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_use_coins_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=get_text("btn_shop_vip7", lang), callback_data="buy_shop:vip7")],
        [InlineKeyboardButton(text=get_text("btn_shop_vip30", lang), callback_data="buy_shop:vip30")],
        [InlineKeyboardButton(text=get_text("btn_shop_limit", lang), callback_data="buy_shop:limit")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_payment_receipt_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✅ Tasdiqlash (30 kun Premium)", callback_data=f"verify_prem:{user_id}:30"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_prem:{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
