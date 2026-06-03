"""FastAPI/routers/auction.py — просмотр лотов, ставки, создание, резерв."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.constants import AUCTION_COMMISSION, AUCTION_MIN_BID
from core.registry import ITEMS_REGISTRY
# ITEMS_REGISTRY used both here and inside loops for item metadata
from infrastructure.repositories.economy import get_balance, get_item_quantity
from infrastructure.repositories.auction import get_reserve
from services.auction import place_bid, create_auction_lot

router = APIRouter(prefix="/auction", tags=["auction"])


@router.get("/lots")
async def active_lots(
    page: int = Query(default=0, ge=0),
    per_page: int = Query(default=20, le=50),
    db=Depends(get_db),
):
    """Активные лоты с пагинацией. page=0,1,2... per_page=20."""
    offset = page * per_page
    async with db.execute(
        "SELECT al.id, al.seller_id, al.item_name, al.quantity, al.min_bid, "
        "al.buyout, al.ends_at, al.status, "
        "COALESCE(MAX(ab.amount), al.min_bid) AS current_bid, "
        "COUNT(ab.id) AS bid_count, "
        "u.user_tg_username AS seller_name "
        "FROM auction_lots al "
        "LEFT JOIN auction_bids ab ON ab.lot_id = al.id AND ab.is_active = 1 "
        "LEFT JOIN users u ON u.user_tg_id = al.seller_id "
        "WHERE al.status = 'active' "
        "GROUP BY al.id, u.user_tg_username "
        f"ORDER BY al.ends_at ASC LIMIT {per_page} OFFSET {offset}",
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]

    # Total count for pagination
    async with db.execute("SELECT COUNT(*) FROM auction_lots WHERE status='active'") as c:
        total = (await c.fetchone())[0]

    for r in rows:
        r["has_bids"] = r.get("bid_count", 0) > 0
        r["min_next_bid"] = int(r["current_bid"] * 1.05) + 1 if r["has_bids"] else int(r["min_bid"])
        # Strip the "||item_id" suffix stored by the bot handler for reverse lookup
        raw_name = r.get("item_name", "") or ""
        parts = raw_name.split("||", 1)
        r["item_name_display"] = parts[0].strip() or "Неизвестный предмет"
        r["item_id_ref"] = parts[1].strip() if len(parts) > 1 else ""
        # Add description from registry if we have item_id
        if r["item_id_ref"]:
            item_data = ITEMS_REGISTRY.get(r["item_id_ref"], {})
            r["item_description"] = item_data.get("description", "")
            r["item_category"] = item_data.get("category", "")

    return {"lots": rows, "total": total, "page": page, "per_page": per_page,
            "has_more": (offset + per_page) < total}


@router.get("/reserved")
async def my_reserved_mora(db=Depends(get_db), user=Depends(require_tg_user)):
    """Разбивка зарезервированной Моры по лотам + общий резерв."""
    reserved_total = await get_reserve(db, user["id"])
    async with db.execute(
        "SELECT ab.lot_id, ab.amount, al.item_name, al.quantity, al.ends_at, "
        "COALESCE(MAX(all_bids.amount), al.min_bid) AS top_bid "
        "FROM auction_bids ab "
        "JOIN auction_lots al ON al.id = ab.lot_id "
        "LEFT JOIN auction_bids all_bids ON all_bids.lot_id = ab.lot_id AND all_bids.is_active = 1 "
        "WHERE ab.bidder_id = ? AND ab.is_active = 1 AND al.status = 'active' "
        "GROUP BY ab.lot_id, ab.amount, al.item_name, al.quantity, al.ends_at, al.min_bid "
        "ORDER BY ab.amount DESC",
        (user["id"],),
    ) as c:
        bids = [dict(r) for r in await c.fetchall()]
    return {"reserved_total": reserved_total, "bids": bids}


@router.get("/my-lots")
async def my_lots(db=Depends(get_db), user=Depends(require_tg_user)):
    """Лоты текущего пользователя."""
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
    item_id:  str
    quantity: int = 1
    min_bid:  float
    buyout:   float | None = None


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

    # item_name format: "Display Name||real_item_id" — used by resolve_lot to restore item
    display = f"{item['name']} ×{body.quantity}" if body.quantity > 1 else item["name"]
    item_name_with_id = f"{display}||{body.item_id}"
    ok, result = await create_auction_lot(
        db, user["id"], item.get("category", "item"),
        "inventory", abs(hash(body.item_id)) % (10**9), body.quantity,
        item_name_with_id,
        body.min_bid, body.buyout,
    )
    if not ok:
        raise HTTPException(400, str(result))

    # Remove item from seller's inventory (escrow until lot is resolved)
    removed = await remove_item(db, user["id"], body.item_id, body.quantity, commit=False)
    if not removed:
        # Lot was created but item can't be removed — cancel it
        from services.auction import cancel_lot
        await cancel_lot(db, result)
        raise HTTPException(400, f"Недостаточно предметов: {item['name']} ×{body.quantity}.")

    await db.commit()
    return {"ok": True, "lot_id": result}


class BidRequest(BaseModel):
    lot_id: int
    amount: float


@router.post("/bid")
async def bid(body: BidRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Поставить ставку. Проверяет свободный баланс (за вычетом резерва)."""
    bal = await get_balance(db, user["id"])
    reserved = await get_reserve(db, user["id"])
    free_mora = bal["user_balance_mora"] - reserved

    if free_mora < body.amount:
        raise HTTPException(
            400,
            f"Недостаточно свободной Моры. Свободно: {free_mora:.0f} 🪙 "
            f"(зарезервировано в ставках: {reserved:.0f} 🪙).",
        )

    result = await place_bid(db, body.lot_id, user["id"], body.amount)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Ошибка ставки."))

    await db.commit()

    # Quest & achievement tracking (same as bot handler does)
    try:
        from services.quests import increment_metric as _q_incr
        from services.achievements import increment_metric as _a_incr
        # Get user's primary chat_id for quest context (use any active chat)
        async with db.execute(
            "SELECT chat_tg_id FROM user_chat_stats WHERE user_tg_id = ? "
            "ORDER BY user_messages_count_all_time DESC LIMIT 1",
            (user["id"],),
        ) as c:
            _chat_row = await c.fetchone()
        if _chat_row:
            await _q_incr(db, user["id"], _chat_row[0], "auction_bids_today", delta=1.0)
            await db.commit()
    except Exception:
        pass

    return {
        "ok": True,
        "is_buyout": result.get("is_buyout", False),
        "commission_pct": AUCTION_COMMISSION * 100,
    }
