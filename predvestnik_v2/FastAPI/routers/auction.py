"""FastAPI/routers/auction.py — просмотр лотов, ставки, создание."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.constants import AUCTION_COMMISSION, AUCTION_MIN_BID
from core.registry import ITEMS_REGISTRY
from infrastructure.repositories.economy import get_balance, get_item_quantity
from services.auction import place_bid, create_auction_lot

router = APIRouter(prefix="/auction", tags=["auction"])


@router.get("/lots")
async def active_lots(db=Depends(get_db)):
    """Активные лоты аукциона."""
    async with db.execute(
        "SELECT al.id, al.seller_id, al.item_name, al.quantity, al.min_bid, "
        "al.buyout, al.ends_at, al.status, "
        "COALESCE(MAX(ab.amount), al.min_bid) AS current_bid, "
        "u.user_tg_username AS seller_name "
        "FROM auction_lots al "
        "LEFT JOIN auction_bids ab ON ab.lot_id = al.id AND ab.is_active = 1 "
        "LEFT JOIN users u ON u.user_tg_id = al.seller_id "
        "WHERE al.status = 'active' "
        "GROUP BY al.id, u.user_tg_username "
        "ORDER BY al.ends_at ASC LIMIT 50",
    ) as c:
        lots = [dict(r) for r in await c.fetchall()]
    return lots


@router.get("/my-lots")
async def my_lots(db=Depends(get_db), user=Depends(require_tg_user)):
    """Лоты текущего пользователя (активные и завершённые)."""
    async with db.execute(
        "SELECT id, item_name, quantity, min_bid, buyout, ends_at, status, "
        "COALESCE((SELECT MAX(amount) FROM auction_bids WHERE lot_id = auction_lots.id AND is_active=1), 0) AS current_bid "
        "FROM auction_lots WHERE seller_id = ? ORDER BY ends_at DESC LIMIT 30",
        (user["id"],),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


@router.get("/my-bids")
async def my_bids(db=Depends(get_db), user=Depends(require_tg_user)):
    """Активные ставки пользователя."""
    async with db.execute(
        "SELECT ab.lot_id, ab.amount, al.item_name, al.quantity, al.ends_at, "
        "COALESCE(MAX(all_bids.amount), al.min_bid) AS top_bid "
        "FROM auction_bids ab "
        "JOIN auction_lots al ON al.id = ab.lot_id "
        "LEFT JOIN auction_bids all_bids ON all_bids.lot_id = ab.lot_id AND all_bids.is_active = 1 "
        "WHERE ab.bidder_id = ? AND al.status = 'active' "
        "GROUP BY ab.lot_id, ab.amount, al.item_name, al.quantity, al.ends_at",
        (user["id"],),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


class CreateLotRequest(BaseModel):
    item_id: str
    quantity: int = 1
    min_bid: float
    buyout: float | None = None


@router.post("/create")
async def create_lot(body: CreateLotRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Выставить предмет из инвентаря на аукцион."""
    item = ITEMS_REGISTRY.get(body.item_id)
    if not item:
        raise HTTPException(400, "Предмет не найден.")
    if body.min_bid < AUCTION_MIN_BID:
        raise HTTPException(400, f"Минимальная ставка: {AUCTION_MIN_BID} 🪙.")

    have = await get_item_quantity(db, user["id"], body.item_id)
    if have < body.quantity:
        raise HTTPException(400, f"В инвентаре только {have} шт.")

    ok, result = await create_auction_lot(
        db, user["id"], item.get("category", "item"),
        "inventory", body.item_id, body.quantity,
        f"{item['name']} ×{body.quantity}" if body.quantity > 1 else item["name"],
        body.min_bid, body.buyout,
    )
    if not ok:
        raise HTTPException(400, str(result))
    await db.commit()
    return {"ok": True, "lot_id": result}


class BidRequest(BaseModel):
    lot_id: int
    amount: float


@router.post("/bid")
async def bid(body: BidRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Поставить ставку на лот."""
    bal = await get_balance(db, user["id"])
    if bal["user_balance_mora"] < body.amount:
        raise HTTPException(400, f"Недостаточно Моры. Нужно {body.amount}, есть {bal['user_balance_mora']:.0f}.")

    result = await place_bid(db, body.lot_id, user["id"], body.amount)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Ошибка ставки."))

    await db.commit()
    return {"ok": True, "is_buyout": result.get("is_buyout", False),
            "commission_pct": AUCTION_COMMISSION * 100}
