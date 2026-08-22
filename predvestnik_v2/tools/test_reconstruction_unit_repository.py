#!/usr/bin/env python3
"""Idempotency checks for the isolated Reconstruction unit XP store."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from infrastructure.repositories import reconstruction_units as repo  # noqa: E402


class Cursor:
    def __init__(self, rows=None):
        self.rows = rows or []
    async def __aenter__(self): return self
    async def __aexit__(self, *_args): return None
    async def fetchone(self): return self.rows[0] if self.rows else None
    async def fetchall(self): return self.rows
    def __await__(self):
        async def done(): return self
        return done().__await__()


class DB:
    def __init__(self):
        self.progress = {}
        self.events = {}
        self.proofs = {}

    def execute(self, sql, args=()):
        compact = " ".join(sql.split())
        upper = compact.upper()
        if upper.startswith("INSERT INTO RECONSTRUCTION_UNIT_PROGRESS"):
            key = (int(args[0]), args[1], args[2])
            self.progress.setdefault(key, {"unit_id": args[2], "total_xp": 0,
                                           "branch_choices_json": "{}", "legacy_mastery": 0})
            return Cursor()
        if upper.startswith("SELECT UNIT_ID, TOTAL_XP"):
            if len(args) == 3:
                row = self.progress.get((int(args[0]), args[1], args[2]))
                return Cursor([dict(row)] if row else [])
            rows = [
                dict(row) for (user_id, version, _unit_id), row in self.progress.items()
                if user_id == int(args[0]) and version == args[1]
            ]
            return Cursor(sorted(rows, key=lambda row: row["unit_id"]))
        if upper.startswith("INSERT INTO RECONSTRUCTION_UNIT_XP_EVENTS"):
            key = (args[0], args[1])
            if key in self.events:
                return Cursor()
            self.events[key] = tuple(args[2:])
            return Cursor([(args[6],)])
        if upper.startswith("UPDATE RECONSTRUCTION_UNIT_PROGRESS"):
            key = (int(args[1]), args[2], args[3])
            if "TOTAL_XP = TOTAL_XP" in upper:
                self.progress[key]["total_xp"] += int(args[0])
                return Cursor()
            if self.progress[key]["branch_choices_json"] == args[4]:
                self.progress[key]["branch_choices_json"] = args[0]
                return Cursor([(args[0],)])
            return Cursor()
        if upper.startswith("SELECT USER_ID, GAME_VERSION"):
            row = self.events.get((args[0], args[1]))
            return Cursor([row] if row else [])
        if upper.startswith("INSERT INTO RECONSTRUCTION_MASTERY_PROOFS"):
            key = (int(args[0]), args[1], args[2])
            self.proofs.setdefault(key, {
                "challenge_id": args[2], "terminal_result_id": args[3],
                "encounter_id": args[4], "proven_at": "2026-08-22T00:00:00Z",
            })
            return Cursor()
        if upper.startswith("SELECT CHALLENGE_ID, TERMINAL_RESULT_ID"):
            rows = [
                dict(row) for (user_id, version, _challenge), row in self.proofs.items()
                if user_id == int(args[0]) and version == args[1]
            ]
            return Cursor(sorted(rows, key=lambda row: row["challenge_id"]))
        raise AssertionError(f"Unexpected SQL: {compact}")


async def main():
    source = (ROOT / "infrastructure/repositories/reconstruction_units.py").read_text(
        encoding="utf-8"
    )
    assert "legacy ``user_units``" in source
    assert "UPDATE user_units" not in source and "INSERT INTO user_units" not in source
    assert "PRIMARY KEY (terminal_result_id, unit_id)" in source

    db = DB()
    request = dict(
        terminal_result_id="reconstruction:44:terminal", user_id=7,
        game_version="3.0.0-alpha.3", policy_version="p1",
        unit_id="r_oath_bell", squad_role="lead", xp_delta=100,
    )
    first = await repo.apply_xp_once(db, **request)
    replay = await repo.apply_xp_once(db, **request)
    assert first["applied"] is True and replay["applied"] is False
    assert first["progress"]["total_xp"] == replay["progress"]["total_xp"] == 100
    assert len(db.events) == 1

    # Reach level 5, then prove and choose exactly one real branch.
    db.progress[(7, "3.0.0-alpha.3", "r_oath_bell")]["total_xp"] = 1190
    proofs = await repo.record_mastery_proofs(
        db, user_id=7, game_version="3.0.0-alpha.3",
        terminal_result_id="reconstruction:43:terminal", encounter_id="e01_two_bells",
        challenge_ids=("bell_recover_three_clean",),
    )
    assert "bell_recover_three_clean" in proofs
    selected = await repo.choose_branch(
        db, user_id=7, game_version="3.0.0-alpha.3", unit_id="r_oath_bell",
        branch_id="bell_broken_vow",
    )
    selected_again = await repo.choose_branch(
        db, user_id=7, game_version="3.0.0-alpha.3", unit_id="r_oath_bell",
        branch_id="bell_broken_vow",
    )
    assert selected["applied"] is True and selected_again["applied"] is False
    assert selected["progress"]["branch_choices"] == {"5": "bell_broken_vow"}
    try:
        await repo.choose_branch(
            db, user_id=7, game_version="3.0.0-alpha.3", unit_id="r_oath_bell",
            branch_id="bell_silent_release",
        )
    except ValueError as exc:
        assert "respec" in str(exc)
    else:
        raise AssertionError("Second free branch was accepted")

    conflict = dict(request, xp_delta=101)
    try:
        await repo.apply_xp_once(db, **conflict)
    except RuntimeError as exc:
        assert "idempotency conflict" in str(exc)
    else:
        raise AssertionError("Conflicting XP replay was accepted")

    print("reconstruction_unit_repository: isolated+idempotent XP  OK")


asyncio.run(main())
