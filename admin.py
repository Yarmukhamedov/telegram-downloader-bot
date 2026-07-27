import os
import asyncio
import logging
from aiogram import Router, Bot, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import get_admin_stats, get_all_user_ids, grant_premium, set_setting, get_setting, create_redeem_code, get_user_language
from keyboards import get_admin_keyboard, get_admin_reply_keyboard

logger = logging.getLogger(__name__)
admin_router = Router()

def get_admin_ids() -> list[int]:
    admin_env = os.getenv("ADMIN_IDS", "")
    ids = []
    for item in admin_env.split(","):
        item = item.strip()
        if item.isdigit():
            ids.append(int(item))
    return ids

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_channel = State()
    waiting_for_premium_input = State()

@admin_router.message(Command("admin"))
@admin_router.message(F.text.in_(["🛠 Admin Panel", "🛠 Админ панель"]))
async def cmd_admin_panel(message: types.Message):
    admin_ids = get_admin_ids()
    if message.from_user.id not in admin_ids:
        await message.answer("❌ Kechirasiz, siz admin emassiz!")
        return

    try:
        lang = await get_user_language(message.from_user.id)
        await message.answer("👨‍💻 *Admin bo'limi:*", reply_markup=get_admin_reply_keyboard(lang), parse_mode="Markdown")
        stats = await get_admin_stats()
        text = (
            "🛠 *Admin Boshqaruv Paneli*\n\n"
            f"👥 *Jami foydalanuvchilar:* {stats['total_users']} ta\n"
            f"⭐ *Premium foydalanuvchilar:* {stats['premium_users']} ta\n"
            f"⚡️ *Bugun faol:* {stats['active_today']} ta\n\n"
            f"📊 *Jami yuklab olishlar:* {stats['total_downloads']} ta\n"
            f"📥 *Bugungi yuklashlar:* {stats['downloads_today']} ta\n\n"
            f"🪙 *Jami Coinlar (bazada):* {stats.get('total_coins', 0)} 🪙\n"
            f"👥 *Jami takliflar (referallar):* {stats.get('total_referrals', 0)} ta\n\n"
            "👇 *Quyidagi tugmalar orqali botni boshqarishingiz mumkin:*"
        )
        await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in cmd_admin_panel: {e}")
        await message.answer(f"❌ Admin panelni ochishda xatolik yuz berdi: {e}")

@admin_router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: types.CallbackQuery):
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Ruxsat berilmagan!", show_alert=True)
        return

    stats = await get_admin_stats()
    text = (
        "📊 *Bot Statistikasi*\n\n"
        f"👥 *Jami foydalanuvchilar:* {stats['total_users']} ta\n"
        f"⭐ *Premium foydalanuvchilar:* {stats['premium_users']} ta\n"
        f"⚡️ *Bugun faol:* {stats['active_today']} ta\n\n"
        f"📊 *Jami yuklab olishlar:* {stats['total_downloads']} ta\n"
        f"📥 *Bugungi yuklashlar:* {stats['downloads_today']} ta\n\n"
        f"🪙 *Jami Coinlar (bazada):* {stats.get('total_coins', 0)} 🪙\n"
        f"👥 *Jami takliflar (referallar):* {stats.get('total_referrals', 0)} ta\n"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Ruxsat berilmagan!", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.message.answer("📢 Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni (matn, rasm yoki video) yuboring:")
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_broadcast)
async def handle_broadcast_message(message: types.Message, state: FSMContext, bot: Bot):
    if message.text in ["⬅️ Orqaga", "⬅️ Назад", "⬅️ Back", "🔙 Orqaga", "🔙 Назад", "🔙 Back", "🏠 Bosh Menu", "🏠 Bosh menyu", "🏠 Главное меню", "🏠 Main Menu"]:
        await state.clear()
        from app import cmd_home_main
        await cmd_home_main(message, state)
        return
    await state.clear()
    user_ids = await get_all_user_ids()
    
    status_msg = await message.answer(f"⏳ Xabar yuborish boshlandi. Jami: {len(user_ids)} foydalanuvchi...")
    
    success = 0
    failed = 0
    
    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            success += 1
            await asyncio.sleep(0.05) # Rate limiting avoidance
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ *Xabar yuborish yakunlandi!*\n\n"
        f"🟢 Muvaffaqiyatli: {success} ta\n"
        f"🔴 Etib bormadi (bloklangan): {failed} ta",
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data == "admin_channel")
async def cb_admin_channel(callback: types.CallbackQuery, state: FSMContext):
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Ruxsat berilmagan!", show_alert=True)
        return

    current_ch = await get_setting("force_channel_id", "Sozlanmagan")
    current_link = await get_setting("force_channel_link", "Sozlanmagan")

    await state.set_state(AdminStates.waiting_for_channel)
    await callback.message.answer(
        f"⚙️ *Majburiy obuna kanali*\n\n"
        f"📌 Joriy Kanal ID/Username: `{current_ch}`\n"
        f"🔗 Joriy Link: `{current_link}`\n\n"
        f"Yangi kanal ma'lumotlarini quyidagi formatda yuboring:\n"
        f"`@kanal_username https://t.me/kanal_link`\n\n"
        f"O'chirib tashlash uchun `off` deb yozing.",
        parse_mode="Markdown"
    )
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_channel)
async def handle_channel_input(message: types.Message, state: FSMContext):
    if message.text in ["⬅️ Orqaga", "⬅️ Назад", "⬅️ Back", "🔙 Orqaga", "🔙 Назад", "🔙 Back", "🏠 Bosh Menu", "🏠 Bosh menyu", "🏠 Главное меню", "🏠 Main Menu"]:
        await state.clear()
        from app import cmd_home_main
        await cmd_home_main(message, state)
        return
    await state.clear()
    text = message.text.strip()
    
    if text.lower() == "off":
        await set_setting("force_channel_id", "")
        await set_setting("force_channel_link", "")
        await message.answer("✅ Majburiy obuna o'chirildi.")
        return

    parts = text.split()
    if len(parts) >= 2:
        ch_id = parts[0]
        ch_link = parts[1]
        await set_setting("force_channel_id", ch_id)
        await set_setting("force_channel_link", ch_link)
        await message.answer(f"✅ Majburiy obuna sozlandi:\nKanal: {ch_id}\nLink: {ch_link}")
    else:
        await message.answer("❌ Noto'g'ri format! Misol: `@kanal_username https://t.me/kanal_link`")

