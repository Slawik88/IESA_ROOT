"""Pure Telegram Stars invoice contract shared by Mini App and bot adapters.

Do not derive validation for an already issued invoice from a future live menu.
When tariffs change, introduce and support a new frozen payload version instead.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from core.constants import STARS_PACKAGES, ZARNIKI_PER_STAR


MAX_STARS = 100_000
STARS_CURRENCY = "XTR"
_PAYLOAD_RE = re.compile(
    r"^zarniki:(?P<version>v[12]):(?P<kind>[pc]):(?P<stars>[1-9]\d{0,5}):(?P<zarniki>[1-9]\d{0,7})$"
)
# Compatibility only for invoices issued before the versioned contract.  Never
# use this shape for a new invoice.
_LEGACY_PAYLOAD_RE = re.compile(r"^zarniki:(?P<zarniki>[1-9]\d{0,6})$")

# Immutable arithmetic for invoices already sent as v1.  A live tariff change
# needs v2; it must never silently change the value of a Telegram invoice.
_V1_PACKAGE_ZARNIKI_BY_STARS = {
    20: 215,
    50: 550,
    100: 1100,
    200: 2200,
    300: 3300,
    400: 4400,
}
_V1_ZARNIKI_PER_STAR = 10

# v2 (2026-10-22): 1⭐ = 12✨, package bonuses keep their share. Frozen the same way as v1.
_V2_PACKAGE_ZARNIKI_BY_STARS = {
    20: 258,
    50: 660,
    100: 1320,
    200: 2640,
    300: 3960,
    400: 5280,
}
_V2_ZARNIKI_PER_STAR = 12

_FROZEN = {
    "v1": (_V1_PACKAGE_ZARNIKI_BY_STARS, _V1_ZARNIKI_PER_STAR),
    "v2": (_V2_PACKAGE_ZARNIKI_BY_STARS, _V2_ZARNIKI_PER_STAR),
}
# Version of every NEW invoice; older versions stay payable at their own frozen price.
CURRENT_VERSION = "v2"


@dataclass(frozen=True, slots=True)
class ZarnikiQuote:
    """Exact goods and Stars price represented by one invoice."""

    stars: int
    zarniki: int
    kind: str  # ``p`` = named package; ``c`` = player-entered custom amount
    version: str


def is_stars_amount(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= MAX_STARS


def package_quote(stars: int) -> ZarnikiQuote | None:
    if not is_stars_amount(stars):
        return None
    package = next((package for package in STARS_PACKAGES if package[0] == stars), None)
    if not package:
        return None
    return ZarnikiQuote(stars=stars, zarniki=package[1] + package[2], kind="p", version=CURRENT_VERSION)


def custom_quote(stars: int) -> ZarnikiQuote | None:
    if not is_stars_amount(stars):
        return None
    return ZarnikiQuote(
        stars=stars,
        zarniki=stars * ZARNIKI_PER_STAR,
        kind="c",
        version=CURRENT_VERSION,
    )


def _frozen_quote(version: str, kind: str, stars: int) -> ZarnikiQuote | None:
    """The quote an invoice of ``version`` represents, from that version's frozen table."""
    if version not in _FROZEN or not is_stars_amount(stars):
        return None
    packages, per_star = _FROZEN[version]
    if kind == "p":
        zarniki = packages.get(stars)
        return ZarnikiQuote(stars=stars, zarniki=zarniki, kind="p", version=version) if zarniki else None
    if kind == "c":
        return ZarnikiQuote(stars=stars, zarniki=stars * per_star, kind="c", version=version)
    return None


def is_issuable_quote(quote: ZarnikiQuote) -> bool:
    """A new invoice must be the current version and match its frozen table exactly."""
    if quote.version != CURRENT_VERSION:
        return False
    expected = _frozen_quote(quote.version, quote.kind, quote.stars)
    return bool(expected and expected.zarniki == quote.zarniki)


def invoice_payload(quote: ZarnikiQuote) -> str:
    return f"zarniki:{quote.version}:{quote.kind}:{quote.stars}:{quote.zarniki}"


def quote_from_paid_invoice(
    payload: object,
    currency: object,
    total_amount: object,
) -> ZarnikiQuote | None:
    """Validate the only quote represented by a Telegram payment callback."""
    if currency != STARS_CURRENCY or not is_stars_amount(total_amount) or not isinstance(payload, str):
        return None

    versioned = _PAYLOAD_RE.fullmatch(payload)
    if versioned:
        stars = int(versioned["stars"])
        zarniki = int(versioned["zarniki"])
        if stars != total_amount:
            return None
        expected = _frozen_quote(versioned["version"], versioned["kind"], stars)
        return expected if expected and expected.zarniki == zarniki else None

    legacy = _LEGACY_PAYLOAD_RE.fullmatch(payload)
    if not legacy:
        return None
    zarniki = int(legacy["zarniki"])
    package = _frozen_quote("v1", "p", total_amount)
    custom = _frozen_quote("v1", "c", total_amount)
    if package and zarniki == package.zarniki:
        return ZarnikiQuote(total_amount, zarniki, "p", "legacy")
    if custom and zarniki == custom.zarniki:
        return ZarnikiQuote(total_amount, zarniki, "c", "legacy")
    return None
