#!/usr/bin/env python3
"""Structural boundary test for the first cosmetics-ledger migration slice."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
service = (ROOT / "services/cosmetics.py").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/cosmetics.py").read_text(encoding="utf-8")
client = (ROOT / "FastAPI/static/app.10.js").read_text(encoding="utf-8")

single_buy = service[service.index("async def buy("):service.index("def lineup_buy_quote")]
assert "apply_balance_change(" in single_buy
assert "find_balance_replay(" in single_buy
assert 'reason_code="cosmetic_purchase"' in single_buy
assert "UPDATE users SET" not in single_buy
assert "if mutation and mutation.applied" in single_buy
assert 'Header(alias="Idempotency-Key")' in router
assert "_looksPurchaseKeys" in client
assert "'Idempotency-Key':requestKey" in client

print("cosmetic purchase ledger contract: OK")
