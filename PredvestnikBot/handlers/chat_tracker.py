"""
handlers/chat_tracker.py — Реактивный трекинг присутствия пользователей в чатах.

Отслеживает ChatMemberUpdated-события и поддерживает таблицу user_chats:
  • Пользователь вступил в чат (JOIN) → добавить запись
  • Пользователь вышел / был кикнут / забанен (LEAVE) → удалить запись
  • Бот добавлен в чат (bot added) → синхронизировать существующих участников (best effort)
  • Бот удалён из чата (bot removed) → очистить user_chats для этого chat_id

Важно: для работы требуется подписка на update-тип «chat_member» (см. allowed_updates в main.py).
"""

import logging

from aiogram import Router
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION
from aiogram.types import ChatMemberUpdated

router = Router()
log = logging.getLogger(__name__)

# ─── Вспомогательная функция ──────────────────────────────────────────────────

def _is_active_member(status: str) -> bool:
    """Статусы, при которых пользователь считается «в чате»."""
    return status in ("member", "administrator", "creator", "restricted")


# ─── Пользователь вступил в чат ───────────────────────────────────────────────

@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def on_user_join(event: ChatMemberUpdated) -> None:
    """Зафиксировать вступление пользователя в чат."""
    user = event.new_chat_member.user
    if user.is_bot:
        return

    from database.db import upsert_user, upsert_user_chat

    try:
        await upsert_user(user.id, user.username or "", user.full_name or "")
        await upsert_user_chat(user.id, event.chat.id)
        log.debug("chat_tracker: +%d in %d", user.id, event.chat.id)
    except Exception as exc:
        log.warning("chat_tracker on_user_join(%d, %d): %s", user.id, event.chat.id, exc)


# ─── Пользователь покинул чат (выход / кик / бан) ────────────────────────────

@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=LEAVE_TRANSITION))
async def on_user_leave(event: ChatMemberUpdated) -> None:
    """Удалить запись о нахождении пользователя в чате."""
    user = event.old_chat_member.user
    if user.is_bot:
        return

    from database.db import remove_user_chat

    try:
        await remove_user_chat(user.id, event.chat.id)
        log.debug("chat_tracker: -%d from %d", user.id, event.chat.id)
    except Exception as exc:
        log.warning("chat_tracker on_user_leave(%d, %d): %s", user.id, event.chat.id, exc)


# ─── Бот удалён из чата ───────────────────────────────────────────────────────

@router.my_chat_member()
async def on_bot_chat_member_updated(event: ChatMemberUpdated) -> None:
    """
    Обрабатывает изменение статуса самого бота в чате.
    Когда бота кикают/удаляют — очищаем user_chats для этого чата,
    т.к. бот больше не отслеживает его участников.
    """
    new_status = event.new_chat_member.status
    # "kicked", "left", "banned" — бот удалён
    if new_status in ("kicked", "left", "banned"):
        chat_id = event.chat.id
        from database.postgres import connect as postgres_connect
        try:
            async with postgres_connect() as db:
                await db.execute(
                    "DELETE FROM user_chats WHERE chat_id = ?",
                    (chat_id,),
                )
                await db.commit()
            log.info("chat_tracker: bot removed from %d — cleared user_chats", chat_id)
        except Exception as exc:
            log.warning("chat_tracker on_bot_removed(%d): %s", chat_id, exc)
