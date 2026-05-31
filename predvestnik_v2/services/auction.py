"""
services/auction.py
Business logic for the global auction system.
No bot imports — callers handle notifications.
"""
from datetime import datetime, timezone, timedelta

from core.constants import (
    AUCTION_DURATION_HOURS, AUCTION_MAX_ACTIVE_LOTS, AUCTION_MAX_LOTS_PER_WEEK,
    AUCTION_MIN_BID, AUCTION_MIN_BID_RAISE, AUCTION_COMMISSION, AUCTION_MAX_BID,
)
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.auction import (
    create_lot, get_lot, update_lot_status, get_highest_bid, get_user_active_bid,
    deactivate_bid, insert_bid, count_seller_active, get_weekly_count,
    incr_weekly_count, add_reserve, remove_reserve, get_reserve,
)


def _week_start() -> str:
    today = datetime.now(timezone.utc)
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")


def _ends_at_str() -> str:
    ends = datetime.now(timezone.utc) + timedelta(hours=AUCTION_DURATION_HOURS)
    return ends.strftime("%Y-%m-%d %H:%M:%S")


async def create_auction_lot(
    db,
    seller_id: int,
    category: str,
    item_type: str,
    item_id_or_pet_id: int,
    quantity: int,
    item_name: str,
    min_bid: float,
    buyout: float | None,
) -> tuple[bool, int | str]:
    """Create a new lot. Returns (True, lot_id) or (False, error_str)."""
    if count_seller := await count_seller_active(db, seller_id):
        if count_seller >= AUCTION_MAX_ACTIVE_LOTS:
            return False, f"Максимум {AUCTION_MAX_ACTIVE_LOTS} активных лотов одновременно."

    week = _week_start()
    weekly = await get_weekly_count(db, seller_id, week)
    if weekly >= AUCTION_MAX_LOTS_PER_WEEK:
        return False, f"Превышен лимит {AUCTION_MAX_LOTS_PER_WEEK} лотов в неделю."

    if min_bid < AUCTION_MIN_BID:
        min_bid = AUCTION_MIN_BID
    if min_bid > AUCTION_MAX_BID:
        return False, f"Минимальная ставка не может превышать {AUCTION_MAX_BID:,.0f} 🪙.".replace(",", " ")

    if buyout is not None and buyout > AUCTION_MAX_BID:
        buyout = AUCTION_MAX_BID

    lot_id = await create_lot(
        db, seller_id, category, item_type, item_id_or_pet_id,
        quantity, item_name, min_bid, buyout, _ends_at_str(),
    )
    await incr_weekly_count(db, seller_id, week)
    await db.commit()
    return True, lot_id


