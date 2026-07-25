from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="⚙️ Sozlamalar"), KeyboardButton(text="👤 Profil / Tarif")],
        [KeyboardButton(text="ℹ️ Yordam")]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_settings_keyboard(current_quality: str = 'best') -> InlineKeyboardMarkup:
    q_map = {
        'best': "🎬 Eng yuqori (1080p / 4K)",
        '720p': "📺 O'rtacha HD (720p)",
        '480p': "📱 Tejamkor (480p)",
        'mp3': "🎵 Faqat MP3 Audio",
        'ask': "❓ Har safar so'rash"
    }

    buttons = []
    for q_key, q_label in q_map.items():
        prefix = "✅ " if current_quality == q_key else ""
        buttons.append([InlineKeyboardButton(text=f"{prefix}{q_label}", callback_data=f"set_quality:{q_key}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_force_sub_keyboard(channel_link: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=channel_link)],
        [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_subscription")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_quality_selector_keyboard(video_url: str) -> InlineKeyboardMarkup:
    # URL is shortened or hashed in callback to prevent Telegram 64-byte payload limits
    import hashlib
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

def get_profile_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🎁 Bepul VIP olish (Do'stlarga taklif)", callback_data="ref_info")],
        [InlineKeyboardButton(text="⭐ Telegram Stars bilan (50 ⭐ / 30 kun)", callback_data="buy_prem_stars")],
        [InlineKeyboardButton(text="💳 Karta orqali (Click / Payme)", callback_data="buy_prem_card")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_payment_receipt_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✅ Tasdiqlash (30 kun VIP)", callback_data=f"verify_prem:{user_id}:30"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_prem:{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
