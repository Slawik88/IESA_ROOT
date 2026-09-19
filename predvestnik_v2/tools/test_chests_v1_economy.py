"""Seeded million-open value and progression envelope for mixed chests."""
from __future__ import annotations

from collections import Counter
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.chests_v1 import FOODS, PAID_KEY_PRICE_ZARNIKI, roll_outcome


N = 1_000_000
rng = random.Random(20260912)
totals = Counter()
species_cards = Counter()
utility_zarniki = 0.0
for _ in range(N):
    outcome = roll_outcome(rng.randrange)
    totals[outcome.reward_kind] += outcome.amount
    if outcome.reward_kind == "mora":
        utility_zarniki += outcome.amount * 0.1  # published 1✨ -> 10 Mora rate
    elif outcome.reward_kind == "diamonds":
        utility_zarniki += outcome.amount * 100  # published 1✨ -> 0.01 Diamond rate
    elif outcome.reward_kind == "zarniki":
        utility_zarniki += outcome.amount
    elif outcome.reward_kind == "food":
        utility_zarniki += int(FOODS[outcome.reward_ref]["restore"]) * 0.1
    elif outcome.reward_kind == "pet_card":
        species_cards[outcome.reward_ref] += outcome.amount
        utility_zarniki += outcome.amount * 0.01
    elif outcome.reward_kind == "joker":
        utility_zarniki += outcome.amount * 0.02
    elif outcome.reward_kind == "vip_days":
        utility_zarniki += outcome.amount * 5  # 150✨ monthly VIP baseline

ev = utility_zarniki / N
common_per_open = species_cards["moss_cat"] / N
free_two_year_cards = common_per_open * 8 * 104
max_paid_two_year_cards = common_per_open * 22 * 104

# Conservative utility excludes collection excitement and VIP cosmetics. It is
# still near the 10✨ price, while a max-frequency player can finish one chosen
# 89,586-card Common curve in about two years. Free progression remains useful.
assert 8.0 <= ev <= PAID_KEY_PRICE_ZARNIKI
assert 30_000 <= free_two_year_cards <= 45_000
assert 89_586 <= max_paid_two_year_cards <= 120_000
assert totals["zarniki"] / N < 0.03  # cashback cannot self-fund a purchase loop
assert totals["diamonds"] / N < 0.03

print(
    f"OK: 1m-open EV={ev:.2f}/{PAID_KEY_PRICE_ZARNIKI} Zarniki; "
    f"chosen Common cards free/max={free_two_year_cards:.0f}/{max_paid_two_year_cards:.0f} in 2y"
)
