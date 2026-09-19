"""Chat-native cooperative Echo event; no wallet or power mutations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import Bot, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from bot.keyboards.cta import answer_group_only
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
from core.chat_echo_v1 import SYMBOLS
from services import chat_echo_v1 as echo
from services.utils import safe_html


router = Router(name="chat_echo_router")
router.message.middleware(ModuleCheckMiddleware("module_echo"))
router.callback_query.middleware(ModuleCheckMiddleware("module_echo"))


class EchoCB(CallbackData, prefix="echo"):
    event_id: int
    symbol_id: str


class EchoStartCB(CallbackData, prefix="echostart"):
    action: str
    user_id: int


def _keyboard(event_id: int, disabled: bool = False) -> types.InlineKeyboardMarkup | None:
    if disabled:
        return None
    builder = InlineKeyboardBuilder()
    for symbol_id, meta in SYMBOLS.items():
        builder.button(
            text=f"{meta['emoji']} {meta['name']}",
            callback_data=EchoCB(event_id=int(event_id), symbol_id=symbol_id),
        )
    builder.adjust(3)
    return builder.as_markup()


def _text(view: dict) -> str:
    counts = view.get("counts") or {}
    lines = [
        "◉ <b>ЭХО В ЧАТЕ</b>",
        "<i>Один знак от участника. Награды, валюты и рейтинга нет.</i>",
        "",
        f"Собрано: <b>{int(view['total'])}/{int(view['target'])}</b> · кворум {int(view['quorum'])}",
        " · ".join(
            f"{meta['emoji']} {int(counts.get(symbol_id, 0))}"
            for symbol_id, meta in SYMBOLS.items()
        ),
    ]
    if view.get("status") == "completed":
        lines.extend(["", f"<b>Контур завершён:</b> {safe_html(str(view.get('finale_text') or 'Эхо затихло.'))}"])
    else:
        lines.append("\nВыбери знак. Решение для этого Эха не меняется.")
    return "\n".join(lines)


async def _is_admin(bot: Bot, user_id: int, chat_id: int, developer_id: int) -> bool:
    if developer_id and int(user_id) == int(developer_id):
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status == "creator" or (
        member.status == "administrator" and bool(getattr(member, "can_manage_chat", False))
    )


async def _eligible_snapshot(bot: Bot, db, chat_id: int) -> list[int]:
    now = datetime.now(timezone.utc)
    eligible: list[int] = []
    for row in await echo.candidates(db, chat_id):
        user_id = int(row["user_id"])
        try:
            member = await bot.get_chat_member(chat_id, user_id)
        except Exception:
            continue
        if member.status not in {"member", "administrator", "creator", "restricted"}:
            continue
        if bool(member.user.is_bot):
            continue
        observed = row.get("membership_since")
        established = bool(
            observed and observed <= now - timedelta(hours=24)
            and int(row.get("user_messages_count_all_time") or 0) >= 3
        )
        telegram_admin = member.status in {"administrator", "creator"}
        if established or telegram_admin:
            eligible.append(user_id)
    return eligible


@router.message(TextCmd(["эхо", "эхо статус", "echo status"]))
async def cmd_echo_status(message: types.Message, db):
    if message.chat.type == "private":
        return await answer_group_only(message)
    view = await echo.overview(db, int(message.chat.id))
    if not view:
        return await message.answer(
            "◉ Активного Эха нет. Совладелец может включить его в «бот настройки чата» и запустить командой «бот эхо начать».",
        )
    await message.answer(
        _text(view), reply_markup=_keyboard(view["event_id"]), parse_mode="HTML"
    )


@router.message(TextCmd(["эхо начать", "запустить эхо", "echo start"]))
async def cmd_echo_start(message: types.Message, db, bot: Bot, developer_id: int = 0):
    if message.chat.type == "private":
        return await answer_group_only(message)
    if not await _is_admin(bot, int(message.from_user.id), int(message.chat.id), developer_id):
        return await message.answer("❌ Запустить Эхо может Telegram-администратор с правом управления чатом или разработчик.")
    eligible = await _eligible_snapshot(bot, db, int(message.chat.id))
    if len(eligible) < 3:
        return await message.answer("❌ Для Эха нужны минимум 3 подтверждённых участника чата.")
    from core.chat_echo_v1 import target_for_active_members
    target = min(len(eligible), target_for_active_members(len(eligible)))
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"Запустить · цель {target}",
        callback_data=EchoStartCB(action="confirm", user_id=int(message.from_user.id)),
    )
    builder.button(
        text="Отмена", callback_data=EchoStartCB(action="cancel", user_id=int(message.from_user.id))
    )
    builder.adjust(1)
    return await message.answer(
        "◉ <b>ЗАПУСТИТЬ ЭХО?</b>\n\n"
        f"Подтверждённых участников: <b>{len(eligible)}</b> · цель: <b>{target}</b>.\n"
        "Событие длится 6 часов, запускается не чаще раза в 7 дней, не выдаёт валюту, силу или личные уведомления.",
        reply_markup=builder.as_markup(), parse_mode="HTML",
    )


@router.callback_query(EchoStartCB.filter())
async def cb_echo_start(
    query: types.CallbackQuery, callback_data: EchoStartCB, db,
    bot: Bot, developer_id: int = 0,
):
    message = getattr(query, "message", None)
    chat = getattr(message, "chat", None)
    if message is None or chat is None or getattr(chat, "type", "private") == "private":
        return await query.answer("Эхо запускается только в групповом чате.", show_alert=True)
    if int(query.from_user.id) != int(callback_data.user_id):
        return await query.answer("Это подтверждение принадлежит другому администратору.", show_alert=True)
    if callback_data.action == "cancel":
        await message.edit_text("◉ Запуск Эха отменён. Состояние чата не изменилось.")
        return await query.answer()
    if callback_data.action != "confirm":
        return await query.answer("Неизвестное действие.", show_alert=True)
    chat_id = int(chat.id)
    if not await _is_admin(bot, int(query.from_user.id), chat_id, developer_id):
        return await query.answer("Права Telegram-администратора больше не подтверждаются.", show_alert=True)
    eligible = await _eligible_snapshot(bot, db, chat_id)
    try:
        view = await echo.start(
            db, chat_id=chat_id, admin_id=int(query.from_user.id),
            eligible_user_ids=eligible,
        )
    except echo.EchoError as exc:
        return await query.answer(str(exc), show_alert=True)
    try:
        sent = await message.answer(
            _text(view), reply_markup=_keyboard(view["event_id"]), parse_mode="HTML"
        )
    except Exception:
        await echo.abort_unpublished(db, view["event_id"], chat_id)
        raise
    try:
        await echo.bind_message(db, view["event_id"], chat_id, int(sent.message_id))
    except Exception:
        await echo.abort_unpublished(db, view["event_id"], chat_id)
        try:
            await sent.edit_text("◉ Эхо не было запущено из-за ошибки публикации.", reply_markup=None)
        except Exception:
            pass
        raise
    await message.edit_text("◉ Эхо запущено. Основное сообщение опубликовано ниже.")
    await query.answer("Эхо запущено")


@router.callback_query(EchoCB.filter())
async def cb_echo(query: types.CallbackQuery, callback_data: EchoCB, db, bot: Bot):
    message = getattr(query, "message", None)
    chat = getattr(message, "chat", None)
    if message is None or chat is None or getattr(chat, "type", "private") == "private" or query.from_user.is_bot:
        return await query.answer("Эхо работает только для участников группового чата.", show_alert=True)
    try:
        member = await bot.get_chat_member(int(chat.id), int(query.from_user.id))
        if member.status not in {"member", "administrator", "creator", "restricted"}:
            raise echo.EchoForbidden("Ты больше не состоишь в этом чате.")
        view = await echo.contribute(
            db, event_id=int(callback_data.event_id), chat_id=int(chat.id),
            user_id=int(query.from_user.id), symbol_id=callback_data.symbol_id,
        )
    except echo.EchoError as exc:
        return await query.answer(str(exc), show_alert=True)
    except Exception:
        return await query.answer("Не удалось подтвердить членство. Попробуй позже.", show_alert=True)
    try:
        await message.edit_text(
            _text(view), reply_markup=_keyboard(
                view["event_id"], disabled=view.get("status") == "completed"
            ), parse_mode="HTML",
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    await query.answer("Твой знак уже учтён" if view.get("idempotent_replay") else "Знак принят")
