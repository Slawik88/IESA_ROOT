#!/usr/bin/env python3
"""Read-only inventory of cosmetic references before a registry removal.

Local-first usage (the default variable is deliberately not DATABASE_URL):

    LOCAL_DATABASE_URL=postgresql://... \
      python scripts/audit_cosmetic_entitlements.py

The script opens a READ ONLY transaction, never writes to the database and
does not print player IDs unless ``--include-user-ids`` is explicitly passed.
Remote hosts are refused unless ``--allow-remote-readonly`` is also explicit.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

try:
    import asyncpg
except ImportError:
    asyncpg = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.registry import BATTLE_PASS_REWARDS  # noqa: E402
from services.cosmetic_lifecycle import build_cosmetic_lifecycle_report  # noqa: E402


LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}
MANDATORY_AUDIT_TABLES = {"user_cosmetics", "user_cosmetic_loadout", "inventory"}


def _extract_cosmetic_ids(value: Any) -> list[str]:
    """Find exact cosmetic IDs in JSON-compatible containers."""
    if isinstance(value, str):
        return [value] if value.startswith("cos_") else []
    if isinstance(value, dict):
        out: list[str] = []
        for child in value.values():
            out.extend(_extract_cosmetic_ids(child))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for child in value:
            out.extend(_extract_cosmetic_ids(child))
        return out
    return []


def _json_value(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None
    return raw


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    return await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"predvestnik.{table}")


async def _collect_references(conn: asyncpg.Connection) -> tuple[list[dict], list[str]]:
    refs: list[dict[str, Any]] = []
    skipped: list[str] = []

    async def rows(table: str, query: str):
        if not await _table_exists(conn, table):
            skipped.append(table)
            return []
        return await conn.fetch(query)

    for row in await rows(
        "user_cosmetics",
        "SELECT user_id, cosmetic_id FROM predvestnik.user_cosmetics",
    ):
        refs.append({"source": "ownership", "user_id": row["user_id"],
                     "cosmetic_id": row["cosmetic_id"]})

    for row in await rows(
        "user_cosmetic_loadout",
        "SELECT user_id, slot, cosmetic_id FROM predvestnik.user_cosmetic_loadout",
    ):
        if row["slot"] != "welcome":
            refs.append({"source": "loadout", "user_id": row["user_id"],
                         "cosmetic_id": row["cosmetic_id"], "slot": row["slot"]})

    # A historical bug could grant cos_* rewards into stackable inventory.
    for row in await rows(
        "inventory",
        "SELECT user_id, item_id, quantity FROM predvestnik.inventory "
        "WHERE item_id LIKE 'cos\\_%' ESCAPE '\\'",
    ):
        refs.append({"source": "inventory", "user_id": row["user_id"],
                     "cosmetic_id": row["item_id"], "quantity": row["quantity"]})

    for row in await rows(
        "cosmetic_presets",
        "SELECT id, user_id, loadout FROM predvestnik.cosmetic_presets",
    ):
        for cosmetic_id in _extract_cosmetic_ids(_json_value(row["loadout"])):
            refs.append({"source": "preset", "user_id": row["user_id"],
                         "cosmetic_id": cosmetic_id, "preset_id": row["id"]})

    for row in await rows(
        "weekly_showcase",
        "SELECT week_key, slots_json FROM predvestnik.weekly_showcase",
    ):
        for cosmetic_id in _extract_cosmetic_ids(_json_value(row["slots_json"])):
            refs.append({"source": "showcase", "cosmetic_id": cosmetic_id,
                         "week_key": row["week_key"]})

    # Reward definitions matter even without a current owner: an invalid ID can
    # create the next orphan the moment a player claims it.
    for row in await rows(
        "battle_pass_reward_overrides",
        "SELECT season_id, level, track, items, reward_options "
        "FROM predvestnik.battle_pass_reward_overrides",
    ):
        payloads = (_json_value(row["items"]), _json_value(row["reward_options"]))
        for payload in payloads:
            for cosmetic_id in _extract_cosmetic_ids(payload):
                refs.append({"source": "bp_reward", "cosmetic_id": cosmetic_id,
                             "season_id": row["season_id"], "level": row["level"],
                             "track": row["track"]})

    # Compensation ledgers are historical evidence, not live entitlements.
    # They are reported separately so a migration cannot pay or grant twice.
    for row in await rows(
        "cosmetic_refund_log",
        "SELECT user_id, cosmetic_id FROM predvestnik.cosmetic_refund_log",
    ):
        refs.append({"source": "refund_log", "user_id": row["user_id"],
                     "cosmetic_id": row["cosmetic_id"]})

    for row in await rows(
        "cosmetics_lineup_wipe_log",
        "SELECT user_id, detail_json FROM predvestnik.cosmetics_lineup_wipe_log",
    ):
        for cosmetic_id in _extract_cosmetic_ids(_json_value(row["detail_json"])):
            refs.append({"source": "lineup_wipe_log", "user_id": row["user_id"],
                         "cosmetic_id": cosmetic_id})

    # Registry rewards are also executable definitions and must be audited even
    # when the corresponding DB override table is absent on a fresh local clone.
    for level, tracks in BATTLE_PASS_REWARDS.items():
        for track, reward in tracks.items():
            for cosmetic_id in _extract_cosmetic_ids(reward.get("items", ())):
                refs.append({"source": "bp_reward", "cosmetic_id": cosmetic_id,
                             "season_id": "registry", "level": level, "track": track})

    return refs, sorted(set(skipped))


def _is_local_dsn(dsn: str) -> bool:
    return (urlparse(dsn).hostname or "") in LOCAL_HOSTS


async def run(args: argparse.Namespace) -> int:
    if asyncpg is None:
        print("ERROR: install asyncpg from the project requirements", file=sys.stderr)
        return 2
    dsn = os.getenv(args.database_url_env, "").strip()
    if not dsn:
        print(f"ERROR: environment variable {args.database_url_env} is not set", file=sys.stderr)
        return 2
    if not _is_local_dsn(dsn) and not args.allow_remote_readonly:
        print("ERROR: remote database refused; use a local clone first. "
              "For an approved production audit pass --allow-remote-readonly explicitly.",
              file=sys.stderr)
        return 2

    conn = await asyncpg.connect(dsn, command_timeout=20)
    try:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            references, skipped = await _collect_references(conn)
    finally:
        await conn.close()

    report = build_cosmetic_lifecycle_report(
        references, include_user_ids=args.include_user_ids,
    )
    missing_mandatory = sorted(MANDATORY_AUDIT_TABLES.intersection(skipped))
    report["audit"] = {
        "mode": "read_only",
        "snapshot": "repeatable_read",
        "complete": not missing_mandatory,
        "database_host": urlparse(dsn).hostname or "local-socket",
        "skipped_missing_tables": skipped,
        "missing_mandatory_tables": missing_mandatory,
        "player_ids_included": bool(args.include_user_ids),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output).resolve()
        output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Read-only report written to {output}")
    else:
        print(rendered)
    if missing_mandatory:
        return 2
    return 1 if report["summary"]["unresolved_id_count"] else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url-env", default="LOCAL_DATABASE_URL",
        help="environment variable containing the DSN (default: LOCAL_DATABASE_URL)",
    )
    parser.add_argument(
        "--allow-remote-readonly", action="store_true",
        help="explicitly allow a remote host; the transaction still remains READ ONLY",
    )
    parser.add_argument(
        "--include-user-ids", action="store_true",
        help="include numeric player IDs in the report (off by default)",
    )
    parser.add_argument("--output", help="optional JSON output path")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
