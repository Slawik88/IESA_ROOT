"""Pure rules for the owner-approved player-created coin exchange."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Final


FEATURE_FLAG_KEY: Final = "economy_player_exchange_v1"
RULES_VERSION: Final = "player-exchange-v1-2026-09-26"
TOKEN_SCALE: Final = 1_000
GENESIS_TOKENS: Final = 1_000_000
GENESIS_UNITS: Final = GENESIS_TOKENS * TOKEN_SCALE
CREATION_FEE_ZARNIKI: Final = 2_000
MIN_INITIAL_MORA: Final = 10_000
MAX_INITIAL_MORA: Final = 1_000_000
AUCTION_HOURS: Final = 24
PRICE_SCALE: Final = 1_000_000
MAX_PRICE_MICROMORA: Final = 1_000_000 * PRICE_SCALE
MAKER_FEE_BPS: Final = 10
TAKER_FEE_BPS: Final = 25
FEE_BPS_SCALE: Final = 10_000
MIN_FEE_NOTIONAL_MORA: Final = Decimal("10")
MIN_AUCTION_SOLD_UNITS: Final = 30_000 * TOKEN_SCALE
MIN_AUCTION_RAISED_MORA: Final = 10_000
TREASURY_LADDER_OFFSETS_PCT: Final = (2, 4, 6, 8, 10)
EMISSION_WAIT_HOURS: Final = 24
EMISSION_COOLDOWN_DAYS: Final = 7
EMISSION_MAX_BPS: Final = 1_000
EMISSION_CANCEL_LOCK_MINUTES: Final = 60
OWNER_VESTING_CLIFF_DAYS: Final = 30
OWNER_VESTING_LINEAR_DAYS: Final = 180
LIQUIDITY_WITHDRAWAL_LOCK_DAYS: Final = 30
LIQUIDITY_WITHDRAWAL_WAIT_HOURS: Final = 24
LIQUIDITY_WITHDRAWAL_COOLDOWN_DAYS: Final = 7
LIQUIDITY_WITHDRAWAL_MAX_BPS: Final = 1_000

GENESIS_ALLOCATION: Final = {
    "auction": 30,
    "owner_locked": 20,
    "treasury": 20,
    "market_reserve": 30,
}

_TICKER_RE = re.compile(r"^[A-Z]{3,6}$")


class PlayerExchangePolicyError(ValueError):
    pass


@dataclass(frozen=True)
class CoinDraft:
    name: str
    ticker: str
    initial_mora: int


@dataclass(frozen=True)
class AuctionBid:
    bid_id: str
    max_price_micromora: int
    escrow_mora: int


@dataclass(frozen=True)
class AuctionClearing:
    clearing_price_micromora: int
    allocations: dict[str, int]
    costs_mora: dict[str, Decimal]
    sold_units: int
    raised_mora: Decimal


def normalize_name(value: str) -> str:
    name = " ".join(unicodedata.normalize("NFKC", str(value)).strip().split())
    if not 3 <= len(name) <= 24:
        raise PlayerExchangePolicyError("Название должно содержать от 3 до 24 символов.")
    if any(unicodedata.category(ch).startswith("C") for ch in name):
        raise PlayerExchangePolicyError("Название содержит недопустимые символы.")
    return name


def normalize_ticker(value: str) -> str:
    ticker = unicodedata.normalize("NFKC", str(value)).strip().upper()
    if not _TICKER_RE.fullmatch(ticker):
        raise PlayerExchangePolicyError("Тикер — от 3 до 6 латинских букв.")
    return ticker


def validate_coin_draft(*, name: str, ticker: str, initial_mora: int) -> CoinDraft:
    try:
        mora = int(initial_mora)
    except (TypeError, ValueError) as exc:
        raise PlayerExchangePolicyError("Стартовая ликвидность должна быть целым числом Моры.") from exc
    if mora < MIN_INITIAL_MORA or mora > MAX_INITIAL_MORA:
        raise PlayerExchangePolicyError(
            f"Стартовая ликвидность — от {MIN_INITIAL_MORA:,} до {MAX_INITIAL_MORA:,} Моры."
        )
    return CoinDraft(normalize_name(name), normalize_ticker(ticker), mora)


def allocation_units() -> dict[str, int]:
    result = {key: GENESIS_UNITS * percent // 100 for key, percent in GENESIS_ALLOCATION.items()}
    if sum(result.values()) != GENESIS_UNITS:
        raise AssertionError("Genesis allocation must conserve the entire supply.")
    return result


def parse_token_amount(value: str | int | Decimal) -> int:
    try:
        amount = Decimal(str(value))
    except Exception as exc:
        raise PlayerExchangePolicyError("Некорректное количество монет.") from exc
    units = int((amount * TOKEN_SCALE).to_integral_value(rounding=ROUND_DOWN))
    if amount <= 0 or Decimal(units) / TOKEN_SCALE != amount:
        raise PlayerExchangePolicyError("Количество должно быть положительным, точность — до 3 знаков.")
    return units


def validate_emission(*, amount: str | int | Decimal, circulating_units: int, reason: str) -> tuple[int, str]:
    units = parse_token_amount(amount)
    maximum = int(circulating_units) * EMISSION_MAX_BPS // FEE_BPS_SCALE
    if maximum <= 0 or units > maximum:
        raise PlayerExchangePolicyError("За одну операцию можно выпустить не более 10% текущего обращения.")
    clean_reason = " ".join(str(reason).strip().split())
    if not 10 <= len(clean_reason) <= 160:
        raise PlayerExchangePolicyError("Причина эмиссии должна содержать от 10 до 160 символов.")
    return units, clean_reason


def clear_uniform_auction(bids: list[AuctionBid], supply_units: int) -> AuctionClearing:
    """Deterministic uniform-price clearing with stable pro-rata remainders."""
    valid = [b for b in bids if b.max_price_micromora > 0 and b.escrow_mora > 0]
    if not valid or supply_units <= 0:
        return AuctionClearing(0, {}, {}, 0, Decimal("0"))
    prices = sorted({b.max_price_micromora for b in valid}, reverse=True)

    def demand(bid: AuctionBid, price: int) -> int:
        return bid.escrow_mora * PRICE_SCALE * TOKEN_SCALE // price

    clearing = prices[-1]
    for price in prices:
        eligible = [b for b in valid if b.max_price_micromora >= price]
        if sum(demand(b, price) for b in eligible) >= supply_units:
            clearing = price
            break

    higher = sorted((b for b in valid if b.max_price_micromora > clearing), key=lambda b: b.bid_id)
    marginal = sorted((b for b in valid if b.max_price_micromora == clearing), key=lambda b: b.bid_id)
    allocations: dict[str, int] = {}
    remaining = supply_units
    for bid in higher:
        fill = min(demand(bid, clearing), remaining)
        allocations[bid.bid_id] = fill
        remaining -= fill
    marginal_demands = {b.bid_id: demand(b, clearing) for b in marginal}
    marginal_total = sum(marginal_demands.values())
    if remaining > 0 and marginal_total:
        distributable = min(remaining, marginal_total)
        for bid in marginal:
            allocations[bid.bid_id] = distributable * marginal_demands[bid.bid_id] // marginal_total
        leftover = distributable - sum(allocations.get(b.bid_id, 0) for b in marginal)
        for bid in marginal:
            if leftover <= 0:
                break
            if allocations[bid.bid_id] < marginal_demands[bid.bid_id]:
                allocations[bid.bid_id] += 1
                leftover -= 1
    allocations = {key: value for key, value in allocations.items() if value > 0}
    costs = {
        key: (Decimal(units) * Decimal(clearing) / Decimal(TOKEN_SCALE * PRICE_SCALE)).quantize(Decimal("0.000001"))
        for key, units in allocations.items()
    }
    sold = sum(allocations.values())
    raised = sum(costs.values(), Decimal("0"))
    return AuctionClearing(clearing, allocations, costs, sold, raised)


def trade_notional(units: int, price_micromora: int) -> Decimal:
    if units <= 0 or price_micromora <= 0:
        raise PlayerExchangePolicyError("Количество и цена сделки должны быть положительными.")
    return (Decimal(units) * Decimal(price_micromora) / Decimal(TOKEN_SCALE * PRICE_SCALE)).quantize(
        Decimal("0.000001")
    )


def trade_fee(notional: Decimal, *, maker: bool) -> Decimal:
    if notional < MIN_FEE_NOTIONAL_MORA:
        return Decimal("0")
    bps = MAKER_FEE_BPS if maker else TAKER_FEE_BPS
    proportional = (notional * Decimal(bps) / Decimal(FEE_BPS_SCALE)).quantize(Decimal("0.000001"))
    return max(Decimal("1"), proportional)


def buy_reserve(units: int, limit_price_micromora: int) -> Decimal:
    notional = trade_notional(units, limit_price_micromora)
    # Minimum-per-fill fees can reach 10% if liquidity arrives in 10-Mora lots.
    # Reserve that deterministic ceiling; unused Mora is returned on close.
    fee_ceiling = Decimal("0") if notional < MIN_FEE_NOTIONAL_MORA else notional / Decimal("10")
    return (notional + max(fee_ceiling, trade_fee(notional, maker=False))).quantize(Decimal("0.000001"))


def protected_limit_price(*, side: str, quote_micromora: int, slippage_percent: int) -> int:
    if side not in {"buy", "sell"} or slippage_percent not in {1, 3, 5} or quote_micromora <= 0:
        raise PlayerExchangePolicyError("Некорректные параметры защищённой заявки.")
    if side == "buy":
        price = quote_micromora * (100 + slippage_percent) // 100
    else:
        price = (quote_micromora * (100 - slippage_percent) + 99) // 100
    if not 1 <= price <= MAX_PRICE_MICROMORA:
        raise PlayerExchangePolicyError("Защитная цена выходит за пределы рынка.")
    return price


def treasury_ladder_prices(clearing_price_micromora: int) -> list[tuple[str, int]]:
    if clearing_price_micromora <= 0:
        raise PlayerExchangePolicyError("Цена запуска должна быть положительной.")
    rows = []
    for offset in TREASURY_LADDER_OFFSETS_PCT:
        rows.append(("buy", max(1, clearing_price_micromora * (100 - offset) // 100)))
        rows.append(("sell", min(MAX_PRICE_MICROMORA, (clearing_price_micromora * (100 + offset) + 99) // 100)))
    return rows


def depth_band_bounds(reference_price_micromora: int) -> tuple[int, int]:
    if reference_price_micromora <= 0:
        raise PlayerExchangePolicyError("Опорная цена должна быть положительной.")
    return (
        (reference_price_micromora * 95 + 99) // 100,
        reference_price_micromora * 105 // 100,
    )
