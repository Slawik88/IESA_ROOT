"""Локальные ранги чата (10 ступеней) и права по рангам.

Владелец (9) всегда один и берётся из Telegram. Разработчик бота стоит выше
всех рангов (DEV_LEVEL) и не может быть целью санкций.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from aiogram import Bot

from bot.chat.access import is_developer

RANKS: tuple[tuple[str, str], ...] = (
    ("👤", "Участник"),
    ("✨", "Активист"),
    ("🧭", "Наставник"),
    ("🔰", "Младший модератор"),
    ("🛡", "Модератор"),
    ("⚔️", "Старший модератор"),
    ("👮", "Администратор"),
    ("🏛", "Управляющий"),
    ("🤝", "Совладелец"),
    ("👑", "Владелец"),
)
OWNER = 9
DEV_LEVEL = 100

# Старая шкала local_rank -> новая (решение владельца бота: перенести).
LEGACY_MAP = {0: 0, 1: 4, 2: 5, 3: 6, 4: 7}


def legacy_rank(old: int | None) -> int:
    old = int(old or 0)
    return LEGACY_MAP.get(old, 8 if old >= 5 else 0)


def rank_name(rank: int) -> str:
    if rank >= DEV_LEVEL:
        return "🛠 Разработчик бота"
    icon, name = RANKS[max(0, min(rank, OWNER))]
    return f"{icon} {name}"


def find_rank(text: str) -> int | None:
    """«5», «модератор», «мл модератор», «ст. модератор» -> номер ранга."""
    t = text.strip().lower().replace("ё", "е").replace(".", " ")
    t = " ".join(t.split())
    if t.isdigit():
        n = int(t)
        return n if 0 <= n <= OWNER else None
    t = t.replace("мл ", "младший ").replace("ст ", "старший ")
    for i, (_, name) in enumerate(RANKS):
        if name.lower() == t:
            return i
    return None


@dataclass(frozen=True)
class Action:
    key: str
    label: str
    default: int


# Всё, что в чате можно ограничить рангом. Владелец меняет пороги командой «бот права».
ACTIONS: tuple[Action, ...] = (
    Action("warn", "Выдавать варны", 3),
    Action("unwarn", "Снимать варны", 4),
    Action("warn_limit", "Менять лимит варнов", 6),
    Action("mute", "Мут", 4),
    Action("unmute", "Снимать мут", 4),
    Action("kick", "Кик", 5),
    Action("ban", "Бан", 6),
    Action("unban", "Снимать бан", 6),
    Action("shield", "Защита от чистки", 5),
    Action("immune", "Иммунитет", 7),
    Action("close_chat", "Закрывать и открывать чат", 6),
    Action("write_closed", "Писать в закрытый чат", 4),
    Action("purge", "Проводить чистку", 7),
    Action("purge_write", "Писать во время чистки", 7),
    Action("set_rank", "Выдавать ранги", 7),
    Action("admin_chat", "Привязывать админ-чат", 8),
    Action("settings", "Настройки чата", 8),
    Action("rights", "Менять права рангов", OWNER),
    Action("pinged", "Получать пинги в админ-сообщениях", 4),
)
ACTION_BY_KEY = {a.key: a for a in ACTIONS}


async def rights_map(db, chat_id: int) -> dict[str, int]:
    out = {a.key: a.default for a in ACTIONS}
    async with db.execute(
        "SELECT action, min_rank FROM chat_rank_rights WHERE chat_id = ?", (chat_id,)
    ) as cur:
        for row in await cur.fetchall():
            if row[0] in out:
                out[row[0]] = int(row[1])
    return out


async def set_right(db, chat_id: int, action: str, min_rank: int, actor_id: int) -> None:
    await db.execute(
        "INSERT INTO chat_rank_rights (chat_id, action, min_rank, updated_by) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (chat_id, action) DO UPDATE SET min_rank = EXCLUDED.min_rank, "
        "updated_by = EXCLUDED.updated_by, updated_at = NOW()",
        (chat_id, action, min_rank, actor_id),
    )
    await _commit(db)


_owner_checked: dict[int, float] = {}
_OWNER_TTL = 3600.0


async def sync_owner(db, bot: Bot, chat_id: int, *, force: bool = False) -> int | None:
    """Владелец из Telegram -> chat_settings.owner_id (не чаще раза в час)."""
    now = time.monotonic()
    if not force and now - _owner_checked.get(chat_id, 0) < _OWNER_TTL:
        return await get_owner(db, chat_id)
    _owner_checked[chat_id] = now
    try:
        admins = await bot.get_chat_administrators(chat_id)
    except Exception:
        return await get_owner(db, chat_id)
    owner = next((a.user.id for a in admins if a.status == "creator"), None)
    if owner:
        await set_owner(db, chat_id, owner)
    return owner


async def set_owner(db, chat_id: int, owner_id: int) -> None:
    await db.execute(
        "INSERT INTO chat_settings (chat_id, owner_id) VALUES (?, ?) "
        "ON CONFLICT (chat_id) DO UPDATE SET owner_id = EXCLUDED.owner_id",
        (chat_id, owner_id),
    )
    await _commit(db)


async def get_owner(db, chat_id: int) -> int | None:
    async with db.execute("SELECT owner_id FROM chat_settings WHERE chat_id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row and row[0] else None


async def get_rank(db, chat_id: int, user_id: int) -> int:
    if is_developer(user_id):
        return DEV_LEVEL
    if await get_owner(db, chat_id) == user_id:
        return OWNER
    async with db.execute(
        "SELECT chat_rank, local_rank FROM user_chat_stats WHERE chat_tg_id = ? AND user_tg_id = ?",
        (chat_id, user_id),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return 0
    rank = int(row[0]) if row[0] is not None else legacy_rank(row[1])
    return min(rank, OWNER - 1)   # владелец только через Telegram


async def can(db, chat_id: int, user_id: int, action: str) -> bool:
    if is_developer(user_id):
        return True
    need = (await rights_map(db, chat_id))[action]
    return await get_rank(db, chat_id, user_id) >= need


async def store_rank(db, chat_id: int, user_id: int, rank: int) -> None:
    await db.execute(
        "INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, chat_rank) VALUES (?, ?, ?) "
        "ON CONFLICT (user_tg_id, chat_tg_id) DO UPDATE SET chat_rank = EXCLUDED.chat_rank",
        (user_id, chat_id, rank),
    )
    await _commit(db)


def check_assign(actor_rank: int, target_rank: int, new_rank: int) -> str | None:
    """Причина отказа или None. Ранги выдаются только ниже своего."""
    if new_rank >= OWNER:
        return "Владелец назначается только через Telegram — передачей прав на группу."
    if actor_rank >= DEV_LEVEL:
        return None
    if target_rank >= actor_rank:
        return "Нельзя менять ранг тому, чей ранг не ниже вашего."
    if new_rank >= actor_rank:
        return "Можно выдать только ранг ниже вашего."
    return None


async def _commit(db) -> None:
    commit = getattr(db, "commit", None)
    if commit:
        await commit()
