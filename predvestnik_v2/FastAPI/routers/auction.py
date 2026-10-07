"""FastAPI/routers/auction.py — просмотр лотов, ставки, создание, резерв."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user, require_module
from core.constants import AUCTION_MIN_BID
from core.registry import ITEMS_REGISTRY
from infrastructure.repositories.auction import get_reserve

router = APIRouter(prefix="/auction", tags=["auction"], dependencies=[Depends(require_module("module_auction"))])


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
        # R5: remaining_sec — разность внутри БД (клиент не парсит naive-строку
        # ends_at против часов устройства; тот же фикс-класс, что у экспедиций)
        "CAST(EXTRACT(EPOCH FROM (al.ends_at - NOW())) AS BIGINT) AS remaining_sec, "
        "COALESCE(MAX(ab.amount), al.min_bid) AS current_bid, "
        "COUNT(ab.id) AS bid_count, "
        "u.user_tg_username AS seller_name, "
        "(v.user_id IS NOT NULL) AS seller_is_vip "
        "FROM auction_lots al "
        "LEFT JOIN auction_bids ab ON ab.lot_id = al.id AND ab.is_active = 1 "
        "LEFT JOIN users u ON u.user_tg_id = al.seller_id "
        "LEFT JOIN vip_subscriptions v ON v.user_id = al.seller_id AND v.expires_at > NOW() "
        "WHERE al.status = 'active' "
        "GROUP BY al.id, u.user_tg_username, v.user_id "
        "ORDER BY al.ends_at ASC LIMIT ? OFFSET ?",
        (per_page, offset),
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
            r["item_rarity"] = item_data.get("rarity", "")   # ШАГ2: для фильтра по редкости

    return {"lots": rows, "total": total, "page": page, "per_page": per_page,
            "has_more": (offset + per_page) < total, "min_bid_floor": AUCTION_MIN_BID,
            "market_open": False,
            "market_message": "Новые лоты и ставки закрыты до проверки происхождения товаров. Активные обязательства можно просмотреть или снять."}


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
async def create_lot(
    body: CreateLotRequest, db=Depends(get_db), user=Depends(require_tg_user),
    request_key: str = Header(alias="Idempotency-Key"),
):
    """Выставить предмет из инвентаря на аукцион."""
    raise HTTPException(410, "Новые лоты откроются после проверки происхождения разрешённых товаров.")


class CreatePetLotRequest(BaseModel):
    pet_id:  int
    min_bid: float
    buyout:  float | None = None


@router.post("/create-pet")
async def create_pet_lot(
    body: CreatePetLotRequest, db=Depends(get_db), user=Depends(require_tg_user),
    request_key: str = Header(alias="Idempotency-Key"),
):
    """Reject retired pet listings without invoking their legacy escrow writer."""
    raise HTTPException(410, "Питомцы не продаются: владение и связь со спутником привязаны к игроку.")


class CancelLotRequest(BaseModel):
    lot_id: int


@router.post("/cancel")
async def cancel_lot_endpoint(body: CancelLotRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Снять свой лот с торгов. Резерв ставивших освобождается, а питомец (если
    лот был на питомца) возвращается на склад продавца. Та же бизнес-логика, что
    и у бота — единый `services.auction.cancel_lot`."""
    from services.auction import cancel_lot
    ok, msg = await cancel_lot(db, body.lot_id, user["id"])
    if not ok:
        raise HTTPException(400, msg)
    await db.commit()
    return {"ok": True, "message": msg}


class BidRequest(BaseModel):
    lot_id: int
    amount: float


@router.post("/bid")
async def bid(
    body: BidRequest, db=Depends(get_db), user=Depends(require_tg_user),
    request_key: str = Header(alias="Idempotency-Key"),
):
    """Поставить ставку; доступная сумма проверяется под блокировкой в сервисе."""
    raise HTTPException(410, "Новые ставки закрыты до безопасного запуска рынка. Текущие резервы будут урегулированы автоматически.")
