"""Update dispatcher — routes incoming Telegram updates to handlers."""
from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async

from .client import (
    answer_callback_query,
    edit_message_reply_markup,
    edit_message_text,
    send_message_async,
    set_bot_commands,
)
from .handlers import (
    handle_admin,
    handle_cancel,
    handle_echo,
    handle_help,
    handle_id,
    handle_link,
    handle_new_channel_member,
    handle_start,
    handle_status,
    handle_unlink_ask,
    handle_unlink_yes,
)

logger = logging.getLogger(__name__)

# ── Text command → handler ─────────────────────────────────────────────────
COMMANDS = {
    "/start":  handle_start,
    "/help":   handle_help,
    "/link":   handle_link,
    "/id":     handle_id,
    "/status": handle_status,
    "/unlink": handle_unlink_ask,
    "/admin":  handle_admin,
}

# ── Callback data → handler ────────────────────────────────────────────────
CALLBACKS = {
    "cb:link":       handle_link,
    "cb:help":       handle_help,
    "cb:status":     handle_status,
    "cb:new_code":   handle_link,        # re-generate code
    "cb:unlink_ask": handle_unlink_ask,
    "cb:unlink_yes": handle_unlink_yes,
    "cb:cancel":     handle_cancel,
}


async def _get_user(chat_id: int):
    def _q():
        from users.models import User
        return User.objects.filter(telegram_chat_id=chat_id).first()
    return await sync_to_async(_q)()


async def process_incoming_update(update: dict[str, Any]) -> bool:
    """
    Process one Telegram update.

    Handles:
      - message / edited_message  → text commands + echo
      - callback_query            → InlineKeyboard button presses
      - chat_member               → welcome new channel members
    """

    # ── 0. New channel/group member ─────────────────────────────────────────
    chat_member_update = update.get("chat_member")
    if chat_member_update:
        chat_info   = chat_member_update.get("chat") or {}
        chat_id     = chat_info.get("id")
        chat_title  = chat_info.get("title") or ""
        old_status  = (chat_member_update.get("old_chat_member") or {}).get("status", "")
        new_member  = chat_member_update.get("new_chat_member") or {}
        new_status  = new_member.get("status", "")

        # Only greet genuine joins (left/kicked → member/administrator)
        joined = new_status in ("member", "administrator") and old_status in ("left", "kicked")
        if chat_id and joined:
            try:
                await handle_new_channel_member(
                    chat_id=chat_id,
                    new_member=new_member,
                    channel_title=chat_title,
                )
            except Exception as exc:
                logger.exception("handle_new_channel_member raised: %s", exc)
        return True

    # ── 1. InlineKeyboard button press ──────────────────────────────────────
    callback = update.get("callback_query")
    if callback:
        cb_id      = callback.get("id")
        cb_data    = (callback.get("data") or "").strip()
        cb_msg     = callback.get("message") or {}
        chat_id    = (cb_msg.get("chat") or {}).get("id")
        message_id = cb_msg.get("message_id")

        if not chat_id:
            return False

        # !! ACK IMMEDIATELY — Telegram times out answerCallbackQuery after 5s.
        # Any DB query before this call risks hitting that timeout and leaving
        # the button in a permanent loading state for the user.
        handler = CALLBACKS.get(cb_data)
        if handler:
            await answer_callback_query(cb_id)
        else:
            # B3-11: информативный fallback вместо generic "неизвестное действие"
            logger.warning("Unknown callback_data=%r from chat=%s", cb_data, chat_id)
            await answer_callback_query(
                cb_id,
                "⚠️ Кнопка устарела. Используй /start для обновления меню.",
                show_alert=True,
            )
            return True

        # Now do the DB lookup and run the handler
        try:
            user_db = await _get_user(chat_id)
        except Exception as exc:
            logger.exception("_get_user failed for chat %s: %s", chat_id, exc)
            await send_message_async("⚠️ Временная ошибка БД. Попробуй через несколько секунд.", chat_id=chat_id)
            return False

        try:
            text, markup = await handler(chat_id, cb_data, user_db)
        except Exception as exc:
            logger.exception("Callback handler %s raised: %s", cb_data, exc)
            await send_message_async("⚠️ Ошибка. Попробуй позже.", chat_id=chat_id)
            return False

        # Edit the existing message in-place if possible, else send new
        try:
            edited = await edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=markup,
            )
        except Exception:
            edited = False
        if not edited:
            await send_message_async(text, chat_id=chat_id, reply_markup=markup)

        return True

    # ── 2. Regular message ──────────────────────────────────────────────────
    message = update.get("message") or update.get("edited_message") or {}
    chat    = message.get("chat") or {}
    chat_id = chat.get("id")
    text    = (message.get("text") or "").strip()

    if not chat_id:
        return False

    # ── 2a. Service message: new members joined the group ──────────────────
    # Telegram sends this even when the bot is NOT an admin —
    # this is the reliable fallback for group welcome messages.
    new_chat_members = message.get("new_chat_members")
    if new_chat_members:
        chat_title = chat.get("title") or ""
        for member in new_chat_members:
            if member.get("is_bot"):
                continue  # skip other bots (including ourselves)
            new_member_obj = {"user": member, "status": "member"}
            try:
                await handle_new_channel_member(
                    chat_id=chat_id,
                    new_member=new_member_obj,
                    channel_title=chat_title,
                )
            except Exception as exc:
                logger.exception("handle_new_channel_member (service msg) raised: %s", exc)
        return True

    # In groups and supergroups, only respond to explicit bot commands ("/...").
    # Responding to every plain message there would spam the entire chat.
    chat_type = chat.get("type", "private")
    is_group   = chat_type in ("group", "supergroup", "channel")

    user_db = await _get_user(chat_id)

    # Match command (strip @botname suffix)
    handler = None
    for cmd, fn in COMMANDS.items():
        if text.lower().split("@")[0].startswith(cmd):
            handler = fn
            break

    if handler is None:
        if not text or is_group:
            return False   # never echo in groups
        handler = handle_echo

    try:
        reply_text, markup = await handler(chat_id, text, user_db)
    except Exception as exc:
        logger.exception("Handler %s raised: %s", handler.__name__, exc)
        reply_text, markup = "⚠️ Внутренняя ошибка. Попробуй позже.", None

    if reply_text:
        return await send_message_async(reply_text, chat_id=chat_id, reply_markup=markup)
    return False


async def init_bot_commands() -> bool:
    """Register bot commands in Telegram so the / menu shows nicely."""
    commands = [
        {"command": "start",  "description": "Главное меню"},
        {"command": "link",   "description": "Привязать аккаунт"},
        {"command": "status", "description": "Мой статус членства"},
        {"command": "help",   "description": "Справка и описание функций"},
        {"command": "unlink", "description": "Отвязать Telegram от аккаунта"},
        {"command": "id",     "description": "Мой Telegram chat ID"},
    ]
    return await set_bot_commands(commands)
