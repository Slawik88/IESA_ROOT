#!/usr/bin/env python3
"""Structural boundary test for the first cosmetics-ledger migration slice."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
service = (ROOT / "services/cosmetics.py").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/cosmetics.py").read_text(encoding="utf-8")
skins = (ROOT / "services/skins_v3.py").read_text(encoding="utf-8")

single_buy = service[service.index("async def buy("):service.index("def lineup_buy_quote")]
lineup_buy = service[service.index("async def buy_lineup("):service.index("async def buy_many(")]
many_buy = service[service.index("async def buy_many("):service.index("async def get_active_cosmetics(")]
gift_buy = service[service.index("async def gift_cosmetic("):service.index("async def buy_chest(")]
chest_buy = service[service.index("async def buy_chest("):service.index("# ── Пресеты косметики")]
assert "apply_balance_change(" in single_buy
assert "find_balance_replay(" in single_buy
assert 'reason_code="cosmetic_purchase"' in single_buy
assert "UPDATE users SET" not in single_buy
assert "if mutation and mutation.applied" in single_buy
for block in (lineup_buy, many_buy, gift_buy, chest_buy):
    assert "apply_balance_change(" in block
    assert "find_reference_replay(" in block
    assert "UPDATE users SET" not in block
assert router.count('Header(alias="Idempotency-Key")') >= 5
# The old purchase flow is closed for good: every mutation answers 410, and the new skins flow pays through the same ledger.
for handler in ("cosmetics_buy", "cosmetics_buy_lineup", "cosmetics_buy_many", "cosmetics_equip", "cosmetics_gift"):
    assert "_retired()" in router.split(f"async def {handler}(", 1)[1].split("@router", 1)[0], handler
buy_skin = skins[skins.index("async def buy("):skins.index("async def equip(")]
assert "apply_balance_change(" in buy_skin and "find_reference_replay(" in buy_skin and 'reason_code="skin_v3_purchase"' in buy_skin
assert "UPDATE users SET" not in skins
gift_client = (ROOT / "FastAPI/static/app.06.js").read_text(encoding="utf-8")
# Cosmetics are intentionally not released before the separate owner-approved
# cosmetics pass. Ledger safety remains covered above; no buy/gift surface may
# leak from the current public profile.
assert "cosmetics/gift',{method:'POST',headers:" not in gift_client
assert "if not applied:" in router
showcase = (ROOT / "FastAPI/routers/showcase.py").read_text(encoding="utf-8")
assert "UPDATE users SET user_balance" not in showcase
assert "apply_balance_change(" in showcase
assert "find_reference_replay(" in showcase
assert "showcase/buy-bundle',{method:'POST',headers:" not in gift_client
assert "showcase/buy',{method:'POST',headers:" not in gift_client

print("cosmetic purchase ledger contract: OK")
