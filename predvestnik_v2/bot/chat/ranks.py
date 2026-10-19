"""Локальные ранги чата (10 ступеней) и права по рангам.

Владелец (9) всегда один и берётся из Telegram. Разработчик бота стоит выше
всех рангов (DEV_LEVEL) и не может быть целью санкций.
"""
from __future__ import annotations

import time

from aiogram import Bot
from loguru import logger

from bot.chat.access import is_developer

from core.chat_rank_policy import (RANKS, OWNER, DEV_LEVEL, rank_name, find_rank, Action, ACTIONS, ACTION_BY_KEY)
from infrastructure.repositories import chat_rank_rights as rights_repo


async def rights_map(db, chat_id: int) -> dict[str, int]:
    return await rights_repo.read(db, chat_id)


async def set_right(db, chat_id: int, action: str, min_rank: int, actor_id: int) -> None:
    if action not in ACTION_BY_KEY or type(min_rank) is not int or not 0 <= min_rank <= OWNER:
        raise ValueError("Некорректное право или ранг.")
    async with db.connection.transaction():
        await rights_repo.lock(db, chat_id)
        # The permission may have been revoked by the web editor while this
        # callback was waiting. Authorize again under the shared write lock.
        if not await can(db, chat_id, actor_id, "rights"):
            raise PermissionError("Нет права менять права рангов.")
        if action == "rights" and min_rank < OWNER and not is_developer(actor_id) \
                and await get_rank(db, chat_id, actor_id) < OWNER:
            raise PermissionError("Передать право настройки может только владелец.")
        await rights_repo.write(db, chat_id, {action: min_rank}, actor_id)
    await _commit(db)


_owner_checked: dict[int, float] = {}
_OWNER_TTL = 3600.0


async def sync_owner(db, bot: Bot, chat_id: int, *, force: bool = False) -> int | None:
    """Владелец из Telegram -> chat_settings.owner_id (не чаще раза в час)."""
    now = time.monotonic()   # отсчёт идёт от запуска сервера: в первый час «0» не должно означать «только что проверяли»
    last = _owner_checked.get(chat_id)
    if not force and last is not None and now - last < _OWNER_TTL:
        return await get_owner(db, chat_id)
    try:
        admins = await bot.get_chat_administrators(chat_id)
    except Exception:
        _owner_checked[chat_id] = now - _OWNER_TTL + 60   # сбой Telegram: повторим через минуту, а не через час
        return await get_owner(db, chat_id)
    _owner_checked[chat_id] = now
    try:
        from services import chat_bots   # боты-администраторы (другие модераторы, сам Предвестник) — не участники для чистки и топов
        await chat_bots.admin_bots(bot, db, chat_id, admins)
    except Exception as exc:   # пометка ботов не должна мешать узнать владельца
        logger.warning(f"admin bots not marked for {chat_id}: {exc}")
    owner = next((a.user.id for a in admins if a.status == "creator"), None)
    if owner:
        await set_owner(db, chat_id, owner)
    return await get_owner(db, chat_id)   # владелец, назначенный разработчиком, важнее телеграмного


async def set_owner(db, chat_id: int, owner_id: int) -> None:
    await db.execute(
        "INSERT INTO chat_settings (chat_id, owner_id) VALUES (?, ?) "
        "ON CONFLICT (chat_id) DO UPDATE SET owner_id = EXCLUDED.owner_id",
        (chat_id, owner_id),
    )
    await _commit(db)


async def get_owner(db, chat_id: int) -> int | None:
    async with db.execute("SELECT COALESCE(owner_override, owner_id) FROM chat_settings WHERE chat_id = ?",
                          (chat_id,)) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row and row[0] else None


async def set_owner_override(db, chat_id: int, user_id: int | None) -> None:
    """Владелец чата в боте, назначенный разработчиком (None — снова как в Telegram)."""
    await db.execute(
        "INSERT INTO chat_settings (chat_id, owner_override) VALUES (?, ?) "
        "ON CONFLICT (chat_id) DO UPDATE SET owner_override = EXCLUDED.owner_override", (chat_id, user_id))
    await _commit(db)


async def get_rank(db, chat_id: int, user_id: int) -> int:
    if is_developer(user_id):
        return DEV_LEVEL
    if await get_owner(db, chat_id) == user_id:
        return OWNER
    # Ранги начаты с нуля (решение владельца бота): старая колонка local_rank
    # не читается, NULL в chat_rank = «Участник».
    async with db.execute(
        "SELECT chat_rank FROM user_chat_stats WHERE chat_tg_id = ? AND user_tg_id = ?",
        (chat_id, user_id),
    ) as cur:
        row = await cur.fetchone()
    rank = int(row[0]) if row and row[0] is not None else 0
    return min(rank, OWNER - 1)   # владелец только через Telegram


async def can(db, chat_id: int, user_id: int, action: str) -> bool:
    if is_developer(user_id):
        return True
    need = (await rights_map(db, chat_id))[action]
    return await get_rank(db, chat_id, user_id) >= need


async def store_rank(db, chat_id: int, user_id: int, rank: int) -> None:
    async with db.connection.transaction():
        await rights_repo.lock(db, chat_id)
        await db.execute(
            "INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, chat_rank) VALUES (?, ?, ?) "
            "ON CONFLICT (user_tg_id, chat_tg_id) DO UPDATE SET chat_rank = EXCLUDED.chat_rank",
            (user_id, chat_id, rank),
        )
    await _commit(db)


def check_assign(actor_rank: int, target_rank: int, new_rank: int) -> str | None:
    """Причина отказа или None. Ранги выдаются только ниже своего."""
    if actor_rank >= DEV_LEVEL:   # разработчику бота можно всё, и назначить владельца тоже
        return None
    if new_rank >= OWNER:
        return "Владелец назначается только через Telegram — передачей прав на группу."
    if target_rank >= actor_rank:
        return "Нельзя менять ранг тому, чей ранг не ниже вашего."
    if new_rank >= actor_rank:
        return "Можно выдать только ранг ниже вашего."
    return None


async def _commit(db) -> None:
    commit = getattr(db, "commit", None)
    if commit:
        await commit()


async def assign_rank(db, chat_id, user_id, new_rank, actor_id, *, expected_rank):
    """Authorize the final assignment after any wait for the web/Telegram lock."""
    if type(new_rank) is not int or not 0<=new_rank<=OWNER:
        raise PermissionError('Неизвестный ранг.')
    async with db.connection.transaction():
        await rights_repo.lock(db,chat_id)
        if not await can(db,chat_id,actor_id,'set_rank'):
            raise PermissionError('У вашего ранга нет права выдавать ранги.')
        if is_developer(user_id) and not is_developer(actor_id):
            raise PermissionError('Ранг разработчика бота изменить нельзя.')
        actor_rank=await get_rank(db,chat_id,actor_id)
        target_rank=await get_rank(db,chat_id,user_id)
        if target_rank!=expected_rank:raise PermissionError('Ранг игрока уже изменился. Повторите команду.')
        reason=check_assign(actor_rank,target_rank,new_rank)
        if reason:raise PermissionError(reason)
        if new_rank>=OWNER:
            await rights_repo.owner_override(db,chat_id,user_id)
        else:
            if target_rank>=OWNER and not is_developer(user_id):
                await rights_repo.owner_override(db,chat_id,None)
            await rights_repo.store_member(db,chat_id,user_id,new_rank)
    await _commit(db)
