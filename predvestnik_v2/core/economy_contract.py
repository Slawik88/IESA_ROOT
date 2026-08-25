"""Canonical vocabulary and validation rules for the game economy.

This module is deliberately dependency-free.  Adapters and repositories use the
same currency definitions so a balance column, a UI label and a ledger entry can
never silently disagree about which currency is being changed.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import re
from types import MappingProxyType
from typing import Mapping


LEDGER_QUANTUM = Decimal("0.000001")
_REASON_CODE_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")


class EconomyContractError(ValueError):
    """Base class for rejected economy mutations."""


class InvalidEconomicMutation(EconomyContractError):
    """A mutation contains an unknown currency, invalid number or bad metadata."""


class InsufficientBalance(EconomyContractError):
    """A mutation would make at least one protected balance negative."""


class IdempotencyConflict(EconomyContractError):
    """An idempotency key was reused for a different operation."""


@dataclass(frozen=True, slots=True)
class CurrencySpec:
    code: str
    label: str
    icon: str
    balance_column: str
    wallet_delta_column: str
    wallet_after_column: str
    role: str
    display_decimals: int


_CURRENCY_SPECS = {
    "mora": CurrencySpec(
        code="mora",
        label="Мора",
        icon="🪙",
        balance_column="user_balance_mora",
        wallet_delta_column="delta_mora",
        wallet_after_column="balance_mora_after",
        role="soft_progression",
        display_decimals=0,
    ),
    "diamonds": CurrencySpec(
        code="diamonds",
        label="Алмазы",
        icon="💎",
        balance_column="user_balance_diamonds",
        wallet_delta_column="delta_diamonds",
        wallet_after_column="balance_diamonds_after",
        role="rare_progression",
        display_decimals=2,
    ),
    "dark_mora": CurrencySpec(
        code="dark_mora",
        label="Тёмная Мора",
        icon="🌑",
        balance_column="user_balance_dark_mora",
        wallet_delta_column="delta_dark_mora",
        wallet_after_column="balance_dark_mora_after",
        role="mode_specific",
        display_decimals=0,
    ),
    "zarniki": CurrencySpec(
        code="zarniki",
        label="Зарники",
        icon="✨",
        balance_column="user_balance_zarniki",
        wallet_delta_column="delta_zarniki",
        wallet_after_column="balance_zarniki_after",
        role="premium_cosmetics",
        display_decimals=0,
    ),
}

CURRENCY_SPECS: Mapping[str, CurrencySpec] = MappingProxyType(_CURRENCY_SPECS)
CURRENCY_CODES = tuple(_CURRENCY_SPECS)


def as_ledger_amount(value: int | float | Decimal) -> Decimal:
    """Return a finite, deterministic six-decimal amount for storage/comparison."""
    if isinstance(value, bool):
        raise InvalidEconomicMutation("Boolean is not a currency amount.")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidEconomicMutation("Currency amount must be numeric.") from exc
    if not amount.is_finite():
        raise InvalidEconomicMutation("Currency amount must be finite.")
    return amount.quantize(LEDGER_QUANTUM, rounding=ROUND_HALF_EVEN)


def normalize_deltas(
    deltas: Mapping[str, int | float | Decimal],
) -> dict[str, Decimal]:
    """Validate currency keys and remove zero deltas in canonical currency order."""
    unknown = sorted((str(code) for code in set(deltas) - set(CURRENCY_CODES)))
    if unknown:
        raise InvalidEconomicMutation(f"Unknown currencies: {', '.join(unknown)}")
    normalized: dict[str, Decimal] = {}
    for code in CURRENCY_CODES:
        amount = as_ledger_amount(deltas.get(code, 0))
        if amount:
            normalized[code] = amount
    return normalized


def validate_reason_code(reason_code: str) -> str:
    code = str(reason_code or "").strip().lower()
    if not _REASON_CODE_RE.fullmatch(code):
        raise InvalidEconomicMutation(
            "reason_code must match [a-z][a-z0-9_.:-]{0,63}."
        )
    return code


def validate_idempotency_key(key: str) -> str:
    normalized = str(key or "").strip()
    if not normalized or len(normalized) > 180:
        raise InvalidEconomicMutation("idempotency_key must contain 1..180 characters.")
    if any(ord(char) < 32 for char in normalized):
        raise InvalidEconomicMutation("idempotency_key contains control characters.")
    return normalized
