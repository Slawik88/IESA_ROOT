"""
Boss service — handles boss damage recording and rewards.

Two attack surfaces share the same service:
  * Bot command   ``бот босс атака``  (in-memory HP, batch persistence via boss.py scheduler)
  * Mini App      POST /api/boss/submit_damage  (direct per-request persistence with anti-cheat)

Usage (Mini App path):
    from services.boss_service import record_miniapp_damage
    result = await record_miniapp_damage(user_id, chat_id, damage)
    # result = {"damage": 350, "mora_earned": 17, "boss_hp_remaining": 499_650}
"""
from database.db import (
    add_boss_damage,
    add_mora,
    get_boss_daily_user_damage,
    get_boss_chat_damage_today,
)
from .exceptions import BossLimitError

# Must match _BOSS_DAILY_DAMAGE_LIMIT in miniapp_views.py
BOSS_DAILY_DAMAGE_LIMIT = 50_000
BOSS_MAX_HP = 500_000


async def record_miniapp_damage(
    user_id: int,
    chat_id: int,
    damage: int,
    *,
    daily_limit: int = BOSS_DAILY_DAMAGE_LIMIT,
    boss_max_hp: int = BOSS_MAX_HP,
) -> dict:
    """Record Mini App boss attack damage with anti-cheat daily cap.

    Parameters
    ----------
    damage      : Damage to record (must be > 0 and ≤ daily_limit).
    daily_limit : Per-user daily damage cap (anti-cheat).
    boss_max_hp : Max HP used to compute remaining HP for the response.

    Returns
    -------
    dict with keys:
        ``damage``            int — damage recorded.
        ``mora_earned``       int — mora reward given.
        ``boss_hp_remaining`` int — estimated remaining boss HP (≥ 0).

    Raises
    ------
    ValueError      If *damage* is not in range (1, daily_limit].
    BossLimitError  If the user's daily damage cap is already reached.
    """
    if damage <= 0 or damage > daily_limit:
        raise ValueError(f"Damage must be between 1 and {daily_limit}, got {damage}")

    today_total = await get_boss_daily_user_damage(user_id, chat_id)
    if today_total + damage > daily_limit:
        raise BossLimitError(daily_limit)

    await add_boss_damage(user_id, chat_id, damage)

    mora_reward = max(5, damage // 20)
    await add_mora(user_id, chat_id, mora_reward)

    total_chat_damage = await get_boss_chat_damage_today(chat_id)

    return {
        "damage": damage,
        "mora_earned": mora_reward,
        "boss_hp_remaining": max(0, boss_max_hp - total_chat_damage),
    }
