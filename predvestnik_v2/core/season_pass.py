"""Pure rules of the free season pass (games only).

One pass per game season (``core.seasons``).  Points come from qualifying games
(a Rhythm run pays by its score, with diminishing returns), levels pay a fixed
slice of the full-track budget in Mora and Essence.  Never cosmetics, keys or Zarniki.  Budget and curve were simulated in
``tools/season_pass_sim.py`` and approved by the owner (pipeline ECO-01).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Final

from core import seasons

FLAG: Final = "season_pass_v1"
LEVELS: Final = 30
POINTS_PER_LEVEL: Final = 300
MINESWEEPER_POINTS: Final = 10          # a won board
# Rhythm: linear up to RHYTHM_LEVEL_SCORE (one level), then every tripling of the score adds one more
# level (10k -> 1, 30k -> 2, 70k -> ~2.8, 90k -> 3), so long runs stay worth it without breaking the track.
RHYTHM_LEVEL_SCORE: Final = 10_000
RHYTHM_MAX_POINTS: Final = 5 * POINTS_PER_LEVEL
FULL_TRACK_MORA: Final = 1200           # approved budget "Средний" for completing all levels
FULL_TRACK_ESSENCE: Final = 300
MORA_PER_LEVEL: Final = FULL_TRACK_MORA // LEVELS          # 40
ESSENCE_PER_LEVEL: Final = FULL_TRACK_ESSENCE // LEVELS    # 10
CLAIM_GRACE: Final = timedelta(days=30)  # unclaimed levels lapse this long after the season ends
RHYTHM_MIN_CORRECT_TAPS: Final = 20      # one chunk of real play
SOURCES: Final = ("rhythm", "minesweeper")   # the only places points can come from

assert MORA_PER_LEVEL * LEVELS == FULL_TRACK_MORA and ESSENCE_PER_LEVEL * LEVELS == FULL_TRACK_ESSENCE


class SeasonPassError(ValueError):
    pass


def utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


def rhythm_qualifies(*, integrity_status: str, correct_taps: int) -> bool:
    """A clear run with at least one chunk of correct taps."""
    return integrity_status == "clear" and int(correct_taps) >= RHYTHM_MIN_CORRECT_TAPS


def minesweeper_qualifies(*, won: bool) -> bool:
    return bool(won)


def level_of(points: int) -> int:
    return max(0, min(LEVELS, int(points) // POINTS_PER_LEVEL))


def rhythm_points(score: int) -> int:
    """Points one qualifying Rhythm run adds for its final score."""
    score = max(0, int(score))
    if score <= RHYTHM_LEVEL_SCORE:
        return max(1, score * POINTS_PER_LEVEL // RHYTHM_LEVEL_SCORE)
    levels = 1 + math.log(score / RHYTHM_LEVEL_SCORE, 3)
    return min(RHYTHM_MAX_POINTS, int(levels * POINTS_PER_LEVEL + 1e-9))


def reward_for_levels(claimed: int, reached: int) -> tuple[int, int]:
    """(Mora, Essence) for the levels in (claimed, reached]."""
    count = max(0, min(LEVELS, int(reached)) - max(0, int(claimed)))
    return count * MORA_PER_LEVEL, count * ESSENCE_PER_LEVEL


def claim_deadline(season: int) -> datetime:
    return seasons.season_bounds(season)[1] + CLAIM_GRACE


def claimable_seasons(now: datetime) -> list[int]:
    """Seasons whose levels can still be claimed: the current one and a finished one within the grace."""
    now = utc(now)
    current = seasons.season_number(now)
    result = [current]
    if current > 1 and now < claim_deadline(current - 1):
        result.insert(0, current - 1)
    return result
