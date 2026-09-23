#!/usr/bin/env python3
"""Static boundary: only approved Zarniki conversion may reach the ledger."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    fixed_api = read("FastAPI/routers/exchange.py")
    wallet_api = read("FastAPI/routers/wallet.py")
    bot_economy = read("bot/handlers/economy.py")
    profile_ui = read("FastAPI/static/app.02.js")
    exchange_policy = read("core/zarniki_exchange_v1.py")
    exchange_service = read("services/zarniki_exchange_v1.py")
    fastapi_main = read("FastAPI/main.py")
    assert not (ROOT / "bot/handlers/exchange.py").exists()
    assert not (ROOT / "FastAPI/routers/events.py").exists()

    assert fixed_api.count("HTTPException(") >= 2
    assert "StrictInt" in wallet_api and "mora|diamonds" in wallet_api
    assert "zarniki_exchange_v1.exchange" in wallet_api
    assert "zarniki_exchange_v1.exchange" in bot_economy
    assert "DAILY_ZARNIKI_CAP: Final = 50" in exchange_policy
    assert "Decimal(\"10\")" in exchange_policy and "Decimal(\"0.01\")" in exchange_policy
    assert "find_balance_replay" in exchange_service
    assert "has_open_premium_hold" in exchange_service
    assert "apply_balance_change" in exchange_service and "add_usage_today" in exchange_service
    assert "Stars" not in exchange_service and "invoice" not in exchange_service
    assert "/wallet/exchange-zarniki" in profile_ui
    legacy_events = fastapi_main[fastapi_main.index('@app.get("/api/events")'):fastapi_main.index('# ── Mini App HTML', fastapi_main.index('@app.get("/api/events")'))]
    assert "SELECT * FROM exchange_events" not in legacy_events
    assert '"exchange_retired": True' in legacy_events
    print("approved Zarniki exchange boundary: OK")


if __name__ == "__main__":
    main()
