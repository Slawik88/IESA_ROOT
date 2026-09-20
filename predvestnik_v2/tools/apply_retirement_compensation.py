#!/usr/bin/env python3
"""Apply one frozen compensation inventory exactly once to a prepared target DB."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.economy_ledger import apply_balance_change, ensure_tables


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_inventory(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    expected = str(data.pop("inventory_sha256", ""))
    actual = hashlib.sha256(canonical(data).encode()).hexdigest()
    data["inventory_sha256"] = expected
    if not expected or actual != expected:
        raise ValueError("inventory checksum mismatch")
    if data.get("policy_version") != "retirement-compensation-value-preserving-v4":
        raise ValueError("unsupported compensation policy")
    return data


async def ensure_receipts(db: PGAdapter) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS retirement_compensation_receipts_v2 (
            snapshot_id TEXT NOT NULL,
            user_id BIGINT NOT NULL,
            policy_version TEXT NOT NULL,
            source_fingerprint TEXT NOT NULL,
            zarniki_carry INTEGER NOT NULL CHECK(zarniki_carry >= 0),
            cosmetics_zarniki INTEGER NOT NULL CHECK(cosmetics_zarniki >= 0),
            themes_zarniki INTEGER NOT NULL CHECK(themes_zarniki >= 0),
            donate_inventory_zarniki INTEGER NOT NULL CHECK(donate_inventory_zarniki >= 0),
            mora_compensation INTEGER NOT NULL CHECK(mora_compensation >= 0),
            diamonds_compensation INTEGER NOT NULL CHECK(diamonds_compensation >= 0),
            retired_exchange_zarniki INTEGER NOT NULL CHECK(retired_exchange_zarniki >= 0),
            legacy_score BIGINT NOT NULL CHECK(legacy_score >= 0),
            vip_seconds INTEGER NOT NULL CHECK(vip_seconds >= 0),
            vip_preserved_seconds INTEGER NOT NULL DEFAULT 0 CHECK(vip_preserved_seconds >= 0),
            vip_bonus_seconds INTEGER NOT NULL DEFAULT 0 CHECK(vip_bonus_seconds >= 0),
            source_summary JSONB NULL,
            economy_operation_id TEXT NULL UNIQUE
              REFERENCES economic_operations(id) ON DELETE RESTRICT,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(snapshot_id, user_id)
        )
    """)
    await db.execute(
        "ALTER TABLE retirement_compensation_receipts_v2 "
        "ALTER COLUMN economy_operation_id DROP NOT NULL"
    )
    await db.execute("ALTER TABLE retirement_compensation_receipts_v2 ADD COLUMN IF NOT EXISTS vip_preserved_seconds INTEGER NOT NULL DEFAULT 0 CHECK(vip_preserved_seconds >= 0)")
    await db.execute("ALTER TABLE retirement_compensation_receipts_v2 ADD COLUMN IF NOT EXISTS vip_bonus_seconds INTEGER NOT NULL DEFAULT 0 CHECK(vip_bonus_seconds >= 0)")
    await db.execute("ALTER TABLE retirement_compensation_receipts_v2 ADD COLUMN IF NOT EXISTS source_summary JSONB NULL")


