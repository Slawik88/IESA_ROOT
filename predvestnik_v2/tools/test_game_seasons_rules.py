#!/usr/bin/env python3
"""Calendar and reward rules for game seasons."""
from datetime import datetime, timezone

from core import seasons as s

utc = lambda *a: datetime(*a, tzinfo=timezone.utc)

start1, end1 = s.season_bounds(1)
assert start1 == s.SEASON_ONE_START and end1 == utc(2027, 5, 11)
start2, end2 = s.season_bounds(2)
assert start2 == end1 and end2 == utc(2027, 12, 11), (start2, end2)
assert s.season_bounds(3)[0] == end2 and s.season_bounds(3)[1] == utc(2028, 7, 11)

assert s.season_number(utc(2026, 1, 1)) == 1, "before launch belongs to season 1"
assert s.season_number(start1) == 1
assert s.season_number(utc(2027, 5, 10, 23, 59, 59)) == 1
assert s.season_number(end1) == 2
assert s.season_number(utc(2027, 12, 10)) == 2 and s.season_number(utc(2027, 12, 11)) == 3
assert s.season_number(utc(2040, 1, 1)) > 3
for n in range(1, 30):
    a, b = s.season_bounds(n)
    assert s.season_number(a) == n and s.season_number(b) == n + 1

info = s.current_season(utc(2027, 5, 1))
assert info["number"] == 1 and info["days_left"] == 10, info

assert [s.reward(p) for p in (1, 2, 3, 4, 10, 11, 25, 26, 5000)] == [
    (800, 200), (600, 150), (450, 120), (250, 80), (250, 80), (120, 40), (120, 40), (40, 10), (40, 10)]
assert s.reward_mora(1) == 800
try:
    s.season_bounds(0)
except s.SeasonRuleError:
    pass
else:
    raise AssertionError("season 0 must be rejected")
print("game seasons rules OK")
