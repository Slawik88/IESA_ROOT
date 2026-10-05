"""Pure, fixed-point rules used by the pre-implementation Shorts safety model.

This module deliberately has no database or HTTP dependencies.  It is not an
enabled trading feature: it makes the proposed margin rules explicit enough to
stress before any player balance, loan, or liquidation writer exists.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_DOWN
from typing import Final

from core.player_exchange_v1 import PRICE_SCALE, TOKEN_SCALE, trade_notional


SHORTS_RULES_VERSION: Final = "player-exchange-shorts-model-2026-10-05"
SHORTS_FEATURE_FLAG_KEY: Final = "economy_player_exchange_shorts_v1"
MIN_TRADING_DAYS: Final = 7
MIN_VERIFIED_TRADES: Final = 100
MIN_UNIQUE_TRADERS: Final = 20
MIN_WEEKLY_VOLUME_MORA: Final = Decimal("50000")
MIN_DEPTH_5PCT_MORA: Final = Decimal("10000")
MIN_QUALIFIED_VWAP_VOLUME_MORA: Final = Decimal("100")
INITIAL_MARGIN_BPS: Final = 20_000
PARTIAL_LIQUIDATION_BPS: Final = 15_000
FULL_LIQUIDATION_BPS: Final = 12_000
PLAYER_CIRCULATION_CAP_BPS: Final = 50
PLAYER_AVAILABLE_POOL_CAP_BPS: Final = 1_000
GLOBAL_CIRCULATION_CAP_BPS: Final = 1_000
GLOBAL_POOL_CAP_BPS: Final = 5_000
LIQUIDATION_PENALTY_BPS: Final = 800
LIQUIDATOR_PENALTY_BPS: Final = 500
INSURANCE_PENALTY_BPS: Final = 300
MINUTES_PER_YEAR: Final = 365 * 24 * 60


class ShortsPolicyError(ValueError):
    pass


def is_short_eligible(*, trading_days: int, verified_trades: int, unique_traders: int,
                      weekly_volume_mora: Decimal, depth_5pct_mora: Decimal) -> bool:
    return (
        int(trading_days) >= MIN_TRADING_DAYS
        and int(verified_trades) >= MIN_VERIFIED_TRADES
        and int(unique_traders) >= MIN_UNIQUE_TRADERS
        and Decimal(str(weekly_volume_mora)) >= MIN_WEEKLY_VOLUME_MORA
        and Decimal(str(depth_5pct_mora)) >= MIN_DEPTH_5PCT_MORA
    )


def usable_lending_capacity_units(lending_pool_units: int) -> int:
    """Only half the voluntary pool can ever be loaned in v1."""
    if int(lending_pool_units) < 0:
        raise ShortsPolicyError("Lending pool cannot be negative.")
    return int(lending_pool_units) * GLOBAL_POOL_CAP_BPS // 10_000


def short_limits_units(*, circulating_units: int, lending_pool_units: int,
                       already_borrowed_units: int) -> tuple[int, int]:
    """Return per-player and aggregate remaining borrow limits in token units."""
    circulating = int(circulating_units)
    pool = int(lending_pool_units)
    borrowed = int(already_borrowed_units)
    if min(circulating, pool, borrowed) < 0:
        raise ShortsPolicyError("Short limits require non-negative balances.")
    available_pool = max(0, pool - borrowed)
    per_player = min(
        circulating * PLAYER_CIRCULATION_CAP_BPS // 10_000,
        available_pool * PLAYER_AVAILABLE_POOL_CAP_BPS // 10_000,
    )
    aggregate = min(
        circulating * GLOBAL_CIRCULATION_CAP_BPS // 10_000,
        usable_lending_capacity_units(pool),
    )
    return per_player, max(0, aggregate - borrowed)


def validate_short_open(*, requested_units: int, circulating_units: int, lending_pool_units: int,
                        already_borrowed_units: int, actor_is_owner_or_linked: bool) -> None:
    requested = int(requested_units)
    if requested <= 0:
        raise ShortsPolicyError("Short size must be positive.")
    if actor_is_owner_or_linked:
        raise ShortsPolicyError("Owner, treasury and linked accounts cannot short this coin.")
    per_player, aggregate_remaining = short_limits_units(
        circulating_units=circulating_units, lending_pool_units=lending_pool_units,
        already_borrowed_units=already_borrowed_units,
    )
    if requested > per_player or requested > aggregate_remaining:
        raise ShortsPolicyError("Short size exceeds the player or aggregate lending limit.")


def pro_rata_lender_allocations(*, requested_units: int,
                                lenders: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Split one loan deterministically by free pool share, then lender id."""
    requested = int(requested_units)
    clean = [(int(lender_id), int(available)) for lender_id, available in lenders]
    if requested <= 0 or any(lender_id <= 0 or available < 0 for lender_id, available in clean):
        raise ShortsPolicyError("Invalid lending allocation.")
    if len({lender_id for lender_id, _ in clean}) != len(clean):
        raise ShortsPolicyError("Lender allocation contains a duplicate lender.")
    total = sum(available for _, available in clean)
    if requested > total:
        raise ShortsPolicyError("Lending pool has insufficient free units.")
    base = [(lender_id, available * requested // total, available * requested % total)
            for lender_id, available in clean if available]
    allocated = sum(units for _, units, _ in base)
    remainder = requested - allocated
    winners = {
        lender_id for lender_id, _, _ in sorted(base, key=lambda row: (-row[2], row[0]))[:remainder]
    }
    result = [(lender_id, units + (1 if lender_id in winners else 0)) for lender_id, units, _ in base]
    if sum(units for _, units in result) != requested or any(units < 0 for _, units in result):
        raise ShortsPolicyError("Lending allocation invariant failed.")
    return [(lender_id, units) for lender_id, units in result if units]


def pool_utilisation_bps(*, lending_pool_units: int, borrowed_units: int) -> int:
    capacity = usable_lending_capacity_units(lending_pool_units)
    borrowed = int(borrowed_units)
    if capacity <= 0 or borrowed < 0 or borrowed > capacity:
        raise ShortsPolicyError("Borrowed units exceed the usable lending capacity.")
    return borrowed * 10_000 // capacity


def borrow_apr_bps(*, utilisation_bps: int) -> int:
    """10% at zero, 30% at 70%, 150% at 90%, capped thereafter."""
    usage = int(utilisation_bps)
    if not 0 <= usage <= 10_000:
        raise ShortsPolicyError("Utilisation must be between zero and 100%.")
    if usage <= 7_000:
        return 1_000 + 2_000 * usage // 7_000
    if usage <= 9_000:
        return 3_000 + 12_000 * (usage - 7_000) // 2_000
    return 15_000


def minute_interest_mora(*, debt_units: int, mark_price_micromora: int, apr_bps: int) -> Decimal:
    if int(debt_units) <= 0 or int(mark_price_micromora) <= 0 or int(apr_bps) < 0:
        raise ShortsPolicyError("Interest needs a positive debt and mark.")
    notional = trade_notional(int(debt_units), int(mark_price_micromora))
    return (notional * Decimal(int(apr_bps)) / Decimal(10_000 * MINUTES_PER_YEAR)).quantize(
        Decimal("0.000001"), rounding=ROUND_DOWN,
    )


def conservative_mark_price_micromora(*, vwap_5m_micromora: int | None,
                                      vwap_5m_volume_mora: Decimal,
                                      executable_buyback_micromora: int | None) -> int | None:
    """No qualified VWAP or no executable buyback means no liquidation mark."""
    vwap = int(vwap_5m_micromora or 0)
    buyback = int(executable_buyback_micromora or 0)
    if (vwap <= 0 or buyback <= 0
            or Decimal(str(vwap_5m_volume_mora)) < MIN_QUALIFIED_VWAP_VOLUME_MORA):
        return None
    return max(vwap, buyback)


def equity_mora(*, posted_collateral_mora: Decimal, locked_sale_proceeds_mora: Decimal,
                debt_units: int, mark_price_micromora: int, accrued_interest_mora: Decimal) -> Decimal:
    debt = trade_notional(int(debt_units), int(mark_price_micromora))
    return (
        Decimal(str(posted_collateral_mora)) + Decimal(str(locked_sale_proceeds_mora))
        - debt - Decimal(str(accrued_interest_mora))
    ).quantize(Decimal("0.000001"))


def margin_ratio_bps(*, posted_collateral_mora: Decimal, locked_sale_proceeds_mora: Decimal,
                     debt_units: int, mark_price_micromora: int,
                     accrued_interest_mora: Decimal) -> int:
    debt = trade_notional(int(debt_units), int(mark_price_micromora))
    if debt <= 0:
        raise ShortsPolicyError("Margin ratio requires positive marked debt.")
    equity = equity_mora(
        posted_collateral_mora=posted_collateral_mora,
        locked_sale_proceeds_mora=locked_sale_proceeds_mora,
        debt_units=debt_units, mark_price_micromora=mark_price_micromora,
        accrued_interest_mora=accrued_interest_mora,
    )
    return int((equity * Decimal(10_000) / debt).to_integral_value(rounding=ROUND_DOWN))


def liquidation_state(*, margin_bps: int, market_halted: bool, mark_available: bool) -> str:
    if market_halted or not mark_available:
        return "frozen"
    if int(margin_bps) < FULL_LIQUIDATION_BPS:
        return "full"
    if int(margin_bps) < PARTIAL_LIQUIDATION_BPS:
        return "partial"
    return "healthy"


def minimum_partial_liquidation_units(*, debt_units: int, mark_price_micromora: int,
                                      current_equity_mora: Decimal,
                                      posted_collateral_mora: Decimal) -> int:
    """Smallest reduce-only close that restores 200%, or a full close if needed."""
    debt_units = int(debt_units)
    if debt_units <= 0:
        raise ShortsPolicyError("Debt must be positive.")
    mark = Decimal(int(mark_price_micromora)) / Decimal(PRICE_SCALE * TOKEN_SCALE)
    penalty_per_unit = (
        Decimal(str(posted_collateral_mora)) * Decimal(LIQUIDATION_PENALTY_BPS)
        / Decimal(10_000 * debt_units)
    )
    needed = Decimal(INITIAL_MARGIN_BPS) / Decimal(10_000) * mark * debt_units - Decimal(str(current_equity_mora))
    denominator = Decimal(INITIAL_MARGIN_BPS) / Decimal(10_000) * mark - penalty_per_unit
    if needed <= 0:
        return 0
    if denominator <= 0:
        return debt_units
    units = int((needed / denominator).to_integral_value(rounding=ROUND_CEILING))
    return min(debt_units, max(1, units))


def liquidation_penalty_split(*, posted_collateral_mora: Decimal, closed_units: int,
                              original_debt_units: int) -> tuple[Decimal, Decimal]:
    if int(original_debt_units) <= 0 or not 0 < int(closed_units) <= int(original_debt_units):
        raise ShortsPolicyError("Invalid liquidation close size.")
    penalty = (
        Decimal(str(posted_collateral_mora)) * Decimal(LIQUIDATION_PENALTY_BPS)
        * Decimal(int(closed_units)) / Decimal(10_000 * int(original_debt_units))
    ).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
    executor = (penalty * Decimal(LIQUIDATOR_PENALTY_BPS) / Decimal(LIQUIDATION_PENALTY_BPS)).quantize(
        Decimal("0.000001"), rounding=ROUND_DOWN,
    )
    return executor, penalty - executor
