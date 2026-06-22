"""
services/quests.py
Daily quest system. No bot imports.
"""
import random
from datetime import datetime, timezone, timedelta

from core.registry import DAILY_QUESTS, WEEKLY_QUESTS
from core.constants import (
    DAILY_QUEST_COMPLETE_ID, DAILY_QUEST_COMPLETE_BONUS,
    WEEKLY_QUEST_COMPLETE_ID, WEEKLY_QUEST_COMPLETE_BONUS,
)
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.quests import (
    get_user_quests, upsert_quest, increment_quest_progress, mark_completed, claim_once,
)
from infrastructure.repositories.streak import get_chat_timezone

_DAILY_IDS = {q["id"] for q in DAILY_QUESTS}
_WEEKLY_IDS = {q["id"] for q in WEEKLY_QUESTS}


def _today_for_tz(tz_offset: int = 0) -> str:
    now = datetime.now(timezone.utc) + timedelta(hours=tz_offset)
    return now.strftime("%Y-%m-%d")


def _week_key(tz_offset: int = 0) -> str:
    """Ключ недели для таблицы daily_quests: «WYYYY-NN» (ISO-неделя). Не пересекается
    с дневными ключами «YYYY-MM-DD», поэтому дневные и недельные живут в одной таблице."""
    now = datetime.now(timezone.utc) + timedelta(hours=tz_offset)
    iso = now.isocalendar()
    return f"W{iso[0]}-{iso[1]:02d}"


async def _resolve_tz(db, chat_id: int, tz_offset: int | None) -> int:
    """Resolve the chat-local timezone so assign + increment always agree.
    If tz_offset is explicitly given, use it; otherwise read the chat setting."""
    if tz_offset is not None:
        return tz_offset
    try:
        return await get_chat_timezone(db, chat_id)
    except Exception:
        return 0


def _select_quests(n: int = 3, seed: str | None = None) -> list[dict]:
    """Pick n weighted-random quests ensuring no duplicate metrics.

    Аудит M10: при seed выбор детерминирован → параллельные первые вызовы
    (бот+сайт) выбирают ОДИН набор, `upsert_quest` (ON CONFLICT) дедуплицирует →
    ровно n квестов на день, без гонки двойного назначения."""
    rng = random.Random(seed) if seed is not None else random
    pool = list(DAILY_QUESTS)
    chosen: list[dict] = []
    used_metrics: set[str] = set()

    for _ in range(n):
        candidates = [q for q in pool if q["metric"] not in used_metrics]
        if not candidates:
            break
        weights = [q["weight"] for q in candidates]
        total = sum(weights)
        r = rng.uniform(0, total)
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
    chosen = _select_quests(3, seed=f"{user_id}:{chat_id}:{today}")
    for q in chosen:
        await upsert_quest(db, user_id, chat_id, today, q["id"], progress=0.0, completed=0)
    await db.commit()

    return [{**q, "progress": 0.0, "completed": 0} for q in chosen]


async def _grant_reward(db, user_id: int, reward: dict, note: str = "") -> None:
    """Начислить награду квеста (мора/алмазы/предметы). No commit — caller коммитит.
    🐿 Белка (Block 12): +% Моры к награде за квесты, если питомец в питомнике."""
    mora = reward.get("mora", 0) or 0
    if mora > 0:
        try:
            from infrastructure.repositories.zoo import get_species_bonus
            sb = await get_species_bonus(db, user_id, "squirrel")
            mora = round(mora * (1.0 + float(sb.get("quest_mora_bonus", 0.0) or 0.0)))
        except Exception:
            pass
        await eco_repo.add_balance(db, user_id, mora=mora, commit=False,
                                   source="quest_reward", note=note)
    if reward.get("diamonds", 0) > 0:
        await eco_repo.add_balance(db, user_id, diamonds=reward["diamonds"], commit=False,
                                   source="quest_reward")
    for item_id, qty in reward.get("items", []):
        await db.execute(
            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
            (user_id, item_id, qty, qty),
        )


