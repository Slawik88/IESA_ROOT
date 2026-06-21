"""bot/handlers/notifications.py — настройки персональных уведомлений (Block 15)."""
from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.constants import NOTIFICATION_CATEGORIES
from infrastructure.repositories import notifications as notif_db
from services.utils import check_callback_owner

router = Router(name="notifications_router")


class NotifCB(CallbackData, prefix="notif"):
    category: str
    user_id: int


async def _render(db, user_id: int) -> tuple[str, types.InlineKeyboardMarkup]:
    prefs = await notif_db.get_prefs(db, user_id)
    b = InlineKeyboardBuilder()
    lines = ["🔔 <b>НАСТРОЙКИ УВЕДОМЛЕНИЙ</b>\n",
             "<i>Включай/выключай личные напоминания от бота:</i>\n"]
    for cat, label in NOTIFICATION_CATEGORIES.items():
        on = prefs.get(cat, True)
        lines.append(f"{'✅' if on else '❌'} {label}")
        b.button(text=f"{'🔕 Выключить' if on else '🔔 Включить'}: {label}",
                 callback_data=NotifCB(category=cat, user_id=user_id))
    b.adjust(1)
    lines.append("\n<i>Групповые сообщения в чат (сундуки, годовщины) приходят всем — здесь не отключаются.</i>")
    return "\n".join(lines), b.as_markup()


@router.message(TextCmd(["уведомления", "настройки уведомлений", "нотификации"]))
async def cmd_notifications(message: types.Message, db):
    text, kb = await _render(db, message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(NotifCB.filter())
async def cb_notif_toggle(query: types.CallbackQuery, callback_data: NotifCB, db):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    if callback_data.category not in NOTIFICATION_CATEGORIES:
        return await query.answer("Неизвестная категория.", show_alert=True)
    new_state = await notif_db.toggle(db, query.from_user.id, callback_data.category)
    text, kb = await _render(db, query.from_user.id)
    try:
        await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await query.answer("🔔 Включено" if new_state else "🔕 Выключено")
