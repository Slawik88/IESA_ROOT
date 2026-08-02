#!/usr/bin/env python3
"""Focused regression checks for the cosmetic entitlement classifier."""
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.cosmetic_lifecycle import (  # noqa: E402
    build_cosmetic_lifecycle_report,
    classify_cosmetic_id,
)
from scripts.audit_cosmetic_entitlements import (  # noqa: E402
    _collect_references,
    _extract_cosmetic_ids,
    _is_local_dsn,
)


class AuditDB:
    tables = {
        "user_cosmetics", "user_cosmetic_loadout", "inventory", "cosmetic_presets",
        "weekly_showcase", "battle_pass_reward_overrides", "cosmetic_refund_log",
        "cosmetics_lineup_wipe_log",
    }

    async def fetchval(self, _query, table_name):
        return table_name.removeprefix("predvestnik.") in self.tables

    async def fetch(self, query):
        if "FROM predvestnik.user_cosmetics" in query:
            return [{"user_id": 1, "cosmetic_id": "cos_owned_removed"}]
        if "FROM predvestnik.user_cosmetic_loadout" in query:
            return [
                {"user_id": 1, "slot": "title", "cosmetic_id": "cos_equipped_removed"},
                {"user_id": 1, "slot": "welcome", "cosmetic_id": "cos_ignore_welcome"},
            ]
        if "FROM predvestnik.inventory" in query:
            return [{"user_id": 2, "item_id": "cos_misplaced", "quantity": 3}]
        if "FROM predvestnik.cosmetic_presets" in query:
            return [{"id": 7, "user_id": 3, "loadout": '{"title":"cos_preset"}'}]
        if "FROM predvestnik.weekly_showcase" in query:
            return [{"week_key": "2026-W31", "slots_json": '[["cos_showcase",1]]'}]
        if "FROM predvestnik.battle_pass_reward_overrides" in query:
            return [{"season_id": "s0", "level": 5, "track": "paid",
                     "items": '[["cos_bp",1]]', "reward_options": None}]
        if "FROM predvestnik.cosmetic_refund_log" in query:
            return [{"user_id": 4, "cosmetic_id": "cos_refunded"}]
        if "FROM predvestnik.cosmetics_lineup_wipe_log" in query:
            return [{"user_id": 5, "detail_json": '[["cos_wiped",440]]'}]
        raise AssertionError(f"unexpected audit query: {query}")


async def check_collector() -> None:
    references, skipped = await _collect_references(AuditDB())
    assert skipped == []
    sources = {ref["source"] for ref in references}
    assert {"ownership", "loadout", "inventory", "preset", "showcase", "bp_reward",
            "refund_log", "lineup_wipe_log"}.issubset(sources)
    ids = {ref["cosmetic_id"] for ref in references}
    assert "cos_ignore_welcome" not in ids
    assert {"cos_owned_removed", "cos_equipped_removed", "cos_misplaced", "cos_preset",
            "cos_showcase", "cos_bp", "cos_refunded", "cos_wiped"}.issubset(ids)


def main() -> None:
    assert _extract_cosmetic_ids({"items": [["cos_title_one", 1], ["spin_token", 2]]}) == [
        "cos_title_one"
    ]
    assert _extract_cosmetic_ids("cos_title_exact") == ["cos_title_exact"]
    assert _extract_cosmetic_ids("prefix cos_title_not_exact") == []
    assert _is_local_dsn("postgresql://localhost/game") is True
    assert _is_local_dsn("postgresql:///game") is True
    assert _is_local_dsn("postgresql://db.example/game") is False

    registry = {
        "cos_title_current": {"name": "Current"},
        "cos_title_archive": {"name": "Archive", "archived": True},
    }
    aliases = {
        "old_current": "cos_title_current",
        "old_removed": "cos_title_removed",
    }

    assert classify_cosmetic_id("cos_title_current", registry, aliases)["status"] == "active"
    assert classify_cosmetic_id("cos_title_archive", registry, aliases)["status"] == "archived"
    assert classify_cosmetic_id("old_current", registry, aliases) == {
        "status": "legacy_alias",
        "target_id": "cos_title_current",
        "recommended_action": "versioned_alias_migration",
    }
    assert classify_cosmetic_id("old_removed", registry, aliases)["status"] == "legacy_target_missing"
    assert classify_cosmetic_id("cos_unknown", registry, aliases)["status"] == "unknown"

    refs = [
        {"source": "ownership", "user_id": 11, "cosmetic_id": "old_current"},
        {"source": "loadout", "user_id": 11, "cosmetic_id": "old_current"},
        {"source": "inventory", "user_id": 12, "cosmetic_id": "cos_title_current", "quantity": 2},
        {"source": "bp_reward", "cosmetic_id": "old_removed"},
        {"source": "preset", "user_id": 13, "cosmetic_id": "cos_title_archive"},
        {"source": "refund_log", "user_id": 99, "cosmetic_id": "compensated_only"},
    ]
    report = build_cosmetic_lifecycle_report(
        refs, registry, aliases, include_user_ids=False,
    )
    assert report["summary"]["affected_user_count"] == 3
    assert report["summary"]["unresolved_id_count"] == 3
    assert all("user_ids" not in item for item in report["all_ids"])

    by_id = {item["cosmetic_id"]: item for item in report["all_ids"]}
    assert by_id["old_current"]["sources"] == {"loadout": 1, "ownership": 1}
    assert by_id["cos_title_current"]["reference_count"] == 2
    assert by_id["cos_title_current"]["issues"] == ["cosmetic_stored_as_stackable_inventory"]
    assert "battle_pass_references_unresolvable_cosmetic" in by_id["old_removed"]["issues"]
    assert by_id["compensated_only"]["safe_to_remove_definition"] is True
    assert by_id["compensated_only"]["historical_reference_count"] == 1
    assert by_id["compensated_only"] not in report["unresolved"]

    detailed = build_cosmetic_lifecycle_report(refs, registry, aliases, include_user_ids=True)
    detailed_by_id = {item["cosmetic_id"]: item for item in detailed["all_ids"]}
    assert detailed_by_id["old_current"]["user_ids"] == [11]
    assert detailed_by_id["compensated_only"]["historical_user_ids"] == [99]
    asyncio.run(check_collector())
    print("ALL COSMETIC LIFECYCLE CHECKS PASSED")


if __name__ == "__main__":
    main()
