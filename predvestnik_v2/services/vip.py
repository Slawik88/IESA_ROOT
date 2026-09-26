"""Single-product VIP status, grants and Zarniki purchases."""
from datetime import datetime, timezone
import math
from uuid import uuid4

from core.registry import VIP_TIERS
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import vip_v2 as vip_repo


VIP_POLICY_VERSION = "vip-v2-2026-09-26"
VIP_PACKAGES: dict[int, int] = {7: 140, 30: 600, 90: 1800, 365: 7300}
VIP_BADGES: dict[str, str] = {
    "spark": "✦", "crown": "♛", "diamond": "◇", "star": "★", "moon": "☾",
    "sun": "☼", "comet": "☄", "flame": "♨", "eye": "◉", "rune": "ᚱ",
    "lotus": "❀", "wing": "𓆩", "orbit": "⊹", "void": "◈", "pulse": "⌁",
    "prism": "⬖", "north": "✧", "arc": "⌒", "mark": "※", "signal": "⌬",
}


class VipError(ValueError):
    pass


class VipConflict(VipError):
    pass

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


async def purchase_vip(db, *, user_id: int, package_days: int, action_id: str) -> dict:
    action_id = str(action_id or "").strip()
    if not action_id or len(action_id) > 96:
        raise VipError("action_id обязателен.")
    try:
        price = VIP_PACKAGES[int(package_days)]
    except (KeyError, TypeError, ValueError) as exc:
        raise VipError("Такого срока VIP нет.") from exc
    await economy_ledger.ensure_tables(db)
    await vip_repo.ensure_tables(db)
    async with db.connection.transaction():
        await vip_repo.lock_user(db, int(user_id))
        replay = await vip_repo.find_purchase(db, user_id=int(user_id), action_id=action_id)
        if replay:
            if int(replay["package_days"]) != int(package_days) or int(replay["price_zarniki"]) != price:
                raise VipConflict("action_id уже использован для другой покупки.")
            return {
                "purchase_id": str(replay["id"]), "applied": False,
                "package_days": int(replay["package_days"]), "price_zarniki": int(replay["price_zarniki"]),
                "expires_at": _aware(replay["expires_at_after"]).isoformat(),
            }
        current = await vip_repo.current_subscription_for_update(db, user_id=int(user_id))
        expires_before = current["expires_at"] if current else None
        purchase_id = uuid4().hex
        mutation = await economy_ledger.apply_balance_change(
            db, int(user_id), {"zarniki": -price}, reason_code="vip_purchase",
            idempotency_key=f"vip-v2:{int(user_id)}:{action_id}", source_type="vip_v2",
            reference_type="vip_purchase", reference_id=purchase_id,
            metadata={"policy_version": VIP_POLICY_VERSION, "package_days": int(package_days),
                      "price_zarniki": price}, note=f"VIP на {int(package_days)} дней",
        )
        expires_after = await vip_repo.extend_subscription(db, user_id=int(user_id), days=int(package_days))
        await vip_repo.save_purchase(
            db, purchase_id=purchase_id, user_id=int(user_id), action_id=action_id,
            package_days=int(package_days), price_zarniki=price,
            economy_operation_id=str(mutation.operation_id), expires_at_before=expires_before,
            expires_at_after=expires_after,
        )
    return {"purchase_id": purchase_id, "applied": True, "package_days": int(package_days),
            "price_zarniki": price, "expires_at": _aware(expires_after).isoformat()}


async def get_preferences(db, *, user_id: int) -> dict:
    await economy_ledger.ensure_tables(db)
    await vip_repo.ensure_tables(db)
    row = await vip_repo.get_preferences(db, user_id=int(user_id))
    return {
        "badge_id": str(row["badge_id"]) if row and row["badge_id"] else "spark",
        "badge_position": str(row["badge_position"]) if row else "left",
        "reminder_enabled": bool(row["reminder_enabled"]) if row else True,
    }


async def get_preferences_batch(db, *, user_ids: list[int]) -> dict[int, dict]:
    await economy_ledger.ensure_tables(db)
    await vip_repo.ensure_tables(db)
    rows = await vip_repo.get_preferences_batch(db, user_ids=user_ids)
    return {user_id: {
        "badge_id": str(row.get("badge_id") or "spark"),
        "badge_position": str(row.get("badge_position") or "left"),
        "reminder_enabled": bool(row.get("reminder_enabled", True)),
    } for user_id, row in rows.items()}


async def get_daily_status(db, *, user_id: int) -> dict:
    await economy_ledger.ensure_tables(db)
    await vip_repo.ensure_tables(db)
    day_key = datetime.now(timezone.utc).date().isoformat()
    progress = await vip_repo.get_daily_progress(db, user_id=int(user_id))
    receipt = await vip_repo.find_daily_receipt(db, user_id=int(user_id), day_key=day_key)
    count = int(progress["completed_count"]) if progress else 0
    return {
        "day_boundary": "UTC", "day_key": day_key,
        "title": "Заверши одну игру", "completed_today": bool(receipt),
        "completed_count": count, "cycle_progress": count % 7,
        "next_milestone_in": 7 - (count % 7), "daily_reward_mora": 20,
        "milestone_reward_mora": 100, "milestone_reward_keys": 1,
        "missed_days_reset_progress": False,
    }


