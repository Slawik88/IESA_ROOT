"""One-time launch migration for Skins V3: refund Zarniki spent on the retired skins and cosmetics.

What happens, per player, in one transaction:
  1. The Zarniki the player actually paid for old skins and cosmetics is read from the economy ledger
     (their own purchase receipts, nothing is estimated) and credited back once.
  2. The old ownership (cosmetics, loadout, whole-app skins, selection) is copied to archive tables and removed,
     so nothing from the retired system stays visible or equipped.
  3. A row in skins_v3_migration marks the player as done. Repeating the run does nothing for them.
Purchases already covered by the one-time retirement compensation (made before its receipt) are not paid again.
Items obtained without paying (VIP perks, drops, gifts received) are archived without a refund.
The run starts in the background after the web process is up; SKINS_V3_MIGRATION=off disables it.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from loguru import logger

from infrastructure.repositories import economy_ledger
from infrastructure.repositories import skins_v3 as skins_repo
from infrastructure.repositories import web_notifications

REFUND_REASON = "skins_v3_migration_refund"
PURCHASE_REASONS = (
    "cosmetic_purchase", "cosmetic_lineup_purchase", "cosmetic_many_purchase",
    "cosmetic_gift_purchase", "global_skin_purchase",
)
ADVISORY_LOCK = 727301
BATCH = 40


@dataclass(frozen=True)
class Plan:
    user_id: int
    refund: int
    has_old_ownership: bool


async def ensure_tables(db) -> None:
    await skins_repo.ensure_tables(db)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS skins_v3_migration (
            user_id BIGINT PRIMARY KEY,
            refunded_zarniki BIGINT NOT NULL DEFAULT 0,
            cosmetics_archived INTEGER NOT NULL DEFAULT 0,
            skins_archived INTEGER NOT NULL DEFAULT 0,
            processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("CREATE TABLE IF NOT EXISTS skins_v3_archive_cosmetics (user_id BIGINT NOT NULL, cosmetic_id TEXT NOT NULL, acquired_at TIMESTAMP, equipped_slot TEXT, archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
    await db.execute("CREATE TABLE IF NOT EXISTS skins_v3_archive_global_skins (user_id BIGINT NOT NULL, skin_id TEXT NOT NULL, source TEXT, selected BOOLEAN NOT NULL DEFAULT FALSE, archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")


async def _table_exists(db, name: str) -> bool:
    async with db.execute("SELECT to_regclass(?)", (name,)) as c:
        return (await c.fetchone())[0] is not None


async def _refund_amounts(db) -> dict[int, int]:
    """Zarniki each player paid for old skins and cosmetics, minus purchases the retirement compensation already covered."""
    reasons = ",".join("?" for _ in PURCHASE_REASONS)
    covered = await _table_exists(db, "retirement_compensation_receipts_v2")
    join = "LEFT JOIN retirement_compensation_receipts_v2 r ON r.user_id = l.user_id" if covered else ""
    window = "AND (r.applied_at IS NULL OR l.created_at > r.applied_at)" if covered else ""
    async with db.execute(
        f"SELECT l.user_id, SUM(-l.delta) AS paid FROM economic_ledger l {join} "
        f"WHERE l.currency = 'zarniki' AND l.delta < 0 AND l.reason_code IN ({reasons}) {window} GROUP BY l.user_id",
        PURCHASE_REASONS,
    ) as c:
        return {int(r[0]): int(round(float(r[1]))) for r in await c.fetchall()}


async def build_plan(db) -> list[Plan]:
    """Everyone who still has something from the old system or paid for it, except players already migrated."""
    refunds = await _refund_amounts(db)
    owners: set[int] = set()
    for table in ("user_cosmetics", "user_cosmetic_loadout", "global_skin_v1_owned", "global_skin_v1_selection"):
        if await _table_exists(db, table):
            async with db.execute(f"SELECT DISTINCT user_id FROM {table}") as c:
                owners |= {int(r[0]) for r in await c.fetchall()}
    done: set[int] = set()
    if await _table_exists(db, "skins_v3_migration"):          # absent before the first launch: the plan is then read-only safe
        async with db.execute("SELECT user_id FROM skins_v3_migration") as c:
            done = {int(r[0]) for r in await c.fetchall()}
    return [Plan(uid, refunds.get(uid, 0), uid in owners) for uid in sorted((set(refunds) | owners) - done)]


async def apply_user(db, plan: Plan) -> bool:
    """Migrate one player. Returns False if someone else finished them first."""
    async with db.connection.transaction():
        await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (plan.user_id,))
        async with db.execute("SELECT 1 FROM users WHERE user_tg_id=? FOR UPDATE", (plan.user_id,)) as c:
            await c.fetchone()
        async with db.execute("SELECT 1 FROM skins_v3_migration WHERE user_id=?", (plan.user_id,)) as c:
            if await c.fetchone():
                return False
        archived_cosmetics = 0
        for old_table, archive in (("user_cosmetics", "cosmetics"), ("global_skin_v1_owned", "skins")):
            if not await _table_exists(db, old_table):
                continue
            if archive == "cosmetics":
                await db.execute(
                    "INSERT INTO skins_v3_archive_cosmetics(user_id, cosmetic_id, acquired_at, equipped_slot) "
                    "SELECT uc.user_id, uc.cosmetic_id, uc.acquired_at, lo.slot FROM user_cosmetics uc "
                    "LEFT JOIN user_cosmetic_loadout lo ON lo.user_id = uc.user_id AND lo.cosmetic_id = uc.cosmetic_id WHERE uc.user_id = ?",
                    (plan.user_id,))
                async with db.execute("SELECT COUNT(*) FROM user_cosmetics WHERE user_id=?", (plan.user_id,)) as c:
                    archived_cosmetics = int((await c.fetchone())[0])
                await db.execute("DELETE FROM user_cosmetics WHERE user_id=?", (plan.user_id,))
                # The welcome animation is not a skin: it stays in the loadout table and is kept.
                await db.execute("DELETE FROM user_cosmetic_loadout WHERE user_id=? AND slot <> 'welcome'", (plan.user_id,))
            else:
                await db.execute(
                    "INSERT INTO skins_v3_archive_global_skins(user_id, skin_id, source, selected) "
                    "SELECT o.user_id, o.skin_id, o.source, COALESCE(s.skin_id = o.skin_id, FALSE) FROM global_skin_v1_owned o "
                    "LEFT JOIN global_skin_v1_selection s ON s.user_id = o.user_id WHERE o.user_id = ?", (plan.user_id,))
                await db.execute("DELETE FROM global_skin_v1_owned WHERE user_id=?", (plan.user_id,))
                await db.execute("DELETE FROM global_skin_v1_selection WHERE user_id=?", (plan.user_id,))
        if plan.refund > 0:
            await economy_ledger.apply_balance_change(
                db, plan.user_id, {"zarniki": plan.refund}, reason_code=REFUND_REASON,
                idempotency_key=f"skins-v3-migration:{plan.user_id}", source_type="skins_v3_migration",
                reference_type="skins_v3_migration", reference_id=str(plan.user_id),
                metadata={"policy": "refund of Zarniki paid for retired skins and cosmetics", "amount": plan.refund},
                note="skins v3 refund")
            await web_notifications.add(db, plan.user_id, {
                "type": "admin_gift",
                "reason": "Скины обновились. Старые скины и косметика заменены новой системой, а Зарники, которые вы на них потратили, возвращены.",
                "gifts": [{"label": "Возврат Зарников", "amount": plan.refund}],
            })
        await db.execute(
            "INSERT INTO skins_v3_migration(user_id, refunded_zarniki, cosmetics_archived) VALUES (?,?,?)",
            (plan.user_id, plan.refund, archived_cosmetics))
    return True


async def run(db) -> dict:
    """Process everyone who is not done yet. Safe to call repeatedly and from several processes."""
    await economy_ledger.ensure_tables(db)
    await ensure_tables(db)
    async with db.execute("SELECT pg_try_advisory_lock(?)", (ADVISORY_LOCK,)) as c:
        if not (await c.fetchone())[0]:
            return {"skipped": "another process is migrating"}
    done = refunded = 0
    try:
        plans = await build_plan(db)
        for index, plan in enumerate(plans):
            try:
                if await apply_user(db, plan):
                    done += 1
                    refunded += plan.refund
            except Exception:
                logger.exception(f"skins_v3 migration failed for user {plan.user_id}; will retry on next start")
            if index % BATCH == BATCH - 1:
                await asyncio.sleep(0)       # let live requests through between batches
    finally:
        await db.execute("SELECT pg_advisory_unlock(?)", (ADVISORY_LOCK,))
    logger.info(f"skins_v3 migration: {done} players migrated, {refunded} Zarniki refunded")
    return {"players": done, "refunded_zarniki": refunded, "total_planned": len(plans)}


def enabled() -> bool:
    return os.getenv("SKINS_V3_MIGRATION", "on").strip().lower() not in {"off", "0", "false", "no"}
