#!/usr/bin/env python3
"""Static contract: retired currency conversions cannot mutate a wallet."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    fixed_api = read("FastAPI/routers/exchange.py")
    event_api = read("FastAPI/routers/events.py")
    wallet_api = read("FastAPI/routers/wallet.py")
    bot_exchange = read("bot/handlers/exchange.py")
    bot_economy = read("bot/handlers/economy.py")
    economy_repo = read("infrastructure/repositories/economy.py")
    profile_ui = read("FastAPI/static/app.02.js")
    market_ui = read("FastAPI/static/app.05.js")
    shared_ui = read("FastAPI/static/app.06.js")
    help_copy = read("bot/handlers/common.py")

    assert fixed_api.count("HTTPException(") >= 2
    assert '"exchange_retired": True' in event_api
    assert "exchange_active" not in event_api
    assert "exchange_next" not in event_api

    assert "Алмазы за Зарники не продаются" in wallet_api
    assert "await exchange_zarniki(" in wallet_api
    assert "quote_zarniki_to_mora" in economy_repo
    assert "validate_exchange_route" in economy_repo
    assert "await eco_db.exchange_zarniki" in bot_economy

    assert "add_balance" not in bot_exchange
    assert "3 000 🪙 = 1 💎" not in help_copy
    assert "1 💎 = 2 000 🪙" not in help_copy
    assert "Мора и Алмазы не обмениваются" in help_copy

    assert "openExchangeZarnikiModal()':" in profile_ui
    assert "/wallet/exchange-zarniki" in shared_ui
    assert "doExchangeZarniki" in shared_ui
    assert "Алмазы выдаются только за испытания и сезонные рубежи" in shared_ui
    assert "Косметика, сервисные возможности и необратимый обмен в Мору" in market_ui

    print("currency exchange retirement contract: OK")


if __name__ == "__main__":
    main()