async def _increment_set(db, user_id: int, chat_id: int, date_key: str,
                         quest_defs: list, existing: list, metric_name: str,
                         delta: float) -> list[dict]:
    """Инкремент квестов набора quest_defs, отслеживающих metric_name (строки existing
    с ключом date_key). Авто-завершение + награда атомарно (H5). No commit.
    Возвращает список закрытых этим вызовом квестов."""
    ids = {r["quest_id"] for r in existing}
    completed: list[dict] = []
    for q in quest_defs:
        if q["id"] not in ids or q["metric"] != metric_name:
            continue
        row = next((r for r in existing if r["quest_id"] == q["id"]), None)
        if not row or row["completed"]:
            continue
        new_progress = await increment_quest_progress(db, user_id, chat_id, date_key, q["id"], delta)
        if new_progress is None:
            continue  # квест уже завершён или отсутствует
        # H5: грантим ТОЛЬКО если этот вызов реально переключил 0→1 (защита от двойной выдачи).
        if new_progress >= q["target"] and await mark_completed(db, user_id, chat_id, date_key, q["id"]):
            await _grant_reward(db, user_id, q.get("reward", {}), note=q["id"])
            completed.append({**q, "progress": new_progress})
    return completed


async def increment_metric(
    db,
    user_id: int,
    chat_id: int,
    metric_name: str,
    delta: float = 1.0,
    tz_offset: int | None = None,
) -> list[dict]:
    """Инкремент прогресса по метрике для ДНЕВНЫХ и НЕДЕЛЬНЫХ квестов сразу.
    Авто-назначает наборы (трекинг 24/7 без «бот задания»), авто-завершает, выдаёт
    награды и проверяет супер-бонусы. Возвращает список закрытых квестов. No commit.

    Один вызов кормит и дневные, и недельные → бот и сайт инкрементят в одних и тех
    же местах, поэтому паритет бот↔сайт получается автоматически.
    tz_offset резолвится из настройки чата, чтобы назначение и инкремент совпадали по
    ключу даты/недели."""
    tz_offset = await _resolve_tz(db, chat_id, tz_offset)
    completed_now: list[dict] = []

    # ── Дневные ───────────────────────────────────────────────────────────────
    today = _today_for_tz(tz_offset)
    existing = await get_user_quests(db, user_id, chat_id, today)
    if not existing:
        try:
            chosen = _select_quests(3, seed=f"{user_id}:{chat_id}:{today}")
            for q in chosen:
                await upsert_quest(db, user_id, chat_id, today, q["id"], progress=0.0, completed=0)
            await db.commit()
            existing = await get_user_quests(db, user_id, chat_id, today)
        except Exception:
            existing = []
    if existing:
        daily_done = await _increment_set(db, user_id, chat_id, today, DAILY_QUESTS,
                                          existing, metric_name, delta)
        completed_now.extend(daily_done)
        if daily_done:
            bonus = await _maybe_grant_daily_bonus(db, user_id, chat_id, today)
            if bonus:
                completed_now.append(bonus)

    # ── Недельные (БЛОК 5) — та же таблица, ключ = неделя ───────────────────────
    week_key = _week_key(tz_offset)
    w_existing = await get_user_quests(db, user_id, chat_id, week_key)
    if len(w_existing) < len(WEEKLY_QUESTS):
        try:
            have = {r["quest_id"] for r in w_existing}
            for q in WEEKLY_QUESTS:
                if q["id"] not in have:
                    await upsert_quest(db, user_id, chat_id, week_key, q["id"], progress=0.0, completed=0)
            await db.commit()
            w_existing = await get_user_quests(db, user_id, chat_id, week_key)
        except Exception:
            pass
    if w_existing:
        weekly_done = await _increment_set(db, user_id, chat_id, week_key, WEEKLY_QUESTS,
                                           w_existing, metric_name, delta)
        completed_now.extend(weekly_done)
        if weekly_done:
            wbonus = await _maybe_grant_weekly_bonus(db, user_id, chat_id, week_key)
            if wbonus:
                completed_now.append(wbonus)

    return completed_now


async def _maybe_grant_daily_bonus(db, user_id: int, chat_id: int, today: str) -> dict | None:
    """Выдать супер-награду, если ВСЕ дневные квесты закрыты (и ещё не выдавали).
    Возвращает dict-уведомление или None. No commit — caller коммитит."""
    rows = await get_user_quests(db, user_id, chat_id, today)
    real = [r for r in rows if r["quest_id"] in _DAILY_IDS]
    if len(real) < 3 or not all(r["completed"] for r in real):
        return None
    if not await claim_once(db, user_id, chat_id, today, DAILY_QUEST_COMPLETE_ID):
        return None  # уже выдавали сегодня

    reward = DAILY_QUEST_COMPLETE_BONUS
    if reward.get("mora", 0) > 0:
        await eco_repo.add_balance(db, user_id, mora=reward["mora"], commit=False,
                                   source="quest_complete_bonus")
    if reward.get("diamonds", 0) > 0:
        await eco_repo.add_balance(db, user_id, diamonds=reward["diamonds"], commit=False,
                                   source="quest_complete_bonus")
    for item_id, qty in reward.get("items", []):
        await db.execute(
            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
            (user_id, item_id, qty, qty),
        )
    return {"id": DAILY_QUEST_COMPLETE_ID, "name": "🏆 Все задания дня закрыты!",
            "reward": reward, "is_completion_bonus": True}


