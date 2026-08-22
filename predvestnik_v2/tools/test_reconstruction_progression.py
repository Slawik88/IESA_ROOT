#!/usr/bin/env python3
"""Pure checks for levels and non-trivial first unit branches."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.economy_v3 import UNIT_LEVEL_CAP_XP, UNIT_XP_REQUIREMENTS  # noqa: E402
from core.reconstruction import STARTER_UNITS  # noqa: E402
from core.reconstruction_progression import (  # noqa: E402
    UNIT_BRANCHES,
    mastery_proofs_from_terminal,
    public_progression_manifest,
    unit_progress_view,
    validate_progression_content,
)


assert validate_progression_content() == []
assert set(UNIT_BRANCHES) == set(STARTER_UNITS)
assert all(len(branches[5]) == 2 for branches in UNIT_BRANCHES.values())
assert len({b["id"] for m in UNIT_BRANCHES.values() for b in m[5]}) == 6
assert unit_progress_view("r_oath_bell", 0)["level"] == 1
at_cap = unit_progress_view("r_oath_bell", UNIT_LEVEL_CAP_XP)
assert at_cap["level"] == 30 and at_cap["mastery_after_cap"] == 0
choice = UNIT_BRANCHES["r_oath_bell"][5][0]["id"]
try:
    unit_progress_view("r_oath_bell", 0, {5: choice})
except ValueError as exc:
    assert "locked" in str(exc)
else:
    raise AssertionError("Locked branch was accepted")

level_five_xp = sum(UNIT_XP_REQUIREMENTS[:4])
view = unit_progress_view("r_oath_bell", level_five_xp, {5: choice})
assert view["level"] == 5 and view["branch_choices"] == {"5": choice}
assert view["next_branch_level"] == 10
assert unit_progress_view("r_oath_bell", level_five_xp)["next_branch_level"] == 5
manifest = public_progression_manifest()
assert manifest["paid_xp_allowed"] is False
assert manifest["ranked_normalization"] is True
assert manifest["implemented_branch_levels"] == [5]
for unit in manifest["branches"].values():
    for branch in unit["5"]:
        assert branch["tradeoff"] and branch["counter_scenario"]
        assert len(branch["telemetry"]) >= 3

proof_state = {
    "status": "won",
    "combo": {"max": 24},
    "mastery": {
        "correct_taps": 30, "mistakes": 1, "missed_signals": 0,
        "discharges": 3, "critical_taps": 4,
        "max_combo_after_mistake": 9,
        "reaction_count": 30, "reaction_total_ms": 15_000,
    },
}
assert set(mastery_proofs_from_terminal(proof_state)) == {
    "bell_recover_three_clean", "bell_three_discharges",
    "seam_three_critical", "seam_clean_twenty",
    "tide_fast_response", "tide_no_miss",
}
assert mastery_proofs_from_terminal({**proof_state, "status": "lost"}) == ()

print("reconstruction_progression: 1-30 curve+six meaningful branches  OK")
