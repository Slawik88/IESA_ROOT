"""
Batch message counter — Phase 2 optimisation.

Instead of hitting PostgreSQL on every single Telegram message, we accumulate
counts in-memory and flush them to the DB once every ~3 minutes with a single
batch UPDATE using unnest(), cutting hundreds of round-trips down to one.

Public API
----------
buffer_message(user_id, chat_id)  — call on every message (replaces increment_message_count_chat)
flush_buffer()                     — called by the background flush-loop in main.py
get_all_pending()                  — used by Smart Top to merge unsaved counts
get_pending_count(user_id, chat_id)
"""

import asyncio
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# (user_id, chat_id) → pending delta
_buffer: dict[tuple[int, int], int] = defaultdict(int)
_lock = asyncio.Lock()


async def buffer_message(user_id: int, chat_id: int) -> None:
    """Increment the in-memory counter for (user_id, chat_id) by 1."""
    async with _lock:
        _buffer[(user_id, chat_id)] += 1


def get_pending_count(user_id: int, chat_id: int) -> int:
    """Return the unsaved count (approximate — no lock needed for reads)."""
    return _buffer.get((user_id, chat_id), 0)


def get_all_pending() -> dict[tuple[int, int], int]:
    """Return a snapshot of all pending counts (approximate, no lock)."""
    return dict(_buffer)


async def flush_buffer() -> int:
    """
    Drain the buffer and write all pending counts to PostgreSQL in one query.
    Returns the number of (user_id, chat_id) pairs flushed.
    Safe to call concurrently — only one flush runs at a time thanks to the lock.
    """
    async with _lock:
        if not _buffer:
            return 0
        snapshot = dict(_buffer)
        _buffer.clear()

    try:
        from database.db import batch_increment_message_counts
        await batch_increment_message_counts(snapshot)
        logger.debug("message_buffer: flushed %d entries", len(snapshot))
    except Exception as exc:
        # On failure put the counts back so they aren't silently lost
        logger.error("message_buffer flush failed (%s), restoring counts", exc)
        async with _lock:
            for key, delta in snapshot.items():
                _buffer[key] += delta
        return 0

    return len(snapshot)
