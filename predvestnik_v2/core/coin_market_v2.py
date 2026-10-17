"""Dependency-free candidate v2 rules. No wallet, SQL, clock or feature activation.

All cash is integer micromora, all token quantities are thousandths of a coin.
Admission reserves the *maximum* claim, never a forecast of the next price.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, replace

MORA = 1_000_000
TOKEN = 1_000
BPS = 10_000
TICK_SECONDS = 300
FEE_BPS = 50
TOTAL_UNITS = 1_000_000 * TOKEN
RULES_VERSION = "coin-market-v2-candidate-2026-10-17"


class MarketError(ValueError):
    pass


def integer(value: int, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum or value > 10**24:
        raise MarketError("Некорректное количество.")
    return value


def ceildiv(n: int, d: int) -> int:
    return (n + d - 1) // d


def fee(gross: int) -> int:
    return ceildiv(integer(gross) * FEE_BPS, BPS)


def split_fee(amount: int) -> tuple[int, int, int]:
    integer(amount)
    reserve = amount * 50 // 100
    insurance = amount * 30 // 100
    return reserve, insurance, amount - reserve - insurance


@dataclass(frozen=True)
class Coin:
    key: str
    base: int
    supply: int = TOTAL_UNITS
    loan_pool: int = TOTAL_UNITS // 10

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not 1 <= len(self.key) <= 64:
            raise MarketError("Некорректная монета.")
        integer(self.base, minimum=100)
        integer(self.supply, minimum=1)
        integer(self.loan_pool)
        if self.loan_pool > self.supply:
            raise MarketError("Резерв займа превышает выпуск.")

    @property
    def floor(self) -> int:
        return self.base // 2

    @property
    def ceiling(self) -> int:
        return ceildiv(self.base * 3, 2)

    def price(self, value: int) -> int:
        integer(value, minimum=1)
        if not self.floor <= value <= self.ceiling:
            raise MarketError("Котировка вне правил монеты.")
        return value


@dataclass(frozen=True)
class Book:
    reserve: int
    held: int = 0
    borrowed: int = 0
    insurance: int = 0  # available cash; position coverage is accounted separately

    def validate(self, coin: Coin) -> None:
        for value in (self.reserve, self.held, self.borrowed, self.insurance):
            integer(value)
        if self.held > coin.supply - coin.loan_pool or self.borrowed > coin.loan_pool:
            raise MarketError("Недостаточно свободных монет.")
        if self.reserve < ceildiv(self.held * coin.ceiling, TOKEN):
            raise MarketError("Недостаточно покрытия новых позиций.")


@dataclass(frozen=True)
class Flow:
    """Conservation witness: wallet + reserve + free/locked insurance + escrow + burn."""
    wallet: int
    reserve: int
    insurance: int
    escrow: int
    burned: int
    treasury: int = 0

    def __post_init__(self) -> None:
        if self.wallet + self.reserve + self.insurance + self.escrow + self.burned + self.treasury != 0:
            raise MarketError("Нарушено сохранение средств.")


@dataclass(frozen=True)
class Spot:
    book: Book
    units: int
    gross: int
    commission: int
    flow: Flow


def buy(coin: Coin, book: Book, price: int, budget: int) -> Spot:
    book.validate(coin)
    coin.price(price)
    integer(budget, minimum=10 * MORA)
    units = budget * BPS * TOKEN // (price * (BPS + FEE_BPS))
    # Two ceilings (notional and fee) can add two micromora above the budget.
    while units > 0:
        gross = ceildiv(units * price, TOKEN)
        commission = fee(gross)
        if gross + commission <= budget:
            break
        units -= 1
    if units <= 0:
        raise MarketError("Суммы недостаточно для покупки.")
    fr, fi, fb = split_fee(commission)
    result = replace(book, reserve=book.reserve + gross + fr,
                     insurance=book.insurance + fi, held=book.held + units)
    result.validate(coin)
    return Spot(result, units, gross, commission,
                Flow(-gross - commission, gross + fr, fi, 0, fb))


def sell(coin: Coin, book: Book, price: int, units: int) -> Spot:
    book.validate(coin)
    coin.price(price)
    integer(units, minimum=1)
    if units > book.held:
        raise MarketError("Недостаточно монет.")
    gross = units * price // TOKEN
    commission = fee(gross)
    # Microscopic quantities may settle to zero. The quote discloses that
    # before manual confirmation; no money is debited from the wallet.
    fr, fi, fb = split_fee(commission)
    result = replace(book, reserve=book.reserve - gross + fr,
                     insurance=book.insurance + fi, held=book.held - units)
    result.validate(coin)
    return Spot(result, units, gross, commission,
                Flow(gross - commission, -gross + fr, fi, 0, fb))


@dataclass(frozen=True)
class Short:
    coin_key: str
    units: int
    collateral: int
    escrow: int
    coverage: int


@dataclass(frozen=True)
class ShortOpen:
    book: Book
    position: Short
    commission: int
    flow: Flow


@dataclass(frozen=True)
class ShortClose:
    book: Book
    payout: int
    commission: int
    penalty: int
    liquidated: bool
    flow: Flow


def open_short(coin: Coin, book: Book, price: int, collateral: int) -> ShortOpen:
    book.validate(coin)
    coin.price(price)
    integer(collateral, minimum=10 * MORA)
    # One times exposure: collateral is an upper bound, never a leverage setting.
    units = collateral * TOKEN // price
    gross = units * price // TOKEN
    commission = fee(gross)
    escrow = collateral + gross - commission
    worst = ceildiv(units * coin.ceiling, TOKEN)
    coverage = max(0, worst + fee(worst) - escrow)
    fr, fi, fb = split_fee(commission)
    result = replace(book, borrowed=book.borrowed + units,
                     reserve=book.reserve - gross + fr,
                     insurance=book.insurance + fi - coverage)
    result.validate(coin)
    position = Short(coin.key, units, collateral, escrow, coverage)
    return ShortOpen(result, position, commission,
                     Flow(-collateral, -gross + fr, fi, escrow, fb))


def close_short(coin: Coin, book: Book, price: int, position: Short) -> ShortClose:
    book.validate(coin)
    coin.price(price)
    if position.coin_key != coin.key:
        raise MarketError("Позиция принадлежит другой монете.")
    for value in (position.units, position.collateral, position.escrow):
        integer(value, minimum=1)
    integer(position.coverage)
    if position.units > book.borrowed:
        raise MarketError("Позиция уже закрыта или учёт займа повреждён.")
    worst = ceildiv(position.units * coin.ceiling, TOKEN)
    if position.coverage < max(0, worst + fee(worst) - position.escrow):
        raise MarketError("Обеспечение позиции повреждено.")
    gross = ceildiv(position.units * price, TOKEN)
    commission = fee(gross)
    equity = position.escrow - gross - commission
    liquidated = equity * 5 <= position.collateral
    penalty = min(max(0, equity), ceildiv(position.collateral * 3, 100)) if liquidated else 0
    payout = max(0, equity) - penalty
    drawn = max(0, -equity)
    fr, fi, fb = split_fee(commission)
    result = replace(book, borrowed=book.borrowed - position.units,
                     reserve=book.reserve + gross + fr,
                     insurance=book.insurance + position.coverage - drawn + fi + penalty)
    result.validate(coin)
    # Flow.insurance includes free AND position-locked insurance: releasing a lock
    # moves no cash. Only actual draw/fee/penalty changes the combined account.
    return ShortClose(result, payout, commission, penalty, liquidated,
                      Flow(payout, gross + fr, -drawn + fi + penalty, -position.escrow, fb))


@dataclass(frozen=True)
class Genesis:
    coin: Coin
    book: Book
    creator_units: int
    zarniki: int


def personal_genesis(key: str, deposited_mora: int, zarniki: int) -> Genesis:
    """deposited_mora must be ACTUALLY funded by wallet or treasury by the caller.

    Diamonds are not Mora: the adapter must atomically transfer paid Mora from
    an exchange treasury before invoking this rule. No implicit conversion here.
    """
    integer(deposited_mora, minimum=1_000 * MORA)
    integer(zarniki, minimum=1_000)
    if deposited_mora > 100_000 * MORA or zarniki > 5_000:
        raise MarketError("Вклад превышает лимит создания.")
    premium = BPS + (zarniki - 1_000) // 2  # up to +20% starting unit price
    base = deposited_mora * TOKEN * premium // (TOTAL_UNITS * BPS)
    coin = Coin(key, base)
    creator_units = coin.supply // 5
    book = Book(deposited_mora, held=creator_units)
    book.validate(coin)
    return Genesis(coin, book, creator_units, zarniki)


@dataclass(frozen=True)
class Character:
    noise: int
    drift: int
    minimum_ticks: int
    maximum_ticks: int
    jump_per_10k: int


CHARACTERS = {
    "calm": Character(16, 7, 24, 72, 5),
    "flow": Character(35, 15, 12, 48, 10),
    "storm": Character(75, 28, 6, 24, 20),
    "tide": Character(40, 18, 12, 60, 30),
}


@dataclass(frozen=True)
class PriceState:
    tick: int
    price: int
    phase: str = "calm"
    remaining: int = 0
    direction: int = 1


def _draw(secret: bytes, key: str, tick: int, stream: str, size: int) -> int:
    message = f"{RULES_VERSION}|{key}|{tick}|{stream}".encode()
    return int.from_bytes(hmac.digest(secret, message, hashlib.sha256), "big") % size


def next_price(coin: Coin, state: PriceState, *, secret: bytes,
               character: str, group: str) -> PriceState:
    """Exactly one time tick. Persist state/version before publication.

    There is deliberately no wallet/book/holdings/volume argument. Passing the
    same coin, secret and prior state produces the same next tick after restart.
    """
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise MarketError("Нужен серверный секрет минимум 32 байта.")
    if character not in CHARACTERS or not isinstance(group, str) or not group:
        raise MarketError("Неизвестный характер или группа.")
    integer(state.tick)
    integer(state.remaining)
    coin.price(state.price)
    phases = ("calm", "trend", "pullback", "active")
    if state.phase not in phases or state.direction not in (-1, 1):
        raise MarketError("Состояние цены повреждено.")
    tick = state.tick + 1
    profile = CHARACTERS[character]
    phase, remaining, direction = state.phase, state.remaining, state.direction
    draw = lambda stream, size: _draw(secret, coin.key, tick, stream, size)
    if remaining == 0:
        # Repeats/skips are allowed: this is not an ordered four-phase cycle.
        phase = phases[draw("phase", len(phases))]
        remaining = profile.minimum_ticks + draw("duration", profile.maximum_ticks - profile.minimum_ticks + 1)
        direction = 1 if draw("direction", 100) < 50 else -1
    group_bias = _draw(secret, "group:" + group, tick // 12, "bias", 21) - 10
    noise = draw("noise", profile.noise * 2 + 1) - profile.noise
    drift = profile.drift * direction if phase == "trend" else 0
    if phase == "pullback":
        drift = -profile.drift * direction
    if phase == "active":
        noise *= 2
    # Gentle mean reversion; fixed origin, never a reserve-derived target.
    pull = (coin.base - state.price) * 4 // coin.base
    bps = noise + drift + group_bias + pull
    if draw("jump-chance", BPS) < profile.jump_per_10k:
        bps += (-1 if draw("jump-sign", 2) else 1) * (100 + draw("jump-size", 151))
    bps = max(-250, min(250, bps))
    change = abs(state.price * bps) // BPS
    price = state.price + (change if bps >= 0 else -change)
    price = max(coin.floor, min(coin.ceiling, price))
    return PriceState(tick, price, phase, remaining - 1, direction)
