"""Pure contract for immutable Reconstruction reward receipt fingerprints."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.repositories import reconstruction_settlements as receipts  # noqa: E402

difficulty = {"id": "support", "policy_version": "difficulty-e01-v1", "wave_plan": [{"hp": 741.0}]}
decision = {"projected": {"mora": 35, "lead_unit_xp": 45, "support_unit_xp_each": 27}}
first = receipts.receipt_fingerprint(
    terminal_result_id="reconstruction:7:terminal", user_id=11, run_id=7,
    policy_version="owner-v3-partial-loss-2", difficulty_snapshot=difficulty, decision=decision,
)
assert first == receipts.receipt_fingerprint(
    terminal_result_id="reconstruction:7:terminal", user_id=11, run_id=7,
    policy_version="owner-v3-partial-loss-2", difficulty_snapshot=dict(difficulty), decision=dict(decision),
)
changed = dict(decision, projected={**decision["projected"], "mora": 36})
assert first != receipts.receipt_fingerprint(
    terminal_result_id="reconstruction:7:terminal", user_id=11, run_id=7,
    policy_version="owner-v3-partial-loss-2", difficulty_snapshot=difficulty, decision=changed,
)
source = (ROOT / "infrastructure/repositories/reconstruction_settlements.py").read_text(encoding="utf-8")
assert "terminal_result_id       TEXT PRIMARY KEY" in source
assert "economic_operations_reconstruction_terminal_unique" in source
assert "duplicate terminal ledger references" in source
assert "FOR UPDATE" in source
print("reconstruction_settlement_receipt: immutable terminal fingerprint contract  OK")