async def apply_user(db: PGAdapter, inventory: dict, record: dict) -> str:
    snapshot_id = str(inventory["snapshot_id"])
    policy = str(inventory["policy_version"])
    user_id = int(record["user_id"])
    fingerprint = str(record["source_fingerprint"])
    carry = int(record["protected_carry"]["zarniki_before_compensation"])
    conversion = record["retired_asset_conversion"]
    cosmetics_zarniki = int(conversion["cosmetics_zarniki"])
    themes_zarniki = int(conversion["themes_zarniki"])
    progress = record["legacy_progress_conversion"]
    donate_inventory_zarniki = int(progress["donate_inventory_zarniki"])
    mora_compensation = int(progress["mora"])
    diamonds_compensation = int(progress["diamonds"])
    retired_exchange_zarniki = int(record["retired_exchange_refund"]["zarniki_spent"])
    legacy_score = int(progress["legacy_score"])
    conversion_total = (cosmetics_zarniki + themes_zarniki + donate_inventory_zarniki
                        + retired_exchange_zarniki)
    final_zarniki = int(record["zarniki_after_compensation"])
    vip = record["protected_carry"]["vip_after_update"]
    vip_seconds = int(vip["total_seconds_from_migration"])
    vip_preserved_seconds = int(vip["preserved_seconds"])
    vip_bonus_seconds = int(vip["update_bonus_seconds"])
    snapshot = record["legacy_snapshot"]
    source_summary = {
        "old_balances": {key: snapshot[key] for key in ("mora", "diamonds", "dark_mora", "crystals")},
        "retired_counts": {
            "inventory": len(snapshot["inventory"]), "pets": len(snapshot["pets"]),
            "units": len(snapshot["units"]), "relics": len(snapshot["relics"]),
            "cosmetics": len(conversion["cosmetics"]), "themes": len(conversion["themes"]),
        },
        "score_breakdown": progress["score_breakdown"],
    }

    async with db.connection.transaction():
        async with db.execute(
            "SELECT source_fingerprint,zarniki_carry,cosmetics_zarniki,themes_zarniki,"
            "donate_inventory_zarniki,mora_compensation,diamonds_compensation,"
            "retired_exchange_zarniki,legacy_score,vip_seconds "
            "FROM retirement_compensation_receipts_v2 WHERE snapshot_id=? AND user_id=? FOR UPDATE",
            (snapshot_id, user_id),
        ) as cursor:
            existing = await cursor.fetchone()
        if existing:
            actual = tuple(existing)
            expected = (fingerprint, carry, cosmetics_zarniki, themes_zarniki,
                        donate_inventory_zarniki, mora_compensation, diamonds_compensation,
                        retired_exchange_zarniki, legacy_score,
                        vip_seconds)
            if actual != expected:
                raise RuntimeError(f"compensation receipt conflict for user {user_id}")
            return "replayed"

        await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,))
        async with db.execute(
            "SELECT COALESCE(user_balance_zarniki,0),COALESCE(user_balance_mora,0),"
            "COALESCE(user_balance_diamonds,0),COALESCE(user_balance_dark_mora,0),"
            "COALESCE(user_balance_crystals,0) FROM users WHERE user_tg_id=? FOR UPDATE",
            (user_id,),
        ) as cursor:
            current_row = await cursor.fetchone()
            current = int(current_row[0])
        if current == 0:
            delta = final_zarniki
        elif current >= carry:
            # Production remains online during the migration. Preserve every
            # post-snapshot credit/debit already reflected in the live balance
            # and add only the frozen conversion component.
            delta = conversion_total
        else:
            raise RuntimeError(
                f"unexpected Zarniki baseline for user {user_id}: {current}; expected 0 or {carry}"
            )
        currency_deltas = {"zarniki": delta}
        for index, currency, target in ((1, "mora", mora_compensation),
                                        (2, "diamonds", diamonds_compensation),
                                        (3, "dark_mora", 0)):
            current_value = float(current_row[index])
            source_value = float(snapshot[currency])
            if abs(current_value) < 1e-9:
                currency_deltas[currency] = target
            else:
                # Apply the frozen replacement as a delta, not an assignment:
                # current + (target - snapshot) keeps legitimate activity that
                # happened after the snapshot. Never drive a live balance below
                # zero if a player already spent more than the retired amount.
                currency_deltas[currency] = max(-current_value, target - source_value)
        if abs(float(current_row[4])) > 1e-9:
            raise RuntimeError(f"legacy crystals require an explicit policy for user {user_id}")
        mutation = None
        if any(abs(float(value)) > 1e-9 for value in currency_deltas.values()):
            mutation = await apply_balance_change(
                db,
                user_id,
                currency_deltas,
                reason_code="retirement_compensation_v2",
                idempotency_key=f"retirement:{snapshot_id}:{user_id}",
                source_type="migration",
                reference_type="retirement_snapshot",
                reference_id=snapshot_id,
                metadata={
                    "policy_version": policy,
                    "source_fingerprint": fingerprint,
                    "zarniki_carry": carry,
                    "cosmetics_zarniki": cosmetics_zarniki,
                    "themes_zarniki": themes_zarniki,
                    "donate_inventory_zarniki": donate_inventory_zarniki,
                    "mora_compensation": mora_compensation,
                    "diamonds_compensation": diamonds_compensation,
                    "retired_exchange_zarniki": retired_exchange_zarniki,
                    "legacy_score": legacy_score,
                    "retired_cosmetic_ids": [x["cosmetic_id"] for x in conversion["cosmetics"]],
                    "retired_theme_ids": [x["theme_id"] for x in conversion["themes"]],
                },
            )

        cosmetic_ids = [str(x["cosmetic_id"]) for x in conversion["cosmetics"]]
        theme_ids = [str(x["theme_id"]) for x in conversion["themes"]]
        if cosmetic_ids:
            await db.connection.execute(
                "DELETE FROM user_cosmetics WHERE user_id=$1 AND cosmetic_id=ANY($2::text[])",
                user_id, cosmetic_ids,
            )
        if theme_ids:
            await db.connection.execute(
                "DELETE FROM user_themes WHERE user_id=$1 AND theme_id=ANY($2::text[])",
                user_id, theme_ids,
            )
        await db.execute(
            "UPDATE users SET account_xp=?,account_level=? WHERE user_tg_id=?",
            (int(snapshot["account_xp"]), int(snapshot["account_level"]), user_id),
        )
        await db.execute("DELETE FROM inventory WHERE user_id=?", (user_id,))
        await db.execute("DELETE FROM pets WHERE owner_id=?", (user_id,))
        await db.execute("DELETE FROM user_units WHERE user_id=?", (user_id,))
        await db.execute("DELETE FROM user_relics WHERE user_id=?", (user_id,))

        if vip_seconds > 0:
            bonus_seconds = int(vip["update_bonus_seconds"])
            await db.execute(
                "INSERT INTO vip_subscriptions(user_id,tier,started_at,expires_at,expiry_notified,total_days) "
                "VALUES (?,?,NOW(),NOW()+make_interval(secs => ?),FALSE,CEIL(? / 86400.0)::integer) "
                "ON CONFLICT(user_id) DO UPDATE SET tier=EXCLUDED.tier,started_at=NOW(),"
                "expires_at=EXCLUDED.expires_at,expiry_notified=FALSE,"
                "total_days=COALESCE(vip_subscriptions.total_days,0)+CEIL(? / 86400.0)::integer",
                (user_id, str(vip["tier"]), vip_seconds, vip_seconds, bonus_seconds),
            )
        await db.execute(
            "INSERT INTO retirement_compensation_receipts_v2 "
            "(snapshot_id,user_id,policy_version,source_fingerprint,zarniki_carry,"
            "cosmetics_zarniki,themes_zarniki,donate_inventory_zarniki,mora_compensation,"
            "diamonds_compensation,retired_exchange_zarniki,legacy_score,vip_seconds,economy_operation_id,"
            "vip_preserved_seconds,vip_bonus_seconds,source_summary) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (snapshot_id, user_id, policy, fingerprint, carry, cosmetics_zarniki,
             themes_zarniki, donate_inventory_zarniki, mora_compensation,
             diamonds_compensation, retired_exchange_zarniki, legacy_score,
             vip_seconds, mutation.operation_id if mutation else None,
             vip_preserved_seconds, vip_bonus_seconds, source_summary),
        )
    return "applied"


async def run(args) -> None:
    inventory = load_inventory(args.inventory)
    summary = inventory["summary"]
    if not args.apply:
        print(json.dumps({"mode": "dry-run", "summary": summary,
                          "inventory_sha256": inventory["inventory_sha256"]}))
        return
    if args.confirmation != inventory["inventory_sha256"]:
        raise ValueError("--confirmation must equal the internal inventory SHA-256")

    connection = await asyncpg.connect(args.dsn)
    db = PGAdapter(connection)
    try:
        await ensure_tables(db)
        await ensure_receipts(db)
        results = {"applied": 0, "replayed": 0}
        for record in inventory["users"]:
            status = await apply_user(db, inventory, record)
            results[status] += 1
        print(json.dumps({"mode": "apply", "results": results, "summary": summary}))
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=False)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirmation")
    args = parser.parse_args()
    if args.apply and not args.dsn:
        parser.error("--dsn is required with --apply")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
