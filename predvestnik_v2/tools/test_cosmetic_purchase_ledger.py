#!/usr/bin/env python3
"""Structural boundary test for the first cosmetics-ledger migration slice."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
service = (ROOT / "services/cosmetics.py").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/cosmetics.py").read_text(encoding="utf-8")
client = (ROOT / "FastAPI/static/app.10.js").read_text(encoding="utf-8")

single_buy = service[service.index("async def buy("):service.index("def lineup_buy_quote")]
lineup_buy = service[service.index("async def buy_lineup("):service.index("async def buy_many(")]
many_buy = service[service.index("async def buy_many("):service.index("async def get_active_cosmetics(")]
assert "apply_balance_change(" in single_buy
assert "find_balance_replay(" in single_buy
assert 'reason_code="cosmetic_purchase"' in single_buy
assert "UPDATE users SET" not in single_buy
assert "if mutation and mutation.applied" in single_buy
for block in (lineup_buy, many_buy):
    assert "apply_balance_change(" in block
    assert "find_reference_replay(" in block
    assert "UPDATE users SET" not in block
assert router.count('Header(alias="Idempotency-Key")') >= 3
assert "_looksPurchaseKeys" in client
assert "'Idempotency-Key':requestKey" in client
assert "cosmetics/buy-lineup',{method:'POST',headers:" in client
assert "cosmetics/buy-many',{method:'POST',headers:" in client

print("cosmetic purchase ledger contract: OK")
