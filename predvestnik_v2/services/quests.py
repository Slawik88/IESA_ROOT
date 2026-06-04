"""
services/quests.py
Daily quest system. No bot imports.
"""
import random
from datetime import datetime, timezone, timedelta

from core.registry import DAILY_QUESTS
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.quests import (
    get_user_quests, upsert_quest, increment_quest_progress, mark_completed,
)
from infrastructure.repositories.streak import get_chat_timezone


def _today_for_tz(tz_offset: int = 0) -> str:
    now = datetime.now(timezone.utc) + timedelta(hours=tz_offset)
    return now.strftime("%Y-%m-%d")


async def _resolve_tz(db, chat_id: int, tz_offset: int | None) -> int:
    """Resolve the chat-local timezone so assign + increment always agree.
    If tz_offset is explicitly given, use it; otherwise read the chat setting."""
    if tz_offset is not None:
        return tz_offset
    try:
        return await get_chat_timezone(db, chat_id)
    except Exception:
        return 0


def _select_quests(n: int = 3) -> list[dict]:
    """Pick n weighted-random quests ensuring no duplicate metrics."""
    pool = list(DAILY_QUESTS)
    chosen: list[dict] = []
    used_metrics: set[str] = set()

    for _ in range(n):
        candidates = [q for q in pool if q["metric"] not in used_metrics]
        if not candidates:
            break
        weights = [q["weight"] for q in candidates]
        total = sum(weights)
        r = random.uniform(0, total)
        cumulative = 0.0
        for q, w in zip(candidates, weights):
            cumulative += w
            if r <= cumulative:
                chosen.append(q)
                used_metrics.add(q["metric"])
                pool.remove(q)
                break

    return chosen


async def get_or_assign_quests(
    db,
    user_id: int,
    chat_id: int,
    tz_offset: int | None = None,
) -> list[dict]:
    """Return today's 3 quests, assigning them if this is the first call today."""
    tz_offset = await _resolve_tz(db, chat_id, tz_offset)
    today = _today_for_tz(tz_offset)
    existing = await get_user_quests(db, user_id, chat_id, today)

    if len(existing) >= 3:
        quest_map = {r["quest_id"]: r for r in existing}
        result = []
        for q in DAILY_QUESTS:
            if q["id"] in quest_map:
                result.append({**q, **quest_map[q["id"]]})
        return result[:3]

    # Assign fresh quests
    chosen = _select_quests(3)
    for q in chosen:
        await upsert_quest(db, user_id, chat_id, today, q["id"], progress=0.0, completed=0)
    await db.commit()

    return [{**q, "progress": 0.0, "completed": 0} for q in chosen]


async def increment_metric(
    db,
    user_id: int,
    chat_id: int,
    metric_name: str,
    delta: float = 1.0,
    tz_offset: int | None = None,
) -> list[dict]:
    """Increment progress on all active quests tracking this metric.
    Auto-completes and grants reward if target reached.
    Returns list of completed quest dicts (for notification).
    No commit — caller handles commit.

    tz_offset is resolved from the chat's setting so that quest assignment
    (бот задания) and metric increments always use the same date key.
    """
    tz_offset = await _resolve_tz(db, chat_id, tz_offset)
    today = _today_for_tz(tz_offset)
    existing = await get_user_quests(db, user_id, chat_id, today)
    if not existing:
        # Auto-assign so quests track 24/7 without needing «бот задания»
        try:
            chosen = _select_quests(3)
            for q in chosen:
                await upsert_quest(db, user_id, chat_id, today, q["id"], progress=0.0, completed=0)
            await db.commit()
            existing = await get_user_quests(db, user_id, chat_id, today)
        except Exception:
            return []
        if not existing:
            return []

    quest_ids_today = {r["quest_id"] for r in existing}
    completed_now: list[dict] = []

    for q in DAILY_QUESTS:
        if q["id"] not in quest_ids_today:
            continue
        if q["metric"] != metric_name:
            continue
        row = next((r for r in existing if r["quest_id"] == q["id"]), None)
        if not row or row["completed"]:
            continue

        new_progress = await increment_quest_progress(
            db, user_id, chat_id, today, q["id"], delta
        )

        if new_progress >= q["target"]:
            await mark_completed(db, user_id, chat_id, today, q["id"])
            # Grant reward
            reward = q.get("reward", {})
            if reward.get("mora", 0) > 0:
                await eco_repo.add_balance(db, user_id, mora=reward["mora"],
                                           commit=False, source="quest_reward",
                                           note=q["id"])
            if reward.get("diamonds", 0) > 0:
                await eco_repo.add_balance(db, user_id, diamonds=reward["diamonds"],
                                           commit=False, source="quest_reward")
            for item_id, qty in reward.get("items", []):
                await db.execute(
                    "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
                    "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
                    (user_id, item_id, qty, qty),
                )
            completed_now.append({**q, "progress": new_progress})

    return completed_now
