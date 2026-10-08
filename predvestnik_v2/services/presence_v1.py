"""Presence V1 service: records activity (throttled) and answers "when was this player last around" per viewer."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from core.presence_v1 import DEFAULT_LEVEL, LEVELS, describe, normalize
from infrastructure.repositories import presence_v1 as repo

TOUCH_EVERY = 60.0                 # one write per player per minute, however many requests a screen makes
_NEXT_TOUCH: dict[int, float] = {}

TITLES = {
    "everyone": ("Всем", "Точное время: «в сети» и «был(а) 12 минут назад»."),
    "approx": ("Примерно", "Только «недавно», «на этой неделе» или «в этом месяце». Что вы сейчас в сети, не видно."),
    "nobody": ("Никому", "Другие не видят ничего. Взамен чужое время вы тоже видите только примерно."),
}


def _aware(moment: datetime | None) -> datetime | None:
    return moment if moment is None or moment.tzinfo else moment.replace(tzinfo=timezone.utc)


async def note_activity(user_id: int) -> None:
    """Called after every authenticated request; swallows every error, it must never slow or break a screen."""
    now = time.monotonic()
    if _NEXT_TOUCH.get(user_id, 0) > now:
        return
    if len(_NEXT_TOUCH) > 20000:
        _NEXT_TOUCH.clear()
    _NEXT_TOUCH[user_id] = now + TOUCH_EVERY
    try:
        from infrastructure.database import create_pool, get_pool
        from infrastructure.pg_adapter import PGAdapter
        await create_pool()
        async with get_pool().acquire() as conn:
            db = PGAdapter(conn)
            await repo.ensure_tables(db)
            await repo.touch(db, int(user_id))
    except Exception:
        _NEXT_TOUCH.pop(user_id, None)


async def view_for(db, owner_id: int, viewer_id: int, now: datetime | None = None) -> dict | None:
    """The presence line a viewer may see for the owner, or None. For one's own card it shows what others see."""
    await repo.ensure_tables(db)
    rows = await repo.get_many(db, [owner_id, viewer_id])
    owner_seen, owner_level = rows.get(int(owner_id), (None, DEFAULT_LEVEL))
    viewer_level = "everyone" if int(owner_id) == int(viewer_id) else rows.get(int(viewer_id), (None, DEFAULT_LEVEL))[1]
    if owner_level == "nobody":
        return None
    chat = await repo.last_chat_message(db, int(owner_id))
    seen = max((m for m in (_aware(owner_seen), _aware(chat)) if m), default=None)
    return describe(seen, owner_level, viewer_level, now or datetime.now(timezone.utc))


async def settings(db, user_id: int) -> dict:
    await repo.ensure_tables(db)
    level = (await repo.get_many(db, [user_id])).get(int(user_id), (None, DEFAULT_LEVEL))[1]
    return {"visibility": level, "default": DEFAULT_LEVEL, "levels": [{"id": k, "title": TITLES[k][0], "hint": TITLES[k][1]} for k in LEVELS],
            "preview": await view_for(db, user_id, user_id)}


async def set_level(db, user_id: int, level: str) -> dict:
    if level not in LEVELS:
        raise ValueError("Такого варианта нет.")
    await repo.ensure_tables(db)
    await repo.set_visibility(db, user_id, normalize(level))
    return await settings(db, user_id)
