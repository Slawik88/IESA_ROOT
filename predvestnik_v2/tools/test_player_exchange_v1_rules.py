import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.player_exchange_v1 import (
    AuctionBid, GENESIS_UNITS, PlayerExchangePolicyError, allocation_units, clear_uniform_auction,
    parse_token_amount, protected_limit_price, validate_coin_draft,
)


def rejects(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except PlayerExchangePolicyError:
        return
    raise AssertionError("Expected PlayerExchangePolicyError")


draft = validate_coin_draft(name="  Северная   звезда ", ticker="nstar", initial_mora=10_000)
assert draft.name == "Северная звезда"
assert draft.ticker == "NSTAR"
assert sum(allocation_units().values()) == GENESIS_UNITS
assert allocation_units()["auction"] == 300_000_000
assert parse_token_amount("1.234") == 1234
rejects(validate_coin_draft, name="ab", ticker="ABC", initial_mora=10_000)
rejects(validate_coin_draft, name="Нормальная", ticker="АБВ", initial_mora=10_000)
rejects(validate_coin_draft, name="Нормальная", ticker="ABC", initial_mora=9_999)
rejects(parse_token_amount, "1.2345")
rejects(parse_token_amount, 0)
clearing = clear_uniform_auction([
    AuctionBid("a", 2_000_000, 100),
    AuctionBid("b", 1_000_000, 100),
], 100_000)
assert clearing.clearing_price_micromora == 1_000_000
assert clearing.allocations == {"a": 100_000}
assert clearing.raised_mora == 100
tie = clear_uniform_auction([
    AuctionBid("a", 1_000_000, 100), AuctionBid("b", 1_000_000, 100),
], 101_001)
assert tie.allocations == {"a": 50_501, "b": 50_500}
assert sum(tie.allocations.values()) == 101_001
for quote in (1, 2, 7, 101):
    for slip in (1, 3, 5):
        buy_limit = protected_limit_price(side="buy", quote_micromora=quote, slippage_percent=slip)
        sell_limit = protected_limit_price(side="sell", quote_micromora=quote, slippage_percent=slip)
        assert buy_limit * 100 <= quote * (100 + slip)
        assert sell_limit * 100 >= quote * (100 - slip)
print("PLAYER_EXCHANGE_V1_RULES_OK")
