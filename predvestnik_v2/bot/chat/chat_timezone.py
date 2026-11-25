"""Часовой пояс чата: по нему считаются полночные сбросы — активность, стрик,
квесты и локальные топы. Управляют владелец или ранг с правом «Настройки чата»
(то же право, что у привязки админ-чата). Смена попадает в журнал админки
(`bot_admin_actions`), кнопки −/+ двигают пояс на шаг.
"""
from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.chat import ranks
from bot.chat.cbutil import edit_or_send
from bot.chat.framework import Ctx, UsageError, registry
from core.constants import CHAT_TIMEZONE_MAX, CHAT_TIMEZONE_MIN
from infrastructure.repositories.streak import get_chat_timezone, set_chat_timezone

router = Router(name="chat_timezone")

_OFFSET_RE = re.compile(r"^[+-]?\d+$")


class TimezoneCB(CallbackData, prefix="ctz"):
    """Шаг часового пояса кнопками: delta=0 — вернуть UTC+0."""

    chat_id: int
    delta: int


def label(offset: int) -> str:
    return f"UTC{int(offset):+d}"


def parse_offset(text: str) -> int:
    """«+3», «-5», «3», «UTC+3» — смещение в часах."""
    raw = str(text or "").strip().upper().replace("UTC", "").replace(" ", "")
    if not _OFFSET_RE.fullmatch(raw):
        raise ValueError("Формат: «бот часовой пояс, +3».")
    return int(raw)


def view_text(offset: int) -> str:
    return (
        "🕐 <b>Часовой пояс чата</b>\n"
        f"Сейчас: <code>{label(offset)}</code>\n"
        "<blockquote>По нему бот считает полночь: сбросы активности и стрика, "
        "новые квесты и локальные топы.</blockquote>\n"
        f"Изменить: <code>бот часовой пояс, +3</code> · диапазон UTC{CHAT_TIMEZONE_MIN} — UTC+{CHAT_TIMEZONE_MAX}."
    )


def view_keyboard(chat_id: int, offset: int) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text="−1 час", callback_data=TimezoneCB(chat_id=chat_id, delta=-1).pack()),
        InlineKeyboardButton(text="+1 час", callback_data=TimezoneCB(chat_id=chat_id, delta=1).pack()),
    ]]
    if offset != 0:
        rows.append([InlineKeyboardButton(
            text="Сделать UTC+0", callback_data=TimezoneCB(chat_id=chat_id, delta=0).pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _apply(db, chat_id: int, *, actor_id: int, before: int, after: int) -> None:
    await set_chat_timezone(db, chat_id, after)
    try:   # журнал — дополнение: смена пояса важнее записи о ней
        from services import admin_people
        await admin_people.audit(db, int(actor_id), "chat_timezone", chat_id=int(chat_id),
                                 details={"before": int(before), "after": int(after)})
        await db.commit()
    except Exception:   # noqa: BLE001
        pass


@registry.command(
    "часовой пояс", aliases=("timezone", "часовойпояс", "часовой пояс чата", "пояс чата"),
    usage="бот часовой пояс, +3", private=False, section="settings",
    summary="Часовой пояс чата: по нему идут полуночные сбросы и локальные топы.",
    example="бот часовой пояс, +3",
)
async def cmd_timezone(ctx: Ctx) -> None:
    chat = ctx.message.chat
    await ranks.sync_owner(ctx.db, ctx.bot, chat.id)
    if not await ranks.can(ctx.db, chat.id, ctx.user_id, "settings"):
        await ctx.reply("⛔ Менять настройки чата может владелец или ранг с этим правом (по умолчанию — совладелец).")
        return
    current = await get_chat_timezone(ctx.db, chat.id)
    if not ctx.args.strip():
        await ctx.reply(view_text(current), reply_markup=view_keyboard(chat.id, current))
        return
    try:
        offset = parse_offset(ctx.args)
    except ValueError:
        raise UsageError("бот часовой пояс, +3") from None
    if offset < CHAT_TIMEZONE_MIN or offset > CHAT_TIMEZONE_MAX:
        await ctx.reply(f"❌ Диапазон: UTC{CHAT_TIMEZONE_MIN} — UTC+{CHAT_TIMEZONE_MAX}.")
        return
    if offset == current:
        await ctx.reply(f"🕐 Часовой пояс уже <code>{label(offset)}</code>.")
        return
    await _apply(ctx.db, chat.id, actor_id=ctx.user_id, before=current, after=offset)
    await ctx.reply(
        f"✅ <b>Часовой пояс чата:</b> <code>{label(current)}</code> → <code>{label(offset)}</code>\n"
        f"<blockquote>Теперь активность, стрик, квесты и локальные топы считаются "
        f"по полуночи {label(offset)}.</blockquote>"
    )


@router.callback_query(TimezoneCB.filter())
async def on_timezone(call: CallbackQuery, callback_data: TimezoneCB, db) -> None:
    message = getattr(call, "message", None)
    if message is None or int(callback_data.chat_id) != int(message.chat.id):
        await call.answer("Меню устарело — откройте «бот часовой пояс» в самом чате.", show_alert=True)
        return
    chat_id = int(callback_data.chat_id)
    if not await ranks.can(db, chat_id, call.from_user.id, "settings"):
        await call.answer("⛔ Менять настройки чата может владелец или ранг с этим правом.", show_alert=True)
        return
    current = await get_chat_timezone(db, chat_id)
    delta = int(callback_data.delta)
    target = 0 if delta == 0 else max(CHAT_TIMEZONE_MIN, min(CHAT_TIMEZONE_MAX, current + delta))
    if target == current:
        await call.answer(f"Диапазон: UTC{CHAT_TIMEZONE_MIN} — UTC+{CHAT_TIMEZONE_MAX}.")
        return
    await _apply(db, chat_id, actor_id=call.from_user.id, before=current, after=target)
    await call.answer(f"🕓 Часовой пояс: {label(target)}")
    await edit_or_send(call, view_text(target), parse_mode="HTML",
                       reply_markup=view_keyboard(chat_id, target), disable_web_page_preview=True)
