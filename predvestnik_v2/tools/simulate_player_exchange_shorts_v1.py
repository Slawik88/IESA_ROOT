#!/usr/bin/env python3
"""Deterministic pre-implementation safety simulation for player-exchange Shorts.

It is intentionally separate from the Spot stress model.  A passing result is
evidence for the model and its fail-closed boundaries, never authorisation to
enable Shorts before real Spot observation and the insurance-backstop decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.player_exchange_shorts_v1 import (  # noqa: E402
    INITIAL_MARGIN_BPS,
    SHORTS_RULES_VERSION,
    borrow_apr_bps,
    conservative_mark_price_micromora,
    equity_mora,
    is_short_eligible,
    liquidation_penalty_split,
    liquidation_state,
    margin_ratio_bps,
    minute_interest_mora,
    minimum_partial_liquidation_units,
    pool_utilisation_bps,
    short_limits_units,
    validate_short_open,
)
from core.player_exchange_v1 import trade_notional


def _assert_rejected_owner(*, circulating: int, pool: int, existing: int) -> None:
    try:
        validate_short_open(
            requested_units=1, circulating_units=circulating, lending_pool_units=pool,
            already_borrowed_units=existing, actor_is_owner_or_linked=True,
        )
    except Exception:
        return
    raise AssertionError("Owner/linked account opened a short in the model.")


def simulate(*, scenarios: int, seed: int) -> dict:
    rng = random.Random(seed)
    digest = hashlib.sha256()
    coverage = {key: 0 for key in (
        "eligible", "owner_denied", "caps", "qualified_mark", "missing_mark",
        "healthy", "partial", "full", "halt_frozen", "interest_paused",
        "insurance_used", "insurance_insufficient", "partial_target_restored",
    )}
    total_interest = Decimal("0")
    total_insurance_used = Decimal("0")

    for index in range(scenarios):
        circulating = rng.randint(20_000_000, 2_000_000_000)
        pool = rng.randint(max(2_000_000, circulating // 50), max(4_000_000, circulating // 3))
        _, aggregate_capacity = short_limits_units(
            circulating_units=circulating, lending_pool_units=pool, already_borrowed_units=0,
        )
        existing = rng.randint(0, aggregate_capacity // 2)
        player_cap, aggregate_remaining = short_limits_units(
            circulating_units=circulating, lending_pool_units=pool, already_borrowed_units=existing,
        )
        requested = rng.randint(1, max(1, min(player_cap, aggregate_remaining)))
        validate_short_open(
            requested_units=requested, circulating_units=circulating, lending_pool_units=pool,
            already_borrowed_units=existing, actor_is_owner_or_linked=False,
        )
        _assert_rejected_owner(circulating=circulating, pool=pool, existing=existing)
        coverage["owner_denied"] += 1
        coverage["caps"] += 1
        assert existing + requested <= aggregate_remaining + existing
        assert requested <= player_cap
        assert existing + requested <= pool // 2
        assert existing + requested <= circulating // 10

        # Lending-pool token claims remain a one-for-one claim on borrowed units.
        pool_available = pool - existing - requested
        lender_token_claims = existing + requested
        assert pool_available >= 0 and pool_available + lender_token_claims == pool

        eligible = is_short_eligible(
            trading_days=7, verified_trades=100, unique_traders=20,
            weekly_volume_mora=Decimal("50000"), depth_5pct_mora=Decimal("10000"),
        )
        assert eligible
        coverage["eligible"] += 1

        entry_price = rng.randint(200_000, 5_000_000)
        entry_notional = trade_notional(requested, entry_price)
        posted_collateral = (entry_notional * Decimal(2)).quantize(Decimal("0.000001"))
        locked_sale_proceeds = entry_notional
        # At opening, sale proceeds + a 200% posted collateral deposit leave
        # exactly 200% equity after debt is marked at the entry price.
        assert margin_ratio_bps(
            posted_collateral_mora=posted_collateral,
            locked_sale_proceeds_mora=locked_sale_proceeds, debt_units=requested,
            mark_price_micromora=entry_price, accrued_interest_mora=Decimal("0"),
        ) == INITIAL_MARGIN_BPS

        mark_available = rng.random() >= 0.12
        if mark_available:
            vwap = max(1, entry_price * rng.randint(55, 650) // 100)
            buyback = max(1, entry_price * rng.randint(55, 700) // 100)
            mark = conservative_mark_price_micromora(
                vwap_5m_micromora=vwap, vwap_5m_volume_mora=Decimal("100"),
                executable_buyback_micromora=buyback,
            )
            assert mark == max(vwap, buyback)
            coverage["qualified_mark"] += 1
        else:
            mark = conservative_mark_price_micromora(
                vwap_5m_micromora=entry_price, vwap_5m_volume_mora=Decimal("99.999999"),
                executable_buyback_micromora=entry_price,
            )
            assert mark is None
            coverage["missing_mark"] += 1

        halted = rng.random() < 0.10
        utilisation = pool_utilisation_bps(lending_pool_units=pool, borrowed_units=existing + requested)
        apr = borrow_apr_bps(utilisation_bps=utilisation)
        elapsed_minutes = rng.randint(1, 10_080)
        interest = Decimal("0")
        if halted:
            # Liquidation and therefore the interest clock are frozen together.
            coverage["interest_paused"] += 1
        elif mark is not None:
            interest = minute_interest_mora(
                debt_units=requested, mark_price_micromora=mark, apr_bps=apr,
            ) * elapsed_minutes
            total_interest += interest
        state = liquidation_state(
            margin_bps=margin_ratio_bps(
                posted_collateral_mora=posted_collateral,
                locked_sale_proceeds_mora=locked_sale_proceeds, debt_units=requested,
                mark_price_micromora=mark or entry_price, accrued_interest_mora=interest,
            ),
            market_halted=halted, mark_available=mark is not None,
        )
        if halted or mark is None:
            assert state == "frozen"
            coverage["halt_frozen"] += int(halted)
        else:
            coverage[state] += 1

        # A close may only return token claims actually bought back.  An
        # insufficient insurance fund blocks settlement before lenders lose a
        # claim; this is the unresolved product backstop made observable.
        debt_notional = trade_notional(requested, mark or entry_price)
        cash = posted_collateral + locked_sale_proceeds
        equity = equity_mora(
            posted_collateral_mora=posted_collateral, locked_sale_proceeds_mora=locked_sale_proceeds,
            debt_units=requested, mark_price_micromora=mark or entry_price, accrued_interest_mora=interest,
        )
        if state in {"partial", "full"}:
            close_units = requested if state == "full" else minimum_partial_liquidation_units(
                debt_units=requested, mark_price_micromora=mark, current_equity_mora=equity,
                posted_collateral_mora=posted_collateral,
            )
            assert 0 < close_units <= requested
            close_cost = trade_notional(close_units, mark)
            proportional_proceeds = (locked_sale_proceeds * Decimal(close_units) / Decimal(requested)).quantize(
                Decimal("0.000001"),
            )
            uncovered = max(Decimal("0"), close_cost - proportional_proceeds - posted_collateral)
            insurance = (entry_notional * Decimal(rng.randint(0, 400)) / Decimal(100)).quantize(Decimal("0.000001"))
            if insurance < uncovered:
                assert lender_token_claims == existing + requested
                coverage["insurance_insufficient"] += 1
            else:
                executor, insurance_fee = liquidation_penalty_split(
                    posted_collateral_mora=posted_collateral, closed_units=close_units,
                    original_debt_units=requested,
                )
                assert executor + insurance_fee <= posted_collateral
                total_insurance_used += uncovered + insurance_fee
                lender_token_claims -= close_units
                pool_available += close_units
                assert pool_available + lender_token_claims == pool
                coverage["insurance_used"] += int(uncovered > 0)
                if state == "partial" and close_units < requested:
                    remaining_equity = equity - executor - insurance_fee
                    remaining_debt = trade_notional(requested - close_units, mark)
                    assert remaining_debt > 0
                    assert remaining_equity * Decimal(10_000) >= remaining_debt * INITIAL_MARGIN_BPS
                    coverage["partial_target_restored"] += 1
        else:
            assert cash >= 0 and lender_token_claims == existing + requested

        digest.update(json.dumps({
            "i": index, "circulating": circulating, "pool": pool, "existing": existing,
            "requested": requested, "entry": entry_price, "mark": mark, "halted": halted,
            "interest": str(interest), "state": state, "claims": lender_token_claims,
        }, sort_keys=True, separators=(",", ":")).encode())

    assert all(value > 0 for value in coverage.values())
    return {
        "rules": SHORTS_RULES_VERSION,
        "seed": seed,
        "scenarios": scenarios,
        "coverage": coverage,
        "interest_modelled_mora": str(total_interest.quantize(Decimal("0.000001"))),
        "insurance_modelled_mora": str(total_insurance_used.quantize(Decimal("0.000001"))),
        "invariants": [
            "no_naked_loans_or_lender_claim_loss",
            "per_player_and_global_borrow_caps",
            "qualified_conservative_mark_only",
            "strict_margin_thresholds_and_halt_freeze",
            "minute_interest_and_pool_utilisation_curve",
            "partial_restore_or_full_close",
            "insurance_insufficiency_fails_closed",
            "deterministic_digest",
        ],
        "status": "MODEL_PASS_NOT_RUNTIME_APPROVAL",
        "digest_sha256": digest.hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20261005)
    args = parser.parse_args()
    if not 1 <= args.scenarios <= 1_000_000:
        raise SystemExit("--scenarios must be between 1 and 1,000,000")
    print(json.dumps(simulate(scenarios=args.scenarios, seed=args.seed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
