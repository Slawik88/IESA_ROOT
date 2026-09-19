#!/usr/bin/env python3
"""Pure policy regression checks for daily Rhythm contracts."""
from __future__ import annotations

import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.retention_v3 import (  # noqa: E402
    DAILY_CONTRACTS,
    daily_offer_ids,
    terminal_contribution,
    validate_content,
)


assert validate_content() == []
offers = daily_offer_ids(7001, date(2026, 8, 26))
assert offers == daily_offer_ids(7001, "2026-08-26")
assert len(offers) == 3 and len(set(offers)) == 3
assert {DAILY_CONTRACTS[item]["category"] for item in offers} == {
    "mastery", "tempo", "discovery"
}
assert offers != daily_offer_ids(7002, date(2026, 8, 26))

mastery = {
    "correct_taps": 9, "mistakes": 2, "missed_signals": 1,
    "max_combo": 8, "discharges": 2,
}
base = {
    "outcome": "lost", "encounter_id": "e02_shattered_causeway",
    "mastery": mastery, "upgrades": ["heavy_echo", "golden_seam"],
    "meaningful": True,
}
assert terminal_contribution("steady_hand", **base) == 1
assert terminal_contribution("returning_echo", **base) == 1
assert terminal_contribution("charged_bell", **base) == 2
assert terminal_contribution("two_attempts", **base) == 1
assert terminal_contribution("living_build", **base) == 1
assert terminal_contribution("unread_path", **base) == 1
assert terminal_contribution("two_attempts", **{**base, "meaningful": False}) == 0

print("OK: Rhythm offers are stable, varied and advance only on meaningful terminals")
