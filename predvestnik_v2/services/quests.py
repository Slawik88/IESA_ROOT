"""Read-only compatibility layer for retired daily and weekly quests.

Existing rows remain visible for migration/audit. No new quest is assigned, no
metric advances, and no reward or Battle Pass XP is produced.
"""
from datetime import datetime, timedelta, timezone

from core.constants import (
    DAILY_QUEST_COMPLETE_BONUS,
    DAILY_QUEST_COMPLETE_ID,
    WEEKLY_QUEST_COMPLETE_BONUS,
    WEEKLY_QUEST_COMPLETE_ID,
)
from core.registry import DAILY_QUESTS, WEEKLY_QUESTS
from infrastructure.repositories.quests import get_user_quests
from infrastructure.repositories.streak import get_chat_timezone

_DAILY_IDS = {q["id"] for q in DAILY_QUESTS}
_WEEKLY_IDS = {q["id"] for q in WEEKLY_QUESTS}


def _today_for_tz(tz_offset: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=tz_offset)).strftime("%Y-%m-%d")


def _week_key(tz_offset: int = 0) -> str:
    iso = (datetime.now(timezone.utc) + timedelta(hours=tz_offset)).isocalendar()
    return f"W{iso[0]}-{iso[1]:02d}"


async def _resolve_tz(db, chat_id: int, tz_offset: int | None) -> int:
    if tz_offset is not None:
        return tz_offset
    try:
        return await get_chat_timezone(db, chat_id)
    except Exception:
        return 0


def _merge_existing(definitions: list[dict], rows: list) -> list[dict]:
    by_id = {row["quest_id"]: row for row in rows}
    return [{**definition, **by_id[definition["id"]]} for definition in definitions
            if definition["id"] in by_id]


async def get_or_assign_quests(db, user_id: int, chat_id: int,
                               tz_offset: int | None = None) -> list[dict]:
    """Return existing quests for today without assigning replacements."""
    tz = await _resolve_tz(db, chat_id, tz_offset)
    rows = await get_user_quests(db, user_id, chat_id, _today_for_tz(tz))
    return _merge_existing(DAILY_QUESTS, rows)


async def get_or_assign_weekly_quests(db, user_id: int, chat_id: int,
                                      tz_offset: int | None = None) -> list[dict]:
    """Return existing quests for this week without assigning replacements."""
    tz = await _resolve_tz(db, chat_id, tz_offset)
    rows = await get_user_quests(db, user_id, chat_id, _week_key(tz))
    return _merge_existing(WEEKLY_QUESTS, rows)


async def increment_metric(db, user_id: int, chat_id: int, metric_name: str,
                           delta: float = 1.0, tz_offset: int | None = None) -> list[dict]:
    """Retired writer boundary: gameplay actions cannot advance old quests."""
    return []


async def daily_bonus_status(db, user_id: int, chat_id: int,
                             tz_offset: int | None = None) -> dict:
    tz = await _resolve_tz(db, chat_id, tz_offset)
    rows = await get_user_quests(db, user_id, chat_id, _today_for_tz(tz))
    real = [r for r in rows if r["quest_id"] in _DAILY_IDS]
    return {
        "reward": DAILY_QUEST_COMPLETE_BONUS,
        "all_done": len(real) >= 3 and all(r["completed"] for r in real),
        "claimed": any(r["quest_id"] == DAILY_QUEST_COMPLETE_ID and r["completed"] for r in rows),
    }


async def weekly_bonus_status(db, user_id: int, chat_id: int,
                              tz_offset: int | None = None) -> dict:
    tz = await _resolve_tz(db, chat_id, tz_offset)
    rows = await get_user_quests(db, user_id, chat_id, _week_key(tz))
    real = [r for r in rows if r["quest_id"] in _WEEKLY_IDS]
    return {
        "reward": WEEKLY_QUEST_COMPLETE_BONUS,
        "all_done": len(real) >= len(WEEKLY_QUESTS) and all(r["completed"] for r in real),
        "claimed": any(r["quest_id"] == WEEKLY_QUEST_COMPLETE_ID and r["completed"] for r in rows),
    }
