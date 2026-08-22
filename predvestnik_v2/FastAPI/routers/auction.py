"""FastAPI/routers/auction.py — просмотр лотов, ставки, создание, резерв."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user, require_module
from core.constants import AUCTION_COMMISSION, AUCTION_MIN_BID
from core.registry import ITEMS_REGISTRY, PET_SPECIES
# ITEMS_REGISTRY used both here and inside loops for item metadata
from infrastructure.repositories.economy import get_item_quantity
from infrastructure.repositories.auction import get_reserve
from services.auction import place_bid, create_auction_lot, queue_lot_announcement

router = APIRouter(prefix="/auction", tags=["auction"], dependencies=[Depends(require_module("module_auction"))])


def _economic_key(value: str, scope: str) -> str:
    key = value.strip()
    if not key or len(key) > 120:
        raise HTTPException(400, "Idempotency-Key должен содержать 1–120 символов.")
    return f"{scope}:{key}"


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
            "has_more": (offset + per_page) < total, "min_bid_floor": AUCTION_MIN_BID}


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
    ok, result, applied = await create_auction_lot(
        db, user["id"], item.get("category", "item"),
        "inventory", abs(hash(body.item_id)) % (10**9), body.quantity,
        item_name_with_id,
        body.min_bid, body.buyout,
        idempotency_key=_economic_key(request_key, "auction-listing"),
    )
    if not ok:
        raise HTTPException(400, str(result))

    await db.commit()
    if applied:
        queue_lot_announcement(result)
    return {"ok": True, "lot_id": result, "replayed": not applied}


class CreatePetLotRequest(BaseModel):
    pet_id:  int
    min_bid: float
    buyout:  float | None = None


@router.post("/create-pet")
async def create_pet_lot(
    body: CreatePetLotRequest, db=Depends(get_db), user=Depends(require_tg_user),
    request_key: str = Header(alias="Idempotency-Key"),
):
    """Выставить питомца со склада на аукцион (web-паритет с ботом).

    Эскроу-first: питомец атомарно переводится из placement='storage' в
    'auction' (RETURNING-guard от гонки/двойного листинга), и только потом
    создаётся лот. Если лот не создался — эскроу откатывается.
    """
    if body.min_bid < AUCTION_MIN_BID:
        raise HTTPException(400, f"Минимальная ставка: {AUCTION_MIN_BID} 🪙.")

    async with db.execute(
        "SELECT species_id, COALESCE(pet_level, 1), placement "
        "FROM pets WHERE id = ? AND owner_id = ?",
        (body.pet_id, user["id"]),
    ) as c:
        row = await c.fetchone()
    if not row:
        raise HTTPException(400, "Питомец не найден.")
    if row[2] != "storage":
        raise HTTPException(400, "Выставить можно только питомца со склада — убери его из слотов питомника.")

    sp = PET_SPECIES.get(row[0], {})
    item_name = f"{sp.get('name', row[0])} Lv{row[1]}"

    ok, result, applied = await create_auction_lot(
        db, user["id"], "pets", "pet", body.pet_id, 1, item_name,
        body.min_bid, body.buyout,
        idempotency_key=_economic_key(request_key, "auction-pet-listing"),
    )
    if not ok:
        raise HTTPException(400, str(result))

    await db.commit()
    if applied:
        queue_lot_announcement(result)
    return {"ok": True, "lot_id": result, "replayed": not applied}


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
    result = await place_bid(
        db, body.lot_id, user["id"], body.amount,
        idempotency_key=_economic_key(request_key, "auction-bid"),
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Ошибка ставки."))

    await db.commit()

    # R5 «Молот Аукциона»: live-событие зрителям комнаты лота. Ставки из БОТА
    # сюда не попадают (WS-хаб живёт в веб-процессе) — комната дополнительно
    # опирается на серверный remaining_sec при каждом событии.
    if result.get("applied"):
        try:
            from FastAPI.notifications import broadcast_lot, lot_viewers
            async with db.execute(
                "SELECT CAST(EXTRACT(EPOCH FROM (ends_at - NOW())) AS BIGINT) "
                "FROM auction_lots WHERE id = ?", (body.lot_id,),
            ) as c:
                _rem_row = await c.fetchone()
            await broadcast_lot(body.lot_id, {
                "type": "lot_bid",
                "lot_id": body.lot_id,
                "amount": float(result.get("amount", body.amount)),
                "bidder_name": user.get("username") or "Игрок",
                "remaining_sec": int(_rem_row[0]) if _rem_row and _rem_row[0] is not None else 0,
                "extended": bool(result.get("extended")),
                "is_buyout": bool(result.get("is_buyout")),
                "viewers": lot_viewers(body.lot_id),
            })
        except Exception:
            pass  # live-комната не должна ломать саму ставку

    # Quest & achievement tracking (same as bot handler does)
    try:
        from services.quests import increment_metric as _q_incr
        # Get user's primary chat_id for quest context (use any active chat)
        async with db.execute(
            "SELECT chat_tg_id FROM user_chat_stats WHERE user_tg_id = ? "
            "ORDER BY user_messages_count_all_time DESC LIMIT 1",
            (user["id"],),
        ) as c:
            _chat_row = await c.fetchone()
        if _chat_row and result.get("applied"):
            await _q_incr(db, user["id"], _chat_row[0], "auction_bids_today", delta=1.0)
            await db.commit()
    except Exception:
        pass

    return {
        "ok": True,
        "is_buyout": result.get("is_buyout", False),
        "amount": result.get("amount", body.amount),
        "replayed": not result.get("applied", True),
        "commission_pct": AUCTION_COMMISSION * 100,
    }
