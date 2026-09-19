"""Pure contract tests for the owner-approved pet foundation."""
from datetime import datetime, timedelta, timezone
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.pets_v1 import (
    ACTIVE_SLOT_SWAP_COST, ACTIVITY_ENDURANCE_COST, ENDURANCE_DRAIN_PER_DAY, MAX_LEVEL, PetPolicyError,
    TREK_AND_EXPEDITION_HOURS, allowed_duration, apply_active_slot_swap,
    endurance_after_elapsed, level_effects, spend_activity_endurance, validate_activity,
    validate_expedition_decision,
)


def must_fail(callable_):
    try:
        callable_()
    except PetPolicyError:
        return
    raise AssertionError("Expected PetPolicyError")


def main() -> None:
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    assert endurance_after_elapsed(100, last_updated_at=now - timedelta(days=1), now=now) == (90, ENDURANCE_DRAIN_PER_DAY)
    assert endurance_after_elapsed(3, last_updated_at=now - timedelta(days=2), now=now) == (0, 3)
    assert endurance_after_elapsed(80, last_updated_at=now + timedelta(hours=1), now=now) == (80, 0)
    assert endurance_after_elapsed(80, last_updated_at=now - timedelta(minutes=143), now=now) == (80, 0)

    assert apply_active_slot_swap(current_pet_id=7, next_pet_id=7, endurance=2) == (7, 2)
    assert apply_active_slot_swap(current_pet_id=7, next_pet_id=8, endurance=20) == (8, 20 - ACTIVE_SLOT_SWAP_COST)
    must_fail(lambda: apply_active_slot_swap(current_pet_id=7, next_pet_id=8, endurance=ACTIVE_SLOT_SWAP_COST - 1))
    must_fail(lambda: level_effects(0))
    must_fail(lambda: level_effects(MAX_LEVEL + 1))
    assert level_effects(1)["visual_stage"] == "Начальный облик"
    assert level_effects(MAX_LEVEL)["max_level_effect"] is True
    assert all(allowed_duration(hours) for hours in TREK_AND_EXPEDITION_HOURS)
    assert not any(allowed_duration(hours) for hours in (2, 4, 12, -3, 0))
    assert validate_activity("trek", 3) == ("trek", 3)
    assert validate_activity("expedition", 9) == ("expedition", 9)
    assert spend_activity_endurance(endurance=100, hours=3) == (75, ACTIVITY_ENDURANCE_COST[3])
    assert spend_activity_endurance(endurance=55, hours=9) == (0, ACTIVITY_ENDURANCE_COST[9])
    must_fail(lambda: spend_activity_endurance(endurance=24, hours=3))
    must_fail(lambda: spend_activity_endurance(endurance=100, hours=4))
    assert validate_expedition_decision(" careful ") == "careful"
    assert validate_expedition_decision("steady") == "steady"
    assert validate_expedition_decision("bold") == "bold"
    must_fail(lambda: validate_activity("raid", 3))
    must_fail(lambda: validate_activity("trek", 4))
    must_fail(lambda: validate_expedition_decision("guaranteed-win"))
    print("OK: pets v1 endurance, slot anti-abuse, levels, timers and route choices")


if __name__ == "__main__":
    main()
