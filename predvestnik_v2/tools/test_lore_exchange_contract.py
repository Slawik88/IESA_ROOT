#!/usr/bin/env python3
"""Contract checks for the world-integrated, ledger-backed lore exchange."""
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import crypto_exchange as market  # noqa: E402


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    repo = read("infrastructure/repositories/crypto.py")
    api = read("FastAPI/routers/exchange.py")
    ui = read("FastAPI/static/app.06.js")
    startup = read("bot/__main__.py")
    trade = repo[repo.index("async def trade("):]

    assert len(market.COINS) == 8
    assert all(c.get("region") and c.get("use") for c in market.COINS)
    phase = market.world_phase(1_800_000_000)
    assert len(phase["focus"]) == 2 and phase["ends_at"] > 1_800_000_000
    assert market.price_at(market.COINS[0], 1_800_000_000) == market.price_at(
        market.COINS[0], 1_800_000_000
    )

    assert "apply_balance_change(" in trade
    assert "find_reference_replay(" in trade
    assert "crypto_market_budget" in trade
    assert "FOR UPDATE" in trade
    assert "UPDATE users SET user_balance_mora" not in trade
    assert "Idempotency-Key" in api
    assert '"risk_budget": budget' in api
    assert '"world_phase": cx.world_phase()' in api
    assert "'Idempotency-Key':_cxTradeKey" in ui
    assert "fmtF(c.price)" in ui
    assert "fmtF(cost)" in ui
    assert "fmt(Math.round(cost))" not in ui
    assert "Резерв продаж" in ui
    assert "crypto_alerts_task" in startup

    print("lore exchange contract: OK")


if __name__ == "__main__":
    main()
