"""Owner-approved, deliberately rate-limited premium exchange policy.

This is not an invoice policy: Stars can only purchase Zarniki through the
separate Telegram payment contract.  This module quotes already-held Zarniki
and never reads balances, calls Telegram or writes a database.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final


POLICY_VERSION: Final = "zarniki-exchange-v1-2026-09-05"
DAILY_ZARNIKI_CAP: Final = 50
EXCHANGE_ROUTES: Final = {
    "mora": Decimal("10"),
    "diamonds": Decimal("0.01"),
}


class ZarnikiExchangePolicyError(ValueError):
    """The request does not fit the approved conversion policy."""


@dataclass(frozen=True, slots=True)
class ExchangeQuote:
    target: str
    zarniki_spent: int
    amount_received: Decimal
    daily_cap: int = DAILY_ZARNIKI_CAP
    policy_version: str = POLICY_VERSION


def quote(*, zarniki: int, target: str) -> ExchangeQuote:
    if isinstance(zarniki, bool) or not isinstance(zarniki, int) or zarniki < 1:
        raise ZarnikiExchangePolicyError("Сумма обмена — целое число Зарников от 1.")
    normalized = str(target or "").strip().lower()
    rate = EXCHANGE_ROUTES.get(normalized)
    if rate is None:
        raise ZarnikiExchangePolicyError("Доступен обмен только в Мору или Алмазы.")
    if zarniki > DAILY_ZARNIKI_CAP:
        raise ZarnikiExchangePolicyError(
            f"За один UTC-день можно обменять не больше {DAILY_ZARNIKI_CAP}✨."
        )
    return ExchangeQuote(
        target=normalized,
        zarniki_spent=zarniki,
        amount_received=(Decimal(zarniki) * rate).quantize(Decimal("0.000001")),
    )


def simulate_stars_package(*, zarniki: int) -> dict[str, int]:
    """Show the economic guardrail without enabling a payment or exchange."""
    if isinstance(zarniki, bool) or not isinstance(zarniki, int) or zarniki < 1:
        raise ZarnikiExchangePolicyError("Количество Зарников должно быть положительным целым.")
    days = (zarniki + DAILY_ZARNIKI_CAP - 1) // DAILY_ZARNIKI_CAP
    return {
        "zarniki": zarniki,
        "minimum_utc_days": days,
        "mora_total": int(Decimal(zarniki) * EXCHANGE_ROUTES["mora"]),
        "diamonds_total_hundredths": int(Decimal(zarniki) * EXCHANGE_ROUTES["diamonds"] * 100),
    }
