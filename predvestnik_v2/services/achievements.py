"""
services/achievements.py
Achievement increment, threshold checking, and reward granting.
No bot/django imports.
"""
from core.constants import BATTLE_PASS_XP_WEIGHTS
from core.registry import ACHIEVEMENTS, ACHIEVEMENT_LEVEL_REWARDS
from infrastructure.repositories.achievements import get_achievement, upsert_achievement
from infrastructure.repositories.economy import add_balance


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

        # H4: каждое достижение обновляем атомарно — транзакция + FOR UPDATE на
        # строке. Раньше read-modify-write терял прогресс при гонке (бот+сайт по
        # одной метрике) и мог выдать награду уровня дважды. Под локом строки
        # параллельные инкременты сериализуются.
        async with db.connection.transaction():
            await db.execute(
                "INSERT INTO achievements (user_id, achievement_id, level, progress) "
                "VALUES (?, ?, 0, 0) ON CONFLICT (user_id, achievement_id) DO NOTHING",
                (user_id, ach_id),
            )
            async with db.execute(
                "SELECT level, progress FROM achievements "
                "WHERE user_id = ? AND achievement_id = ? FOR UPDATE",
                (user_id, ach_id),
            ) as _c:
                _row = await _c.fetchone()
            current_level = int(_row[0]) if _row else 0
            if current_level >= 10:
                continue  # already maxed — выходит из transaction (коммит лока) и идёт дальше

            new_progress = (float(_row[1]) if _row else 0.0) + delta
            thresholds = ach["thresholds"]

            while current_level < 10:
                if new_progress >= thresholds[current_level]:
                    current_level += 1
                    reward = ACHIEVEMENT_LEVEL_REWARDS.get(current_level, {})

                    # Grant mora (add_balance уже пишет в wallet_log — без дубля!)
                    if reward.get("mora", 0) > 0:
                        await add_balance(db, user_id, mora=reward["mora"], commit=False,
                                          source="achievement_reward", chat_id=chat_id,
                                          note=f"{ach_id}_lv{current_level}")
                    if reward.get("diamonds", 0) > 0:
                        await add_balance(db, user_id, diamonds=reward["diamonds"], commit=False,
                                          source="achievement_reward", chat_id=chat_id,
                                          note=f"{ach_id}_lv{current_level}")
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
