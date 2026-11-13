"""Кнопки под карточкой жалобы («бот жалоба»): взять в работу, мут, варн, бан, отклонить — без захода в админку.

Не дублирует правила админки: кнопка вызывает те же обработчики раздела «Жалобы» (`FastAPI/routers/bot_admin/reports.py`),
поэтому действуют те же роли и права по действиям, тот же журнал, та же защита от двойного наказания и то же письмо автору
жалобы. Нажать может только персонал бота с доступом к «Жалобам»; остальные видят отказ, а карточка не меняется.
Бан здесь на 7 дней и после подтверждения. Бессрочный бан в этом чате — только у создателя, в его личке и с подтверждением.
Глобальные действия остаются в админке и управляются через «Права» (решение владельца 2026-11-13).
"""
from __future__ import annotations

import html
import time

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from fastapi import HTTPException
from loguru import logger

router = Router(name="chat_report_cards")

BAN_MINUTES = 7 * 24 * 60
SECTION = "section:reports"
SECTION_DEFAULT_RANK = 2
# код кнопки → (действие админки, минуты, что написать на карточке)
PUNISH = {"m": ("mute", 60, "мут на 1 час"), "w": ("warn", 0, "предупреждение"), "B": ("ban", BAN_MINUTES, "бан на 7 дней"),
          "P": ("ban", 0, "бан навсегда")}   # 0 минут — бан без срока (как в админке)
OWNER_CODES = {"p", "P"}   # бессрочный бан в чате: только создатель
CONFIRM_SECONDS = 5 * 60
CONFIRM = {"b": ("✅ Да, бан на 7 дней", "B", "Бан на 7 дней — подтверди."),
           "p": ("✅ Да, бан навсегда", "P", "Бан навсегда в этом чате — подтверди.")}


def _btn(text: str, code: str, rid: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=f"rp:{code}:{rid}")


def keyboard(rid: int, *, taken: bool = False, confirm: str = "", owner: bool = False) -> InlineKeyboardMarkup:
    """confirm — код кнопки, которую подтверждаем (b, p); owner — карточка создателя: ещё бан навсегда в этом чате."""
    if confirm:
        text, code, _ = CONFIRM[confirm]
        return InlineKeyboardMarkup(inline_keyboard=[[_btn(text, code, rid), _btn("↩️ Отмена", "x", rid)]])
    rows = [[_btn("🔇 Мут 1 ч", "m", rid), _btn("⚠️ Варн", "w", rid), _btn("🚫 Бан", "b", rid)],
            [_btn("❌ Отклонить", "r", rid)]]
    if owner:
        rows.insert(1, [_btn("⛔ Бан навсегда", "p", rid)])
    if not taken:
        rows[-1].insert(0, _btn("👁 В работу", "t", rid))
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def is_owner(db, user_id: int) -> bool:
    """Создатель бота (роль 6 или разработчик): его карточка жалобы получает тяжёлые баны."""
    from bot.chat.global_ranks import get_bot_rank
    from services import admin_security
    return admin_security.is_owner(int(user_id), await get_bot_rank(db, int(user_id)))


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
async def on_report_button(call: CallbackQuery, db, state: FSMContext) -> None:
    from FastAPI.routers.bot_admin import reports as admin_reports
    msg, parts = call.message, (call.data or "").split(":")
    if not isinstance(msg, Message) or len(parts) != 3 or not parts[2].isdigit() or parts[1] not in {"t", "r", "m", "w", "b", "B", "x", *OWNER_CODES}:
        await call.answer("Кнопка устарела.", show_alert=True)
        return
    code, rid = parts[1], int(parts[2])
    user = await _principal(db, call.from_user.id)
    if user is None:
        await call.answer("Эти кнопки — для персонала бота с доступом к жалобам.", show_alert=True)
        return
    owner = await is_owner(db, call.from_user.id)
    if code in OWNER_CODES and not owner:   # права проверяются при каждом нажатии: поддельная кнопка ничего не даст
        await call.answer("Бан навсегда из лички выдаёт только создатель бота.", show_alert=True)
        return
    heavy = owner and msg.chat.type == "private" and msg.chat.id == call.from_user.id
    if code in OWNER_CODES and not heavy:
        await call.answer("Эти действия доступны только в твоей личке с ботом.", show_alert=True)
        return
    if code == "P":
        confirmation = (await state.get_data()).get("report_confirmation") or {}
        if (confirmation.get("report") != rid or confirmation.get("message") != msg.message_id
                or confirmation.get("code") != code or confirmation.get("until", 0) < time.time()):
            await call.answer("Подтверди бан заново на карточке жалобы.", show_alert=True)
            return
        await state.update_data(report_confirmation=None)
    base = _base(msg.html_text)
    if code in CONFIRM or code == "x":   # бан спрашивает ещё раз; «Отмена» возвращает обычные кнопки
        await state.update_data(report_confirmation=None)
        taken = base != msg.html_text and "\n\n👁 В работе" in msg.html_text
        await _edit(msg, msg.html_text, keyboard(rid, confirm=code if code in CONFIRM else "", taken=taken, owner=heavy))
        if code == "p":
            await state.update_data(report_confirmation={"report": rid, "message": msg.message_id,
                                                       "code": CONFIRM[code][1], "until": time.time() + CONFIRM_SECONDS})
        await call.answer(CONFIRM[code][2] if code in CONFIRM else "")
        return
    try:
        if code == "t":
            await admin_reports.report_action(rid, {"action": "take"}, user, db, None)
            await _edit(msg, f"{base}\n\n👁 В работе: {_name(call)}", keyboard(rid, taken=True, owner=heavy))
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
