"""One-time launch migration for Skins V3: refund Zarniki spent on the retired skins and cosmetics.

What happens, per player, in one transaction:
  1. The Zarniki the player actually paid for old skins and cosmetics is read from the economy ledger
     (their own purchase receipts, nothing is estimated) and credited back once.
  2. The old ownership (cosmetics, loadout, whole-app skins, selection) is copied to archive tables and removed,
     so nothing from the retired system stays visible or equipped.
  3. A row in skins_v3_migration marks the player as done. Repeating the run does nothing for them.
Purchases already paid back are not paid again: anything bought before the player's latest earlier refund (the retirement
compensation receipts, the July 2026 wipe/epoch/gap cosmetics refunds) is skipped, whatever number of receipts the player has.
Items obtained without paying (VIP perks, drops, gifts received) are archived without a refund.
A refund above SKINS_V3_REFUND_CAP (default 5000 Zarniki) is held for the owner: the player is left untouched until their id
is listed in SKINS_V3_APPROVED_USERS (comma separated). The plan script and the log show who is held.
The run starts in the background after the web process is up; SKINS_V3_MIGRATION=off disables it.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone

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
EARLIER_REFUND_ACTIONS = ("cosmetic_refund", "cosmetics_gap_refund", "cosmetics_lineup_wipe")   # admin_grant_log entries of the older one-off scripts


def refund_cap() -> int:
    try:
        return max(0, int(os.getenv("SKINS_V3_REFUND_CAP", "5000")))
    except ValueError:
        return 5000


def approved_users() -> frozenset[int]:
    return frozenset(int(x) for x in os.getenv("SKINS_V3_APPROVED_USERS", "").replace(";", ",").split(",") if x.strip().isdigit())


@dataclass(frozen=True)
class Plan:
    user_id: int
    refund: int
    has_old_ownership: bool

    @property
    def held(self) -> bool:
        """A large refund waits for the owner: nothing is paid or archived until the player is approved."""
        return self.refund > refund_cap() and self.user_id not in approved_users()


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


def _utc(moment) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


async def _earlier_refund_cutoffs(db) -> dict[int, datetime]:
    """{user_id: moment of the latest earlier refund}. Purchases before it were already paid back by an older mechanism."""
    parts = []
    if await _table_exists(db, "retirement_compensation_receipts_v2"):
        parts.append("SELECT user_id, applied_at AS ts FROM retirement_compensation_receipts_v2")
    if await _table_exists(db, "cosmetics_lineup_wipe_log"):
        parts.append("SELECT user_id, processed_at AS ts FROM cosmetics_lineup_wipe_log")
    if await _table_exists(db, "cosmetic_refund_log"):
        parts.append("SELECT user_id, refunded_at AS ts FROM cosmetic_refund_log")
    params: tuple = ()
    if await _table_exists(db, "admin_grant_log"):
        marks = ",".join("?" for _ in EARLIER_REFUND_ACTIONS)
        parts.append(f"SELECT target_id AS user_id, created_at AS ts FROM admin_grant_log WHERE action IN ({marks})")
        params = EARLIER_REFUND_ACTIONS
    if not parts:
        return {}
    async with db.execute("SELECT user_id, MAX(ts) FROM (" + " UNION ALL ".join(parts) + ") x GROUP BY user_id", params) as c:
        return {int(r[0]): _utc(r[1]) for r in await c.fetchall() if r[1] is not None}


async def _purchases(db) -> list[tuple]:
    reasons = ",".join("?" for _ in PURCHASE_REASONS)
    async with db.execute(
        f"SELECT user_id, -delta, created_at, reason_code FROM economic_ledger WHERE currency = 'zarniki' AND delta < 0 AND reason_code IN ({reasons}) ORDER BY created_at",
        PURCHASE_REASONS,
    ) as c:
        return [(int(r[0]), float(r[1]), _utc(r[2]), r[3]) for r in await c.fetchall()]


async def _refund_amounts(db) -> dict[int, int]:
    """Zarniki each player paid for old skins and cosmetics after their latest earlier refund (never counted twice)."""
    cutoffs = await _earlier_refund_cutoffs(db)
    totals: dict[int, float] = {}
    for user_id, paid, when, _reason in await _purchases(db):
        cut = cutoffs.get(user_id)
        if cut is None or (when is not None and when > cut):
            totals[user_id] = totals.get(user_id, 0.0) + paid
    return {uid: int(round(total)) for uid, total in totals.items()}


async def explain(db, user_id: int) -> dict:
    """Read-only breakdown of one player's refund: what was paid, what the earlier refunds cover, what is left."""
    cutoffs = await _earlier_refund_cutoffs(db)
    cut = cutoffs.get(int(user_id))
    rows = [r for r in await _purchases(db) if r[0] == int(user_id)]
    by_reason: dict[str, dict] = {}
    counted = 0.0
    for _uid, paid, when, reason in rows:
        item = by_reason.setdefault(reason, {"count": 0, "sum": 0.0, "first": when, "last": when})
        item["count"] += 1; item["sum"] += paid; item["last"] = when
        if cut is None or (when is not None and when > cut):
            counted += paid
    sources: dict[str, object] = {}
    if await _table_exists(db, "retirement_compensation_receipts_v2"):
        async with db.execute("SELECT snapshot_id, applied_at, cosmetics_zarniki, zarniki_carry FROM retirement_compensation_receipts_v2 WHERE user_id = ?", (int(user_id),)) as c:
            sources["compensation_receipts"] = [{"snapshot": r[0], "applied_at": _utc(r[1]), "cosmetics_zarniki": r[2], "zarniki_carry": r[3]} for r in await c.fetchall()]
    if await _table_exists(db, "admin_grant_log"):
        marks = ",".join("?" for _ in EARLIER_REFUND_ACTIONS)
        async with db.execute(f"SELECT action, amount, created_at FROM admin_grant_log WHERE target_id = ? AND action IN ({marks}) ORDER BY created_at", (int(user_id), *EARLIER_REFUND_ACTIONS)) as c:
            sources["earlier_refunds"] = [{"action": r[0], "amount": r[1], "at": _utc(r[2])} for r in await c.fetchall()]
    async with db.execute("SELECT COALESCE(user_balance_zarniki,0) FROM users WHERE user_tg_id = ?", (int(user_id),)) as c:
        row = await c.fetchone()
    top = sorted(rows, key=lambda r: -r[1])[:8]
    return {"user_id": int(user_id), "balance_zarniki": float(row[0]) if row else 0.0, "cutoff": cut, "paid_total": sum(r[1] for r in rows), "counted_refund": int(round(counted)),
            "by_reason": by_reason, "sources": sources, "largest": [{"paid": r[1], "reason": r[3], "at": r[2]} for r in top]}


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
    """Migrate one player. Returns False if someone else finished them first or the refund is held for the owner."""
    if plan.held:
        return False
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
    done = refunded = held = 0
    try:
        plans = await build_plan(db)
        for index, plan in enumerate(plans):
            if plan.held:
                held += 1
                logger.warning(f"skins_v3 migration: refund of {plan.refund} Zarniki for user {plan.user_id} is above the cap {refund_cap()} and waits for approval (SKINS_V3_APPROVED_USERS)")
                continue
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
    logger.info(f"skins_v3 migration: {done} players migrated, {refunded} Zarniki refunded, {held} held for approval")
    return {"players": done, "refunded_zarniki": refunded, "held": held, "total_planned": len(plans)}


def enabled() -> bool:
    return os.getenv("SKINS_V3_MIGRATION", "on").strip().lower() not in {"off", "0", "false", "no"}
