"""
api/boss.py — boss combat operations.

Thin wrapper around services.boss_service for consistent access from
both bot handlers and the miniapp.
"""

BOSS_MAX_HP = 500_000
BOSS_DAILY_DAMAGE_LIMIT = 50_000


async def submit_damage(
    uid: int,
    chat_id: int,
    damage: int,
    *,
    daily_limit: int = BOSS_DAILY_DAMAGE_LIMIT,
    boss_max_hp: int = BOSS_MAX_HP,
) -> dict:
    """Record miniapp boss attack damage with anti-cheat daily cap.

    Delegates to services.boss_service.record_miniapp_damage.
    Raises ValueError or services.exceptions.BossLimitError on error.
    Returns {damage, mora_earned, boss_hp_remaining}.
    """
    from services.boss_service import record_miniapp_damage

    return await record_miniapp_damage(
        uid, chat_id, damage,
        daily_limit=daily_limit,
        boss_max_hp=boss_max_hp,
    )
