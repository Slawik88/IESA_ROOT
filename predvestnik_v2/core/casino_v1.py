"""Casino «Зал Фортуны» v1: pure rules, odds and payouts. No SQL, no clock, no randomness source.

Social casino on its own chips («жетоны»), on purpose:
* Мора can be bought with Зарники (and those with Telegram Stars), so a game that paid Мора back would be
  gambling for a purchasable currency and a Мора printer. Chips come in only (a free daily gift, or Мора at a
  fixed rate, capped per day) and never go out: winnings are chips, there is no chips → Мора/Зарники route.
* Every game has a published, exactly computed return (tools/test_casino_v1_rules.py enumerates it): the house
  keeps 4–5% over the distance, the player sees honest odds.

Money is integer chips; multipliers are integer hundredths (×1.5 = 150), payout = stake × mult // 100.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from typing import Callable, Final

POLICY_VERSION: Final = "casino-v1-2026-10-22"
CHIP_NAME: Final = "жетоны"

DAILY_GIFT: Final = 1_000                  # free chips once per UTC day
CHIPS_PER_MORA: Final = 10
MORA_PACKS: Final = (100, 500, 1_000)      # Мора → 1 000 / 5 000 / 10 000 chips
DAILY_BUY_CAP_CHIPS: Final = 20_000        # bought chips per UTC day: a ceiling against a bad evening
STAKES: Final = (10, 50, 100, 250, 500, 1_000)


class CasinoRuleError(ValueError):
    pass


@dataclass(frozen=True)
class Outcome:
    game: str
    mult: int            # hundredths
    payout: int
    detail: dict


def payout(stake: int, mult: int) -> int:
    return stake * mult // 100


def check_stake(stake: object) -> int:
    if isinstance(stake, bool) or not isinstance(stake, int) or stake not in STAKES:
        raise CasinoRuleError("Выберите ставку из списка.")
    return stake


# ── «Руны удачи»: three reels ─────────────────────────────────────────────────────────────────────────────
REEL: Final = (("blank", 7), ("fehu", 8), ("raido", 6), ("thurs", 4), ("comet", 3), ("herald", 2))
REEL_TOTAL: Final = sum(weight for _, weight in REEL)
SYMBOLS: Final = {"blank": "·", "fehu": "ᚠ", "raido": "ᚱ", "thurs": "ᚦ", "comet": "☄", "herald": "🌌"}
TRIPLE: Final = {"fehu": 1_100, "raido": 2_000, "thurs": 4_000, "comet": 8_000, "herald": 30_000}
TWO_HERALDS: Final = 800
ONE_HERALD: Final = 100      # the stake comes back
FIRST_PAIR: Final = 50       # two equal runes on the first two reels: half the stake back


def slots_mult(reels: tuple[str, str, str]) -> int:
    a, b, c = reels
    if a == b == c and a in TRIPLE:
        return TRIPLE[a]
    heralds = reels.count("herald")
    if heralds == 2:
        return TWO_HERALDS
    if heralds == 1:
        return ONE_HERALD
    if a == b and a != "blank":
        return FIRST_PAIR
    return 0


def _reel(roll: int) -> str:
    for symbol, weight in REEL:
        if roll < weight:
            return symbol
        roll -= weight
    raise CasinoRuleError("reel roll out of range")


def spin_slots(stake: int, randbelow: Callable[[int], int]) -> Outcome:
    stake = check_stake(stake)
    reels = tuple(_reel(randbelow(REEL_TOTAL)) for _ in range(3))
    mult = slots_mult(reels)
    return Outcome("slots", mult, payout(stake, mult), {"reels": list(reels)})


# ── «Колесо Предвестника»: twenty equal sectors ───────────────────────────────────────────────────────────
WHEEL: Final = (0, 150, 0, 100, 0, 200, 0, 50, 0, 300, 0, 100, 0, 150, 0, 500, 100, 50, 0, 200)


def spin_wheel(stake: int, randbelow: Callable[[int], int]) -> Outcome:
    stake = check_stake(stake)
    sector = randbelow(len(WHEEL))
    mult = WHEEL[sector]
    return Outcome("wheel", mult, payout(stake, mult), {"sector": sector})


# ── «Кости судьбы»: the player picks the chance ───────────────────────────────────────────────────────────
DICE_CHANCES: Final = (10, 25, 50, 75, 90)
DICE_EDGE_BPS: Final = 400   # 4%: multiplier = 96 / chance


def dice_mult(chance: int) -> int:
    return (10_000 - DICE_EDGE_BPS) // chance


def roll_dice(stake: int, chance: object, randbelow: Callable[[int], int]) -> Outcome:
    stake = check_stake(stake)
    if isinstance(chance, bool) or chance not in DICE_CHANCES:
        raise CasinoRuleError("Выберите шанс из списка.")
    roll = randbelow(100) + 1
    mult = dice_mult(chance) if roll <= chance else 0
    return Outcome("dice", mult, payout(stake, mult), {"roll": roll, "chance": chance})


GAMES: Final = ("slots", "wheel", "dice")


def play(game: str, stake: int, params: dict, randbelow: Callable[[int], int]) -> Outcome:
    if game == "slots":
        return spin_slots(stake, randbelow)
    if game == "wheel":
        return spin_wheel(stake, randbelow)
    if game == "dice":
        return roll_dice(stake, (params or {}).get("chance"), randbelow)
    raise CasinoRuleError("Неизвестная игра.")


# ── Exact returns (published in the help sheet) ───────────────────────────────────────────────────────────
def slots_rtp() -> Fraction:
    weights = dict(REEL)
    return sum((Fraction(weights[a] * weights[b] * weights[c], REEL_TOTAL ** 3) * slots_mult((a, b, c))
                for a, b, c in product(weights, repeat=3)), Fraction(0)) / 100


def slots_hit_rate() -> Fraction:
    weights = dict(REEL)
    return sum((Fraction(weights[a] * weights[b] * weights[c], REEL_TOTAL ** 3)
                for a, b, c in product(weights, repeat=3) if slots_mult((a, b, c))), Fraction(0))


def wheel_rtp() -> Fraction:
    return Fraction(sum(WHEEL), len(WHEEL) * 100)


def dice_rtp(chance: int) -> Fraction:
    return Fraction(chance * dice_mult(chance), 100 * 100)


def public_rules() -> dict:
    """What the help sheet shows: every multiplier and the exact return of each game."""
    pct = lambda value: round(float(value) * 100, 1)  # noqa: E731
    return {
        "policy_version": POLICY_VERSION, "daily_gift": DAILY_GIFT, "chips_per_mora": CHIPS_PER_MORA,
        "mora_packs": list(MORA_PACKS), "daily_buy_cap": DAILY_BUY_CAP_CHIPS, "stakes": list(STAKES),
        "slots": {"symbols": SYMBOLS, "triple": TRIPLE, "two_heralds": TWO_HERALDS, "one_herald": ONE_HERALD,
                  "first_pair": FIRST_PAIR, "rtp": pct(slots_rtp()), "hit_rate": pct(slots_hit_rate())},
        "wheel": {"sectors": list(WHEEL), "rtp": pct(wheel_rtp())},
        "dice": {"chances": [{"chance": c, "mult": dice_mult(c), "rtp": pct(dice_rtp(c))} for c in DICE_CHANCES]},
    }
