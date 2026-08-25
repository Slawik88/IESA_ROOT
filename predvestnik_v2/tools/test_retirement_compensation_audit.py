#!/usr/bin/env python3
"""Contract tests for the local, read-only retirement inventory."""
from __future__ import annotations

import asyncio
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "audit_retirement_compensation.py"
SPEC = importlib.util.spec_from_file_location("retirement_audit", MODULE_PATH)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


ALL_COLUMNS = {
    "user_units": {"user_id", "unit_id", "level", "shards", "obtained_at"},
    "user_squad": {"user_id", "slot", "unit_id"},
    "battles": {"id", "user_id", "mode", "ref_id", "status", "state_json", "created_at"},
    "duels": {"id", "challenger_id", "stake", "status", "created_at"},
    "user_reserve": {"user_id", "reserved_mora"},
    "active_expeditions": {"pet_id", "chat_id", "duration_hours", "cost_mora", "ends_at", "early_finish"},
    "pets": {"id", "owner_id", "placement"},
    "shadow_gate_runs": {"pet_id", "user_id", "started_at", "dark_mora", "status"},
    "clan_raids": {"raid_id", "clan_id", "status", "ends_at"},
    "raid_contributions": {"raid_id", "user_id", "damage"},
    "clan_abyss": {"clan_id", "week_key", "floor"},
    "clan_abyss_contrib": {"clan_id", "user_id", "week_key", "shards"},
    "clan_abyss_opens": {"user_id", "day", "cnt"},
    "war_nodes": {"id", "owner_clan_id"},
    "clan_wars2": {"id", "node_id", "status", "ends_at"},
    "clan_war_attacks": {"war_id", "user_id", "damage"},
    "clans": {"clan_id", "treasury_shards", "treasury_mora"},
    "clan_members": {"clan_id", "user_id", "clan_coins"},
    "clan_buildings": {"clan_id", "key", "level"},
}


class FakeSnapshot:
    """Aggregate-only fixture; it refuses to carry identifiers or raw state."""

    async def fetch(self, query, *args):
        if "information_schema.columns" in query:
            return [
                {"table_name": table, "column_name": column}
                for table, columns in ALL_COLUMNS.items()
                for column in columns
            ]
        if "retirement_inventory:battles */" in query:
            return [{"mode": "gates", "status": "active", "rows": 1, "owners": 1}]
        raise AssertionError(f"unexpected fetch: {query}")

    async def fetchval(self, query, *args):
        if "to_regprocedure" in query:
            return True
        if "retirement_inventory:battles_json" in query:
            return 1
        raise AssertionError(f"unexpected fetchval: {query}")

    async def fetchrow(self, query, *args):
        rows = {
            "retirement_inventory:units": {
                "rows": 3, "owners": 2, "opened_rows": 1, "partial_unlock_rows": 1,
                "shards_total": 12, "invalid_rows": 0,
            },
            "retirement_inventory:user_squad": {
                "rows": 1, "owners": 1, "invalid_slot_rows": 0, "orphan_unit_rows": 0,
            },
            "retirement_inventory:duel_escrow": {
                "pending_rows": 1, "challengers": 1, "pending_stake": 20,
                "pending_at_cutoff": 1, "all_reserve": 10, "invalid_stake_rows": 0,
            },
            "retirement_inventory:legacy_expeditions": {
                "rows": 1, "owners": 1, "prepaid_mora": 30, "overdue_rows": 1,
                "early_finish_rows": 0, "orphan_pet_rows": 0,
            },
            "retirement_inventory:shadow_gates": {
                "active_rows": 1, "accrued_dark_mora": 7, "orphan_pet_rows": 0,
                "cap_exceeded_rows": 1, "placement_without_run_rows": 1,
            },
            "retirement_inventory:raids": {
                "active_rows": 1, "overdue_rows": 1, "contribution_rows": 2,
                "contributors": 2, "contribution_damage": 50, "orphan_contribution_rows": 1,
            },
            "retirement_inventory:clan_abyss": {
                "state_rows": 1, "clans": 1, "contribution_rows": 1, "contributors": 1,
                "contributed_shards": 3, "opens_rows": 1, "invalid_open_rows": 0,
            },
            "retirement_inventory:clan_wars": {
                "owned_nodes": 1, "active_rows": 1, "overdue_rows": 1, "attack_rows": 2,
                "attackers": 2, "attack_damage": 8, "orphan_attack_rows": 1,
            },
            "retirement_inventory:clan_balances": {
                "clans": 1, "treasury_shards": 10, "treasury_mora": 20,
                "member_coin_rows": 1, "member_coins": 3, "building_rows": 1,
                "invalid_building_rows": 0,
            },
        }
        for marker, row in rows.items():
            if marker in query:
                return row
        raise AssertionError(f"unexpected fetchrow: {query}")


