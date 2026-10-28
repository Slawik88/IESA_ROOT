"""Time on Mini App tabs (analytics heartbeat): summed in memory, written in one statement at most every FLUSH_SEC.

Before S04 every open Mini App sent a heartbeat each 15 s, and each one was an UPDATE of its own. Now the client
sends one per minute (and when hidden), and the server adds the seconds up here. A restart loses at most the last
FLUSH_SEC of this secondary statistic; money, progress and achievements never pass through here.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

from infrastructure.repositories import analytics as analytics_repo

FLUSH_SEC = 60
MAX_PENDING = 50_000   # sessions waiting for a write; past it new seconds are dropped until the next write
MAX_PENDING_PER_PLAYER = 20   # one player inventing sessions cannot fill the table for everybody

_pending: dict[tuple[int, str, str], int] = {}
_per_player: dict[int, int] = {}
_last_flush = time.monotonic()
_flush_task: asyncio.Task | None = None


def add(user_id: int, tab: str, session_id: str, seconds: int) -> None:
    """Count the seconds; start a background write when the last one is FLUSH_SEC old."""
    key = (int(user_id), tab, session_id)
    if key in _pending:
        _pending[key] += int(seconds)
    elif len(_pending) < MAX_PENDING and _per_player.get(key[0], 0) < MAX_PENDING_PER_PLAYER:
        _per_player[key[0]] = _per_player.get(key[0], 0) + 1
        _pending[key] = int(seconds)
    if time.monotonic() - _last_flush >= FLUSH_SEC and (_flush_task is None or _flush_task.done()):
        _start_flush()


def _start_flush() -> None:
    global _flush_task, _last_flush
    _last_flush = time.monotonic()
    _flush_task = asyncio.create_task(_flush_in_background(), name="predvestnik:tab-time-flush")


async def _flush_in_background() -> None:
    from services.broadcasts import pool_db_factory
    try:
        async with pool_db_factory()() as db:
            await flush(db)
    except Exception as error:   # statistics only: log and go on, the next minute writes again
        logger.warning("tab time not written: {}: {}", type(error).__name__, error)


async def flush(db) -> int:
    """Write everything summed so far; returns the number of visits updated. Seconds of a failed write are lost."""
    global _pending, _per_player
    batch, _pending, _per_player = _pending, {}, {}
    await analytics_repo.add_tab_durations(db, [(*key, seconds) for key, seconds in batch.items()])
    return len(batch)
