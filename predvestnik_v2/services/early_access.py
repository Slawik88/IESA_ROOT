"""Early access to content that is not public yet (admin «Права» → «Ранний доступ к контенту»).

One threshold, set by the creator: every global role at or above it sees the early content.  By default
only the creator does.  It was the way to see the League demo before season 2; the League has been public since 25.10.2026 (core.league_v1.is_public),
so today the right opens nothing on its own and is kept for the next piece of unreleased content.
"""
from __future__ import annotations

from bot.chat.global_ranks import get_bot_rank
from core.league_v1 import FLAG_KEY
from services import admin_access


async def min_rank(db) -> int:
    default = admin_access.FEATURES["early_access"][1]
    return admin_access.effective_min(FLAG_KEY, default, await admin_access.load_grants(db))


async def allowed(db, user_id: int) -> bool:
    rank = await get_bot_rank(db, int(user_id))
    if rank < admin_access.bounds(FLAG_KEY)[0]:
        return False
    return rank >= await min_rank(db)
