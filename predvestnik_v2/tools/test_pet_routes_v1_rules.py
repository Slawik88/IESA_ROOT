"""Pure rules for expedition route outcomes: equal EV across routes, level nudges, caps."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.pet_routes_v1 import EV_BY_HOURS, ROUTE_CHANCE, ROUTES, WEEKLY_CAP_MORA, payout_after_cap, roll_success, route_available, route_odds
from core.pets_v1 import level_effects

for hours, ev in EV_BY_HOURS.items():
    for route in ("careful", "steady", "scout", "bold"):
        odds = route_odds(route, hours, level_effects(1))
        assert abs(odds.chance_percent / 100 * odds.reward_mora - ev) <= ev * 0.02, (route, hours)
assert not route_available("scout", 11) and route_available("scout", 12) and not route_available("nope", 16)
assert route_odds("careful", 9, level_effects(8)).chance_percent == 99, "chance is capped at 99%"
assert [route_odds("scout", h, level_effects(1)).reward_mora for h in (3, 6, 9)] == [57, 114, 171]
assert route_odds("scout", 6, level_effects(1)).chance_percent == 70 and route_odds("scout", 6, level_effects(8)).chance_percent == 75
assert route_odds("bold", 9, level_effects(1)).chance_percent == 60 and route_odds("bold", 9, level_effects(8)).chance_percent == 65
# the best possible uplift of a level-16 pet stays near the agreed +24% of EV
# at L16 no route dominates another: expected values keep rising with risk
ev16 = {r: route_odds(r, 6, level_effects(16)).chance_percent / 100 * route_odds(r, 6, level_effects(16)).reward_mora for r in ROUTES}
assert ev16["careful"] < ev16["steady"] < ev16["scout"] < ev16["bold"], ev16
best = max(route_odds(r, 6, level_effects(16)).chance_percent / 100 * route_odds(r, 6, level_effects(16)).reward_mora for r in ROUTES)
assert best <= EV_BY_HOURS[6] * 1.30, best
assert payout_after_cap(200, 300) == 100 and payout_after_cap(50, WEEKLY_CAP_MORA) == 0 and payout_after_cap(50, 0) == 50
rolls = [roll_success(route_odds("steady", 3, level_effects(1)), lambda n: i) for i in range(100)]
assert sum(rolls) == 80 and set(ROUTE_CHANCE) <= set(ROUTES)
print("OK: route outcomes keep equal EV, level nudges stay small, caps hold")
