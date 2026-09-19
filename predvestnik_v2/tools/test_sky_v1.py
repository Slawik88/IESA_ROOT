"""Compact policy contract for the non-economic Harbinger Sky."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.sky_v1 import MAX_PATH_SLOTS, NODES, can_allocate, path_budget, public_view, validate_allocated_state


def main() -> None:
    assert len(NODES) == 12
    assert path_budget(-1) == 0
    assert path_budget(999) == MAX_PATH_SLOTS == 7

    allocated: set[str] = set()
    assert can_allocate(allocated, "rift_reader", 7) == (False, "parent_required")
    assert can_allocate(allocated, "rift_gate", 0) == (False, "no_path_slots")
    assert can_allocate(allocated, "missing", 7) == (False, "unknown_node")

    allocated.add("rift_gate")
    assert can_allocate(allocated, "rift_reader", 7) == (True, None)
    allocated.add("rift_reader")
    assert can_allocate(allocated, "rift_vow", 7) == (False, "route_already_chosen")
    assert can_allocate(allocated, "rift_sigil", 7) == (True, None)

    capped = {"rift_gate", "rift_reader", "rift_sigil", "archive_gate",
              "archive_ink", "archive_sigil", "bond_gate"}
    assert can_allocate(capped, "bond_care", 7) == (False, "no_path_slots")

    view = public_view(
        allocated=allocated, active_sigil="rift_sigil", revision=3,
        completed_feats=13, eclipse_cycle_key=None, current_cycle_no=2,
        current_cycle_key="scar-map-v1-2026-08-28:2",
    )
    assert view["path_slots"] == 7
    assert view["new_currency"] is False
    assert view["economic_reward"] is None
    assert view["combat_power"] is False
    assert view["stars_can_buy_progress"] is False
    # A sigil cannot be projected as active before it is actually allocated.
    assert view["active_sigil"] is None
    for corrupt in ({"rift_reader"}, {"rift_gate", "rift_reader", "rift_vow"}):
        try:
            validate_allocated_state(corrupt)
        except RuntimeError:
            pass
        else:
            raise AssertionError("corrupt route accepted")
    print("OK: Harbinger Sky routes are bounded, exclusive and non-economic")


if __name__ == "__main__":
    main()
