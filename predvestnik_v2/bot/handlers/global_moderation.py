# bot/handlers/global_moderation.py
# Глобальная модерация экосистемы бота: варны/ограничения/баны + апелляции (Implementation Block 6.6).
# Команды работают в любом чате И в личных сообщениях.

from datetime import datetime, timedelta

from aiogram import Router, types, Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot.filters.text_commands import TextCmd
from bot.handlers.moderation import parse_time
from infrastructure.repositories import global_moderation as global_mod_repo
from infrastructure.repositories.users import get_global_rank
from services import global_moderation
from services.utils import resolve_target, safe_html


router = Router(name="global_moderation_router")

_SANCTION_TITLES = {"warn": "⚠️ Варн", "restrict": "🚫 Ограничение", "ban": "⛔ Бан"}


def _split_reason_and_duration(text: str | None) -> tuple[str | None, timedelta | None]:
    text = (text or "").strip()
    if not text:
        return None, None
    parts = text.split()
    duration = parse_time(parts[-1])
    if duration is not None:
        return (" ".join(parts[:-1]) or None), duration
    return text, None


def _target_link(target_id: int, target_name: str | None) -> str:
    return f'<a href="tg://user?id={target_id}">{safe_html(target_name or str(target_id))}</a>'


def _format_sanctions_list(target_label: str, sanctions: list[dict]) -> str:
    if not sanctions:
        return f"📋 У {target_label} нет глобальных санкций."

    now = datetime.now()
    lines = [f"📋 <b>Глобальные санкции:</b> {target_label}\n"]
    for s in sanctions:
        title = _SANCTION_TITLES.get(s["sanction_type"], s["sanction_type"])
        is_active = s["revoked_at"] is None and (s["expires_at"] is None or s["expires_at"] > now)
        status = "🔴 активна" if is_active else "⚪ неактивна"
        until = "" if not s["expires_at"] else f" до {s['expires_at']:%d.%m.%Y}"
        reason = f" — {safe_html(s['reason'])}" if s["reason"] else ""
        lines.append(f"#{s['id']} {title}{until}{reason} [{status}]")
    return "\n".join(lines)


# ==========================================
# ВАРНЫ
# ==========================================
@router.message(TextCmd(["глоб варн"]))
async def cmd_global_warn(message: types.Message, db, bot: Bot, text_args: str = None):
    actor_rank = await get_global_rank(db, message.from_user.id)
    if actor_rank < 1:
        return

    target_id, target_name, reason = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот глоб варн, @юзер [причина]</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )
    if reason == "error_user_not_found":
        return await message.answer("❌ Пользователь не найден.")

    target_rank = await get_global_rank(db, target_id)
    ok, msg = await global_moderation.issue_global_sanction(
        db, bot, message.from_user.id, actor_rank, "user", target_id,
        "warn", reason or None, target_global_rank=target_rank,
    )
    suffix = f"\n👤 Цель: {_target_link(target_id, target_name)}" if ok else ""
    await message.answer(msg + suffix, parse_mode="HTML")


@router.message(TextCmd(["глоб снять варн"]))
async def cmd_global_unwarn(message: types.Message, db, bot: Bot, text_args: str = None):
    actor_rank = await get_global_rank(db, message.from_user.id)
    if actor_rank < 1:
        return

    args = (text_args or "").strip()
    if not args and not (message.reply_to_message and message.reply_to_message.from_user):
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот глоб снять варн, @юзер</code>\n"
            "(также: ID санкции, Telegram ID или ответом на сообщение)\n"
            "<i>Снимается последний активный варн цели. "
            "История: <code>бот глоб санкции, @юзер</code></i>",
            parse_mode="HTML",
        )

    # admin_audit C3: принимаем и числовой ID санкции (легаси), и @username/
    # Telegram ID/reply — тогда ревокаем ПОСЛЕДНИЙ активный варн цели.
    sanction_id = None
    if args.isdigit():
        # число может быть и ID санкции, и Telegram ID юзера — сначала пробуем
        # как ID санкции (легаси), при промахе трактуем как юзера
        _s = await global_mod_repo.get_sanction_by_id(db, int(args))
        if _s:
            sanction_id = int(args)
    if sanction_id is None:
        target_id, target_name, _rest = await resolve_target(message, db, args)
        if not target_id:
            return await message.answer(
                "❌ Пользователь (или санкция с таким ID) не найден.", parse_mode="HTML")
        sanction_id = await global_mod_repo.get_last_active_warn_id(db, target_id)
        if not sanction_id:
            return await message.answer(
                f"ℹ️ У <b>{safe_html(target_name)}</b> нет активных глобальных варнов.\n"
                f"<i>История: <code>бот глоб санкции, @юзер</code></i>",
                parse_mode="HTML",
            )

    ok, msg = await global_moderation.revoke_global_sanction(db, bot, message.from_user.id, actor_rank, sanction_id)
    await message.answer(msg, parse_mode="HTML")


