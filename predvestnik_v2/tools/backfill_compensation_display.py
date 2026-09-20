#!/usr/bin/env python3
"""Backfill display-only compensation facts from the frozen signed inventory.

This never touches balances or entitlements. Every row is locked and must match
the immutable source fingerprint written by the original migration.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import asyncpg

from apply_retirement_compensation import load_inventory


async def run(dsn: str, inventory_path: Path, confirmation: str) -> None:
    inventory = load_inventory(inventory_path)
    if confirmation != inventory.get("inventory_sha256"):
        raise ValueError("--confirmation must equal the frozen inventory SHA-256")
    connection = await asyncpg.connect(dsn)
    updated = 0
    try:
        async with connection.transaction():
            await connection.execute("ALTER TABLE retirement_compensation_receipts_v2 ADD COLUMN IF NOT EXISTS vip_preserved_seconds INTEGER NOT NULL DEFAULT 0 CHECK(vip_preserved_seconds >= 0)")
            await connection.execute("ALTER TABLE retirement_compensation_receipts_v2 ADD COLUMN IF NOT EXISTS vip_bonus_seconds INTEGER NOT NULL DEFAULT 0 CHECK(vip_bonus_seconds >= 0)")
            await connection.execute("ALTER TABLE retirement_compensation_receipts_v2 ADD COLUMN IF NOT EXISTS source_summary JSONB NULL")
            for record in inventory["users"]:
                user_id = int(record["user_id"])
                row = await connection.fetchrow(
                    "SELECT source_fingerprint FROM retirement_compensation_receipts_v2 "
                    "WHERE snapshot_id=$1 AND user_id=$2 FOR UPDATE",
                    inventory["snapshot_id"], user_id,
                )
                if not row or str(row["source_fingerprint"]) != str(record["source_fingerprint"]):
                    raise RuntimeError(f"receipt fingerprint mismatch for user {user_id}")
                snapshot = record["legacy_snapshot"]
                conversion = record["retired_asset_conversion"]
                progress = record["legacy_progress_conversion"]
                vip = record["protected_carry"]["vip_after_update"]
                summary = {
                    "old_balances": {key: snapshot[key] for key in ("mora", "diamonds", "dark_mora", "crystals")},
                    "retired_counts": {
                        "inventory": len(snapshot["inventory"]), "pets": len(snapshot["pets"]),
                        "units": len(snapshot["units"]), "relics": len(snapshot["relics"]),
                        "cosmetics": len(conversion["cosmetics"]), "themes": len(conversion["themes"]),
                    },
                    "score_breakdown": progress["score_breakdown"],
                }
                result = await connection.execute(
                    "UPDATE retirement_compensation_receipts_v2 SET "
                    "vip_preserved_seconds=$1,vip_bonus_seconds=$2,source_summary=$3::jsonb "
                    "WHERE snapshot_id=$4 AND user_id=$5",
                    int(vip["preserved_seconds"]), int(vip["update_bonus_seconds"]),
                    json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
                    inventory["snapshot_id"], user_id,
                )
                if result != "UPDATE 1":
                    raise RuntimeError(f"unexpected update result for user {user_id}: {result}")
                updated += 1
            count = await connection.fetchval(
                "SELECT COUNT(*) FROM retirement_compensation_receipts_v2 "
                "WHERE snapshot_id=$1 AND source_summary IS NOT NULL",
                inventory["snapshot_id"],
            )
            if int(count) != len(inventory["users"]):
                raise RuntimeError(f"display backfill incomplete: {count}/{len(inventory['users'])}")
    finally:
        await connection.close()
    print(json.dumps({"ok": True, "updated": updated, "snapshot_id": inventory["snapshot_id"]}))


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True)
parser.add_argument("--inventory", required=True, type=Path)
parser.add_argument("--confirmation", required=True)
args = parser.parse_args()
asyncio.run(run(args.dsn, args.inventory, args.confirmation))
