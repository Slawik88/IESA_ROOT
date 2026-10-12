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
# Payout terms: participation, podium gating by board size, one board pays.
assert (s.MIN_PARTICIPATION_RUNS, s.MIN_PARTICIPATION_DAYS) == (5, 3)
assert s.qualifies(5, 3) and not s.qualifies(4, 9) and not s.qualifies(9, 2)
big = dict(board_size=1000, runs=5, days=3)
assert [s.payout(p, **big) for p in (1, 2, 3, 4, 10, 11, 25, 26)] == [
    (800, 200), (600, 150), (450, 120), (250, 80), (250, 80), (120, 40), (120, 40), (40, 10)]
assert s.payout(1, board_size=9, runs=5, days=3) == (40, 10), "podium needs 10 qualified players"
assert s.payout(1, board_size=10, runs=5, days=3) == (800, 200)
assert s.payout(4, board_size=19, runs=5, days=3) == (40, 10) and s.payout(4, board_size=20, runs=5, days=3) == (250, 80)
assert s.payout(11, board_size=49, runs=5, days=3) == (40, 10) and s.payout(11, board_size=50, runs=5, days=3) == (120, 40)
assert s.payout(1, board_size=1000, runs=4, days=9) == (0, 0) and s.payout(1, board_size=1000, runs=9, days=2) == (0, 0)
try:
    s.payout(0, **big)
except s.SeasonRuleError:
    pass
else:
    raise AssertionError("place 0 must be rejected")
assert s.is_paying("rhythm", "normal")
assert not any(s.is_paying("minesweeper", b) for b in ("easy", "normal", "hard")), "Minesweeper pays nothing yet"
assert s.SETTLEMENT_DELAY.total_seconds() == 48 * 3600
assert s.terms() == {"min_runs": 5, "min_days": 3, "podium_min_players": {"3": 10, "10": 20, "25": 50}}

# Ranking only qualified players keeps ties and closes the gaps left by the unqualified.
from services.game_seasons import qualified_places
rows = [dict(user_id=1, place=1, runs=2, days=1), dict(user_id=2, place=2, runs=5, days=3),
        dict(user_id=3, place=2, runs=6, days=4), dict(user_id=4, place=4, runs=5, days=3),
        dict(user_id=5, place=5, runs=9, days=2)]
assert [(r["user_id"], r["place_among_qualified"]) for r in qualified_places(rows)] == [(2, 1), (3, 1), (4, 3)]
print("game seasons rules OK")
