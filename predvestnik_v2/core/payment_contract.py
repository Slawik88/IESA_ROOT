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
_PAYLOAD_V1_RE = re.compile(
    r"^zarniki:v1:(?P<kind>[pc]):(?P<stars>[1-9]\d{0,5}):(?P<zarniki>[1-9]\d{0,6})$"
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
    return ZarnikiQuote(stars=stars, zarniki=package[1] + package[2], kind="p", version="v1")


def custom_quote(stars: int) -> ZarnikiQuote | None:
    if not is_stars_amount(stars):
        return None
    return ZarnikiQuote(
        stars=stars,
        zarniki=stars * ZARNIKI_PER_STAR,
        kind="c",
        version="v1",
    )


def _v1_package_quote(stars: int) -> ZarnikiQuote | None:
    if not is_stars_amount(stars):
        return None
    zarniki = _V1_PACKAGE_ZARNIKI_BY_STARS.get(stars)
    if zarniki is None:
        return None
    return ZarnikiQuote(stars=stars, zarniki=zarniki, kind="p", version="v1")


def _v1_custom_quote(stars: int) -> ZarnikiQuote | None:
    if not is_stars_amount(stars):
        return None
    return ZarnikiQuote(
        stars=stars,
        zarniki=stars * _V1_ZARNIKI_PER_STAR,
        kind="c",
        version="v1",
    )


def is_issuable_v1_quote(quote: ZarnikiQuote) -> bool:
    if quote.version != "v1" or quote.kind not in {"p", "c"}:
        return False
    expected = _v1_package_quote(quote.stars) if quote.kind == "p" else _v1_custom_quote(quote.stars)
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

    v1 = _PAYLOAD_V1_RE.fullmatch(payload)
    if v1:
        stars = int(v1["stars"])
        zarniki = int(v1["zarniki"])
        if stars != total_amount:
            return None
        expected = _v1_package_quote(stars) if v1["kind"] == "p" else _v1_custom_quote(stars)
        return expected if expected and expected.zarniki == zarniki else None

    legacy = _LEGACY_PAYLOAD_RE.fullmatch(payload)
    if not legacy:
        return None
    zarniki = int(legacy["zarniki"])
    package = _v1_package_quote(total_amount)
    custom = _v1_custom_quote(total_amount)
    if package and zarniki == package.zarniki:
        return ZarnikiQuote(total_amount, zarniki, "p", "legacy")
    if custom and zarniki == custom.zarniki:
        return ZarnikiQuote(total_amount, zarniki, "c", "legacy")
    return None