def test_input_boundary() -> None:
    cutoff = audit.validate_local_snapshot_args(
        "postgresql://readonly@127.0.0.1/predvestnik_snapshot",
        "cutover-2026-08-24",
        "2026-08-24T00:00:00Z",
    )
    assert cutoff == datetime(2026, 8, 24, tzinfo=timezone.utc)
    for dsn in ("", "postgresql://readonly@db.example/predvestnik", "sqlite:///tmp/test.db"):
        try:
            audit.validate_local_snapshot_args(dsn, "cutover-2026-08-24", "2026-08-24T00:00:00Z")
        except audit.AuditInputError:
            pass
        else:
            raise AssertionError(f"unsafe DSN was accepted: {dsn!r}")


def test_catalog_fail_closed() -> None:
    assert audit.category_readiness({}, {"user_units": {"user_id"}}) == {
        "status": "missing_table", "missing_tables": ["user_units"]
    }
    assert audit.category_readiness({"user_units": {"user_id"}}, {"user_units": {"user_id", "shards"}}) == {
        "status": "missing_columns", "missing_columns": {"user_units": ["shards"]}
    }


async def test_aggregate_and_anomaly_contract() -> None:
    result = await audit.collect_inventory(
        FakeSnapshot(), "cutover-2026-08-24", datetime(2026, 8, 24, tzinfo=timezone.utc)
    )
    categories = result["categories"]
    assert categories["units"]["units"]["partial_unlock_rows"] == 1
    assert categories["battles"]["status"] == "manual_recovery_required"
    assert "invalid_battle_state_json" in categories["battles"]["manual_recovery_reasons"]
    assert "pending_duel_stake_exceeds_shared_reserve" in categories["duel_escrow"]["manual_recovery_reasons"]
    assert "pet_placement_gate_mismatch" in categories["shadow_gates"]["manual_recovery_reasons"]
    assert "orphan_raid_contribution" in categories["raids"]["manual_recovery_reasons"]
    rendered = audit.finalize_report(result)
    repeated = audit.finalize_report(result)
    assert json.dumps(rendered, sort_keys=True, separators=(",", ":")) == json.dumps(repeated, sort_keys=True, separators=(",", ":"))
    text = json.dumps(rendered, ensure_ascii=False)
    # Metric names may honestly mention state JSON; raw state and player identity
    # must never make it into the aggregate report.
    for forbidden in ("user_id", "username", "payment", "999", "raw-state-payload"):
        assert forbidden not in text, f"PII/raw-state marker leaked: {forbidden}"


def test_static_read_only_contract() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    upper = source.upper()
    for forbidden in ("INSERT INTO", "UPDATE ", "DELETE FROM", "CREATE TABLE", "ALTER TABLE", "DROP TABLE"):
        assert forbidden not in upper, f"audit must remain read-only: {forbidden}"
    for forbidden_import in ("FASTAPI", "BOT.CORE.DATABASE", "ENSURE_TABLE"):
        assert forbidden_import not in upper, f"audit must not import app startup: {forbidden_import}"
    assert "readonly=True" in source and "repeatable_read" in source
    assert "os.environ" not in source and "load_dotenv" not in source
    for excluded in ("companion_v3_", "reconstruction_", "user_cosmetics", "economy_ledger"):
        assert excluded not in source


def main() -> None:
    test_input_boundary()
    test_catalog_fail_closed()
    asyncio.run(test_aggregate_and_anomaly_contract())
    test_static_read_only_contract()
    print("retirement compensation audit contract: OK")


if __name__ == "__main__":
    main()
