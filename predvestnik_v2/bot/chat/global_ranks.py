"""Глобальные роли в боте (не в чате). Создатель — DEVELOPER_ID, всегда наверху."""
from __future__ import annotations

from bot.chat.access import is_developer

BOT_RANKS: tuple[tuple[str, str], ...] = (
    ("", "Пользователь"),
    ("🧪", "Тестер"),
    ("🌱", "Младший хелпер"),
    ("💬", "Хелпер"),
    ("🎓", "Старший хелпер"),
    ("🛠", "Разработчик"),
    ("👑", "Создатель"),
)
CREATOR = 6
HELPER_MIN = 2   # с этой роли видны ID игроков


def bot_rank_name(rank: int) -> str:
    icon, name = BOT_RANKS[max(0, min(rank, CREATOR))]
    return f"{icon} {name}".strip()


async def get_bot_rank(db, user_id: int) -> int:
    if is_developer(user_id):
        return CREATOR
    async with db.execute("SELECT bot_rank FROM users WHERE user_tg_id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    return min(int(row[0] or 0), CREATOR - 1) if row else 0


async def is_sponsor(db, user_id: int) -> bool:
    async with db.execute("SELECT is_sponsor FROM users WHERE user_tg_id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    return bool(row and row[0])
