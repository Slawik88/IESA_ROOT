#!/usr/bin/env python3
"""Presence V1 rules: labels, privacy levels and the no-leak guarantee (pure, no database)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.presence_v1 import DEFAULT_LEVEL, LEVELS, describe, normalize, visible_detail  # noqa: E402

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
ago = lambda **kw: NOW - timedelta(**kw)  # noqa: E731

assert LEVELS == ("everyone", "approx", "nobody") and DEFAULT_LEVEL == "approx", "the careful option is the default"
assert normalize(None) == "approx" and normalize("junk") == "approx" and normalize("nobody") == "nobody"

# exact level: relative labels with proper Russian plurals
cases = [({"seconds": 30}, "online", "в сети"), ({"minutes": 3}, "online", "в сети"), ({"minutes": 4}, "ago", "был(а) 4 минуты назад"), ({"minutes": 21}, "ago", "был(а) 21 минуту назад"),
         ({"minutes": 12}, "ago", "был(а) 12 минут назад"), ({"hours": 1}, "ago", "был(а) 1 час назад"), ({"hours": 5}, "ago", "был(а) 5 часов назад"), ({"hours": 23}, "ago", "был(а) 23 часа назад"),
         ({"days": 1, "hours": 2}, "ago", "был(а) вчера"), ({"days": 3}, "ago", "был(а) 3 дня назад"), ({"days": 11}, "ago", "был(а) 11 дней назад"), ({"days": 40}, "ago", "был(а) 29.08.2026")]
for delta, state, label in cases:
    got = describe(NOW - timedelta(**delta), "everyone", "everyone", NOW)
    assert got == {"state": state, "label": label}, (delta, got)

# approximate level: coarse buckets only, never "в сети", never a number
for delta, label in [({"seconds": 5}, "был(а) недавно"), ({"days": 3}, "был(а) недавно"), ({"days": 5}, "был(а) на этой неделе"), ({"days": 20}, "был(а) в этом месяце"), ({"days": 90}, "был(а) давно")]:
    assert describe(NOW - timedelta(**delta), "approx", "everyone", NOW) == {"state": "recent", "label": label}, delta

# hidden owner shows nothing; unknown time shows nothing
assert describe(ago(minutes=1), "nobody", "everyone", NOW) is None and describe(None, "everyone", "everyone", NOW) is None
# reciprocity: a viewer who hides their own time sees the others only coarsely
assert visible_detail("everyone", "nobody") == "approx" and visible_detail("everyone", "approx") == "exact" and visible_detail("nobody", "nobody") == "none"
assert describe(ago(minutes=1), "everyone", "nobody", NOW)["label"] == "был(а) недавно"

# nothing in an answer can carry a timestamp
for level in LEVELS:
    out = describe(ago(minutes=7), level, "everyone", NOW)
    if out:
        assert set(out) == {"state", "label"} and "2026" not in out["label"].replace("29.08.2026", "")
print("OK: presence labels, privacy levels, reciprocity and no-leak")
