"""Read-only VIP status and compatibility grants for existing entitlements.

New paid VIP purchases are retired because the legacy paid track can issue
progression items. Existing subscriptions and already-earned claims remain
readable until the owner-approved compensation pass.
"""
from datetime import datetime, timezone
import math

from core.registry import VIP_TIERS

def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

async def grant_vip_days(db, user_id: int, tier: str, days: int) -> None:
    """Compatibility grant used by existing referral/dev obligations; no charge."""
    await db.execute("INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING",(user_id,))
    await db.execute(
        "INSERT INTO vip_subscriptions (user_id,tier,started_at,expires_at,expiry_notified,total_days) "
        "VALUES (?,?,NOW(),NOW()+make_interval(days => ?),FALSE,?) "
        "ON CONFLICT (user_id) DO UPDATE SET tier=EXCLUDED.tier, "
        "started_at=CASE WHEN vip_subscriptions.expires_at>NOW() THEN vip_subscriptions.started_at ELSE NOW() END, "
        "expires_at=CASE WHEN vip_subscriptions.expires_at>NOW() THEN vip_subscriptions.expires_at+make_interval(days => ?) ELSE NOW()+make_interval(days => ?) END, "
        "expiry_notified=FALSE,total_days=COALESCE(vip_subscriptions.total_days,0)+?",
        (user_id,tier,days,days,days,days,days),
    )

async def is_vip_active(db, user_id: int) -> bool:
    async with db.execute("SELECT 1 FROM vip_subscriptions WHERE user_id=? AND expires_at>NOW()",(user_id,)) as c:
        return await c.fetchone() is not None

async def is_vip_active_batch(db, user_ids: list[int]) -> set[int]:
    ids=[int(user_id) for user_id in (user_ids or [])]
    if not ids: return set()
    placeholders=",".join(["?"]*len(ids))
    async with db.execute(f"SELECT user_id FROM vip_subscriptions WHERE user_id IN ({placeholders}) AND expires_at>NOW()",tuple(ids)) as c:
        return {int(row[0]) for row in await c.fetchall()}

async def get_vip_info(db, user_id: int) -> dict | None:
    async with db.execute("SELECT tier,expires_at FROM vip_subscriptions WHERE user_id=? AND expires_at>NOW()",(user_id,)) as c:
        row=await c.fetchone()
    if not row: return None
    tier,expires_at=row[0],_aware(row[1])
    return {"tier":tier,"tier_label":VIP_TIERS.get(tier,{}).get("label",tier),"expires_at":expires_at,
            "days_left":max(0,math.ceil((expires_at-datetime.now(timezone.utc)).total_seconds()/86400))}

async def get_extra_pet_slots(db, user_id: int) -> int:
    return 0

async def get_vip_seniority_days(db, user_id: int) -> int:
    async with db.execute("SELECT COALESCE(total_days,0) FROM vip_subscriptions WHERE user_id=?",(user_id,)) as c:
        row=await c.fetchone()
    return int(row[0]) if row else 0
