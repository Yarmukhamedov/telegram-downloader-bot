from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import hashlib
from locales import get_text

def get_main_keyboard(is_admin: bool = False, lang: str = "uz") -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text=get_text("btn_profile", lang)),
            KeyboardButton(text=get_text("btn_settings", lang))
        ],
        [
            KeyboardButton(text=get_text("btn_shop_redeem", lang)),
            KeyboardButton(text=get_text("btn_help", lang))
        ]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text=get_text("btn_admin", lang))])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_settings_reply_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text=get_text("btn_quality", lang)),
            KeyboardButton(text=get_text("btn_language", lang))
        ],
        [
            KeyboardButton(text=get_text("btn_main_menu", lang))
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_single_back_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text=get_text("btn_back", lang)),
            KeyboardButton(text=get_text("btn_main_menu", lang))
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_admin_reply_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text=get_text("btn_admin_stats", lang)),
            KeyboardButton(text=get_text("btn_admin_broadcast", lang))
        ],
        [
            KeyboardButton(text=get_text("btn_admin_give_prem", lang)),
            KeyboardButton(text=get_text("btn_admin_give_coin", lang))
        ],
        [
            KeyboardButton(text=get_text("btn_admin_promos", lang)),
            KeyboardButton(text=get_text("btn_admin_channel", lang))
        ],
        [
            KeyboardButton(text=get_text("btn_admin_export", lang)),
            KeyboardButton(text=get_text("btn_main_menu", lang))
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_profile_reply_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text=get_text("btn_balance", lang)),
            KeyboardButton(text=get_text("btn_invite_center", lang))
        ],
        [
            KeyboardButton(text=get_text("btn_daily_bonus", lang))
        ],
        [
            KeyboardButton(text=get_text("btn_main_menu", lang))
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_balance_keyboard(lang: str = "uz", user_msg_id: int = 0) -> InlineKeyboardMarkup:
    btn_spend = "🪙 Coinlarni sarflash" if lang == 'uz' else ("🪙 Потратить монеты" if lang == 'ru' else "🪙 Spend Coins")
    btn_close = "❌ Yopish" if lang == 'uz' else ("❌ Закрыть" if lang == 'ru' else "❌ Close")
    buttons = [
        [InlineKeyboardButton(text=btn_spend, callback_data=f"use_coins_menu:{user_msg_id}")],
        [InlineKeyboardButton(text=btn_close, callback_data=f"close_balance:{user_msg_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_invite_center_reply_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text=get_text("btn_invite_link", lang)),
            KeyboardButton(text=get_text("btn_invite_stats", lang))
        ],
        [
            KeyboardButton(text=get_text("btn_back", lang)),
            KeyboardButton(text=get_text("btn_main_menu", lang))
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_language_keyboard(user_msg_id: int = 0) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data=f"set_lang:uz:{user_msg_id}"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data=f"set_lang:ru:{user_msg_id}"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data=f"set_lang:en:{user_msg_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_settings_keyboard(current_quality: str = '720p', lang: str = "uz", user_msg_id: int = 0, is_premium: bool = False) -> InlineKeyboardMarkup:
    q_map = {
        'best': "🎬 Eng yuqori (4K Ultra HD)" if lang == 'uz' else ("🎬 Максимальное (4K Ultra HD)" if lang == 'ru' else "🎬 Highest (4K Ultra HD)"),
        '2k': "💎 Ultra HD (2K 1440p)" if lang == 'uz' else ("💎 Ultra HD (2K 1440p)" if lang == 'ru' else "💎 Ultra HD (2K 1440p)"),
        '1080p': "🎥 Full HD (1080p)" if lang == 'uz' else ("🎥 Full HD (1080p)" if lang == 'ru' else "🎥 Full HD (1080p)"),
        '720p': "📺 O'rtacha HD (720p)" if lang == 'uz' else ("📺 Среднее HD (720p)" if lang == 'ru' else "📺 Medium HD (720p)"),
        '480p': "📱 Tejamkor (480p)" if lang == 'uz' else ("📱 Экономное (480p)" if lang == 'ru' else "📱 Data Saver (480p)"),
        'mp3': "🎵 Faqat MP3 Audio" if lang == 'uz' else ("🎵 Только MP3 Аудио" if lang == 'ru' else "🎵 MP3 Audio Only"),
        'ask': "❓ Har safar so'rash" if lang == 'uz' else ("❓ Спрашивать каждый раз" if lang == 'ru' else "❓ Ask every time")
    }

    buttons = []
    for q_key, q_label in q_map.items():
        if q_key in ['best', '2k', '1080p'] and not is_premium:
            label = f"🔒 {q_label} ⭐️"
        else:
            prefix = "✅ " if current_quality == q_key else ""
            label = f"{prefix}{q_label}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"set_quality:{q_key}:{user_msg_id}")])
    
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

def get_quality_selector_keyboard(video_url: str, is_premium: bool = False, lang: str = "uz", user_msg_id: int = 0) -> InlineKeyboardMarkup:
    url_hash = hashlib.md5(video_url.encode()).hexdigest()[:10]
    if is_premium:
        best_str = "🎬 4K Ultra HD"
        k2_str = "💎 2K (1440p)"
        fhd_str = "🎥 1080p Full HD"
    else:
        best_str = "🔒 4K Ultra HD ⭐️"
        k2_str = "🔒 2K (1440p) ⭐️"
        fhd_str = "🔒 1080p Full HD ⭐️"
    
    hd_str = "📺 720p HD"
    sd_str = "📱 480p SD"
    mp3_str = "🎵 MP3 Audio"

    buttons = [
        [
            InlineKeyboardButton(text=best_str, callback_data=f"download_q:{url_hash}:best:{user_msg_id}"),
            InlineKeyboardButton(text=k2_str, callback_data=f"download_q:{url_hash}:2k:{user_msg_id}")
        ],
        [
            InlineKeyboardButton(text=fhd_str, callback_data=f"download_q:{url_hash}:1080p:{user_msg_id}"),
            InlineKeyboardButton(text=hd_str, callback_data=f"download_q:{url_hash}:720p:{user_msg_id}")
        ],
        [
            InlineKeyboardButton(text=sd_str, callback_data=f"download_q:{url_hash}:480p:{user_msg_id}"),
            InlineKeyboardButton(text=mp3_str, callback_data=f"download_q:{url_hash}:mp3:{user_msg_id}")
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
            InlineKeyboardButton(text="🎁 Premium hadya etish", callback_data="admin_give_prem"),
            InlineKeyboardButton(text="🪙 Coin Ulashishi", callback_data="admin_give_coin")
        ],
        [
            InlineKeyboardButton(text="🎟 Promokodlar", callback_data="admin_promos"),
            InlineKeyboardButton(text="👥 Foydalanuvchi b-n ishlash", callback_data="admin_user_manage")
        ],
        [
            InlineKeyboardButton(text="📢 Majburiy obuna kanali", callback_data="admin_channel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_confirm_keyboard(confirm_data: str) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=confirm_data),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_give_cancel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_profile_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    btn_text = "🔗 Taklif havolasini olish" if lang == 'uz' else ("🔗 Получить реф. ссылку" if lang == 'ru' else "🔗 Get Invite Link")
    buttons = [
        [InlineKeyboardButton(text=btn_text, callback_data="show_invite_link")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_invite_center_keyboard(ref_link: str, lang: str = "uz") -> InlineKeyboardMarkup:
    share_text = "🚀 Eng zo'r video yuklovchi bot! Hech qanday suv belgisiz va super sifatda yuklaydi!" if lang == 'uz' else (
        "🚀 Лучший бот для скачивания видео! Без водяных знаков и в высоком качестве!" if lang == 'ru' else
        "🚀 Best video downloader bot! High quality without watermarks!"
    )
    btn_share = "📤 Havolani do'stlarga yuborish" if lang == 'uz' else ("📤 Поделиться ссылкой" if lang == 'ru' else "📤 Share Link with Friends")
    
    from urllib.parse import quote
    share_url = f"https://t.me/share/url?url={quote(ref_link)}&text={quote(share_text)}"
    
    buttons = [
        [InlineKeyboardButton(text=btn_share, url=share_url)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_shop_reply_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    t_prem = get_text("btn_buy_prem_menu", lang)
    t_redeem = get_text("btn_redeem_code", lang)
    
    buttons = [
        [
            KeyboardButton(text=t_prem),
            KeyboardButton(text=t_redeem)
        ],
        [
            KeyboardButton(text=get_text("btn_back", lang)),
            KeyboardButton(text=get_text("btn_main_menu", lang))
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_shop_keyboard(lang: str = "uz", user_msg_id: int = 0) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=get_text("btn_shop_vip7", lang), callback_data=f"buy_shop:vip7:{user_msg_id}")],
        [InlineKeyboardButton(text=get_text("btn_shop_vip30", lang), callback_data=f"buy_shop:vip30:{user_msg_id}")],
        [InlineKeyboardButton(text=get_text("btn_shop_limit", lang), callback_data=f"buy_shop:limit:{user_msg_id}")],
        [InlineKeyboardButton(text=get_text("btn_redeem_code", lang), callback_data="redeem_code_prompt")],
        [InlineKeyboardButton(text=get_text("btn_buy_stars", lang), callback_data=f"buy_prem_stars:1m:{user_msg_id}")],
        [InlineKeyboardButton(text=get_text("btn_buy_card", lang), callback_data="buy_prem_card")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_buy_prem_stars_keyboard(lang: str = "uz", user_msg_id: int = 0) -> InlineKeyboardMarkup:
    t1 = "1 oy — 50 ⭐" if lang == 'uz' else ("1 месяц — 50 ⭐" if lang == 'ru' else "1 Month — 50 ⭐")
    t2 = "2 oy — 90 ⭐ (-10%)" if lang == 'uz' else ("2 месяца — 90 ⭐ (-10%)" if lang == 'ru' else "2 Months — 90 ⭐ (-10%)")
    t3 = "3 oy — 130 ⭐ (-15%)" if lang == 'uz' else ("3 месяца — 130 ⭐ (-15%)" if lang == 'ru' else "3 Months — 130 ⭐ (-15%)")
    buttons = [
        [InlineKeyboardButton(text=t1, callback_data=f"buy_stars:1m:{user_msg_id}")],
        [InlineKeyboardButton(text=t2, callback_data=f"buy_stars:2m:{user_msg_id}")],
        [InlineKeyboardButton(text=t3, callback_data=f"buy_stars:3m:{user_msg_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_use_coins_keyboard(lang: str = "uz", user_msg_id: int = 0, show_back_to_balance: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=get_text("btn_shop_vip7", lang), callback_data=f"buy_shop:vip7:{user_msg_id}")],
        [InlineKeyboardButton(text=get_text("btn_shop_vip30", lang), callback_data=f"buy_shop:vip30:{user_msg_id}")],
        [InlineKeyboardButton(text=get_text("btn_shop_limit", lang), callback_data=f"buy_shop:limit:{user_msg_id}")]
    ]
    if show_back_to_balance:
        btn_back = get_text("btn_back", lang)
        buttons.append([InlineKeyboardButton(text=btn_back, callback_data=f"back_to_balance:{user_msg_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_payment_receipt_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✅ Tasdiqlash (30 kun Premium)", callback_data=f"verify_prem:{user_id}:30"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_prem:{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
