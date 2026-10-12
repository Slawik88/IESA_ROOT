"""Pure rules of the free season pass (games only).

One pass per game season (``core.seasons``).  Points come from qualifying games,
a day is capped, levels pay a fixed slice of the full-track budget in Mora and
Essence.  Never cosmetics, keys or Zarniki.  Budget and curve were simulated in
``tools/season_pass_sim.py`` and approved by the owner (pipeline ECO-01).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final

from core import seasons

FLAG: Final = "season_pass_v1"
LEVELS: Final = 30
POINTS_PER_LEVEL: Final = 300
POINTS_PER_GAME: Final = 10
DAILY_POINT_CAP: Final = 100            # 10 qualifying games per UTC day
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


def granted_points(day_points: int) -> int:
    """Points one more qualifying game adds on a day that already holds ``day_points``."""
    return max(0, min(POINTS_PER_GAME, DAILY_POINT_CAP - int(day_points)))


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
