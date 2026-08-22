#!/usr/bin/env python3
"""Pure tests for shadow Reconstruction integrity evidence."""
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.reconstruction_integrity import (  # noqa: E402
    public_integrity_manifest,
    record_strike,
    terminal_result,
    verdict,
)


state = {}
record_strike(state, {"accepted": False, "reaction_ms": 1})
record_strike(state, {"accepted": True, "reaction_ms": "1"})
assert verdict(state)["reaction_samples"] == 0

for reaction in (42, 45, 51, 150, 170):
    record_strike(state, {"accepted": True, "reaction_ms": reaction})

review = verdict(state)
assert review["status"] == "review_required"
assert review["implausibly_fast_samples"] == 3
assert review["fastest_reaction_ms"] == 42
assert review["average_reaction_ms"] == 92
assert review["automatic_ban"] is False

receipt = terminal_result(run_id=7, revision=23, outcome="won", state=state)
assert receipt["id"] == "reconstruction:7:terminal"
assert receipt["server_revision"] == 23
assert receipt["integrity"] == review

manifest = public_integrity_manifest()
assert manifest["mode"] == "shadow_review"
assert manifest["automatic_ban"] is False
assert manifest["real_rewards_enabled"] is False

print("reconstruction_integrity: reactions+review verdict+terminal id  OK")
