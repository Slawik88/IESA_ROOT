#!/usr/bin/env python3
"""Build a deterministic per-user compensation inventory from a local snapshot."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.cosmetics import COSMETICS
from core.themes import THEMES


POLICY_VERSION = "retirement-compensation-value-preserving-v4"
LOCAL_HOSTS = {None, "localhost", "127.0.0.1", "::1"}
UPDATE_VIP_SECONDS = 0
THEME_RARITY_ZARNIKI = {
    "common": 100,
    "uncommon": 150,
    "rare": 200,
    "seasonal": 250,
    "epic": 300,
    "shadow": 350,
    "legendary": 400,
    "mythic": 500,
}

NON_PAID_MORA_CAP = 2_000
ITEM_MORA_VALUES = {
    "abyss_shard": 2, "exp_boost_1h": 20, "exp_boost_2h": 35,
    "exp_boost_4h": 60, "food_basic": 2, "food_elite": 8,
    "food_energy": 10, "food_fried": 4, "food_stew": 6,
    "food_super": 12, "lucky_charm": 25, "potion_luck_m": 30,
    "potion_luck_s": 15, "potion_sprint": 15, "soul_shard": 2,
    "spin_token": 5, "spin_token_diamond": 50, "star_dust_l": 25,
    "star_dust_s": 5, "study_notes": 10, "treasure_map": 25,
}
DONATE_ITEM_ZARNIKI = {
    "zarniki_cooldown_skip": 50,
    "zarniki_nickname_token": 20,
    "cosmetic_shard": 10,
    "cos_avatar_frame_bronze": 100,
    "cos_name_glow_silver": 100,
}
ITEM_SCORE_VALUES = {
    "abyss_shard": 100, "exp_boost_1h": 300, "exp_boost_2h": 500,
    "exp_boost_4h": 900, "food_basic": 135, "food_elite": 560,
    "food_energy": 600, "food_fried": 255, "food_stew": 400,
    "food_super": 850, "lucky_charm": 900, "potion_luck_m": 1200,
    "potion_luck_s": 400, "potion_sprint": 500, "soul_shard": 20,
    "spin_token": 600, "spin_token_diamond": 5000, "star_dust_l": 1500,
    "star_dust_s": 200, "study_notes": 300, "treasure_map": 900,
}


def _vip_seconds_from_score(score: int) -> int:
    """Continuous diminishing conversion: every point is retained, no rounding loss."""
    remaining = max(0, int(score))
    days = Decimal(0)
    first = min(remaining, 300_000)
    days += Decimal(first) / Decimal(10_000)
    remaining -= first
    second = min(remaining, 700_000)
    days += Decimal(second) / Decimal(20_000)
    remaining -= second
    days += Decimal(remaining) / Decimal(50_000)
    return int(days * Decimal(86_400))


def _tier(value: Decimal, bands: tuple[tuple[Decimal, int], ...]) -> int:
    result = 0
    for threshold, award in bands:
        if value >= threshold:
            result = award
    return result


def _legacy_progress_conversion(snapshot: dict, exchange: dict) -> dict:
    old_mora = max(Decimal("0"), Decimal(snapshot["mora"]))
    old_diamonds = max(Decimal("0"), Decimal(snapshot["diamonds"]))
    old_dark_mora = max(Decimal("0"), Decimal(snapshot["dark_mora"]))
    mora_balance = _tier(old_mora, (
        (Decimal("1"), 100), (Decimal("1000"), 250),
        (Decimal("5000"), 500), (Decimal("20000"), 750),
        (Decimal("100000"), 1000),
    ))
    diamonds = _tier(old_diamonds, (
        (Decimal("1"), 2), (Decimal("10"), 5), (Decimal("30"), 10),
        (Decimal("75"), 15), (Decimal("150"), 20),
    ))
    dark_mora = _tier(old_dark_mora, (
        (Decimal("1"), 50), (Decimal("25"), 100), (Decimal("100"), 200),
    ))
    inventory_mora = 0
    donate_zarniki = 0
    item_lines = []
    for item in snapshot["inventory"]:
        item_id, quantity = str(item["item_id"]), int(item["quantity"])
        if item_id in DONATE_ITEM_ZARNIKI:
            unit = DONATE_ITEM_ZARNIKI[item_id]
            donate_zarniki += unit * quantity
            item_lines.append({"item_id": item_id, "quantity": quantity,
                               "currency": "zarniki", "unit_value": unit})
        elif item_id in ITEM_MORA_VALUES:
            unit = ITEM_MORA_VALUES[item_id]
            inventory_mora += unit * quantity
            item_lines.append({"item_id": item_id, "quantity": quantity,
                               "currency": "mora", "unit_value": unit})
        else:
            raise ValueError(f"legacy item has no compensation valuation: {item_id}")

    pet_mora_raw = sum(25 + 5 * max(1, int(p["pet_level"] or 1)) for p in snapshot["pets"])
    unit_mora_raw = sum(30 + 10 * max(1, int(u["level"] or 1)) for u in snapshot["units"])
    relic_mora_raw = 100 * len(snapshot["relics"])
    components = {
        "legacy_mora_tier": mora_balance,
        "legacy_dark_mora_tier": dark_mora,
        "inventory_mora": min(750, inventory_mora),
        "pets_mora": min(500, pet_mora_raw),
        "units_mora": min(300, unit_mora_raw),
        "relics_mora": min(200, relic_mora_raw),
    }
    protected_mora = max(Decimal(0), old_mora - Decimal(str(exchange["mora_received"])))
    protected_diamonds = max(Decimal(0), old_diamonds - Decimal(str(exchange["diamonds_received"])))
    balance_score = int(protected_mora + protected_diamonds * Decimal(3000)
                        + old_dark_mora * Decimal(1000))
    inventory_score = sum(
        ITEM_SCORE_VALUES.get(str(item["item_id"]), 0) * int(item["quantity"])
        for item in snapshot["inventory"]
    )
    pet_score = sum(
        5_000 + 2_000 * max(1, int(p["pet_level"] or 1))
        + 500 * max(0, int(p["duplicates_collected"] or 0))
        for p in snapshot["pets"]
    )
    unit_score = sum(
        8_000 + 3_000 * max(1, int(u["level"] or 1)) + 200 * max(0, int(u["shards"] or 0))
        for u in snapshot["units"]
    )
    relic_score = 25_000 * len(snapshot["relics"])
    retained_score = (min(NON_PAID_MORA_CAP, sum(components.values()))
                      + diamonds * 3000)
    legacy_score = max(0, balance_score + inventory_score + pet_score + unit_score
                       + relic_score - retained_score)
    return {
        "mora": min(NON_PAID_MORA_CAP, sum(components.values())),
        "diamonds": diamonds,
        "donate_inventory_zarniki": donate_zarniki,
        "components_before_total_cap": components,
        "item_lines": item_lines,
        "legacy_score": legacy_score,
        "score_breakdown": {
            "balances": balance_score, "inventory": inventory_score,
            "pets": pet_score, "units": unit_score, "relics": relic_score,
            "retained_liquid_value": retained_score,
        },
        "vip_seconds_from_score": _vip_seconds_from_score(legacy_score),
    }


def _cosmetic_zarniki(cosmetic_id: str) -> int:
    definition = COSMETICS.get(cosmetic_id)
    if not definition:
        raise ValueError(f"owned cosmetic has no current valuation: {cosmetic_id}")
    values = [int(price["zarniki"]) for price in definition.get("price", ()) if price.get("zarniki")]
    if len(values) != 1 or values[0] <= 0:
        raise ValueError(f"owned cosmetic has ambiguous Zarniki valuation: {cosmetic_id}")
    return values[0]


def _theme_zarniki(theme_id: str) -> int:
    definition = THEMES.get(theme_id)
    if not definition:
        raise ValueError(f"owned theme has no legacy valuation: {theme_id}")
    direct = definition.get("price_zarniki")
    if direct is not None:
        value = int(direct)
    else:
        value = THEME_RARITY_ZARNIKI.get(str(definition.get("rarity")), 0)
    if value <= 0:
        raise ValueError(f"owned theme has ambiguous Zarniki valuation: {theme_id}")
    return value


def _validate(dsn: str, cutoff_text: str) -> datetime:
    parsed = urlparse(dsn)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in LOCAL_HOSTS:
        raise ValueError("compensation inventory accepts only an explicit local PostgreSQL snapshot")
    cutoff = datetime.fromisoformat(cutoff_text.replace("Z", "+00:00"))
    if cutoff.tzinfo is None:
        raise ValueError("cutoff must include a timezone")
    return cutoff.astimezone(timezone.utc)


def _value(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_value)


async def _rows(conn, sql: str, *args) -> list[dict]:
    return [dict(row) for row in await conn.fetch(sql, *args)]


async def build(dsn: str, snapshot_id: str, cutoff: datetime) -> dict:
    conn = await asyncpg.connect(dsn, server_settings={"default_transaction_read_only": "on"})
    tx = conn.transaction(readonly=True, isolation="repeatable_read")
    await tx.start()
    try:
        users = await _rows(conn, """
            SELECT user_tg_id AS user_id, user_balance_mora AS mora,
                   user_balance_diamonds AS diamonds,
                   user_balance_dark_mora AS dark_mora,
                   user_balance_zarniki AS zarniki,
                   user_balance_crystals AS crystals,
                   account_xp, account_level
            FROM predvestnik.users
            WHERE deleted_at IS NULL
            ORDER BY user_tg_id
        """)
        cosmetics = await _rows(conn, """
            SELECT user_id, cosmetic_id, acquired_at FROM predvestnik.user_cosmetics
            ORDER BY user_id, cosmetic_id
        """)
        themes = await _rows(conn, """
            SELECT user_id, theme_id, acquired_at FROM predvestnik.user_themes
            ORDER BY user_id, theme_id
        """)
        inventory = await _rows(conn, """
            SELECT user_id, item_id, quantity FROM predvestnik.inventory
            WHERE quantity > 0 ORDER BY user_id, item_id
        """)
        vip = await _rows(conn, """
            SELECT user_id, tier, started_at, expires_at, total_days
            FROM predvestnik.vip_subscriptions ORDER BY user_id
        """)
        pets = await _rows(conn, """
            SELECT id, owner_id AS user_id, species_id, rarity, pet_level,
                   duplicates_collected, copy_index, created_at
            FROM predvestnik.pets ORDER BY owner_id, id
        """)
        units = await _rows(conn, """
            SELECT user_id, unit_id, level, shards, obtained_at
            FROM predvestnik.user_units ORDER BY user_id, unit_id
        """)
        relics = await _rows(conn, """
            SELECT user_id, relic_id, acquired_at FROM predvestnik.user_relics
            ORDER BY user_id, relic_id
        """)
        expedition_refunds = await _rows(conn, """
            SELECT p.owner_id AS user_id, COALESCE(SUM(e.cost_mora), 0)::numeric AS mora
            FROM predvestnik.active_expeditions e
            JOIN predvestnik.pets p ON p.id = e.pet_id
            GROUP BY p.owner_id ORDER BY p.owner_id
        """)
        zarniki_sources = await _rows(conn, """
            SELECT user_id, source, count(*)::bigint AS rows,
                   sum(delta_zarniki)::numeric AS delta
            FROM predvestnik.wallet_log
            WHERE delta_zarniki <> 0
            GROUP BY user_id, source ORDER BY user_id, source
        """)
        exchanges = await _rows(conn, """
            SELECT user_id, -SUM(delta_zarniki)::numeric AS zarniki_spent,
                   SUM(delta_mora)::numeric AS mora_received,
                   SUM(delta_diamonds)::numeric AS diamonds_received
            FROM predvestnik.wallet_log
            WHERE source='zarniki_exchange' AND delta_zarniki < 0
            GROUP BY user_id ORDER BY user_id
        """)

        by_user = {int(row["user_id"]): {
            "user_id": int(row["user_id"]),
            "protected_carry": {
                "zarniki_before_compensation": int(row["zarniki"]),
                "vip": None,
            },
            "retired_asset_conversion": {
                "cosmetics": [], "themes": [],
                "cosmetics_zarniki": 0, "themes_zarniki": 0,
            },
            "legacy_snapshot": {
                "mora": str(Decimal(str(row["mora"]))),
                "diamonds": str(Decimal(str(row["diamonds"]))),
                "dark_mora": str(Decimal(str(row["dark_mora"]))),
                "crystals": str(Decimal(str(row["crystals"]))),
                "account_xp": int(row["account_xp"] or 0),
                "account_level": int(row["account_level"] or 0),
                "inventory": [], "pets": [], "units": [], "relics": [],
            },
            "zarniki_provenance": [],
            "manual_review": [],
            "protected_legacy_refunds": {"expedition_prepaid_mora": 0},
            "retired_exchange_refund": {"zarniki_spent": 0, "mora_received": "0", "diamonds_received": "0"},
        } for row in users}

        for row in cosmetics:
            if int(row["user_id"]) in by_user:
                value = _cosmetic_zarniki(str(row["cosmetic_id"]))
                target = by_user[int(row["user_id"])]["retired_asset_conversion"]
                target["cosmetics"].append({"cosmetic_id": row["cosmetic_id"], "zarniki": value})
                target["cosmetics_zarniki"] += value
        for row in themes:
            if int(row["user_id"]) in by_user:
                value = _theme_zarniki(str(row["theme_id"]))
                target = by_user[int(row["user_id"])]["retired_asset_conversion"]
                target["themes"].append({"theme_id": row["theme_id"], "zarniki": value})
                target["themes_zarniki"] += value
        for row in inventory:
            if int(row["user_id"]) in by_user:
                by_user[int(row["user_id"])]["legacy_snapshot"]["inventory"].append({
                    "item_id": row["item_id"], "quantity": int(row["quantity"]),
                })
        for row in pets:
            if int(row["user_id"]) in by_user:
                by_user[int(row["user_id"])]["legacy_snapshot"]["pets"].append({
                    key: _value(row[key]) for key in (
                        "id", "species_id", "rarity", "pet_level",
                        "duplicates_collected", "copy_index", "created_at",
                    )
                })
        for row in units:
            if int(row["user_id"]) in by_user:
                by_user[int(row["user_id"])]["legacy_snapshot"]["units"].append({
                    key: _value(row[key]) for key in ("unit_id", "level", "shards", "obtained_at")
                })
        for row in relics:
            if int(row["user_id"]) in by_user:
                by_user[int(row["user_id"])]["legacy_snapshot"]["relics"].append({
                    "relic_id": row["relic_id"], "acquired_at": _value(row["acquired_at"]),
                })
        for row in expedition_refunds:
            uid = int(row["user_id"])
            if uid in by_user:
                by_user[uid]["protected_legacy_refunds"]["expedition_prepaid_mora"] = int(row["mora"])
        for row in exchanges:
            uid = int(row["user_id"])
            if uid in by_user:
                by_user[uid]["retired_exchange_refund"] = {
                    "zarniki_spent": int(row["zarniki_spent"]),
                    "mora_received": str(row["mora_received"]),
                    "diamonds_received": str(row["diamonds_received"]),
                }
        for row in vip:
            uid = int(row["user_id"])
            if uid not in by_user:
                continue
            expires = row["expires_at"].replace(tzinfo=timezone.utc)
            seconds = max(0, int((expires - cutoff).total_seconds()))
            by_user[uid]["protected_carry"]["vip"] = {
                "tier": row["tier"], "remaining_seconds": seconds,
                "original_expires_at": _value(row["expires_at"]),
                "total_days": int(row["total_days"] or 0),
            }
        for row in zarniki_sources:
            uid = int(row["user_id"])
            if uid in by_user:
                by_user[uid]["zarniki_provenance"].append({
                    "source": row["source"], "rows": int(row["rows"]), "delta": str(row["delta"]),
                })

        for record in by_user.values():
            zarniki = record["protected_carry"]["zarniki_before_compensation"]
            if zarniki < 0:
                record["manual_review"].append("negative_zarniki")
            if any(p["source"] in {"dev_console", "promocode"} for p in record["zarniki_provenance"]):
                record["manual_review"].append("non_stars_zarniki_source_present")
            if any(p["source"] == "stars_purchase" for p in record["zarniki_provenance"]):
                record["manual_review"].append("legacy_stars_receipt_has_no_charge_table")
            vip = record["protected_carry"]["vip"]
            preserved_seconds = int(vip["remaining_seconds"]) if vip else 0
            progress = _legacy_progress_conversion(record["legacy_snapshot"], record["retired_exchange_refund"])
            progress["mora"] += record["protected_legacy_refunds"]["expedition_prepaid_mora"]
            record["legacy_progress_conversion"] = progress
            record["protected_carry"]["vip_after_update"] = {
                "tier": vip["tier"] if vip and preserved_seconds else "1m",
                "preserved_seconds": preserved_seconds,
                "update_bonus_seconds": progress["vip_seconds_from_score"],
                "total_seconds_from_migration": preserved_seconds + progress["vip_seconds_from_score"],
            }
            conversion = record["retired_asset_conversion"]
            conversion_total = (conversion["cosmetics_zarniki"] + conversion["themes_zarniki"]
                                + progress["donate_inventory_zarniki"]
                                + record["retired_exchange_refund"]["zarniki_spent"])
            record["zarniki_after_compensation"] = zarniki + conversion_total
            record["source_fingerprint"] = hashlib.sha256(_canonical(record).encode()).hexdigest()

        result = {
            "policy_version": POLICY_VERSION,
            "snapshot_id": snapshot_id,
            "cutoff_utc": cutoff.isoformat().replace("+00:00", "Z"),
            "rules": {
                "zarniki": "carry current non-negative integer balance exactly once; never add gross purchases",
                "cosmetics": "retire ownership and convert each unique entitlement to its exact catalogue Zarniki price",
                "themes": "retire ownership; use direct legacy Zarniki price or the fixed rarity valuation table",
                "vip": "preserve active duration; convert every uncompensated legacy score continuously with diminishing rates",
                "retired_zarniki_exchange": "refund all immutable exchange spend 1:1 in Zarniki; exclude its proceeds from score",
                "legacy_progress": "tiered veteran package; all non-paid Mora components are capped at 2000 Mora per user",
                "unfinished_expeditions": "refund prepaid Mora exactly outside the veteran-package cap",
                "diamonds": "tiered by old balance and capped at 20 per user",
                "donate_inventory": "retired paid items convert at exact catalogue Zarniki price; no shared cap",
            },
            "users": list(by_user.values()),
        }
        result["summary"] = {
            "users": len(by_user),
            "zarniki_carry_total": sum(r["protected_carry"]["zarniki_before_compensation"] for r in by_user.values()),
            "cosmetic_entitlements_converted": sum(len(r["retired_asset_conversion"]["cosmetics"]) for r in by_user.values()),
            "theme_entitlements_converted": sum(len(r["retired_asset_conversion"]["themes"]) for r in by_user.values()),
            "cosmetics_zarniki": sum(r["retired_asset_conversion"]["cosmetics_zarniki"] for r in by_user.values()),
            "themes_zarniki": sum(r["retired_asset_conversion"]["themes_zarniki"] for r in by_user.values()),
            "zarniki_after_compensation_total": sum(r["zarniki_after_compensation"] for r in by_user.values()),
            "legacy_progress_mora": sum(r["legacy_progress_conversion"]["mora"] for r in by_user.values()),
            "expedition_prepaid_mora_refunded": sum(r["protected_legacy_refunds"]["expedition_prepaid_mora"] for r in by_user.values()),
            "legacy_progress_diamonds": sum(r["legacy_progress_conversion"]["diamonds"] for r in by_user.values()),
            "donate_inventory_zarniki": sum(r["legacy_progress_conversion"]["donate_inventory_zarniki"] for r in by_user.values()),
            "retired_exchange_zarniki_refund": sum(r["retired_exchange_refund"]["zarniki_spent"] for r in by_user.values()),
            "legacy_score": sum(r["legacy_progress_conversion"]["legacy_score"] for r in by_user.values()),
            "vip_seconds_from_score": sum(r["legacy_progress_conversion"]["vip_seconds_from_score"] for r in by_user.values()),
            "active_vip_users": sum(bool(r["protected_carry"]["vip"] and r["protected_carry"]["vip"]["remaining_seconds"] > 0) for r in by_user.values()),
            "vip_update_bonus_users": sum(r["legacy_progress_conversion"]["vip_seconds_from_score"] > 0 for r in by_user.values()),
            "manual_review_users": sum(bool(r["manual_review"]) for r in by_user.values()),
        }
        result["inventory_sha256"] = hashlib.sha256(_canonical(result).encode()).hexdigest()
        return result
    finally:
        await tx.rollback()
        await conn.close()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--cutoff-utc", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cutoff = _validate(args.dsn, args.cutoff_utc)
    report = await build(args.dsn, args.snapshot_id, cutoff)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=_value), encoding="utf-8")
    print(json.dumps({"summary": report["summary"], "inventory_sha256": report["inventory_sha256"]}))


if __name__ == "__main__":
    asyncio.run(main())
