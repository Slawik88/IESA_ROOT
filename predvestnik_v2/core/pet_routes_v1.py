"""Expedition route outcomes paid in Mora (ECO-04 route rewards). Pure rules: no clock, no database.

Every route has the same expected value per expedition, so the choice is risk taste, not a better deal:
reward on success R = EV / p.  Level effects only nudge the numbers: a route bonus on the reward, a risk
guard on the chance and, from L4, the exact odds shown before choosing.  Failure pays nothing and takes nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from core.pets_v1 import PetPolicyError

POLICY_VERSION: Final = "pet-routes-v1-2026-10-13"
FLAG: Final = "pets_route_rewards_v1"
REASON_CODE: Final = "pet_route_reward"

# Expected Mora per expedition at level 1, by duration in hours.
EV_BY_HOURS: Final = {3: 40, 6: 80, 9: 120}
ROUTE_CHANCE: Final = {"careful": 0.95, "steady": 0.80, "bold": 0.60}
SCOUT_CHANCE: Final = 0.70          # unlocked by the L12 extra option: one more risk notch between steady and bold
SCOUT_EV_SHARE: Final = 1.0         # same expected value as every other route: a finer choice, never a better deal
CHANCE_CAP: Final = 0.99
RISK_GUARD_POINTS: Final = 0.05
WEEKLY_CAP_MORA: Final = 400        # per player, UTC week, route rewards only
HINT_MIN_LEVEL: Final = 4
SCOUT_MIN_LEVEL: Final = 12
ROUTES: Final = ("careful", "steady", "scout", "bold")   # ordered by risk


@dataclass(frozen=True, slots=True)
class RouteOdds:
    route: str
    chance_percent: int       # exact server chance, 0..99
    reward_mora: int          # paid on success, route bonus included
    base_reward_mora: int


def route_available(route: str, level: int) -> bool:
    if route not in ROUTES:
        return False
    return route != "scout" or int(level) >= SCOUT_MIN_LEVEL


def route_odds(route: str, hours: int, effects: dict) -> RouteOdds:
    if route not in ROUTES:
        raise PetPolicyError("Неизвестный маршрут.")
    if int(hours) not in EV_BY_HOURS:
        raise PetPolicyError("Длительность: только 3, 6 или 9 часов.")
    ev = EV_BY_HOURS[int(hours)]
    if route == "scout":
        chance = SCOUT_CHANCE
        base_ev = ev * SCOUT_EV_SHARE
    else:
        chance = ROUTE_CHANCE[route]
        base_ev = float(ev)
    base_reward = round(base_ev / chance)
    reward = (base_reward * (100 + int(effects.get("expedition_route_bonus_percent", 0))) + 50) // 100
    guard = RISK_GUARD_POINTS if int(effects.get("expedition_risk_guard_percent", 0)) else 0.0
    chance = min(CHANCE_CAP, chance + guard)
    return RouteOdds(route, int(round(chance * 100)), int(reward), int(base_reward))


def roll_success(odds: RouteOdds, randbelow) -> bool:
    """randbelow(n) is a server-side CSPRNG; the client never supplies or sees the roll."""
    return randbelow(100) < odds.chance_percent


def payout_after_cap(reward: int, paid_this_week: int) -> int:
    return max(0, min(int(reward), WEEKLY_CAP_MORA - max(0, int(paid_this_week))))
