"""Automatic screen of phone-timed Rhythm results before season places are frozen.

Rhythm runs are timed on the phone, so a forged journal could take a paid place.  Before the snapshot
every clear phone-timed run of the season is checked with the marks of the League
(services.league_rhythm, a stricter count of fast taps): many correct taps faster than a human can react to one of three random runes,
or machine-steady timing.  A marked run goes to review instead of the table (the player's next best run
counts); a person can still clear it later.  Honest play never meets these marks (tools/test_league_v1_rules.py).
"""
from __future__ import annotations

import statistics

from loguru import logger

from core import rhythm_v2 as rules
from infrastructure.repositories import rhythm_screen as repo
from services import league_rhythm as marks

# Stricter than the League: after a resume the rune seen before the pause comes back with a fresh window,
# so an honest player can make one instant tap per pause.  Twenty of them in one run is not play.
FAST_TAPS_TO_HOLD = 20


def journal_marks(seed: bytes, actions: list) -> list[str]:
    fast, steady = [], []
    for action in actions:
        if not isinstance(action, dict) or action.get("kind") != "tap":
            continue
        rune, elapsed, signal = action.get("rune"), action.get("elapsed_ms"), action.get("signal_no")
        if rune is None or type(elapsed) is not int or type(signal) is not int or signal < 1:
            continue
        correct = rune == rules.expected_rune(seed, signal)
        if elapsed < marks.FAST_TAP_MS:
            fast.append(correct)
        if correct:
            steady.append(elapsed)
    found = []
    if len(fast) >= FAST_TAPS_TO_HOLD and sum(fast) >= 0.8 * len(fast):
        found.append("fast_correct_taps")
    if len(steady) >= marks.STEADY_TAPS_TO_REVIEW and statistics.pstdev(steady) < marks.STEADY_SPREAD_MS:
        found.append("machine_steady_timing")
    return found


async def screen_season(db, *, mode: str, starts_at, ends_at) -> int:
    """Hold every marked run of the window for review; returns how many were held."""
    held = 0
    for row in await repo.local_runs(db, mode=mode, starts_at=starts_at, ends_at=ends_at):
        found = journal_marks(bytes(row["seed"]), row["actions"])
        if found and await repo.hold_for_review(db, run_id=row["run_id"], reason="auto_screen:" + ",".join(found),
                                                evidence={"marks": found, "taps": len(row["actions"])}):
            held += 1
            logger.warning("Season screen held Rhythm run {} of user {} for review: {}", row["run_id"], row["user_id"], found)
    return held
