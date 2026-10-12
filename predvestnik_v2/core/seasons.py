"""Pure calendar and reward rules for competitive game seasons.

A season is a fixed UTC window.  Leaderboards are computed from the runs that
finished inside the window, so a season "reset" is only the calendar moving on:
no player result is ever deleted or rewritten.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Final

SEASON_MONTHS: Final = 7
# Season 1 opens here (UTC).  Day 11 exists in every month, so month
# arithmetic below never has to clamp a day.
SEASON_ONE_START: Final = datetime(2026, 10, 11, tzinfo=timezone.utc)

# (max place, Mora, Essence).  The first matching tier wins; the last entry is
# the participation reward for everyone with at least one ranked result.
# Scale: the free quests pay about 315 Mora and 65 Essence a week, so first
# place is worth roughly three weeks of quests: it feels weighty but never
# buys a season-long head start.  Never cosmetics, keys or Zarniki.
REWARD_TIERS: Final = ((1, 800, 200), (2, 600, 150), (3, 450, 120), (10, 250, 80),
                       (25, 120, 40), (10**9, 40, 10))


class SeasonRuleError(ValueError):
    pass


def _add_months(moment: datetime, months: int) -> datetime:
    total = moment.year * 12 + (moment.month - 1) + months
    return moment.replace(year=total // 12, month=total % 12 + 1)


def season_bounds(number: int) -> tuple[datetime, datetime]:
    """Half-open [start, end) window of a season; seasons are numbered from 1."""
    if int(number) < 1:
        raise SeasonRuleError("season number must be positive")
    start = _add_months(SEASON_ONE_START, (int(number) - 1) * SEASON_MONTHS)
    return start, _add_months(start, SEASON_MONTHS)


def season_number(now: datetime) -> int:
    """Season containing ``now``; moments before the launch belong to season 1."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    months = (now.year - SEASON_ONE_START.year) * 12 + now.month - SEASON_ONE_START.month
    number = max(0, months // SEASON_MONTHS) + 1
    # Month division is only an estimate (the 12th may not have arrived yet).
    while number > 1 and now < season_bounds(number)[0]:
        number -= 1
    while now >= season_bounds(number)[1]:
        number += 1
    return number


def current_season(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    number = season_number(now)
    start, end = season_bounds(number)
    days_left = max(0, (end - now).days) if now.tzinfo else 0
    return {"number": number, "starts_at": start.isoformat(), "ends_at": end.isoformat(), "days_left": days_left,
            "rewards": reward_table()}


def reward(place: int) -> tuple[int, int]:
    """(Mora, Essence) for a final place."""
    if int(place) < 1:
        raise SeasonRuleError("place must be positive")
    _, mora, essence = next(tier for tier in REWARD_TIERS if int(place) <= tier[0])
    return mora, essence


def reward_table() -> list[dict]:
    """Display rows for the reward tiers: place label, Mora, Essence."""
    rows, previous = [], 0
    for limit, mora, essence in REWARD_TIERS:
        if limit >= 10**9:
            label = f"{previous + 1}+"
        elif limit == previous + 1:
            label = str(limit)
        else:
            label = f"{previous + 1}–{limit}"
        rows.append({"label": label, "mora": mora, "essence": essence})
        previous = limit
    return rows


def reward_mora(place: int) -> int:
    return reward(place)[0]
