#!/usr/bin/env python3
"""Offline proof (audit A12): a failed daily job is retried on the next maintenance
pass the same day, a successful one runs once per UTC day, and one job's failure
does not block the other. No network or database."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import scheduler

runs = {"flaky": 0, "steady": 0}
fail_next = {"flaky": True}


async def flaky(db) -> None:
    runs["flaky"] += 1
    if fail_next["flaky"]:
        fail_next["flaky"] = False
        raise ConnectionError("database briefly unavailable")


async def steady(db) -> None:
    runs["steady"] += 1


async def main() -> None:
    scheduler._DAILY_JOBS = (("flaky", flaky), ("steady", steady))
    scheduler._daily_done.clear()
    scheduler._daily_attempts.clear()
    await scheduler._daily_gc(None)            # flaky fails, steady still runs
    assert runs == {"flaky": 1, "steady": 1}, runs
    await scheduler._daily_gc(None)            # same day: flaky retried, steady not rerun
    assert runs == {"flaky": 2, "steady": 1}, runs
    await scheduler._daily_gc(None)            # both done for today
    assert runs == {"flaky": 2, "steady": 1}, runs
    scheduler._daily_done.clear()              # next UTC day
    scheduler._daily_attempts.clear()
    await scheduler._daily_gc(None)
    assert runs == {"flaky": 3, "steady": 2}, runs

    # A permanently failing job stops after the daily attempt cap.
    async def broken(db) -> None:
        runs["broken"] = runs.get("broken", 0) + 1
        raise ConnectionError("still down")

    scheduler._DAILY_JOBS = (("broken", broken),)
    for _ in range(scheduler._DAILY_MAX_ATTEMPTS + 5):
        await scheduler._daily_gc(None)
    assert runs["broken"] == scheduler._DAILY_MAX_ATTEMPTS, runs


asyncio.run(main())
print("daily maintenance retry: OK")
