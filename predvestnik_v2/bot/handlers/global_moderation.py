# bot/handlers/global_moderation.py
# Глобальная модерация экосистемы бота: варны/ограничения/баны + апелляции (Implementation Block 6.6).
# Команды работают в любом чате И в личных сообщениях.

from datetime import datetime, timedelta

from aiogram import Router, types, Bot

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
    ok, msg, sanction_id = await global_moderation.issue_global_sanction(
        db, bot, message.from_user.id, actor_rank, "user", target_id,
        "warn", reason or None, target_global_rank=target_rank,
        photos_json=_reply_photos_json(message),
    )
    suffix = f"\n👤 Цель: {_target_link(target_id, target_name)}" if ok else ""
    await message.answer(msg + suffix, parse_mode="HTML")
    if ok:
        await _after_sanction(message, db, target_id, sanction_id)


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
    ok, msg, sanction_id = await global_moderation.issue_global_sanction(
        db, bot, message.from_user.id, actor_rank, "user", target_id,
        "restrict", reason, expires_at=expires_at, target_global_rank=target_rank,
        photos_json=_reply_photos_json(message),
    )
    suffix = f"\n👤 Цель: {_target_link(target_id, target_name)}" if ok else ""
    await message.answer(msg + suffix, parse_mode="HTML")
    if ok:
        await _after_sanction(message, db, target_id, sanction_id)


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
    ok, msg, sanction_id = await global_moderation.issue_global_sanction(
        db, bot, message.from_user.id, actor_rank, "user", target_id,
        "ban", reason, expires_at=expires_at, target_global_rank=target_rank,
        photos_json=_reply_photos_json(message),
    )
    suffix = f"\n👤 Цель: {_target_link(target_id, target_name)}" if ok else ""
    await message.answer(msg + suffix, parse_mode="HTML")
    if ok:
        await _after_sanction(message, db, target_id, sanction_id)


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

    ok, msg, _sid = await global_moderation.issue_global_sanction(
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


# ── admin_audit B1: фото-доказательства и панель каналов уведомления ─────────

def _reply_photos_json(message: types.Message) -> str:
    """Фото-доказательство к санкции: команда, отправленная ОТВЕТОМ на фото,
    прикрепляет его file_id к санкции (видно в истории дел на сайте)."""
    import json as _json
    rt = message.reply_to_message
    if rt and rt.photo:
        return _json.dumps([rt.photo[-1].file_id])
    return "[]"


async def _after_sanction(message: types.Message, db, target_id: int, sanction_id: int):
    """После выдачи санкции юзеру: (1) ЛС-инструкция нарушителю — всегда;
    (2) панель выбора каналов уведомления сообществу (admin_audit B1)."""
    sanction = await global_mod_repo.get_sanction_by_id(db, sanction_id)
    dm_ok = await global_moderation.send_appeal_instruction(db, target_id, sanction or {})
    dm_note = ("📨 Инструкция по апелляции выслана нарушителю в ЛС." if dm_ok
               else "⚠️ ЛС нарушителя закрыты — инструкция не доставлена (увидит на сайте).")
    cur_title = safe_html(message.chat.title or str(message.chat.id))
    kb = {"inline_keyboard": [
        [{"text": "📣 Уведомить ВСЕ чаты игрока", "callback_data": f"sn:{sanction_id}:all"}],
        [{"text": f"📍 Только этот чат ({cur_title[:20]})",
          "callback_data": f"sn:{sanction_id}:{message.chat.id}"}],
        [{"text": "🔕 Не уведомлять чаты", "callback_data": f"sn:{sanction_id}:skip"}],
    ]}
    await message.answer(
        f"{dm_note}\n\n<b>Уведомить сообщество о санкции?</b>\n"
        f"<i>Текущий чат: {cur_title}</i>",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(**kb),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("sn:"))
async def cb_sanction_notify(callback: types.CallbackQuery, db):
    """Выбор каналов уведомления о санкции. Жмёт модерация (ранг ≥1)."""
    actor_rank = await get_global_rank(db, callback.from_user.id)
    if actor_rank < 1:
        return await callback.answer("Только для глобальной модерации.", show_alert=True)
    try:
        _, sid, mode = callback.data.split(":")
        sanction_id = int(sid)
    except (IndexError, ValueError):
        return await callback.answer("Ошибка данных.", show_alert=True)
    if mode == "skip":
        await callback.answer("Уведомления не отправлены.")
        try:
            await callback.message.edit_text(
                (callback.message.html_text or "") + "\n\n🔕 <b>Без уведомлений.</b>",
                parse_mode="HTML")
        except Exception:
            pass
        return
    targets = "all" if mode == "all" else [int(mode)]
    sent = await global_moderation.send_sanction_notices(db, sanction_id, targets)
    await callback.answer(f"📣 Уведомлено чатов: {sent}")
    try:
        await callback.message.edit_text(
            (callback.message.html_text or "") + f"\n\n📣 <b>Уведомлено чатов: {sent}.</b>",
            parse_mode="HTML")
    except Exception:
        pass


# ==========================================
# АПЕЛЛЯЦИИ 2.0 (admin_audit B1): диалог до закрытия, фото, статусы
# ==========================================
@router.message(TextCmd(["апелляция ответ", "ответ апелляция"]))
async def cmd_appeal_reply(message: types.Message, db, bot: Bot, text_args: str = None):
    """Модерация (ранг ≥1): «бот апелляция ответ, ID|@юзер, текст».
    Фото — отправьте команду ОТВЕТОМ на фото."""
    actor_rank = await get_global_rank(db, message.from_user.id)
    if actor_rank < 1:
        return
    args = (text_args or "").strip()
    head, _, body = args.partition(",")
    head, body = head.strip(), body.strip()
    if not head or not body:
        return await message.answer(
            "ℹ️ <code>бот апелляция ответ, ID_апелляции, текст</code>\n"
            "(или @юзер вместо ID — возьмётся его открытая апелляция)\n"
            "<i>Фото: отправьте команду ответом на фото. Список: "
            "<code>бот апелляции</code></i>",
            parse_mode="HTML")
    appeal_id = await _resolve_appeal_id(message, db, head)
    if not appeal_id:
        return await message.answer("❌ Открытая апелляция не найдена.", parse_mode="HTML")
    photos = []
    if message.reply_to_message and message.reply_to_message.photo:
        photos = [message.reply_to_message.photo[-1].file_id]
    ok, msg = await global_moderation.staff_reply_appeal(
        db, appeal_id, message.from_user.id, body, photos)
    await message.answer(
        msg + ("\n<i>Закрыть дело: <code>бот апелляция закрыть, "
               f"{appeal_id}, решение</code></i>" if ok else ""),
        parse_mode="HTML")


@router.message(TextCmd(["апелляция закрыть", "закрыть апелляцию"]))
async def cmd_appeal_close(message: types.Message, db, bot: Bot, text_args: str = None):
    """Модерация: закрыть дело. «бот апелляция закрыть, ID|@юзер[, решение]»."""
    actor_rank = await get_global_rank(db, message.from_user.id)
    if actor_rank < 1:
        return
    args = (text_args or "").strip()
    head, _, resolution = args.partition(",")
    head = head.strip()
    if not head:
        return await message.answer(
            "ℹ️ <code>бот апелляция закрыть, ID_апелляции[, решение]</code>",
            parse_mode="HTML")
    appeal_id = await _resolve_appeal_id(message, db, head)
    if not appeal_id:
        return await message.answer("❌ Открытая апелляция не найдена.", parse_mode="HTML")
    ok, msg = await global_moderation.close_appeal(
        db, appeal_id, message.from_user.id, resolution.strip() or None)
    await message.answer(msg, parse_mode="HTML")


@router.message(TextCmd(["апелляции", "список апелляций"]))
async def cmd_appeals_list(message: types.Message, db):
    """Модерация: открытые апелляции с подсказками действий."""
    actor_rank = await get_global_rank(db, message.from_user.id)
    if actor_rank < 1:
        return
    rows = await global_mod_repo.list_appeals(db, "pending")
    if not rows:
        return await message.answer("📭 Открытых апелляций нет.", parse_mode="HTML")
    lines = ["📨 <b>ОТКРЫТЫЕ АПЕЛЛЯЦИИ:</b>\n"]
    for a in rows[:20]:
        lines.append(f"#{a['id']} от <code>{a['user_id']}</code> · санкция #{a['sanction_id']}\n"
                     f"   <i>{safe_html((a['text'] or '')[:80])}</i>")
    lines.append("\n<i>Ответить: <code>бот апелляция ответ, ID, текст</code> · "
                 "Закрыть: <code>бот апелляция закрыть, ID, решение</code> · "
                 "полные диалоги — на сайте (Глобальная модерация)</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")


async def _resolve_appeal_id(message: types.Message, db, head: str) -> int | None:
    """ID апелляции: число = ID; @юзер/reply = его открытая апелляция."""
    if head.isdigit():
        appeal = await global_mod_repo.get_appeal_by_id(db, int(head))
        if appeal:
            return int(head)
        # число могло быть Telegram ID юзера
    target_id, _tn, _r = await resolve_target(message, db, head)
    if target_id:
        appeal = await global_mod_repo.get_open_appeal(db, target_id)
        if appeal:
            return appeal["id"]
    return None


@router.message(TextCmd(["апелляция"]))
async def cmd_appeal(message: types.Message, db, bot: Bot, text_args: str = None, developer_id: int = 0):
    """Игрок: подать апелляцию ИЛИ дописать в открытую (диалог до закрытия).
    Фото: отправьте фото с подписью «бот апелляция, текст» (в ЛС бота)."""
    text = (text_args or "").strip()
    if not text:
        st = await global_mod_repo.get_open_appeal(db, message.from_user.id)
        if st:
            thread = await global_mod_repo.appeal_thread(db, st["id"])
            tail = "\n".join(
                f"{'👮' if m['is_staff'] else '🙋'} {safe_html((m['text'] or '(фото)')[:100])}"
                for m in thread[-5:])
            return await message.answer(
                f"📨 <b>Ваша апелляция #{st['id']}</b> (открыта)\n{tail}\n\n"
                f"<i>Дописать: <code>бот апелляция, текст</code> · фото — с подписью</i>",
                parse_mode="HTML")
        return await message.answer(
            "ℹ️ <b>Использование:</b> <code>бот апелляция, текст обращения</code>\n"
            "<i>Можно приложить фото: отправьте фото с этой подписью (в ЛС бота).</i>",
            parse_mode="HTML")

    ok, msg, appeal_id = await global_moderation.appeal_add_message(
        db, message.from_user.id, text)
    await message.answer(
        msg + ("\n<i>Статус диалога: <code>бот апелляция</code> (без текста)</i>" if ok else ""),
        parse_mode="HTML")
    if ok:
        await global_moderation.notify_staff_about_appeal(
            db, appeal_id, message.from_user.id, text, developer_id)


@router.message(lambda m: m.chat.type == "private" and m.photo)
async def dm_appeal_photo(message: types.Message, db, bot: Bot, developer_id: int = 0):
    """Фото в ЛС бота: прикрепляется к апелляции (открытой или создаёт новую при
    активной санкции). Подпись — текст сообщения. Без санкции/апелляции — подсказка."""
    caption = (message.caption or "").strip()
    # обрезаем «бот апелляция» из подписи, если игрок написал по инструкции
    low = caption.lower()
    for pref in ("бот апелляция,", "бот апелляция"):
        if low.startswith(pref):
            caption = caption[len(pref):].strip()
            break
    has_open = await global_mod_repo.get_open_appeal(db, message.from_user.id)
    has_sanction = await global_mod_repo.get_active_sanction_for_user(db, message.from_user.id)
    if not has_open and not has_sanction:
        return  # не наш кейс (например, дев шлёт стикеры/картинки) — молчим
    photo_id = message.photo[-1].file_id
    ok, msg, appeal_id = await global_moderation.appeal_add_message(
        db, message.from_user.id, caption, [photo_id])
    await message.answer(
        ("📷 " + msg) if ok else msg, parse_mode="HTML")
    if ok:
        await global_moderation.notify_staff_about_appeal(
            db, appeal_id, message.from_user.id, caption or "(фото)", developer_id)