async def place_bid(
    db,
    lot_id: int,
    bidder_id: int,
    amount: float,
    chat_id: int | None = None,
) -> dict:
    """Place or raise a bid.
    Returns: {"ok": bool, "error": str|None,
              "outbid_user_id": int|None, "outbid_amount": float,
              "is_buyout": bool}
    """
    lot = await get_lot(db, lot_id)
    if not lot or lot["status"] != "active":
        return {"ok": False, "error": "Лот не найден или уже закрыт."}

    ends = lot["ends_at"]
    if isinstance(ends, str):
        ends = datetime.strptime(ends, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    elif ends.tzinfo is None:
        ends = ends.replace(tzinfo=timezone.utc)
    if ends <= datetime.now(timezone.utc):
        return {"ok": False, "error": "Аукцион истёк."}

    if bidder_id == lot["seller_id"]:
        return {"ok": False, "error": "Нельзя ставить на свой лот."}

    # Minimum raise
    highest = await get_highest_bid(db, lot_id)
    current_high = highest["amount"] if highest else (lot["min_bid"] - 0.01)
    min_required = max(lot["min_bid"], current_high * (1 + AUCTION_MIN_BID_RAISE))
    if amount < min_required:
        return {"ok": False, "error": f"Ставка должна быть ≥ {min_required:.0f} 🪙."}
    if amount > AUCTION_MAX_BID:
        return {"ok": False, "error": f"Максимальная ставка — {int(AUCTION_MAX_BID):,} 🪙.".replace(",", " ")}

    # Check free balance
    bal = await eco_repo.get_balance(db, bidder_id)
    already_reserved = await get_reserve(db, bidder_id)
    # Subtract the bidder's own current bid on THIS lot to get truly free balance
    own_bid = await get_user_active_bid(db, lot_id, bidder_id)
    own_bid_amount = own_bid["amount"] if own_bid else 0.0
    free_balance = bal["user_balance_mora"] - already_reserved + own_bid_amount

    if free_balance < amount:
        return {"ok": False, "error": f"Недостаточно Моры (нужно {amount:.0f}, свободно {free_balance:.0f})."}

    outbid_user_id = None
    outbid_amount = 0.0

    # Deactivate previous highest bid (if from different user)
    if highest and highest["bidder_id"] != bidder_id:
        outbid_user_id = highest["bidder_id"]
        outbid_amount = highest["amount"]
        await deactivate_bid(db, highest["id"])
        await remove_reserve(db, outbid_user_id, outbid_amount)

    # Deactivate own old bid on this lot
    if own_bid:
        await deactivate_bid(db, own_bid["id"])
        await remove_reserve(db, bidder_id, own_bid_amount)

    # Insert new bid + reserve
    await insert_bid(db, lot_id, bidder_id, amount)
    await add_reserve(db, bidder_id, amount)

    # Buyout?
    is_buyout = lot.get("buyout") is not None and amount >= lot["buyout"]
    if is_buyout:
        await _finalize_lot(db, lot, bidder_id, amount, chat_id)

    await db.commit()

    return {
        "ok": True,
        "error": None,
        "outbid_user_id": outbid_user_id,
        "outbid_amount": outbid_amount,
        "is_buyout": is_buyout,
        "lot": lot,
    }


async def resolve_lot(db, lot_id: int) -> dict:
    """Resolve an expired lot. Returns info dict for notifications.
    Caller must send messages."""
    lot = await get_lot(db, lot_id)
    if not lot or lot["status"] != "active":
        return {}

    highest = await get_highest_bid(db, lot_id)

    if highest:
        await _finalize_lot(db, lot, highest["bidder_id"], highest["amount"])
        await db.commit()
        return {
            "status": "sold",
            "lot": lot,
            "winner_id": highest["bidder_id"],
            "final_price": highest["amount"],
        }
    else:
        await update_lot_status(db, lot_id, "expired")
        await db.commit()
        return {"status": "expired", "lot": lot, "winner_id": None}


async def cancel_lot(db, lot_id: int, user_id: int) -> tuple[bool, str]:
    lot = await get_lot(db, lot_id)
    if not lot:
        return False, "Лот не найден."
    if lot["seller_id"] != user_id:
        return False, "Это не ваш лот."
    if lot["status"] != "active":
        return False, "Лот уже закрыт."

    highest = await get_highest_bid(db, lot_id)
    if highest:
        await deactivate_bid(db, highest["id"])
        await remove_reserve(db, highest["bidder_id"], highest["amount"])

    await update_lot_status(db, lot_id, "cancelled")
    await db.commit()
    return True, "Лот отменён."


async def _finalize_lot(db, lot: dict, winner_id: int, price: float, chat_id: int | None = None):
    """Transfer item to winner, transfer mora (minus commission) to seller."""
    commission = price * AUCTION_COMMISSION
    seller_gain = price - commission

    # Unreserve winner's mora
    await remove_reserve(db, winner_id, price)

    # Deduct from winner
    await eco_repo.add_balance(db, winner_id, mora=-price, commit=False,
                               source="auction_buy", note=f"lot={lot['id']}")

    # Give seller their cut
    await eco_repo.add_balance(db, lot["seller_id"], mora=seller_gain, commit=False,
                               source="auction_sale", note=f"lot={lot['id']}")

    # Transfer item to winner
    if lot["item_type"] == "inventory":
        await db.execute(
            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + ?",
            (winner_id, str(lot["item_id_or_pet_id"]), lot["quantity"], lot["quantity"]),
        )
    elif lot["item_type"] == "pet":
        await db.execute(
            "UPDATE pets SET owner_id = ?, placement = 'storage' WHERE id = ?",
            (winner_id, lot["item_id_or_pet_id"]),
        )

    await update_lot_status(db, lot["id"], "sold")