@admin_router.callback_query(F.data == "admin_premium")
async def cb_admin_premium(callback: types.CallbackQuery, state: FSMContext):
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Ruxsat berilmagan!", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_for_premium_input)
    await callback.message.answer(
        "👑 *Premium Berish*\n\n"
        "Foydalanuvchi ID si va kunlar sonini quyidagi formatda kiriting:\n"
        "`123456789 30` (ID va Kun)",
        parse_mode="Markdown"
    )
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_premium_input)
async def handle_premium_input(message: types.Message, state: FSMContext):
    if message.text in ["⬅️ Orqaga", "⬅️ Назад", "⬅️ Back", "🔙 Orqaga", "🔙 Назад", "🔙 Back", "🏠 Bosh Menu", "🏠 Bosh menyu", "🏠 Главное меню", "🏠 Main Menu"]:
        await state.clear()
        from app import cmd_home_main
        await cmd_home_main(message, state)
        return
    await state.clear()
    parts = message.text.strip().split()
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        uid = int(parts[0])
        days = int(parts[1])
        res = await grant_premium(uid, days)
        if res:
            await message.answer(f"✅ Foydalanuvchi `{uid}` ga {days} kunlik Premium berildi!", parse_mode="Markdown")
        else:
            await message.answer(f"❌ Foydalanuvchi `{uid}` ma'lumotlar bazasidan topilmadi.", parse_mode="Markdown")
    else:
        await message.answer("❌ Noto'g'ri format! Misol: `123456789 30`", parse_mode="Markdown")

@admin_router.message(Command("grant_premium"))
async def cmd_grant_premium(message: types.Message):
    admin_ids = get_admin_ids()
    if message.from_user.id not in admin_ids:
        return

    parts = message.text.strip().split()
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        uid = int(parts[1])
        days = int(parts[2])
        res = await grant_premium(uid, days)
        if res:
            await message.answer(f"✅ Foydalanuvchi `{uid}` ga {days} kunlik Premium berildi!")
        else:
            await message.answer(f"❌ Foydalanuvchi `{uid}` bazadan topilmadi.")
    else:
        await message.answer("ℹ️ Foydalanish: `/grant_premium <user_id> <days>`")

@admin_router.message(Command("create_code"))
async def cmd_create_code(message: types.Message):
    admin_ids = get_admin_ids()
    if message.from_user.id not in admin_ids:
        return

    parts = message.text.strip().split()
    if len(parts) >= 4:
        code = parts[1]
        r_type = parts[2]
        val = int(parts[3])
        max_u = int(parts[4]) if len(parts) > 4 else 100
        res = await create_redeem_code(code, r_type, val, max_u)
        if res:
            await message.answer(f"✅ Yangi promokod yaratildi!\n🎟 *Kod:* `{code}`\n🎁 *Turi:* {r_type} (+{val})\n👥 *Limit:* {max_u} ta kishi", parse_mode="Markdown")
        else:
            await message.answer("❌ Bu kod avval yaratilgan yoki xatolik yuz berdi.")
    else:
        await message.answer("ℹ️ Foydalanish formatlari:\n`/create_code NAVROZ2026 coins 500 100` (100 kishi 500 coindan oladi)\n`/create_code PREM2026 days 7 50` (50 kishi 7 kunlik Premium oladi)", parse_mode="Markdown")
