"""Early access to content that is not public yet (admin «Права» → «Ранний доступ к контенту»).

One threshold, set by the creator: every global role at or above it sees the early content.  By default
only the creator does.  Today it opens the demo of the new season (the League); rewards there are fake.
"""
from __future__ import annotations

from bot.chat.global_ranks import get_bot_rank
from core.league_v1 import FLAG_KEY
from services import admin_access


async def min_rank(db) -> int:
    default = admin_access.FEATURES["early_access"][1]
    return admin_access.effective_min(FLAG_KEY, default, await admin_access.load_grants(db))


async def allowed(db, user_id: int) -> bool:
    return await get_bot_rank(db, int(user_id)) >= await min_rank(db)