async def daily_bonus_status(db, user_id: int, chat_id: int, tz_offset: int | None = None) -> dict:
    """Статус супер-награды дня для UI: {reward, all_done, claimed}."""
    tz_offset = await _resolve_tz(db, chat_id, tz_offset)
    today = _today_for_tz(tz_offset)
    rows = await get_user_quests(db, user_id, chat_id, today)
    real = [r for r in rows if r["quest_id"] in _DAILY_IDS]
    all_done = len(real) >= 3 and all(r["completed"] for r in real)
    claimed = any(r["quest_id"] == DAILY_QUEST_COMPLETE_ID and r["completed"] for r in rows)
    return {"reward": DAILY_QUEST_COMPLETE_BONUS, "all_done": all_done, "claimed": claimed}


# ── Недельные квесты (БЛОК 5) ─────────────────────────────────────────────────
async def get_or_assign_weekly_quests(db, user_id: int, chat_id: int,
                                      tz_offset: int | None = None) -> list[dict]:
    """Недельные квесты игрока (фиксированный набор). Назначает недостающие при первом
    обращении на этой неделе — не сбрасывая уже накопленный прогресс."""
    tz_offset = await _resolve_tz(db, chat_id, tz_offset)
    week_key = _week_key(tz_offset)
    existing = await get_user_quests(db, user_id, chat_id, week_key)
    have = {r["quest_id"] for r in existing}
    missing = [q for q in WEEKLY_QUESTS if q["id"] not in have]
    if missing:
        for q in missing:
            await upsert_quest(db, user_id, chat_id, week_key, q["id"], progress=0.0, completed=0)
        await db.commit()
        existing = await get_user_quests(db, user_id, chat_id, week_key)
    quest_map = {r["quest_id"]: r for r in existing}
    return [{**q, **quest_map[q["id"]]} for q in WEEKLY_QUESTS if q["id"] in quest_map]


async def _maybe_grant_weekly_bonus(db, user_id: int, chat_id: int, week_key: str) -> dict | None:
    """Супер-награда, если ВСЕ недельные квесты закрыты (и ещё не выдавали на этой
    неделе). Атомарно через claim_once. No commit — caller коммитит."""
    rows = await get_user_quests(db, user_id, chat_id, week_key)
    real = [r for r in rows if r["quest_id"] in _WEEKLY_IDS]
    if len(real) < len(WEEKLY_QUESTS) or not all(r["completed"] for r in real):
        return None
    if not await claim_once(db, user_id, chat_id, week_key, WEEKLY_QUEST_COMPLETE_ID):
        return None  # уже выдавали на этой неделе
    await _grant_reward(db, user_id, WEEKLY_QUEST_COMPLETE_BONUS, note="weekly_bonus")
    return {"id": WEEKLY_QUEST_COMPLETE_ID, "name": "🏆 Все недельные задания закрыты!",
            "reward": WEEKLY_QUEST_COMPLETE_BONUS, "is_completion_bonus": True}


async def weekly_bonus_status(db, user_id: int, chat_id: int, tz_offset: int | None = None) -> dict:
    """Статус недельной супер-награды для UI: {reward, all_done, claimed}."""
    tz_offset = await _resolve_tz(db, chat_id, tz_offset)
    week_key = _week_key(tz_offset)
    rows = await get_user_quests(db, user_id, chat_id, week_key)
    real = [r for r in rows if r["quest_id"] in _WEEKLY_IDS]
    all_done = len(real) >= len(WEEKLY_QUESTS) and all(r["completed"] for r in real)
    claimed = any(r["quest_id"] == WEEKLY_QUEST_COMPLETE_ID and r["completed"] for r in rows)
    return {"reward": WEEKLY_QUEST_COMPLETE_BONUS, "all_done": all_done, "claimed": claimed}
