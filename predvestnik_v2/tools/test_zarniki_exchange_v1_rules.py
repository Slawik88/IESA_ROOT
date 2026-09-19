"""Pure simulation and boundary proof for the approved premium exchange."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.zarniki_exchange_v1 import (  # noqa: E402
    DAILY_ZARNIKI_CAP, ZarnikiExchangePolicyError, quote, simulate_stars_package,
)


def must_fail(call):
    try:
        call()
    except ZarnikiExchangePolicyError:
        return
    raise AssertionError("invalid exchange request was accepted")


def main() -> None:
    mora = quote(zarniki=50, target="mora")
    diamonds = quote(zarniki=50, target="diamonds")
    assert mora.amount_received == 500 and diamonds.amount_received == 0.5
    assert mora.daily_cap == DAILY_ZARNIKI_CAP == 50
    # The popular 200 Stars package gives 2,200 Zarniki; it cannot turn into
    # progression immediately because its shared daily conversion takes 44 days.
    simulation = simulate_stars_package(zarniki=2200)
    assert simulation == {
        "zarniki": 2200, "minimum_utc_days": 44,
        "mora_total": 22000, "diamonds_total_hundredths": 2200,
    }
    for invalid in (0, -1, 51, True, 1.5):
        must_fail(lambda invalid=invalid: quote(zarniki=invalid, target="mora"))
    for target in ("stars", "dark_mora", "", None):
        must_fail(lambda target=target: quote(zarniki=1, target=target))
    print("OK: Zarniki v1 rates, shared cap boundaries and 200 Stars simulation")


if __name__ == "__main__":
    main()
