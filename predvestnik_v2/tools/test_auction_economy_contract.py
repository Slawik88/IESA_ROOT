#!/usr/bin/env python3
"""Structural regression checks for the auction ownership/accounting boundary."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
service = (ROOT / "services/auction.py").read_text(encoding="utf-8")
repo = (ROOT / "infrastructure/repositories/auction.py").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/auction.py").read_text(encoding="utf-8")
client = (ROOT / "FastAPI/static/app.04.js").read_text(encoding="utf-8")
client_cards = (ROOT / "FastAPI/static/app.06.js").read_text(encoding="utf-8")

create = service[service.index("async def create_auction_lot("):service.index("async def place_bid(")]
bid = service[service.index("async def place_bid("):service.index("async def resolve_lot(")]
resolve = service[service.index("async def resolve_lot("):service.index("async def cancel_lot(")]
cancel = service[service.index("async def cancel_lot("):service.index("async def _finalize_lot(")]
finalize = service[service.index("async def _finalize_lot("):]

assert 'return False, "Старый аукцион закрыт.", False' in create
assert '"ok": False' in bid and "db.execute" not in bid
assert "db.execute" not in create
assert 'raise RuntimeError("Legacy auction settlement is retired")' in finalize
assert "return {}" in resolve and "db.execute" not in resolve
assert "return False" in cancel and "db.execute" not in cancel
assert "_restore_asset_escrow(db, lot)" not in finalize
assert "UPDATE users SET user_balance" not in service
assert 'raise RuntimeError("Legacy wallet holds are retired")' in repo

assert '"market_open": False' in router
for marker in (
    "Новые лоты откроются после проверки происхождения",
    "Питомцы не продаются",
    "Новые ставки закрыты",
):
    assert marker in router

# The accounting code stays archived for support and future compensation audits,
# but reconstruction explicitly removes the old auction from every public screen.
for retired_ui_marker in ("openBidModal", "loadAuction", "Создать лот", "💰 Ставка"):
    assert retired_ui_marker not in client
    assert retired_ui_marker not in client_cards

print("auction settlement boundary: OK")
