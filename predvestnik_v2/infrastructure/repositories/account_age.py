"""First appearance of accounts, read from chat records (no ``created_at`` exists on ``users``)."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from core import account_age


async def first_seen(db, user_ids: Iterable[int]) -> dict[int, datetime]:
    """Earliest known presence per user; users without any chat record are absent."""
    ids = sorted({int(u) for u in user_ids})
    if not ids:
        return {}
    joined: dict[int, list] = {u: [None, None, None] for u in ids}
    async with db.execute("SELECT user_tg_id, MIN(joined_at), MIN(membership_since) FROM user_chat_stats "
                          "WHERE user_tg_id = ANY(?::bigint[]) GROUP BY user_tg_id", (ids,)) as cursor:
        for user_id, j, m in await cursor.fetchall():
            joined[int(user_id)][0:2] = [j, m]
    async with db.execute("SELECT user_id, MIN(date) FROM daily_user_stats "
                          "WHERE user_id = ANY(?::bigint[]) GROUP BY user_id", (ids,)) as cursor:
        for user_id, day in await cursor.fetchall():
            joined[int(user_id)][2] = day
    seen = {u: account_age.first_seen(*parts) for u, parts in joined.items()}
    return {u: at for u, at in seen.items() if at}