# ==========================================
# ОГРАНИЧЕНИЯ
# ==========================================
@router.message(TextCmd(["глоб ограничить"]))
async def cmd_global_restrict(message: types.Message, db, bot: Bot, text_args: str = None):
    actor_rank = await get_global_rank(db, message.from_user.id)
    if actor_rank < 1:
        return

    target_id, target_name, rest = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот глоб ограничить, @юзер [причина] [10м/2ч/1д]</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )
    if rest == "error_user_not_found":
        return await message.answer("❌ Пользователь не найден.")

    reason, duration = _split_reason_and_duration(rest)
    expires_at = (datetime.now() + duration) if duration else None

    target_rank = await get_global_rank(db, target_id)
    ok, msg = await global_moderation.issue_global_sanction(
        db, bot, message.from_user.id, actor_rank, "user", target_id,
        "restrict", reason, expires_at=expires_at, target_global_rank=target_rank,
    )
    suffix = f"\n👤 Цель: {_target_link(target_id, target_name)}" if ok else ""
    await message.answer(msg + suffix, parse_mode="HTML")


@router.message(TextCmd(["глоб снять ограничение"]))
async def cmd_global_unrestrict(message: types.Message, db, bot: Bot, text_args: str = None):
    actor_rank = await get_global_rank(db, message.from_user.id)
    if actor_rank < 1:
        return

    target_id, target_name, rest = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот глоб снять ограничение, @юзер</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )
    if rest == "error_user_not_found":
        return await message.answer("❌ Пользователь не найден.")

    restriction = await global_mod_repo.get_active_restriction(db, "user", target_id)
    if not restriction or restriction["sanction_type"] != "restrict":
        return await message.answer(f"ℹ️ У {_target_link(target_id, target_name)} нет активного ограничения.", parse_mode="HTML")

    ok, msg = await global_moderation.revoke_global_sanction(db, bot, message.from_user.id, actor_rank, restriction["id"])
    await message.answer(msg, parse_mode="HTML")


# ==========================================
# БАНЫ (ПОЛЬЗОВАТЕЛЬ) — доступно только Главному разработчику (RANK_ALLOWED)
# ==========================================
@router.message(TextCmd(["глоб бан"]))
async def cmd_global_ban(message: types.Message, db, bot: Bot, text_args: str = None):
    actor_rank = await get_global_rank(db, message.from_user.id)
    if actor_rank < 1:
        return

    target_id, target_name, rest = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот глоб бан, @юзер [причина] [10м/2ч/1д]</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )
    if rest == "error_user_not_found":
        return await message.answer("❌ Пользователь не найден.")

    reason, duration = _split_reason_and_duration(rest)
    expires_at = (datetime.now() + duration) if duration else None

    target_rank = await get_global_rank(db, target_id)
    ok, msg = await global_moderation.issue_global_sanction(
        db, bot, message.from_user.id, actor_rank, "user", target_id,
        "ban", reason, expires_at=expires_at, target_global_rank=target_rank,
    )
    suffix = f"\n👤 Цель: {_target_link(target_id, target_name)}" if ok else ""
    await message.answer(msg + suffix, parse_mode="HTML")


@router.message(TextCmd(["глоб разбан"]))
async def cmd_global_unban(message: types.Message, db, bot: Bot, text_args: str = None):
    actor_rank = await get_global_rank(db, message.from_user.id)
    if actor_rank < 1:
        return

    target_id, target_name, rest = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот глоб разбан, @юзер</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )
    if rest == "error_user_not_found":
        return await message.answer("❌ Пользователь не найден.")

    restriction = await global_mod_repo.get_active_restriction(db, "user", target_id)
    if not restriction or restriction["sanction_type"] != "ban":
        return await message.answer(f"ℹ️ У {_target_link(target_id, target_name)} нет активного бана.", parse_mode="HTML")

    ok, msg = await global_moderation.revoke_global_sanction(db, bot, message.from_user.id, actor_rank, restriction["id"])
    await message.answer(msg, parse_mode="HTML")


