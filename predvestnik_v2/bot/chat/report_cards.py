"""Кнопки под карточкой жалобы («бот жалоба»): взять в работу, мут, варн, бан, отклонить — без захода в админку.

Не дублирует правила админки: кнопка вызывает те же обработчики раздела «Жалобы» (`FastAPI/routers/bot_admin/reports.py`),
поэтому действуют те же роли и права по действиям, тот же журнал, та же защита от двойного наказания и то же письмо автору
жалобы. Нажать может только персонал бота с доступом к «Жалобам»; остальные видят отказ, а карточка не меняется.
Бан здесь только на 7 дней и после подтверждения; бессрочный — в админке.
"""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from fastapi import HTTPException
from loguru import logger

router = Router(name="chat_report_cards")

BAN_MINUTES = 7 * 24 * 60
SECTION = "section:reports"
SECTION_DEFAULT_RANK = 2
# код кнопки → (действие админки, минуты, что написать на карточке)
PUNISH = {"m": ("mute", 60, "мут на 1 час"), "w": ("warn", 0, "предупреждение"), "B": ("ban", BAN_MINUTES, "бан на 7 дней")}


def _btn(text: str, code: str, rid: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=f"rp:{code}:{rid}")


def keyboard(rid: int, *, taken: bool = False, confirm_ban: bool = False) -> InlineKeyboardMarkup:
    if confirm_ban:
        return InlineKeyboardMarkup(inline_keyboard=[[_btn("✅ Да, бан на 7 дней", "B", rid), _btn("↩️ Отмена", "x", rid)]])
    rows = [[_btn("🔇 Мут 1 ч", "m", rid), _btn("⚠️ Варн", "w", rid), _btn("🚫 Бан", "b", rid)],
            [_btn("❌ Отклонить", "r", rid)]]
    if not taken:
        rows[1].insert(0, _btn("👁 В работу", "t", rid))
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _principal(db, user_id: int) -> dict | None:
    """Тот же «пропуск», что у входа в админку; None — не персонал или роль ниже, чем нужна для «Жалоб»."""
    from bot.chat.global_ranks import get_bot_rank
    from services import admin_access
    rank = await get_bot_rank(db, user_id)
    if rank <= 0:
        return None
    user = admin_access.staff_principal(user_id, rank, await admin_access.load_grants(db))
    return user if rank >= admin_access.min_rank(user, SECTION, SECTION_DEFAULT_RANK) else None


async def _edit(msg: Message, text: str, kb: InlineKeyboardMarkup | None) -> None:
    try:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


def _base(html_text: str) -> str:
    """Текст карточки без нашей последней приписки («В работе…», «Закрыта…»): сам текст жалобы пишет посторонний человек."""
    head, _, tail = html_text.rpartition("\n\n")
    return head if head and tail.startswith(("✅", "👁 В работе")) else html_text


async def _is_closed(db, rid: int) -> bool:
    from services import reports
    row = await reports.get(db, rid)
    return row is None or row["status"] not in reports.OPEN


def _name(call: CallbackQuery) -> str:
    user = call.from_user
    return html.escape(f"@{user.username}" if user.username else user.full_name)


@router.callback_query(F.data.startswith("rp:"))
async def on_report_button(call: CallbackQuery, db) -> None:
    from FastAPI.routers.bot_admin import reports as admin_reports
    msg, parts = call.message, (call.data or "").split(":")
    if not isinstance(msg, Message) or len(parts) != 3 or not parts[2].isdigit() or parts[1] not in {"t", "r", "m", "w", "b", "B", "x"}:
        await call.answer("Кнопка устарела.", show_alert=True)
        return
    code, rid = parts[1], int(parts[2])
    user = await _principal(db, call.from_user.id)
    if user is None:
        await call.answer("Эти кнопки — для персонала бота с доступом к жалобам.", show_alert=True)
        return
    base = _base(msg.html_text)
    if code in ("b", "x"):   # бан спрашивает ещё раз; «Отмена» возвращает обычные кнопки
        await _edit(msg, base, keyboard(rid, confirm_ban=code == "b"))
        await call.answer("Бан на 7 дней — подтверди." if code == "b" else "")
        return
    try:
        if code == "t":
            await admin_reports.report_action(rid, {"action": "take"}, user, db, None)
            await _edit(msg, f"{base}\n\n👁 В работе: {_name(call)}", keyboard(rid, taken=True))
            await call.answer("Взял в работу.")
            return
        if code == "r":
            await admin_reports.report_action(rid, {"action": "reject"}, user, db, None)
            await _edit(msg, f"{base}\n\n✅ Отклонена: {_name(call)}", None)
            await call.answer("Отклонена.")
            return
        action, minutes, title = PUNISH[code]
        await admin_reports.report_punish(rid, {"action": action, "minutes": minutes or None, "reason": f"жалоба №{rid}"}, user, db, None)
    except HTTPException as exc:
        await call.answer(str(exc.detail)[:190], show_alert=True)
        if exc.status_code == 409 and await _is_closed(db, rid):   # закрыли другие: кнопки убираем, чтобы не звали наказать второй раз
            await _edit(msg, f"{base}\n\n✅ Жалоба уже закрыта.", None)
        return
    except Exception:
        logger.exception("report card button failed")
        await call.answer("Не получилось. Проверь жалобу в админке: возможно, действие уже выполнено.", show_alert=True)
        return
    await _edit(msg, f"{base}\n\n✅ {title.capitalize()}: {_name(call)}. Жалоба закрыта.", None)
    await call.answer("Готово.")
