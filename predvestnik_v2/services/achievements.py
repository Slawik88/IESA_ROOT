"""
services/achievements.py
Achievement increment, threshold checking, and reward granting.
No bot/django imports.
"""
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
                        "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + ?",
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

    return granted


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
