"""
services/achievements.py
Achievement increment, threshold checking, and reward granting.
No bot/django imports.
"""
from core.constants import BATTLE_PASS_XP_WEIGHTS
from core.registry import ACHIEVEMENTS, ACHIEVEMENT_LEVEL_REWARDS
from infrastructure.repositories.achievements import get_achievement, upsert_achievement
from infrastructure.repositories.economy import add_balance
from infrastructure.repositories.wallet_log import log_wallet


async def increment_metric(
    db,
    user_id: int,
    metric_name: str,
    delta: float = 1.0,
    chat_id: int | None = None,
) -> list[dict]:
    """Increment all achievements that track `metric_name` by `delta`.
    Checks thresholds and grants rewards for newly unlocked levels.
    Returns list of newly granted level dicts: {achievement_id, icon, name, level, reward}.
    No commit — caller must commit.
    """
    granted: list[dict] = []

    for ach_id, ach in ACHIEVEMENTS.items():
        if ach["metric"] != metric_name:
            continue

        record = await get_achievement(db, user_id, ach_id)
        if record is None:
            record = {"level": 0, "progress": 0.0}

        current_level = record["level"]
        if current_level >= 10:
            continue  # already maxed

        new_progress = record["progress"] + delta
        thresholds = ach["thresholds"]

        # Check if any new levels are unlocked
        while current_level < 10:
            threshold = thresholds[current_level]
            if new_progress >= threshold:
                current_level += 1
                reward = ACHIEVEMENT_LEVEL_REWARDS.get(current_level, {})

                # Grant mora
                if reward.get("mora", 0) > 0:
                    await add_balance(db, user_id, mora=reward["mora"], commit=False,
                                      source="achievement_reward",
                                      note=f"{ach_id}_lv{current_level}")
                    await log_wallet(db, user_id, delta_mora=reward["mora"],
                                     source="achievement_reward", chat_id=chat_id,
                                     note=f"{ach_id}_lv{current_level}")

                # Grant diamonds
                if reward.get("diamonds", 0) > 0:
                    await add_balance(db, user_id, diamonds=reward["diamonds"], commit=False,
                                      source="achievement_reward")

                # Grant items
                for item_id, qty in reward.get("items", ()):
                    await db.execute(
                        "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
                        "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
                        (user_id, item_id, qty, qty),
                    )

                granted.append({
                    "achievement_id": ach_id,
                    "icon": ach["icon"],
                    "name": ach["name"],
                    "level": current_level,
                    "reward": reward,
                })
            else:
                break

        await upsert_achievement(db, user_id, ach_id, current_level, new_progress)

    # Боевой пропуск (Implementation Block 5.5) — единая точка интеграции:
    # любой increment_metric с метрикой из BATTLE_PASS_XP_WEIGHTS даёт XP БП.
    if metric_name in BATTLE_PASS_XP_WEIGHTS:
        from services.battle_pass import add_xp
        await add_xp(db, user_id, metric_name, delta)

    return granted


async def backfill_metric(
    db,
    user_id: int,
    metric_name: str,
    true_value: float,
    chat_id: int | None = None,
) -> list[dict]:
    """Catch up `metric_name`'s progress to `true_value` if it's behind.

    For metrics whose true cumulative/peak value can be recomputed from current
    DB state (pets owned, balances, message counts, etc.), this lets players
    with pre-existing history get retroactive progress + rewards for thresholds
    they already qualify for. Idempotent — a no-op once progress has caught up,
    safe to call on every page view. No commit — caller must commit.
    """
    ach_id = next((aid for aid, a in ACHIEVEMENTS.items() if a["metric"] == metric_name), None)
    if ach_id is None:
        return []
    record = await get_achievement(db, user_id, ach_id)
    current = record["progress"] if record else 0.0
    if true_value <= current:
        return []
    return await increment_metric(db, user_id, metric_name, delta=true_value - current, chat_id=chat_id)


def format_achievement_notification(grants: list[dict]) -> str:
    """Format granted achievements into a compact notification string."""
    if not grants:
        return ""
    lines = []
    for g in grants:
        r = g["reward"]
        parts = []
        if r.get("mora", 0) > 0:
            parts.append(f"+{int(r['mora'])} 🪙")
        if r.get("diamonds", 0) > 0:
            parts.append(f"+{r['diamonds']} 💎")
        for iid, qty in r.get("items", ()):
            parts.append(f"+{qty}× {iid}")
        reward_str = ", ".join(parts)
        lv = g["level"]
        drama = "🎉🎉🎉" if lv >= 6 else "🏆"
        lines.append(f"{drama} Достижение <b>{g['icon']} {g['name']}</b> — Ур.{lv}!\n└ {reward_str}")
    return "\n\n".join(lines)
