#!/usr/bin/env python3
"""Static contract: Dark Mora is spend-only and never powers economy v3."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    api = read("FastAPI/routers/dark_mora.py")
    bot = read("bot/handlers/dark_mora.py")
    repo = read("infrastructure/repositories/dark_mora.py")
    startup = read("bot/__main__.py")
    ui = read("FastAPI/static/app.05.js")
    relic_repo = read("infrastructure/repositories/relics.py")
    relic_api = read("FastAPI/routers/relics.py")
    registry = read("core/registry.py")
    policy = read("core/economy_v3.py")
    promo_repo = read("infrastructure/repositories/promocodes.py")

    contrabanda = api[api.index("async def contrabanda("):api.index('@router.post("/ritual")')]
    ritual = api[api.index("async def ritual("):api.index('@router.get("/merchant-status")')]
    assert "410" in contrabanda and "410" in ritual
    assert '"active": False' in api
    assert "if amount > 0:" in repo
    assert "legacy_archive" in repo
    assert "shadow_merchant_task(bot)" not in startup
    assert "Новые пророчества Торговца закрыты" in bot
    assert "doContrabanda(this)" not in ui and "doRitual(this)" not in ui

    buy_relic = relic_repo[relic_repo.index("async def buy_relic("):]
    assert "apply_balance_change(" in buy_relic
    assert "find_balance_replay(" in buy_relic
    assert "UPDATE users SET" not in buy_relic
    assert "Idempotency-Key" in relic_api
    assert '"archive_only": True' in relic_api
    assert "return 0.0" in relic_repo

    relics = registry[registry.index("RELICS: dict"):registry.index("# ── Shadow Relics")]
    assert relics.count('"exp_mora_pct": 0.0,') >= 1
    assert '"dark_mora":' in relics
    assert "LEGACY_BALANCE_POLICIES" in policy
    assert 'lifecycle="legacy_spend_only"' in policy
    assert "if dark_mora or zarniki:" in promo_repo

    print("dark archive contract: OK")


if __name__ == "__main__":
    main()
