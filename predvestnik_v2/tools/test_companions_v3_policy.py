#!/usr/bin/env python3
"""Deterministic checks for the isolated companion-v3 policy."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.companions_v3 import (  # noqa: E402
    BOND_MILESTONES,
    CARE_BANK_CAP,
    COMPANION_ROLES,
    CompanionPolicyError,
    REAL_REWARDS_ENABLED,
    bond_progress,
    public_companion_manifest,
    quote_expedition,
    recover_care_bank,
    role_unlock_count,
)


assert len(COMPANION_ROLES) == 10
assert [role_unlock_count(day) for day in (0, 4, 5, 44, 45, 999)] == [1, 1, 2, 9, 10, 10]
assert bond_progress(0) == {
    "points": 0, "milestones_reached": 0, "last_milestone": None,
    "next_milestone": 1, "points_to_next": 1,
}
assert bond_progress(78)["next_milestone"] is None
assert BOND_MILESTONES[-1] == 78 and CARE_BANK_CAP == 7
anchor = datetime(2026, 8, 1, tzinfo=timezone.utc)
assert recover_care_bank(1, anchor, anchor + timedelta(hours=47)) == (1, anchor)
assert recover_care_bank(1, anchor, anchor + timedelta(hours=96))[0] == 3
assert recover_care_bank(6, anchor, anchor + timedelta(days=30)) == (
    7, anchor + timedelta(days=30)
)

assert (quote_expedition(2).base_mora, quote_expedition(6).base_mora,
        quote_expedition(12).base_mora) == (50, 145, 285)
limited = quote_expedition(12, 570)
assert limited.projected_mora == 30 and limited.weekly_mora_after == 600
assert limited.cap_reached and not limited.can_settle
closed = quote_expedition(2, 600)
assert closed.projected_mora == 0 and closed.cap_reached

manifest = public_companion_manifest()
assert manifest["real_rewards_enabled"] is REAL_REWARDS_ENABLED is False
assert manifest["care"]["missed_care_penalty"] is False
assert manifest["care"]["duplicate_power"] is False
assert manifest["expeditions"]["rewards_expire"] is False

for bad in (-1, True, 1.5):
    try:
        role_unlock_count(bad)
    except CompanionPolicyError:
        pass
    else:
        raise AssertionError(f"Invalid meaningful day accepted: {bad!r}")

for bad in (4, 8, 24, True):
    try:
        quote_expedition(bad)
    except CompanionPolicyError:
        pass
    else:
        raise AssertionError(f"Invalid expedition duration accepted: {bad!r}")

print("companions_v3_policy: roles+Bond+expedition caps shadow contract  OK")
