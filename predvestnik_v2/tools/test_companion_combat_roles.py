#!/usr/bin/env python3
"""Combat proofs for implemented companion role trade-offs."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import reconstruction_combat as combat  # noqa: E402


def open_first_signal(state):
    result = combat.apply_action(state, {"type": "frame", "delta_ms": 500})
    assert result["ok"]
    result = combat.apply_action(state, {"type": "frame", "delta_ms": 200})
    assert result["ok"] and state["challenge"]["active"]


lantern = combat.new_encounter(seed=771, companion_role_id="lantern")
open_first_signal(lantern)
hinted = [item for item in lantern["challenge"]["options"] if item.get("companion_hint") == "decoy"]
assert len(hinted) == 1
assert hinted[0]["symbol"] != lantern["challenge"]["target_symbol"]
public = combat.public_state(lantern)
assert any(item.get("companion_hint") == "decoy" for item in public["challenge"]["options"])
combat._complete_wave(lantern)
assert lantern["status"] == "reward" and len(lantern["reward_options"]) == 2

guardian = combat.new_encounter(seed=991, companion_role_id="guardian")
too_early = combat.apply_action(guardian, {
    "type": "branch_action", "command": "companion_guardian_window", "delta_ms": 0,
})
assert not too_early["ok"]
open_first_signal(guardian)
original_expiry = guardian["challenge"]["expires_at_ms"]
armed = combat.apply_action(guardian, {
    "type": "branch_action", "command": "companion_guardian_window", "delta_ms": 0,
})
assert armed["ok"] and armed["result"] == "window_extended"
assert guardian["challenge"]["expires_at_ms"] == original_expiry + 320
again = combat.apply_action(guardian, {
    "type": "branch_action", "command": "companion_guardian_window", "delta_ms": 0,
})
assert not again["ok"]
challenge = guardian["challenge"]
slot = next(item["slot"] for item in challenge["options"] if item["symbol"] == challenge["target_symbol"])
strike = combat.apply_action(guardian, {
    "type": "strike", "delta_ms": 0, "challenge_id": challenge["id"], "target_slot": slot,
})["strike"]
assert strike["correct"] and strike["companion_result"] == "guardian_wide_window"
assert strike["damage"] == 52.0  # 65 base × 0.8; wider window has a real price.

rhythm = combat.new_encounter(
    "e02_shattered_causeway", seed=119, companion_role_id="rhythm_keeper",
)
too_early = combat.apply_action(rhythm, {
    "type": "branch_action", "command": "companion_rhythm_guard", "delta_ms": 0,
})
assert not too_early["ok"]
open_first_signal(rhythm)
rhythm["combo"]["count"] = 21
assert combat._combo_multiplier(rhythm) == 1.48
rhythm["team"]["charge"] = 50.0
integrity_before = rhythm["objective_state"]["lantern_integrity"]
guarded_id = rhythm["challenge"]["id"]
armed = combat.apply_action(rhythm, {
    "type": "branch_action", "command": "companion_rhythm_guard", "delta_ms": 0,
})
assert armed["ok"] and armed["challenge_id"] == guarded_id
while rhythm["challenge"] and rhythm["challenge"]["id"] == guarded_id:
    combat.apply_action(rhythm, {"type": "frame", "delta_ms": 500})
assert rhythm["mastery"]["missed_signals"] == 1  # Accuracy is never forgiven.
assert rhythm["combo"]["count"] == 0 and rhythm["team"]["charge"] == 50.0
assert rhythm["objective_state"]["lantern_integrity"] == integrity_before
again = combat.apply_action(rhythm, {
    "type": "branch_action", "command": "companion_rhythm_guard", "delta_ms": 0,
})
assert not again["ok"]

for unsupported in ("navigator", "trickster", "unknown"):
    try:
        combat.new_encounter(seed=1, companion_role_id=unsupported)
    except ValueError:
        pass
    else:
        raise AssertionError(f"Unsupported companion role entered combat: {unsupported}")

print("companion_combat_roles: Lantern + Guardian + Rhythm Keeper contracts  OK")
