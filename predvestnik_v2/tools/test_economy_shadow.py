#!/usr/bin/env python3
"""Contract checks for immutable, wallet-free shadow reward persistence."""
from __future__ import annotations

import asyncio
import copy
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infrastructure.repositories import economy_shadow as repo  # noqa: E402


class Cursor:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def fetchone(self):
        return self.rows[0] if self.rows else None


class DB:
    def __init__(self):
        self.rows = []

    def execute(self, sql, args=()):
        compact = " ".join(sql.split())
        upper = compact.upper()
        if upper.startswith("SELECT DECISION_JSON"):
            row = next((row for row in self.rows if row["terminal"] == args[0]), None)
            return Cursor([(row["decision_json"],)] if row else [])
        if upper.startswith("SELECT COUNT(*)") and "POLICY_VERSION" in upper:
            count = sum(
                row["user_id"] == int(args[0])
                and row["policy_version"] == args[1]
                and row["eligible"]
                for row in self.rows
            )
            return Cursor([(count,)])
        if upper.startswith("SELECT COUNT(*)") and "SEED_FINGERPRINT" in upper:
            count = sum(
                row["user_id"] == int(args[0])
                and row["fingerprint"] == args[1]
                and row["outcome"] == "lost"
                and row["eligible"]
                for row in self.rows
            )
            return Cursor([(count,)])
        if upper.startswith("INSERT INTO ECONOMY_SHADOW_REWARDS"):
            if any(row["terminal"] == args[0] for row in self.rows):
                return Cursor()
            self.rows.append({
                "terminal": args[0], "user_id": int(args[1]), "run_id": int(args[2]),
                "policy_version": args[5], "outcome": args[6], "fingerprint": args[8],
                "eligible": bool(args[9]), "decision_json": args[12],
            })
            return Cursor([(len(self.rows),)])
        raise AssertionError(f"Unexpected SQL: {compact}")


async def main():
    source = (ROOT / "infrastructure/repositories/economy_shadow.py").read_text(
        encoding="utf-8"
    )
    assert "CHECK (settled = FALSE)" in source
    assert "wallet" not in source.replace("wallet imports", "")
    assert "NOW() - INTERVAL '7 days'" in source

    db = DB()
    fingerprint = repo.seed_fingerprint("g1", "e1", 77)
    decision = {
        "settlement_mode": "shadow_only", "settled": False, "eligible": True,
        "projected": {"mora": 100},
    }
    values = dict(
        terminal_result_id="reconstruction:9:terminal", user_id=7, run_id=9,
        game_version="g1", balance_version="b1", policy_version="p1",
        outcome="lost", run_kind="campaign", fingerprint=fingerprint,
        eligible=True, reason="eligible_shadow", accepted_result_ordinal=1,
        decision=decision, inputs={"server_terminal_confirmed": True},
    )
    first = await repo.save_decision(db, **values)
    replay = await repo.save_decision(db, **values)
    assert first == replay == decision and len(db.rows) == 1
    assert await repo.count_accepted_last_7_days(db, 7, "p1") == 1
    assert await repo.count_same_seed_eligible_losses(db, 7, fingerprint) == 1

    conflict = copy.deepcopy(values)
    conflict["decision"] = {**decision, "projected": {"mora": 999}}
    try:
        await repo.save_decision(db, **conflict)
    except RuntimeError as exc:
        assert "idempotency conflict" in str(exc)
    else:
        raise AssertionError("Conflicting shadow replay was accepted")

    print("economy_shadow: immutable+idempotent+wallet-free  OK")


asyncio.run(main())
