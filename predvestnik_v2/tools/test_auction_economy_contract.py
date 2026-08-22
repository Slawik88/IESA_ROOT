#!/usr/bin/env python3
"""Structural regression checks for the auction ownership/accounting boundary."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
service = (ROOT / "services/auction.py").read_text(encoding="utf-8")
repo = (ROOT / "infrastructure/repositories/auction.py").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/auction.py").read_text(encoding="utf-8")
client = (ROOT / "FastAPI/static/app.04.js").read_text(encoding="utf-8")

create = service[service.index("async def create_auction_lot("):service.index("async def place_bid(")]
bid = service[service.index("async def place_bid("):service.index("async def resolve_lot(")]
resolve = service[service.index("async def resolve_lot("):service.index("async def cancel_lot(")]
cancel = service[service.index("async def cancel_lot("):service.index("async def _finalize_lot(")]
finalize = service[service.index("async def _finalize_lot("):]

assert "async with eco_repo.atomic(db, seller_id)" in create
assert "find_reference_replay(" in create
assert 'source="auction_listing_fee"' in create
assert "listing_operation_id" in repo
assert "UPDATE inventory SET quantity = quantity - ?" in create
assert "placement = 'auction'" in create

restore = service[service.index("async def _restore_asset_escrow("):service.index("async def create_auction_lot(")]
assert "INSERT INTO inventory" in restore
assert "placement = 'storage'" in restore
assert "_restore_asset_escrow(db, lot)" in resolve
assert "_restore_asset_escrow(db, lot)" in cancel

assert bid.index("FOR UPDATE") < bid.index("highest = await get_highest_bid")
assert "get_bid_by_request(" in bid
assert "effective_amount = float(lot[\"buyout\"])" in bid
assert '"applied": False' in bid and '"applied": True' in bid
assert "request_key" in repo and "idx_auction_bids_request" in repo

assert 'idempotency_key=f"auction-settle:{lot[\'id\']}:buyer"' in finalize
assert 'idempotency_key=f"auction-settle:{lot[\'id\']}:seller"' in finalize
assert "UPDATE users SET user_balance" not in service

assert router.count('Header(alias="Idempotency-Key")') >= 3
for path in ("/auction/create", "/auction/create-pet", "/auction/bid"):
    assert f"api('{path}'" in client
assert client.count("'Idempotency-Key':requestKey") >= 3
assert 'if result.get("applied")' in router

print("auction economy contract: OK")
