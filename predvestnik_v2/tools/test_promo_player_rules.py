"""Promo codes screen (services/promo_player): which codes a player is shown in «Доступно сейчас». Pure rules, no database."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.promo_player import _offer  # noqa: E402

ME, NOW = 42, datetime(2026, 10, 15, tzinfo=timezone.utc)
MORA = '[{"type": "mora", "amount": 500}]'


def row(code="C", start=None, end=None, max_act=0, used=0, users="", rewards=MORA, shown=True):
    return (code, start, end, max_act, used, users, rewards, shown)


assert _offer(row(), ME, NOW)["rewards"] == ["🪙 500 мора"], "a public code is offered with its rewards"
assert _offer(row(shown=False), ME, NOW) is None, "a code the admin did not mark for the Mini App stays secret"
assert _offer(row(shown=False, users="[42]"), ME, NOW)["personal"] is True, "a personal code is shown to its player"
assert _offer(row(users="[421, 7]"), ME, NOW) is None, "LIKE '%42%' matched 421: the exact list check rejects it"
assert _offer(row(users="[421, 42]"), ME, NOW)["personal"] is True
assert _offer(row(end=(NOW - timedelta(days=1)).isoformat()), ME, NOW) is None, "an expired code is not offered"
assert _offer(row(start=(NOW + timedelta(days=1)).isoformat()), ME, NOW) is None, "a code that has not started is not offered"
assert _offer(row(max_act=10, used=10), ME, NOW) is None, "a code with no activations left is not offered"
assert _offer(row(max_act=10, used=4), ME, NOW)["left"] == 6
assert _offer(row(max_act=0, used=99), ME, NOW)["left"] is None, "no limit: nothing to count down"
assert _offer(row(rewards=None), ME, NOW) is None and _offer(row(rewards="[]"), ME, NOW) is None, "an old-format code cannot be redeemed, so it is not offered"
assert _offer(row(rewards="{oops"), ME, NOW) is None
until = _offer(row(end="2026-10-31T00:00:00+00:00"), ME, NOW)["until"]
assert until.startswith("2026-10-31"), until

# Every offered code passes the same server checks again on redeem: the screen never grants anything itself.
src = (ROOT / "FastAPI/static/app.45.js").read_text(encoding="utf-8")
assert "api('/promo-v2/redeem'" in src and "api('/promo-v2/me')" in src and "_profileEsc(o.code)" in src
repo = (ROOT / "infrastructure/repositories/promo_player.py").read_text(encoding="utf-8")
assert "allowed_chats_json, '') = ''" in repo and "NOT EXISTS (SELECT 1 FROM promocode_redemptions" in repo and "is_active = 1" in repo
from FastAPI.routers import promo_redeem as redeem_api  # noqa: E402
for i in range(redeem_api.FAILS_LIMIT):   # 10 неудачных вводов подряд — дальше 429 до конца окна
    assert redeem_api._fail_wait(7, 100.0 + i) == 0
    redeem_api._fails[7].append(100.0 + i)
assert redeem_api._fail_wait(7, 120.0) > 0
assert redeem_api._fail_wait(7, 100.0 + redeem_api.FAILS_WINDOW + redeem_api.FAILS_LIMIT) == 0 and 7 not in redeem_api._fails
print("OK: the promo screen offers only codes the player can redeem in the Mini App right now")
