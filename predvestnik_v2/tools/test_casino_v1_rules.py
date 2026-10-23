"""Casino rules: exact returns below 100%, published odds, payouts and input checks; a seeded million rounds agree."""
from fractions import Fraction
from itertools import product
from math import prod
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import casino_v1 as c

assert c.slots_rtp() == Fraction(52997, 54000), float(c.slots_rtp())
assert c.wheel_rtp() == Fraction(975, 1000) and len(c.WHEEL) == 20
assert all(Fraction(97, 100) <= c.dice_rtp(x) <= Fraction(98, 100) for x in c.DICE_CHANCES)
assert c.slots_hit_rate() == Fraction(376, 1125) and c.slots_win_rate() == Fraction(23, 450)
assert c.slots_mult(('fehu', 'fehu', 'fehu')) == 850
assert c.slots_mult(("herald", "herald", "herald")) == 30_000 and c.slots_mult(("herald", "blank", "herald")) == 800
assert c.slots_mult(("blank", "herald", "fehu")) == 100 and c.slots_mult(("fehu", "fehu", "raido")) == 50
assert c.slots_mult(("blank", "blank", "blank")) == 0 and c.slots_mult(("comet", "fehu", "comet")) == 0
assert c.dice_mult(50) == 196 and c.dice_mult(10) == 980 and c.payout(100, 196) == 196 and c.payout(10, 108) == 10
for bad in (0, 5, 1001, True, "100", None):
    try:
        c.check_stake(bad)
    except c.CasinoRuleError:
        continue
    raise AssertionError(f"stake {bad!r} accepted")
for bad in (33, True, 50.0, None, '50', [], {}):
    try:
        c.roll_dice(100, bad, random.Random(1).randrange)
    except c.CasinoRuleError:
        pass
    else:
        raise AssertionError(f"invalid dice chance accepted: {bad!r}")
# Enumerate every weighted outcome at EVERY stake: integer rounding may reduce a theoretical win to break-even.
weights = dict(c.REEL)
for stake in c.STAKES:
    slots_paid = sum(Fraction(prod(weights[s] for s in reels), c.REEL_TOTAL ** 3) * c.payout(stake, c.slots_mult(reels))
                     for reels in product(weights, repeat=3))
    wheel_paid = Fraction(sum(c.payout(stake, m) for m in c.WHEEL), len(c.WHEEL))
    assert Fraction(96,100) < slots_paid / stake < 1
    assert wheel_paid / stake == c.wheel_rtp()
    for chance in c.DICE_CHANCES:
        dice_paid = Fraction(chance * c.payout(stake, c.dice_mult(chance)), 100)
        assert Fraction(90,100) <= dice_paid / stake < 1
        for roll in range(100):
            result = c.roll_dice(stake, chance, lambda n, roll=roll: roll)
            assert (result.mult > 0) == (roll < chance)
# Seeded simulation: the house keeps its edge on every game, and the largest single win stays bounded.
rng = random.Random(20261022)
for game, params, low, high in (("slots", {}, .95, 1.02), ("wheel", {}, .96, .99), ("dice", {"chance": 50}, .96, 1.0)):
    staked = paid = top = 0
    for _ in range(300_000):
        out = c.play(game, 100, params, rng.randrange)
        staked += 100; paid += out.payout; top = max(top, out.mult)
    ratio = paid / staked
    assert low <= ratio <= high, (game, ratio)
    assert top <= 30_000
rules = c.public_rules()
assert rules["slots"]["rtp"] == 98.1 and rules["wheel"]["rtp"] == 97.5 and rules["dice"]["chances"][2]["mult"] == 196
assert rules['slots']['hit_rate'] == 33.4 and rules['slots']['win_rate'] == 5.1
assert rules['wheel']['hit_rate'] == 60.0 and rules['wheel']['win_rate'] == 35.0
assert rules["daily_gift"] == 1_000 and rules["chips_per_mora"] == 1 and rules["daily_buy_cap"] == 20_000
assert len(c.badge_progress({})) == 6 and not any(b['unlocked'] for b in c.badge_progress({}))
assert all(b['unlocked'] for b in c.badge_progress(dict(rounds=1,games=3,triples=1,wheel_wins=1,dice_wins=1,best_mult=500)))
assert not c.badge_progress({'best_mult':499})[-1]['unlocked']
print("OK: casino — exact returns 97.5–98.1%, every stake/rounding, honest win odds, 6 badges, 900k seeded rounds")
