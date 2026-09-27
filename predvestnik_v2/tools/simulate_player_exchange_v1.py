#!/usr/bin/env python3
"""Deterministic pure-model stress simulation for the hidden player exchange."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.player_exchange_v1 import (
    GENESIS_UNITS,
    MAX_PRICE_MICROMORA,
    PRICE_SCALE,
    TOKEN_SCALE,
    AuctionBid,
    allocation_units,
    buy_reserve,
    clear_uniform_auction,
    depth_band_bounds,
    protected_limit_price,
    trade_fee,
    trade_notional,
    treasury_ladder_prices,
)


def simulate_spot_market(rng: random.Random, digest: hashlib._Hash) -> tuple[int, Decimal, dict[str, int]]:
    actors = ("owner", "p1", "p2", "treasury")
    mora = {actor: Decimal("1000000") for actor in actors}
    tokens = {"owner": 100_000_000, "p1": 100_000_000, "p2": 100_000_000,
              "treasury": 300_000_000}
    initial_mora = sum(mora.values(), Decimal("0"))
    initial_tokens = sum(tokens.values())
    circulating = tokens["owner"] + tokens["p1"] + tokens["p2"]
    orders: list[dict] = []
    insurance = Decimal("0")
    burned = Decimal("0")
    trades = 0
    halted = False
    coverage = {key: 0 for key in (
        "partial_fills", "ioc_residual_cancels", "self_cross_preventions", "owner_treasury_preventions",
        "treasury_trades", "halt_transitions", "maker_buy", "maker_sell", "user_cancels",
    )}

    def cancel(order: dict) -> None:
        if order["status"] != "open":
            return
        if order["side"] == "buy":
            mora[order["actor"]] += order["reserved_mora"]
            order["reserved_mora"] = Decimal("0")
        else:
            tokens[order["actor"]] += order["remaining"]
            order["reserved_units"] = 0
        order["remaining"] = 0
        order["status"] = "cancelled"

    def match() -> None:
        nonlocal insurance, burned, trades, circulating
        if halted:
            return
        for _ in range(32):
            bids = sorted((o for o in orders if o["status"] == "open" and o["side"] == "buy"),
                          key=lambda o: (-o["price"], o["seq"]))
            asks = sorted((o for o in orders if o["status"] == "open" and o["side"] == "sell"),
                          key=lambda o: (o["price"], o["seq"]))
            if not bids or not asks or bids[0]["price"] < asks[0]["price"]:
                return
            buy, sell = bids[0], asks[0]
            if {buy["actor"], sell["actor"]} == {"owner", "treasury"}:
                coverage["owner_treasury_preventions"] += 1
                cancel(buy if buy["actor"] == "owner" else sell)
                continue
            if buy["actor"] == sell["actor"]:
                coverage["self_cross_preventions"] += 1
                cancel(buy if buy["seq"] > sell["seq"] else sell)
                continue
            maker_buy = buy["seq"] < sell["seq"]
            price = buy["price"] if maker_buy else sell["price"]
            units = min(buy["remaining"], sell["remaining"])
            if units < buy["remaining"] or units < sell["remaining"]:
                coverage["partial_fills"] += 1
            gross = trade_notional(units, price)
            buyer_fee = trade_fee(gross, maker=maker_buy)
            seller_fee = trade_fee(gross, maker=not maker_buy)
            charge = gross + buyer_fee
            assert buy["reserved_mora"] >= charge
            buy["reserved_mora"] -= charge
            sell["reserved_units"] -= units
            buy["remaining"] -= units
            sell["remaining"] -= units
            tokens[buy["actor"]] += units
            mora[sell["actor"]] += gross - seller_fee
            if sell["actor"] == "treasury":
                circulating += units
            if buy["actor"] == "treasury":
                circulating -= units
            total_fee = buyer_fee + seller_fee
            fee_insurance = (total_fee * 3 / 10).quantize(Decimal("0.000001"))
            insurance += fee_insurance
            burned += total_fee - fee_insurance
            trades += 1
            coverage["maker_buy" if maker_buy else "maker_sell"] += 1
            if "treasury" in {buy["actor"], sell["actor"]}:
                coverage["treasury_trades"] += 1
            for order in (buy, sell):
                if order["remaining"] == 0:
                    order["status"] = "filled"
            if buy["status"] == "filled" and buy["reserved_mora"]:
                mora[buy["actor"]] += buy["reserved_mora"]
                buy["reserved_mora"] = Decimal("0")

    for seq in range(rng.randint(8, 20)):
        roll = rng.random()
        if roll < 0.08:
            halted = not halted
            coverage["halt_transitions"] += 1
            continue
        open_orders = [order for order in orders if order["status"] == "open"]
        if roll < 0.22 and open_orders:
            cancel(rng.choice(open_orders))
            coverage["user_cancels"] += 1
            continue
        if halted:
            continue
        actor = rng.choice(actors)
        side = rng.choice(("buy", "sell"))
        price = rng.randint(500_000, 5_000_000)
        units = rng.randint(20_000, 300_000)
        if trade_notional(units, price) < Decimal("10"):
            continue
        tif = "ioc" if rng.random() < 0.25 else "gtc"
        order = {"seq": seq, "actor": actor, "side": side, "price": price,
                 "remaining": units, "status": "open", "reserved_mora": Decimal("0"),
                 "reserved_units": 0, "tif": tif}
        if side == "buy":
            reserve = buy_reserve(units, price)
            if mora[actor] < reserve:
                continue
            mora[actor] -= reserve
            order["reserved_mora"] = reserve
        else:
            if tokens[actor] < units:
                continue
            tokens[actor] -= units
            order["reserved_units"] = units
        orders.append(order)
        match()
        if tif == "ioc" and order["status"] == "open":
            cancel(order)
            coverage["ioc_residual_cancels"] += 1

    for order in orders:
        cancel(order)
    free_mora = sum(mora.values(), Decimal("0"))
    reserved_mora = sum((o["reserved_mora"] for o in orders), Decimal("0"))
    assert free_mora + reserved_mora + insurance + burned == initial_mora
    free_tokens = sum(tokens.values())
    reserved_tokens = sum(o["reserved_units"] for o in orders)
    assert free_tokens + reserved_tokens == initial_tokens
    assert all(
        order["status"] == "open" or (
            order["reserved_mora"] == 0 and order["reserved_units"] == 0 and order["remaining"] == 0
        ) for order in orders
    )
    assert circulating == tokens["owner"] + tokens["p1"] + tokens["p2"]
    digest.update(json.dumps({
        "mora": {key: str(value) for key, value in mora.items()}, "tokens": tokens,
        "insurance": str(insurance), "burned": str(burned), "circulating": circulating,
        "trades": trades, "halted": halted,
        "orders": [{
            "seq": o["seq"], "actor": o["actor"], "side": o["side"], "price": o["price"],
            "status": o["status"], "remaining": o["remaining"],
            "reserved_mora": str(o["reserved_mora"]), "reserved_units": o["reserved_units"],
            "tif": o["tif"],
        } for o in orders],
    }, sort_keys=True, separators=(",", ":")).encode())
    return trades, insurance + burned, coverage


def simulate(*, markets: int, seed: int) -> dict:
    rng = random.Random(seed)
    digest = hashlib.sha256()
    nonempty = 0
    empty = 0
    total_bids = 0
    total_allocated = 0
    total_fees = Decimal("0")
    total_spot_trades = 0
    spot_coverage: dict[str, int] = {}
    allocations = allocation_units()
    assert sum(allocations.values()) == GENESIS_UNITS

    for market_index in range(markets):
        bid_count = rng.randint(0, 24)
        bids = []
        escrow_by_id = {}
        for bid_index in range(bid_count):
            price = rng.randint(1, 25_000_000)
            escrow = rng.randint(1, 1_000_000)
            bid_id = f"{market_index:06x}:{bid_index:02x}"
            bids.append(AuctionBid(bid_id, price, escrow))
            escrow_by_id[bid_id] = escrow
        total_bids += bid_count
        clearing = clear_uniform_auction(bids, allocations["auction"])
        assert 0 <= clearing.sold_units <= allocations["auction"]
        assert clearing.sold_units == sum(clearing.allocations.values())
        assert clearing.raised_mora == sum(clearing.costs_mora.values(), Decimal("0"))
        for bid_id, units in clearing.allocations.items():
            assert units > 0
            assert Decimal("0") < clearing.costs_mora[bid_id] <= escrow_by_id[bid_id]
        total_allocated += clearing.sold_units
        if clearing.clearing_price_micromora:
            nonempty += 1
            ladder = treasury_ladder_prices(clearing.clearing_price_micromora)
            assert len(ladder) == 10
            assert all(price < clearing.clearing_price_micromora for side, price in ladder if side == "buy")
            assert all(price > clearing.clearing_price_micromora for side, price in ladder if side == "sell")
        else:
            empty += 1

        quote = rng.randint(1, MAX_PRICE_MICROMORA // 2)
        slip = rng.choice((1, 3, 5))
        buy_limit = protected_limit_price(side="buy", quote_micromora=quote, slippage_percent=slip)
        sell_limit = protected_limit_price(side="sell", quote_micromora=quote, slippage_percent=slip)
        assert buy_limit * 100 <= quote * (100 + slip)
        assert sell_limit * 100 >= quote * (100 - slip)

        units = rng.randint(1, 5_000_000)
        price = rng.randint(1, 50_000_000)
        gross = trade_notional(units, price)
        maker_fee = trade_fee(gross, maker=True)
        taker_fee = trade_fee(gross, maker=False)
        assert maker_fee >= 0 and taker_fee >= maker_fee
        assert buy_reserve(units, price) >= gross + taker_fee
        total_fee = maker_fee + taker_fee
        insurance = (total_fee * 3 / 10).quantize(Decimal("0.000001"))
        burned = total_fee - insurance
        assert insurance + burned == total_fee
        total_fees += total_fee

        spot_trades, spot_fees, market_coverage = simulate_spot_market(rng, digest)
        total_spot_trades += spot_trades
        total_fees += spot_fees
        for key, value in market_coverage.items():
            spot_coverage[key] = spot_coverage.get(key, 0) + value

        reference = rng.randint(1, MAX_PRICE_MICROMORA)
        floor, ceiling = depth_band_bounds(reference)
        assert floor * 100 >= reference * 95
        assert ceiling * 100 <= reference * 105
        assert floor >= 1 and ceiling <= MAX_PRICE_MICROMORA * 105 // 100

        digest.update(
            json.dumps({"market": market_index, "bids": [(b.bid_id, b.max_price_micromora, b.escrow_mora) for b in bids],
                        "clearing": clearing.clearing_price_micromora, "sold": clearing.sold_units,
                        "raised": str(clearing.raised_mora), "buy_limit": buy_limit,
                        "sell_limit": sell_limit, "gross": str(gross), "fee": str(total_fee),
                        "depth": [reference, floor, ceiling]}, separators=(",", ":")).encode()
        )

    assert all(value > 0 for value in spot_coverage.values())
    return {
        "rules": "player-exchange-v1-2026-09-26",
        "seed": seed,
        "markets": markets,
        "nonempty_auction_models": nonempty,
        "empty_auction_models": empty,
        "bids_generated": total_bids,
        "allocated_token_units": total_allocated,
        "spot_trades_modelled": total_spot_trades,
        "spot_coverage": spot_coverage,
        "fees_modelled_mora": str(total_fees),
        "invariants_checked_per_market": [
            "auction_supply_and_escrow_conservation",
            "deterministic_uniform_clearing",
            "treasury_ladder_price_separation",
            "protected_order_slippage_bounds",
            "buyer_reserve_covers_trade_and_fee",
            "fee_burn_insurance_conservation",
            "mutable_order_book_mora_conservation",
            "mutable_order_book_token_and_circulation_conservation",
            "partial_fill_cancel_ioc_and_halt_sequences",
            "strict_inward_depth_boundaries",
        ],
        "digest_sha256": digest.hexdigest(),
        "status": "PASS",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markets", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260927)
    args = parser.parse_args()
    if not 1 <= args.markets <= 1_000_000:
        raise SystemExit("--markets must be between 1 and 1,000,000")
    print(json.dumps(simulate(markets=args.markets, seed=args.seed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
