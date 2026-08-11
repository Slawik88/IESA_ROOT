#!/usr/bin/env python3
"""Regression checks for tutorial milestone reconciliation."""
from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from FastAPI.routers import battle as battle_router


class FakeDB:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


async def main():
    original_get = battle_router.users_repo.get_combat_tutorial_done
    original_set = battle_router.users_repo.set_combat_tutorial_done
    original_completed = battle_router.bt_repo.has_completed

    state = {"flag": False, "won": False, "sets": 0, "fail_set": False, "history_reads": 0}

    async def get_flag(_db, _uid):
        return state["flag"]

    async def set_flag(_db, _uid):
        state["sets"] += 1
        if state["fail_set"]:
            raise RuntimeError("temporary projection write failure")
        state["flag"] = True

    async def has_completed(_db, _uid, mode, status="won"):
        state["history_reads"] += 1
        assert mode == "tutorial" and status == "won"
        return state["won"]

    battle_router.users_repo.get_combat_tutorial_done = get_flag
    battle_router.users_repo.set_combat_tutorial_done = set_flag
    battle_router.bt_repo.has_completed = has_completed
    try:
        db = FakeDB()

        state["flag"] = True
        assert await battle_router._tutorial_done_reconciled(db, 7001) is True
        assert state["history_reads"] == 0 and state["sets"] == 0

        state["flag"] = False
        assert await battle_router._tutorial_done_reconciled(db, 7001) is False
        assert state["history_reads"] == 1 and state["sets"] == 0

        state["won"] = True
        assert await battle_router._tutorial_done_reconciled(db, 7001) is True
        assert state["sets"] == 1 and state["flag"] is True and db.commits == 1

        state["flag"] = False
        state["fail_set"] = True
        assert await battle_router._tutorial_done_reconciled(db, 7001) is True
        assert state["sets"] == 2 and db.commits == 1 and db.rollbacks == 1
    finally:
        battle_router.users_repo.get_combat_tutorial_done = original_get
        battle_router.users_repo.set_combat_tutorial_done = original_set
        battle_router.bt_repo.has_completed = original_completed

    print("OK: tutorial flag reconciles from won battle and tolerates projection failure")


asyncio.run(main())
