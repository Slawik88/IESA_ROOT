#!/usr/bin/env python3
"""Pure rules for ECO-04 PR-A keys by stars: tier mapping, public odds, card value per tier."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.chests_v1 import (
    CARD_AMOUNTS, JOKER_AMOUNTS, KEY_OFFERS, KEY_TIER_BY_SOURCE, KEY_TIERS, PAID_KEY_DAILY_LIMIT,
    REWARD_WEIGHTS, STAR_WEIGHTS, ChestPolicyError, catalog_payload, key_tier, roll_outcome,
    stars_for_roll, stars_for_tier_roll, tier_star_odds,
)

JOKER_IN_CARDS = 250  # owner's valuation for comparing tiers (handoff §3.3)


def card_value(tier: int) -> float:
    total = 0.0
    for row in tier_star_odds(tier):
        stars, p = int(row["stars"]), row["basis_points"] / 10_000
        weights = REWARD_WEIGHTS[stars]
        cards = weights.get("pet_card", 0) / 100 * CARD_AMOUNTS.get(stars, 0)
        jokers = weights.get("joker", 0) / 100 * JOKER_AMOUNTS.get(stars, 0) * JOKER_IN_CARDS
        total += p * (cards + jokers)
    return total


def main() -> None:
    for roll in range(10_000):
        base = stars_for_roll(roll)
        for tier in KEY_TIERS:
            assert stars_for_tier_roll(roll, tier) == max(base, tier)
    for tier in KEY_TIERS:
        rows = tier_star_odds(tier)
        assert sum(r["basis_points"] for r in rows) == 10_000 and rows[0]["stars"] == tier
        assert all(r["basis_points"] == STAR_WEIGHTS[r["stars"]] for r in rows[1:])
        rolls = iter(range(10_000))
        for _ in range(2_000):
            outcome = roll_outcome(lambda n: next(rolls) % n if n == 10_000 else 0, tier=tier)
            assert outcome.stars >= tier
    assert [tier_star_odds(t)[0]["percent"] for t in (3, 4, 6)] == [80.0, 89.0, 97.0]
    values = {tier: round(card_value(tier)) for tier in KEY_TIERS}
    assert values == {1: 308, 3: 438, 4: 630, 6: 1699}, values
    for bad in (0, 2, 5, 7, True, "3"):
        try:
            key_tier(bad)
        except ChestPolicyError:
            continue
        raise AssertionError(bad)
    assert {o["tier"] for o in KEY_OFFERS.values()} == {3, 4, 6}
    assert KEY_OFFERS["silver_zarniki"]["limit"] == PAID_KEY_DAILY_LIMIT
    assert {k: KEY_TIER_BY_SOURCE[k] for k in KEY_TIER_BY_SOURCE if not k.startswith("offer_")} == {
        "quest_daily_set_complete": 1, "quest_weekly_set_complete": 1, "zarniki_purchase": 1,
        "pet_trek_complete": 1, "pet_expedition_complete": 1, "vip_daily_milestone": 1}
    assert catalog_payload()["key_offers"] is KEY_OFFERS
    print(f"OK: key tiers keep the roll, lift stars to the tier, odds 80/89/97%, card value {values}")


main()
