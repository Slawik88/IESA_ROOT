"""Reproducible candidate Monte Carlo; prints aggregate-only JSON to stdout.

Each run is an independent 24-tick path (2 hours), not a single tick disguised
as a run. Also tests round trips, admission exhaustion, shorts and global cash.
No database, no production secret, no files written by this command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.coin_market_v2 import (
    CHARACTERS,
    MORA,
    RULES_VERSION,
    Book,
    Coin,
    MarketError,
    PriceState,
    buy,
    close_short,
    next_price,
    open_short,
    personal_genesis,
    sell,
)


def simulate(runs: int, seed: int) -> dict:
    rng = random.Random(seed)
    coin = Coin("SIM", 20_000)
    results = defaultdict(list)
    counts = Counter()
    phases = Counter()
    digest = hashlib.sha256()
    for run in range(runs):
        character = tuple(CHARACTERS)[run % len(CHARACTERS)]
        secret = hashlib.sha256(f"public-test-only:{seed}:{run}".encode()).digest()
        state = PriceState(0, coin.base)
        changes = []
        checkpoint = None
        for tick in range(24):
            prior = state
            state = next_price(coin, prior, secret=secret, character=character, group="sim")
            assert coin.floor <= state.price <= coin.ceiling
            assert abs(state.price - prior.price) * 10_000 <= prior.price * 250
            assert state.tick == prior.tick + 1
            changes.append((state.price - prior.price) / prior.price)
            phases[state.phase] += 1
            if tick == 11:
                checkpoint = PriceState(**vars(state))
        if run % 100 == 0:
            for _ in range(12):
                checkpoint = next_price(coin, checkpoint, secret=secret,
                                        character=character, group="sim")
            assert checkpoint == state
            counts["restart_paths"] += 1
        results[character].append((state.price / coin.base - 1, statistics.fmean(map(abs, changes))))
        digest.update(f"{run}:{state.price}:{state.phase}".encode())
        counts["paths"] += 1
        counts["ticks"] += 24

        # Cash conservation holds for profitable AND losing arbitrary exits.
        book = Book(20_000 * MORA, insurance=10_000 * MORA)
        wallet_delta = burned = 0
        holdings = []
        positions = []
        for _ in range(6):
            price = rng.randint(coin.floor, coin.ceiling)
            budget = rng.randint(10, 1_000) * MORA
            try:
                if rng.randrange(2):
                    trade = buy(coin, book, price, budget)
                    holdings.append(trade.units)
                else:
                    trade = open_short(coin, book, price, budget)
                    positions.append(trade.position)
            except MarketError:
                # Pool exhaustion is an expected admission decision, not a loss
                # of the already accepted positions or their closing rights.
                counts["entry_rejections"] += 1
                continue
            book = trade.book
            wallet_delta += trade.flow.wallet
            burned += trade.flow.burned
        for quantity in holdings:
            trade = sell(coin, book, rng.randint(coin.floor, coin.ceiling), quantity)
            book = trade.book
            wallet_delta += trade.flow.wallet
            burned += trade.flow.burned
            counts["spot_exits"] += 1
        for position in positions:
            # Includes a jump straight to the absolute max: outage or skipped
            # liquidation ticks must not create user debt or insolvency.
            price = coin.ceiling if run % 5 == 0 else rng.randint(coin.floor, coin.ceiling)
            trade = close_short(coin, book, price, position)
            book = trade.book
            wallet_delta += trade.flow.wallet
            burned += trade.flow.burned
            counts["short_exits"] += 1
            counts["liquidations"] += trade.liquidated
            assert trade.payout >= 0
        assert book.held == book.borrowed == 0
        assert book.reserve + book.insurance + wallet_delta + burned == 30_000 * MORA
        book.validate(coin)

    # Repeated perfect timing exhausts finite funding: reject only NEW claims.
    book = Book(20_000 * MORA)
    while True:
        try:
            bought = buy(coin, book, coin.floor, 1_000 * MORA)
        except MarketError:
            break
        book = sell(coin, bought.book, coin.ceiling, bought.units).book
        counts["perfect_round_trips_before_entry_block"] += 1
        assert counts["perfect_round_trips_before_entry_block"] < 1_000
    book.validate(coin)
    assert book.held == 0

    for zarniki in (1_000, 2_500, 5_000):
        for deposit in (1_000, 10_000, 100_000):
            genesis = personal_genesis(f"{zarniki}-{deposit}", deposit * MORA, zarniki)
            payout = sell(genesis.coin, genesis.book, genesis.coin.ceiling,
                          genesis.creator_units).flow.wallet
            assert payout < deposit * MORA
            counts["creation_cases"] += 1

    # Separate seven-day paths expose long phases, reversals and boundary
    # sticking that two-hour start-at-base paths cannot reveal.
    long_profiles = {}
    for character in CHARACTERS:
        phases_seen = Counter()
        durations = []
        returns = []
        boundary_ticks = reversals = jumps = transitions = 0
        for run in range(64):
            state = PriceState(0, coin.base)
            secret = hashlib.sha256(f"long:{seed}:{run}".encode()).digest()
            direction = 0
            length = 0
            phase = state.phase
            for _ in range(7 * 24 * 12):
                prior = state
                state = next_price(coin, prior, secret=secret, character=character, group="sim")
                delta = state.price - prior.price
                assert abs(delta) * 10_000 <= prior.price * 250
                assert coin.floor <= state.price <= coin.ceiling
                current_direction = 1 if delta > 0 else (-1 if delta < 0 else 0)
                if direction and current_direction and current_direction != direction:
                    reversals += 1
                direction = current_direction or direction
                jumps += abs(delta) * 100 > prior.price  # >1% visible move, not secret jump label
                boundary_ticks += state.price in (coin.floor, coin.ceiling)
                if state.phase != phase:
                    if length:
                        durations.append(length)
                    transitions += 1
                    phase, length = state.phase, 0
                length += 1
                phases_seen[state.phase] += 1
            returns.append((state.price / coin.base - 1) * 100)
        tick_count = 64 * 7 * 24 * 12
        long_profiles[character] = {
            "paths": 64, "days_per_path": 7, "ticks": tick_count,
            "phase_ticks": dict(phases_seen), "phase_transitions": transitions,
            "mean_observed_phase_ticks": round(statistics.fmean(durations), 2),
            "direction_reversals_pct": round(reversals / tick_count * 100, 3),
            "moves_over_one_pct": jumps, "boundary_ticks_pct": round(boundary_ticks / tick_count * 100, 3),
            "seven_day_return_min_max_pct": [round(min(returns), 3), round(max(returns), 3)],
        }

    profiles = {}
    for character, data in results.items():
        returns = sorted(row[0] for row in data)
        profiles[character] = {
            "runs": len(data),
            "mean_abs_tick_pct": round(statistics.fmean(row[1] for row in data) * 100, 4),
            "two_hour_return_percentiles_pct": {
                str(p): round(returns[min(len(returns) - 1, len(returns) * p // 100)] * 100, 4)
                for p in (1, 10, 50, 90, 99)
            },
        }
    return {"rules": RULES_VERSION, "seed": seed, "ticks_per_path": 24,
            "counts": dict(counts), "phase_ticks": dict(phases), "profiles": profiles,
            "seven_day_diagnostics": long_profiles,
            "digest": digest.hexdigest(), "status": "PASS",
            "limitations": ["No PostgreSQL/API/browser/concurrency proof",
                             "No statistical claim of cryptographic unpredictability",
                             "Finite profitable turnover exhausts new-entry headroom"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20261017)
    args = parser.parse_args()
    if not 4 <= args.runs <= 1_000_000:
        parser.error("runs must be between 4 and 1000000")
    print(json.dumps(simulate(args.runs, args.seed), ensure_ascii=False, indent=2))
