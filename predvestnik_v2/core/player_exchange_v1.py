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