# ==========================================
# БАНЫ (ЧАТ) — доступно только Главному разработчику (RANK_ALLOWED)
# ==========================================
@router.message(TextCmd(["глоб бан чат"]))
async def cmd_global_ban_chat(message: types.Message, db, bot: Bot, text_args: str = None):
    actor_rank = await get_global_rank(db, message.from_user.id)
    if actor_rank < 1:
        return

    args = (text_args or "").strip().split(maxsplit=1)
    if not args or not args[0].lstrip("-").isdigit():
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот глоб бан чат, ID_чата [причина]</code>",
            parse_mode="HTML",
        )
    chat_id = int(args[0])
    reason = args[1] if len(args) > 1 else None

    ok, msg = await global_moderation.issue_global_sanction(
        db, bot, message.from_user.id, actor_rank, "chat", chat_id, "ban", reason,
    )
    await message.answer(msg, parse_mode="HTML")


@router.message(TextCmd(["глоб разбан чат"]))
async def cmd_global_unban_chat(message: types.Message, db, bot: Bot, text_args: str = None):
    actor_rank = await get_global_rank(db, message.from_user.id)
    if actor_rank < 1:
        return

    args = (text_args or "").strip()
    if not args.lstrip("-").isdigit():
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот глоб разбан чат, ID_чата</code>",
            parse_mode="HTML",
        )
    chat_id = int(args)

    restriction = await global_mod_repo.get_active_restriction(db, "chat", chat_id)
    if not restriction or restriction["sanction_type"] != "ban":
        return await message.answer("ℹ️ У этого чата нет активного бана.")

    ok, msg = await global_moderation.revoke_global_sanction(db, bot, message.from_user.id, actor_rank, restriction["id"])
    await message.answer(msg, parse_mode="HTML")


# ==========================================
# СПИСОК САНКЦИЙ
# ==========================================
@router.message(TextCmd(["глоб санкции чат"]))
async def cmd_global_sanctions_chat(message: types.Message, db, text_args: str = None):
    actor_rank = await get_global_rank(db, message.from_user.id)
    if actor_rank < 1:
        return

    args = (text_args or "").strip()
    if not args.lstrip("-").isdigit():
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот глоб санкции чат, ID_чата</code>",
            parse_mode="HTML",
        )
    chat_id = int(args)
    sanctions = await global_mod_repo.list_sanctions(db, "chat", chat_id)
    await message.answer(_format_sanctions_list(f"чата <code>{chat_id}</code>", sanctions), parse_mode="HTML")


@router.message(TextCmd(["глоб санкции"]))
async def cmd_global_sanctions_user(message: types.Message, db, text_args: str = None):
    actor_rank = await get_global_rank(db, message.from_user.id)
    if actor_rank < 1:
        return

    target_id, target_name, rest = await resolve_target(message, db, text_args)
    if not target_id:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот глоб санкции, @юзер</code>\n"
            "Или ответьте на сообщение пользователя.",
            parse_mode="HTML",
        )
    if rest == "error_user_not_found":
        return await message.answer("❌ Пользователь не найден.")

    sanctions = await global_mod_repo.list_sanctions(db, "user", target_id)
    await message.answer(_format_sanctions_list(_target_link(target_id, target_name), sanctions), parse_mode="HTML")


# ==========================================
# АПЕЛЛЯЦИИ
# ==========================================
@router.message(TextCmd(["апелляция"]))
async def cmd_appeal(message: types.Message, db, bot: Bot, text_args: str = None, developer_id: int = 0):
    text = (text_args or "").strip()
    if not text:
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот апелляция, текст обращения</code>",
            parse_mode="HTML",
        )

    sanction = await global_mod_repo.get_active_sanction_for_user(db, message.from_user.id)
    if not sanction:
        return await message.answer("У тебя нет активных глобальных санкций.")

    appeal_id = await global_mod_repo.create_appeal(db, message.from_user.id, sanction["id"], text)

    if developer_id:
        try:
            await bot.send_message(
                developer_id,
                f"📨 <b>Апелляция #{appeal_id}</b> от <code>{message.from_user.id}</code> "
                f"на санкцию #{sanction['id']}:\n{safe_html(text)}",
                parse_mode="HTML",
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            pass

    await message.answer("✅ Апелляция отправлена. Ответ придёт уведомлением.")
