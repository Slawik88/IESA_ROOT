"""Casino rules: exact returns below 100%, published odds, payouts and input checks; a seeded million rounds agree."""
from fractions import Fraction
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import casino_v1 as c

assert Fraction(95, 100) <= c.slots_rtp() < Fraction(96, 100), float(c.slots_rtp())
assert c.wheel_rtp() == Fraction(95, 100) and len(c.WHEEL) == 20
assert all(Fraction(95, 100) <= c.dice_rtp(x) <= Fraction(96, 100) for x in c.DICE_CHANCES)
assert Fraction(30, 100) <= c.slots_hit_rate() <= Fraction(33, 100), "about every third spin pays something"
assert c.slots_mult(("herald", "herald", "herald")) == 30_000 and c.slots_mult(("herald", "blank", "herald")) == 800
assert c.slots_mult(("blank", "herald", "fehu")) == 100 and c.slots_mult(("fehu", "fehu", "raido")) == 50
assert c.slots_mult(("blank", "blank", "blank")) == 0 and c.slots_mult(("comet", "fehu", "comet")) == 0
assert c.dice_mult(50) == 192 and c.dice_mult(10) == 960 and c.payout(100, 192) == 192 and c.payout(10, 106) == 10
for bad in (0, 5, 1001, True, "100", None):
    try:
        c.check_stake(bad)
    except c.CasinoRuleError:
        continue
    raise AssertionError(f"stake {bad!r} accepted")
try:
    c.roll_dice(100, 33, random.Random(1).randrange)
except c.CasinoRuleError:
    pass
else:
    raise AssertionError("unlisted dice chance accepted")
# Seeded simulation: the house keeps its edge on every game, and the largest single win stays bounded.
rng = random.Random(20261022)
for game, params, low, high in (("slots", {}, .93, .98), ("wheel", {}, .93, .97), ("dice", {"chance": 50}, .94, .98)):
    staked = paid = top = 0
    for _ in range(300_000):
        out = c.play(game, 100, params, rng.randrange)
        staked += 100; paid += out.payout; top = max(top, out.mult)
    ratio = paid / staked
    assert low <= ratio <= high, (game, ratio)
    assert top <= 30_000
rules = c.public_rules()
assert rules["slots"]["rtp"] == 95.6 and rules["wheel"]["rtp"] == 95.0 and rules["dice"]["chances"][2]["mult"] == 192
assert rules["daily_gift"] == 1_000 and rules["chips_per_mora"] == 10 and rules["daily_buy_cap"] == 20_000
print("OK: casino — exact returns 95–96%, paytable, stakes and chances, 900k seeded rounds keep the house edge")
