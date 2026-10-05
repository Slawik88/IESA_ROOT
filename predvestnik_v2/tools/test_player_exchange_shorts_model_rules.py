"""Pure boundary proof for the pre-implementation Shorts safety model."""
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.player_exchange_shorts_v1 import (  # noqa: E402
    FULL_LIQUIDATION_BPS, INITIAL_MARGIN_BPS, PARTIAL_LIQUIDATION_BPS,
    ShortsPolicyError, borrow_apr_bps, conservative_mark_price_micromora,
    equity_mora, is_short_eligible, liquidation_penalty_split, liquidation_state,
    margin_ratio_bps, minute_interest_mora, minimum_partial_liquidation_units,
    pool_utilisation_bps, short_limits_units, validate_short_open,
)


def rejects(fn, **kwargs):
    try:
        fn(**kwargs)
    except ShortsPolicyError:
        return
    raise AssertionError("Expected ShortsPolicyError")


assert is_short_eligible(
    trading_days=7, verified_trades=100, unique_traders=20,
    weekly_volume_mora=Decimal("50000"), depth_5pct_mora=Decimal("10000"),
)
assert not is_short_eligible(
    trading_days=6, verified_trades=100, unique_traders=20,
    weekly_volume_mora=Decimal("50000"), depth_5pct_mora=Decimal("10000"),
)
per_player, aggregate = short_limits_units(
    circulating_units=1_000_000, lending_pool_units=400_000, already_borrowed_units=0,
)
assert per_player == 5_000 and aggregate == 100_000
validate_short_open(
    requested_units=5_000, circulating_units=1_000_000, lending_pool_units=400_000,
    already_borrowed_units=0, actor_is_owner_or_linked=False,
)
rejects(validate_short_open, requested_units=1, circulating_units=1_000_000,
        lending_pool_units=400_000, already_borrowed_units=0, actor_is_owner_or_linked=True)
assert pool_utilisation_bps(lending_pool_units=400_000, borrowed_units=100_000) == 5_000
assert borrow_apr_bps(utilisation_bps=0) == 1_000
assert borrow_apr_bps(utilisation_bps=7_000) == 3_000
assert borrow_apr_bps(utilisation_bps=9_000) == 15_000
assert borrow_apr_bps(utilisation_bps=10_000) == 15_000
assert conservative_mark_price_micromora(
    vwap_5m_micromora=1_000_000, vwap_5m_volume_mora=Decimal("100"),
    executable_buyback_micromora=1_100_000,
) == 1_100_000
assert conservative_mark_price_micromora(
    vwap_5m_micromora=1_000_000, vwap_5m_volume_mora=Decimal("99.999999"),
    executable_buyback_micromora=1_100_000,
) is None
assert minute_interest_mora(debt_units=100_000, mark_price_micromora=1_000_000, apr_bps=15_000) > 0
assert equity_mora(
    posted_collateral_mora=Decimal("200"), locked_sale_proceeds_mora=Decimal("100"),
    debt_units=100_000, mark_price_micromora=1_000_000, accrued_interest_mora=Decimal("0"),
) == Decimal("200.000000")
ratio = margin_ratio_bps(
    posted_collateral_mora=Decimal("200"), locked_sale_proceeds_mora=Decimal("100"),
    debt_units=100_000, mark_price_micromora=1_000_000, accrued_interest_mora=Decimal("0"),
)
assert ratio == INITIAL_MARGIN_BPS
assert liquidation_state(margin_bps=PARTIAL_LIQUIDATION_BPS, market_halted=False, mark_available=True) == "healthy"
assert liquidation_state(margin_bps=PARTIAL_LIQUIDATION_BPS - 1, market_halted=False, mark_available=True) == "partial"
assert liquidation_state(margin_bps=FULL_LIQUIDATION_BPS, market_halted=False, mark_available=True) == "partial"
assert liquidation_state(margin_bps=FULL_LIQUIDATION_BPS - 1, market_halted=False, mark_available=True) == "full"
assert liquidation_state(margin_bps=0, market_halted=True, mark_available=True) == "frozen"
close_units = minimum_partial_liquidation_units(
    debt_units=100_000, mark_price_micromora=1_500_000,
    current_equity_mora=Decimal("120"), posted_collateral_mora=Decimal("200"),
)
assert 0 < close_units <= 100_000
executor, insurance = liquidation_penalty_split(
    posted_collateral_mora=Decimal("200"), closed_units=100_000, original_debt_units=100_000,
)
assert executor == Decimal("10.000000") and insurance == Decimal("6.000000")
print("PLAYER_EXCHANGE_SHORTS_MODEL_RULES_OK")
