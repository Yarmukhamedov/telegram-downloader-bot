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
    waiting_for_give_id = State()
    waiting_for_give_amount = State()

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

@admin_router.callback_query(F.data.in_(["admin_give_prem", "admin_give_coin"]))
async def cb_admin_give_start(callback: types.CallbackQuery, state: FSMContext):
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("Ruxsat berilmagan!", show_alert=True)
        return

    give_type = "premium" if callback.data == "admin_give_prem" else "coin"
    await state.set_state(AdminStates.waiting_for_give_id)
    await state.update_data(give_type=give_type)
    
    text = "👤 *Foydalanuvchi ID raqamini kiriting:*"
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_give_id)
async def handle_give_id(message: types.Message, state: FSMContext):
    if message.text in ["⬅️ Orqaga", "⬅️ Назад", "⬅️ Back", "🔙 Orqaga", "🔙 Назад", "🔙 Back", "🏠 Bosh Menu", "🏠 Bosh menyu", "🏠 Главное меню", "🏠 Main Menu"]:
        await state.clear()
        from app import cmd_home_main
        await cmd_home_main(message, state)
        return
        
    uid_text = message.text.strip()
    if not uid_text.isdigit():
        await message.answer("❌ Noto'g'ri format! Faqat raqamlardan iborat ID kiriting:")
        return
        
    uid = int(uid_text)
    await state.update_data(give_uid=uid)
    from keyboards import get_admin_confirm_keyboard
    
    await message.answer(
        f"Kiritilgan ID: `{uid}`\nTasdiqlaysizmi?",
        reply_markup=get_admin_confirm_keyboard("admin_confirm_id"),
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data == "admin_give_cancel")
async def cb_admin_give_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("❌ Amaliyot bekor qilindi.")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_confirm_id")
async def cb_admin_confirm_id(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    give_type = data.get("give_type")
    
    await callback.message.delete()
    await state.set_state(AdminStates.waiting_for_give_amount)
    
    if give_type == "premium":
        text = "Muddatni (*kunlar soni*) kiriting:"
    else:
        text = "Miqdorni (*Coin*) kiriting:"
        
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_give_amount)
async def handle_give_amount(message: types.Message, state: FSMContext):
    if message.text in ["⬅️ Orqaga", "⬅️ Назад", "⬅️ Back", "🔙 Orqaga", "🔙 Назад", "🔙 Back", "🏠 Bosh Menu", "🏠 Bosh menyu", "🏠 Главное меню", "🏠 Main Menu"]:
        await state.clear()
        from app import cmd_home_main
        await cmd_home_main(message, state)
        return
        
    amount_text = message.text.strip()
    if not amount_text.isdigit():
        await message.answer("❌ Noto'g'ri format! Faqat raqam kiriting:")
        return
        
    amount = int(amount_text)
    await state.update_data(give_amount=amount)
    from keyboards import get_admin_confirm_keyboard
    
    data = await state.get_data()
    give_type = data.get("give_type")
    
    unit = "kun" if give_type == "premium" else "Coin"
    await message.answer(
        f"Kiritilgan miqdor: `{amount}` {unit}\nTasdiqlaysizmi?",
        reply_markup=get_admin_confirm_keyboard("admin_confirm_amount"),
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data == "admin_confirm_amount")
async def cb_admin_confirm_amount(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid = data.get("give_uid")
    amount = data.get("give_amount")
    give_type = data.get("give_type")
    
    await state.clear()
    await callback.message.delete()
    
    if not uid or not amount:
        await callback.message.answer("❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")
        return
        
    if give_type == "premium":
        res = await grant_premium(uid, amount)
        if res:
            await callback.message.answer(f"✅ Foydalanuvchi `{uid}` ga {amount} kunlik Premium taqdim etildi!", parse_mode="Markdown")
            try:
                lang = await get_user_language(uid)
                msg = f"🎉 *Tabriklaymiz!*\nSizga administrator tomonidan *{amount} kunlik Premium* obunasi taqdim etildi! 🥳" if lang == 'uz' else (
                    f"🎉 *Поздравляем!*\nАдминистратор выдал вам *{amount} дней Premium* подписки! 🥳" if lang == 'ru' else
                    f"🎉 *Congratulations!*\nAn administrator has granted you *{amount} days of Premium*! 🥳")
                await bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
            except Exception:
                pass
        else:
            await callback.message.answer(f"❌ Foydalanuvchi `{uid}` ma'lumotlar bazasidan topilmadi.", parse_mode="Markdown")
    else:
        from database import add_user_coins
        try:
            new_balance = await add_user_coins(uid, amount)
            await callback.message.answer(f"✅ Foydalanuvchi `{uid}` hisobiga {amount} Coin qo'shildi!\n🪙 *Yangi balans:* {new_balance}", parse_mode="Markdown")
            try:
                lang = await get_user_language(uid)
                msg = f"🎉 *Tabriklaymiz!*\nAdministrator tomonidan sizning hisobingizga *{amount} Coin* qo'shildi! 🥳" if lang == 'uz' else (
                    f"🎉 *Поздравляем!*\nАдминистратор добавил вам *{amount} монет*! 🥳" if lang == 'ru' else
                    f"🎉 *Congratulations!*\nAn administrator has added *{amount} Coins* to your balance! 🥳")
                await bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
            except Exception:
                pass
        except Exception as e:
            await callback.message.answer(f"❌ Xatolik yuz berdi: ehtimol foydalanuvchi topilmadi.")
            
    await callback.answer()

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
