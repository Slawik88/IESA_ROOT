import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.player_exchange_v1 import (
    GENESIS_UNITS, PlayerExchangePolicyError, allocation_units,
    parse_token_amount, validate_coin_draft,
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
print("PLAYER_EXCHANGE_V1_RULES_OK")