async def set_preferences(
    db, *, user_id: int, badge_id: str, badge_position: str, reminder_enabled: bool,
) -> dict:
    if badge_id not in VIP_BADGES:
        raise VipError("Неизвестный VIP-значок.")
    if badge_position not in {"left", "right", "both", "hidden"}:
        raise VipError("Некорректное положение VIP-значка.")
    if not await is_vip_active(db, int(user_id)):
        raise VipConflict("Настройки VIP доступны только при активном статусе.")
    await economy_ledger.ensure_tables(db)
    await vip_repo.ensure_tables(db)
    async with db.connection.transaction():
        await vip_repo.lock_user(db, int(user_id))
        if not await is_vip_active(db, int(user_id)):
            raise VipConflict("Срок VIP уже закончился. Обнови экран.")
        await vip_repo.save_preferences(
            db, user_id=int(user_id), badge_id=badge_id, badge_position=badge_position,
            reminder_enabled=bool(reminder_enabled),
        )
    return {"badge_id": badge_id, "badge": VIP_BADGES[badge_id],
            "badge_position": badge_position, "reminder_enabled": bool(reminder_enabled)}


async def complete_daily_mission_from_game(
    db, *, user_id: int, source_event_id: str, day_key: str,
) -> dict | None:
    """Complete today's easy mission once; missed calendar days never reset count."""
    if not await is_vip_active(db, int(user_id)):
        return None
    replay = await vip_repo.find_daily_receipt(db, user_id=int(user_id), day_key=day_key)
    if replay:
        return {"completed": True, "already_completed": True,
                "completion_no": int(replay["completion_no"]), "mora_reward": int(replay["mora_reward"]),
                "key_reward": bool(replay["chest_key_grant_id"])}
    progress = await vip_repo.get_daily_progress_for_update(db, user_id=int(user_id))
    completion_no = int(progress["completed_count"]) + 1
    milestone = completion_no % 7 == 0
    mora_reward = 20 + (100 if milestone else 0)
    mutation = await economy_ledger.apply_balance_change(
        db, int(user_id), {"mora": mora_reward}, reason_code="vip_daily_reward",
        idempotency_key=f"vip-daily:{int(user_id)}:{day_key}", source_type="vip_v2",
        reference_type="vip_daily", reference_id=f"{int(user_id)}:{day_key}",
        metadata={"policy_version": VIP_POLICY_VERSION, "completion_no": completion_no,
                  "milestone": milestone, "source_event_id": source_event_id},
        note="VIP-поручение дня",
    )
    key_grant_id = None
    if milestone:
        from core.chests_v1 import (POLICY_VERSION as CHEST_POLICY_VERSION, KeyGrant,
                                    canonical_snapshot_fingerprint, validate_key_grant)
        from infrastructure.repositories import chests_v1 as chest_repo
        await chest_repo.assert_delivery_ready(db)
        grant = validate_key_grant(KeyGrant(
            source_kind="vip_daily_milestone", source_event_id=f"{int(user_id)}:{day_key}", amount=1,
            source_snapshot={"vip_policy_version": VIP_POLICY_VERSION,
                             "completion_no": completion_no, "day_key": day_key},
        ))
        snapshot_hash = canonical_snapshot_fingerprint(grant.source_snapshot)
        existing = await chest_repo.find_grant(
            db, user_id=int(user_id), source_kind=grant.source_kind,
            source_event_id=grant.source_event_id,
        )
        if existing:
            key_grant_id = str(existing["id"])
        else:
            account = await chest_repo.lock_account(db, int(user_id))
            key_grant_id = uuid4().hex
            await chest_repo.apply_grant(
                db, grant_id=key_grant_id, user_id=int(user_id), source_kind=grant.source_kind,
                source_event_id=grant.source_event_id, amount=1, policy_version=CHEST_POLICY_VERSION,
                source_snapshot=dict(grant.source_snapshot), source_snapshot_hash=snapshot_hash,
                balance_before=int(account["balance"]), account_epoch=int(account["account_epoch"]),
            )
    await vip_repo.save_daily_completion(
        db, user_id=int(user_id), day_key=day_key, source_event_id=source_event_id,
        completion_no=completion_no, mora_reward=mora_reward,
        mora_operation_id=str(mutation.operation_id), chest_key_grant_id=key_grant_id,
    )
    return {"completed": True, "already_completed": False, "completion_no": completion_no,
            "streak_progress": completion_no % 7, "mora_reward": mora_reward,
            "key_reward": bool(key_grant_id)}


async def daily_reminder_candidates(db, *, now: datetime | None = None) -> list[int]:
    instant = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    if instant.hour < 18:
        return []
    await economy_ledger.ensure_tables(db)
    await vip_repo.ensure_tables(db)
    rows = await vip_repo.reminder_candidates(db, day_key=instant.date().isoformat())
    return [int(row["user_id"]) for row in rows]


async def record_daily_reminder_sent(db, *, user_id: int, now: datetime | None = None) -> None:
    instant = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    await vip_repo.mark_reminder_sent(db, user_id=int(user_id), day_key=instant.date().isoformat())

async def get_extra_pet_slots(db, user_id: int) -> int:
    return 0

async def get_vip_seniority_days(db, user_id: int) -> int:
    async with db.execute("SELECT COALESCE(total_days,0) FROM vip_subscriptions WHERE user_id=?",(user_id,)) as c:
        row=await c.fetchone()
    return int(row[0]) if row else 0
