#!/usr/bin/env python3
"""Pure contract for finite non-economic Chronicle feats."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.feats_v1 import FEATS, FEATS_VERSION, evaluate_feats, feat_definition_digest
from core.scar_map_v1 import POLICY_VERSION as SCAR_POLICY
from core.weekly_case_v1 import CASE_CATALOG, definition_digest
from services.feats_v1 import _verified_scar_completions, _verified_weekly_counts


assert FEATS_VERSION.startswith("chronicle-feats-v2")
assert len(FEATS) == 13
assert len({item["id"] for item in FEATS}) == len(FEATS)
assert len({feat_definition_digest(item) for item in FEATS}) == len(FEATS)
assert all(item["metric"] not in {"messages", "spend", "wallet", "streak", "purchases"} for item in FEATS)

empty = evaluate_feats({})
assert not any(item["completed"] for item in empty)
assert all(item["reward"] is None and item["competitive"] is False for item in empty)

complete = evaluate_feats({
    "completed_encounters": 99,
    "memories": 2,
    "route_choices": 1,
    "recovery_proofs": 1,
    "mastery_proofs": 6,
    "distinct_upgrades": 8,
    "rhythm_days": 40,
    "distinct_care_actions": 3,
    "distinct_discoveries": 12,
    "weekly_cases_completed": 8,
    "pack_2_cases_completed": 4,
    "scar_maps_completed": 1,
})
assert all(item["completed"] and item["pct"] == 100 for item in complete)
assert all(item["progress"] <= item["target"] for item in complete)

try:
    evaluate_feats({"completed_encounters": True})
except ValueError:
    pass
else:
    raise AssertionError("Boolean metric was accepted as an integer")

case = CASE_CATALOG[4]
valid_case = {"case_id": case["case_id"], "policy_version": case["policy_version"],
              "definition_digest": definition_digest(case), "completed_at": "now",
              "progress_days": 3, "path_id": next(iter(case["paths"])), "finale_id": "single_note"}
assert _verified_weekly_counts([valid_case]) == (1, 1)
assert _verified_weekly_counts([{**valid_case, "definition_digest": "stale"}]) == (0, 0)

valid_scar = {"policy_version": SCAR_POLICY, "completed_at": "now",
              "counters_json": '{"terminal_runs":5,"discharges":10,"meaningful_days":4,"archive_discoveries":6,"max_accuracy":80,"max_combo":12,"flawless_wins":1}',
              "encounters_json": '["a","b","c"]'}
assert _verified_scar_completions([valid_scar]) == 1
assert _verified_scar_completions([{**valid_scar, "counters_json": "bad-json"}]) == 0

print("OK: Chronicle feats are finite, bounded, non-economic and non-competitive")
