#!/usr/bin/env python3
"""Deterministic checks for the shadow-only Alliance constitution."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.alliance_v3 import (  # noqa: E402
    REAL_REWARDS_ENABLED, clan_feature_gates, cycle_target,
    public_manifest, quote_contribution, stage_progress,
)

assert cycle_target(0) == 18
assert cycle_target(10) == 33
assert cycle_target(10_000) == 1200

win = quote_contribution(
    outcome="won", meaningful=True, practice=False, quarantined=False,
    daily_signals=0, weekly_signals=0,
)
assert (win.requested, win.accepted, win.daily_after, win.weekly_after) == (2, 2, 2, 2)
partial = quote_contribution(
    outcome="won", meaningful=True, practice=False, quarantined=False,
    daily_signals=3, weekly_signals=11,
)
assert partial.accepted == 1 and partial.reason == "cap_partial" and not partial.settled
for rejected in (
    quote_contribution(outcome="lost", meaningful=False, practice=False, quarantined=False, daily_signals=0, weekly_signals=0),
    quote_contribution(outcome="won", meaningful=True, practice=True, quarantined=False, daily_signals=0, weekly_signals=0),
    quote_contribution(outcome="won", meaningful=True, practice=False, quarantined=True, daily_signals=0, weekly_signals=0),
):
    assert rejected.accepted == 0

assert stage_progress(6, 24)["stages_reached"] == [25]
assert stage_progress(24, 24)["complete"]
assert clan_feature_gates(1, [8]) == {
    "projects": False, "competition": False,
    "active_clans": 1, "competition_ready_clans": 1,
}
assert clan_feature_gates(3, [4, 4, 4])["projects"]
assert not clan_feature_gates(8, [5] * 7 + [4])["competition"]
assert clan_feature_gates(8, [5] * 8)["competition"]
manifest = public_manifest()
assert manifest["real_rewards_enabled"] is REAL_REWARDS_ENABLED is False
assert manifest["economic_reward"] is None and manifest["legacy_clans_preserved"]

print("alliance_v3_policy: reachable targets + caps + honest clan gates  OK")
