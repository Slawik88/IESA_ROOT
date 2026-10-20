#!/usr/bin/env python3
"""Pure rules of the free season pass."""
from datetime import datetime, timedelta, timezone

from core import season_pass as p
from core import seasons

utc = lambda *a: datetime(*a, tzinfo=timezone.utc)

assert (p.LEVELS, p.POINTS_PER_LEVEL, p.MINESWEEPER_POINTS, p.RHYTHM_LEVEL_SCORE) == (30, 300, 10, 10_000)
assert (p.FULL_TRACK_MORA, p.FULL_TRACK_ESSENCE) == (1200, 300), "owner-approved budget 'Средний'"
assert (p.MORA_PER_LEVEL, p.ESSENCE_PER_LEVEL) == (40, 10)
assert p.reward_for_levels(0, p.LEVELS) == (1200, 300), "the whole track pays exactly the approved budget"
assert p.reward_for_levels(0, 10**6) == (1200, 300), "levels above the track pay nothing extra"
assert p.reward_for_levels(10, 10) == (0, 0) and p.reward_for_levels(12, 5) == (0, 0)
assert p.reward_for_levels(3, 5) == (80, 20)

assert [p.level_of(x) for x in (0, 299, 300, 8999, 9000, 10**9)] == [0, 0, 1, 29, 30, 30]
# Rhythm pays by score: linear up to one level at 10k, then each tripling of the score adds a level.
assert [p.rhythm_points(x) for x in (-5, 0, 100, 2000, 10_000)] == [1, 1, 3, 60, 300]
assert [p.rhythm_points(x) for x in (30_000, 70_000, 90_000)] == [600, 831, 900]
assert p.rhythm_points(10**9) == p.RHYTHM_MAX_POINTS == 1500
scores = list(range(0, 2_000_001, 997))
assert all(p.rhythm_points(a) <= p.rhythm_points(b) for a, b in zip(scores, scores[1:])), "more score never pays less"
assert all(p.rhythm_points(b) / b <= p.rhythm_points(a) / a + 1e-9 for a, b in zip(scores[11:], scores[12:])), \
    "points per score point never grow"

assert p.SOURCES == ("rhythm", "minesweeper"), "Mafia events are not verified yet"
assert p.rhythm_qualifies(integrity_status="clear", correct_taps=20)
assert not p.rhythm_qualifies(integrity_status="clear", correct_taps=19)
for bad in ("pending", "review_required", "quarantined", "offline_exposed", "legacy_unverified"):
    assert not p.rhythm_qualifies(integrity_status=bad, correct_taps=500), bad
assert p.minesweeper_qualifies(won=True) and not p.minesweeper_qualifies(won=False)

# Claim windows: the current season and a finished one for 30 days after its end.
end1 = seasons.season_bounds(1)[1]
assert p.claim_deadline(1) == end1 + timedelta(days=30)
assert p.claimable_seasons(utc(2026, 11, 1)) == [1]
assert p.claimable_seasons(end1 + timedelta(days=29)) == [1, 2]
assert p.claimable_seasons(end1 + timedelta(days=30)) == [2]
assert p.claimable_seasons(utc(2028, 2, 1)) == [3]

assert p.utc(datetime(2027, 1, 1)).tzinfo == timezone.utc

from core import account_age as age

seen = utc(2026, 10, 1)
assert age.MIN_ACCOUNT_AGE == timedelta(days=14)
assert age.is_eligible(seen, utc(2026, 10, 15)) and not age.is_eligible(seen, utc(2026, 10, 14, 23, 59))
assert not age.is_eligible(None, utc(2030, 1, 1)) and age.eligible_from(None) is None, "no chat record = new"
assert age.first_seen(datetime(2026, 10, 5), utc(2026, 10, 3, 12), "2026-10-04") == utc(2026, 10, 3, 12), "earliest wins"
assert age.first_seen(None, None, "2026-10-04") == utc(2026, 10, 4) and age.first_seen(None, None, "junk") is None
assert age.eligible_ids({1: seen, 2: utc(2026, 10, 10)}, [1, 2, 3], utc(2026, 10, 20)) == {1}
print("season pass rules OK")
