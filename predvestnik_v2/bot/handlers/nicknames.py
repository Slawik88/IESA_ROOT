"""
bot/handlers/nicknames.py
B8: бот мой ник — set/view/reset local per-chat pseudonym.
"""
from datetime import datetime, timezone

from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.constants import NICKNAME_FREE_CHANGES_PER_MONTH
from infrastructure.repositories.economy import get_item_quantity, remove_item
from infrastructure.repositories.users import get_nickname, set_nickname, delete_nickname
from services.utils import safe_html
from services.vip import is_vip_active

router = Router(name="nicknames_router")

_MAX_LEN = 20
_MIN_LEN = 2


class NickCB(CallbackData, prefix="nick"):
    action: str   # "reset" | "cancel"


@router.message(TextCmd(["мой ник", "мой никнейм", "псевдоним"]))
async def cmd_my_nick(message: types.Message, db, text_args: str = None):
    if message.chat.type == "private":
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    # No argument → show current nick + reset button
    if not text_args or not text_args.strip():
        current = await get_nickname(db, user_id, chat_id)
        if current:
            b = InlineKeyboardBuilder()
            b.button(text="❌ Сбросить псевдоним", callback_data=NickCB(action="reset"))
            await message.answer(
                f"🏷 <b>Ваш псевдоним в этом чате:</b> <code>{safe_html(current)}</code>\n\n"
                f"<i>Чтобы изменить, напишите: <code>бот мой ник, Новое имя</code></i>",
                reply_markup=b.as_markup(),
                parse_mode="HTML",
            )
        else:
            await message.answer(
                "🏷 <b>Псевдоним не установлен.</b>\n\n"
                "<i>Установите: <code>бот мой ник, Ваш псевдоним</code>\n"
                f"Длина: {_MIN_LEN}–{_MAX_LEN} символов, без HTML-тегов.</i>",
                parse_mode="HTML",
            )
        return

    # Set new nickname
    raw = text_args.strip()

    # Validation
    if len(raw) < _MIN_LEN:
        return await message.answer(
            f"❌ Псевдоним слишком короткий. Минимум {_MIN_LEN} символа.", parse_mode="HTML"
        )
    if len(raw) > _MAX_LEN:
        return await message.answer(
            f"❌ Псевдоним слишком длинный. Максимум {_MAX_LEN} символов.", parse_mode="HTML"
        )

    # Strip HTML tags
    cleaned = safe_html(raw)
    if cleaned != raw:
        return await message.answer(
            "❌ Псевдоним не должен содержать HTML-теги или спецсимволы.",
            parse_mode="HTML",
        )

    # Monthly nickname-change limit (Block 4.1) — VIP = безлимит
    is_vip = await is_vip_active(db, user_id)
    use_token = False
    count = 0
    reset_at = None
    if not is_vip:
        async with db.execute(
            "SELECT nickname_changes_count, nickname_changes_reset_at "
            "FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
        # nickname_changes_reset_at — TIMESTAMP без зоны (naive); asyncpg падает
        # с "can't subtract offset-naive and offset-aware datetimes" при записи
        # aware-значения в naive-колонку. now/reset_at держим naive — сравниваем
        # только .year/.month (это просто int-атрибуты, awareness не важна).
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        count = row[0] if row else 0
        reset_at = row[1] if row else now
        if reset_at.tzinfo is not None:
            reset_at = reset_at.replace(tzinfo=None)
        if (now.year, now.month) != (reset_at.year, reset_at.month):
            count = 0
            reset_at = now
        if count >= NICKNAME_FREE_CHANGES_PER_MONTH:
            if await get_item_quantity(db, user_id, "zarniki_nickname_token") > 0:
                use_token = True
            else:
                return await message.answer(
                    f"❌ Лимит смены ника исчерпан ({NICKNAME_FREE_CHANGES_PER_MONTH}/мес в этом чате). "
                    "Сброс в начале следующего месяца.\n"
                    "Хочешь менять ник без ограничений? Оформи VIP ✨ — «бот вип», "
                    "либо используй ✨ Жетон смены ника из инвентаря.",
                    parse_mode="HTML",
                )

    try:
        await set_nickname(db, user_id, chat_id, raw)
        if not is_vip:
            if use_token:
                await remove_item(db, user_id, "zarniki_nickname_token", 1)
            else:
                await db.execute(
                    "INSERT INTO user_chat_stats "
                    "(user_tg_id, chat_tg_id, nickname_changes_count, nickname_changes_reset_at) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT (user_tg_id, chat_tg_id) DO UPDATE "
                    "SET nickname_changes_count = ?, nickname_changes_reset_at = ?",
                    (user_id, chat_id, count + 1, reset_at, count + 1, reset_at),
                )
            await db.commit()
        await message.answer(
            f"✅ <b>Псевдоним установлен:</b> <code>{safe_html(raw)}</code>\n"
            f"<i>Теперь бот будет обращаться к вам так в этом чате.</i>",
            parse_mode="HTML",
        )
    except Exception:
        await message.answer(
            "❌ Этот псевдоним уже занят в данном чате. Выберите другой.",
            parse_mode="HTML",
        )


@router.callback_query(NickCB.filter(F.action == "reset"))
async def cb_nick_reset(query: types.CallbackQuery, db):
    user_id = query.from_user.id
    chat_id = query.message.chat.id

    current = await get_nickname(db, user_id, chat_id)
    if not current:
        await query.answer("Псевдоним уже не установлен.", show_alert=False)
        return

    await delete_nickname(db, user_id, chat_id)
    await query.message.edit_text(
        "✅ <b>Псевдоним сброшен.</b>\n<i>Бот снова будет использовать ваше имя из Telegram.</i>",
        parse_mode="HTML",
    )
    await query.answer()
