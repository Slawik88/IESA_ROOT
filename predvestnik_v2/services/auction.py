"""
services/auction.py
Business logic for the global auction system.
Чистые функции без bot/FastAPI-импортов на верхнем уровне. Единственное
исключение — flush_pending_announcements(bot, db): шлёт дайджест новых лотов,
поэтому ленивый import aiogram.types только внутри неё (та же граница, что
уже допускает services/scheduler.py для проактивных уведомлений).
"""
import asyncio
import hashlib
import json
import math
import os
from datetime import datetime, timezone, timedelta

from core.constants import (
    AUCTION_DURATION_HOURS, AUCTION_MAX_ACTIVE_LOTS, AUCTION_MAX_LOTS_PER_WEEK,
    AUCTION_MIN_BID, AUCTION_MIN_BID_RAISE, AUCTION_COMMISSION, AUCTION_MAX_BID,
    AUCTION_LISTING_FEE, AUCTION_ANTISNIPE_WINDOW_SEC, AUCTION_ANTISNIPE_EXTEND_SEC,
    AUCTION_MAX_EXTENSION_SEC,
)
from core.registry import ITEMS_REGISTRY as _ITEMS_REGISTRY
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.economy_ledger import find_reference_replay
from infrastructure.repositories.auction import (
    create_lot, get_lot, update_lot_status, get_highest_bid, get_user_active_bid,
    deactivate_bid, insert_bid, count_seller_active, get_weekly_count,
    incr_weekly_count, add_reserve, remove_reserve, get_reserve,
    get_bid_by_request,
)
from infrastructure.repositories.routing import get_announce_chats


def _week_start() -> str:
    today = datetime.now(timezone.utc)
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")


def _ends_at_str() -> str:
    ends = datetime.now(timezone.utc) + timedelta(hours=AUCTION_DURATION_HOURS)
    return ends.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_mora(v) -> str:
    """Float-формат моры для анонсов: разделители тысяч + до 2 знаков без хвостовых нулей."""
    s = f"{float(v or 0):,.2f}".replace(",", " ")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


# ── Анонс новых лотов: дайджест вместо спама ────────────────────────────────
# Раньше каждый созданный лот сразу же летел отдельным сообщением во ВСЕ основные
# чаты — если 10 продавцов за минуту выставляли по 5 предметов, чаты получали
# 50 сообщений подряд. Теперь лоты копятся в памяти процесса (single-process —
# бот и веб делят один event loop) и раз в минуту (тик duel_and_auction_task)
# улетают ОДНИМ сообщением: 1 лот — подробная карточка как раньше, 2+ — компактный
# дайджест-список. queue_lot_announcement() — неблокирующий, без БД/IO.
_pending_lot_ids: list[int] = []


def queue_lot_announcement(lot_id: int) -> None:
    """Поставить лот в очередь анонса (разгрузка — реальная отправка батчем, см. flush_pending_announcements)."""
    _pending_lot_ids.append(lot_id)


def _take_pending_lot_ids() -> list[int]:
    ids = _pending_lot_ids[:]
    _pending_lot_ids.clear()
    return ids


def build_lots_digest(lots: list[dict], bot_username: str = "") -> tuple[str, dict | None]:
    """Компактный дайджест 2+ лотов одним сообщением (вместо отдельного на каждый)."""
    _MAX_LINES = 10
    lines = [f"🔨 <b>{len(lots)} новых лотов на аукционе!</b>"]
    for lot in lots[:_MAX_LINES]:
        name = (lot.get("item_name") or "Лот").split("||")[0]
        qty = lot.get("quantity") or 1
        is_pet = lot.get("item_type") == "pet"
        icon = "🐾" if is_pet else "📦"
        qty_part = f" ×{qty}" if (qty and qty > 1 and not is_pet) else ""
        buyout_part = f" · выкуп {_fmt_mora(lot.get('buyout'))}🪙" if lot.get("buyout") else ""
        lines.append(f"{icon} {name}{qty_part} — от {_fmt_mora(lot.get('min_bid'))}🪙{buyout_part}")
    if len(lots) > _MAX_LINES:
        lines.append(f"…и ещё {len(lots) - _MAX_LINES}.")
    lines.append("⏳ Загляни во вкладку «Аукцион», чтобы сделать ставку!")
    text = "\n".join(lines)
    markup = None
    if bot_username:
        url = f"https://t.me/{bot_username}?startapp=auction"
        markup = {"inline_keyboard": [[{"text": "🔨 Открыть аукцион", "url": url}]]}
    return text, markup


async def flush_pending_announcements(bot, db) -> None:
    """Вызывается раз в минуту (duel_and_auction_task) — отправляет ОДНО сообщение
    на все основные чаты со всеми лотами, накопленными за последнюю минуту."""
    ids = _take_pending_lot_ids()
    if not ids:
        return
    bot_username = os.getenv("BOT_USERNAME", "")
    lots = []
    seen = set()
    for lid in ids:
        if lid in seen:
            continue
        seen.add(lid)
        lot = await get_lot(db, lid)
        if lot:
            lots.append(lot)
    if not lots:
        return
    chats = await get_announce_chats(db)
    if not chats:
        return
    if len(lots) == 1:
        text, markup = build_lot_announcement(lots[0], bot_username)
    else:
        text, markup = build_lots_digest(lots, bot_username)
    # build_lot*() отдают чистый dict (без bot-импортов, см. их docstring) —
    # aiogram Bot.send_message() ждёт типизированный объект, конвертируем здесь,
    # на единственной границе, где services/ реально говорит с aiogram.
    reply_markup = None
    if markup:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=b["text"], url=b["url"]) for b in row]
            for row in markup["inline_keyboard"]
        ])
    from infrastructure.repositories.moderation import chat_notif_enabled
    for cid in chats:
        # Категорийный тумблер игровых уведомлений (бот настройки чата → 🔔)
        if not await chat_notif_enabled(db, cid, "notif_auction"):
            continue
        try:
            await bot.send_message(cid, text, parse_mode="HTML",
                                   disable_web_page_preview=True, reply_markup=reply_markup)
        except Exception:
            pass
        await asyncio.sleep(0.05)


def build_lot_announcement(lot: dict, bot_username: str = "") -> tuple[str, dict | None]:
    """Текст + inline-клавиатура анонса нового лота для основных чатов.
    Чистое форматирование (без доставки/bot-импортов). reply_markup=None без bot_username."""
    name = (lot.get("item_name") or "Лот").split("||")[0]
    qty = lot.get("quantity") or 1
    is_pet = lot.get("item_type") == "pet"
    icon = "🐾" if is_pet else "📦"
    lines = [
        "🔨 <b>Новый лот на аукционе!</b>",
        f"{icon} <b>{name}</b>" + (f" ×{qty}" if (qty and qty > 1 and not is_pet) else ""),
        f"💰 Старт: <b>{_fmt_mora(lot.get('min_bid'))}</b> 🪙",
    ]
    if lot.get("buyout"):
        lines.append(f"⚡ Мгновенный выкуп: <b>{_fmt_mora(lot.get('buyout'))}</b> 🪙")
    lines.append(f"⏳ Идёт {AUCTION_DURATION_HOURS} ч · успей сделать ставку во вкладке «Аукцион»!")
    text = "\n".join(lines)
    markup = None
    if bot_username:
        url = f"https://t.me/{bot_username}?startapp=auction_{lot.get('id', '')}"
        markup = {"inline_keyboard": [[{"text": "🔨 Открыть аукцион", "url": url}]]}
    return text, markup


async def _restore_asset_escrow(db, lot: dict) -> None:
    """Return an unsold pet or inventory item to its seller exactly once.

    The lot row is locked by callers before this runs.  Older code restored
    pets only, so cancelling or expiring an inventory lot silently destroyed
    the listed item.
    """
    if lot.get("item_type") == "pet":
        await db.execute(
            "UPDATE pets SET placement = 'storage' WHERE id = ? AND owner_id = ?",
            (lot["item_id_or_pet_id"], lot["seller_id"]),
        )
    elif lot.get("item_type") == "inventory":
        parts = (lot.get("item_name") or "").split("||", 1)
        if len(parts) != 2 or not parts[1].strip():
            raise RuntimeError(f"Лот {lot['id']} не содержит идентификатор предмета эскроу.")
        item_id = parts[1].strip()
        quantity = int(lot.get("quantity") or 1)
        await db.execute(
            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
            (lot["seller_id"], item_id, quantity, quantity),
        )


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
    idempotency_key: str | None = None,
) -> tuple[bool, int | str, bool]:
    """Atomically escrow an asset, charge the fee and create a lot.

    The third return value is ``applied``.  It is false for an exact retry, so
    callers do not send a duplicate announcement or repeat quest progress.
    """
    if quantity <= 0:
        return False, "Количество должно быть больше нуля.", False
    if not math.isfinite(float(min_bid)) or min_bid < AUCTION_MIN_BID:
        return False, f"Минимальная ставка: {AUCTION_MIN_BID:.0f} 🪙.", False
    if min_bid > AUCTION_MAX_BID:
        return False, f"Минимальная ставка не может превышать {AUCTION_MAX_BID:,.0f} 🪙.".replace(",", " "), False
    if buyout is not None:
        if not math.isfinite(float(buyout)):
            return False, "Цена выкупа указана неверно.", False
        if buyout < min_bid:
            return False, "Цена выкупа не может быть ниже минимальной ставки.", False
        if buyout > AUCTION_MAX_BID:
            return False, f"Цена выкупа не может превышать {AUCTION_MAX_BID:,.0f} 🪙.".replace(",", " "), False

    week = _week_start()
    listing_fee = max(1.0, round(min_bid * AUCTION_LISTING_FEE, 2))
    request_payload = {
        "seller_id": seller_id,
        "category": category,
        "item_type": item_type,
        "item_id": item_id_or_pet_id,
        "quantity": quantity,
        "item_name": item_name,
        "min_bid": round(float(min_bid), 2),
        "buyout": round(float(buyout), 2) if buyout is not None else None,
        "week": week,
    }
    reference_id = hashlib.sha256(
        json.dumps(request_payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()

    try:
        async with eco_repo.atomic(db, seller_id):
            replay = None
            if idempotency_key:
                replay = await find_reference_replay(
                    db, seller_id,
                    reason_code="auction_listing_fee",
                    idempotency_key=idempotency_key,
                    source_type="auction",
                    reference_type="listing_request",
                    reference_id=reference_id,
                )
            if replay:
                async with db.execute(
                    "SELECT id FROM auction_lots WHERE listing_operation_id = ?",
                    (replay.operation_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                if not row:
                    raise RuntimeError("Повтор операции найден, но связанный лот отсутствует.")
                return True, int(row[0]), False

            active_count = await count_seller_active(db, seller_id)
            if active_count >= AUCTION_MAX_ACTIVE_LOTS:
                return False, f"Максимум {AUCTION_MAX_ACTIVE_LOTS} активных лотов одновременно.", False
            weekly = await get_weekly_count(db, seller_id, week)
            if weekly >= AUCTION_MAX_LOTS_PER_WEEK:
                return False, f"Превышен лимит {AUCTION_MAX_LOTS_PER_WEEK} лотов в неделю.", False

            if item_type == "inventory":
                parts = (item_name or "").split("||", 1)
                if len(parts) != 2 or not parts[1].strip():
                    return False, "Не удалось определить предмет для эскроу.", False
                real_item_id = parts[1].strip()
                async with db.execute(
                    "UPDATE inventory SET quantity = quantity - ? "
                    "WHERE user_id = ? AND item_id = ? AND quantity >= ? RETURNING quantity",
                    (quantity, seller_id, real_item_id, quantity),
                ) as cursor:
                    claimed = await cursor.fetchone()
                if not claimed:
                    return False, "Недостаточно предметов в инвентаре.", False
                await db.execute(
                    "DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0",
                    (seller_id, real_item_id),
                )
            elif item_type == "pet":
                async with db.execute(
                    "UPDATE pets SET placement = 'auction' "
                    "WHERE id = ? AND owner_id = ? AND placement = 'storage' RETURNING id",
                    (item_id_or_pet_id, seller_id),
                ) as cursor:
                    claimed = await cursor.fetchone()
                if not claimed:
                    return False, "Питомец уже не на складе или недоступен.", False
            else:
                return False, "Этот тип лота не поддерживается.", False

            mutation = await eco_repo.add_balance(
                db, seller_id, mora=-listing_fee,
                source="auction_listing_fee",
                source_type="auction",
                idempotency_key=idempotency_key,
                reference_type="listing_request",
                reference_id=reference_id,
                metadata=request_payload,
                note=f"Листинг-сбор за лот «{item_name.split('||')[0]}»",
            )
            lot_id = await create_lot(
                db, seller_id, category, item_type, item_id_or_pet_id,
                quantity, item_name, min_bid, buyout, _ends_at_str(),
                mutation.operation_id if mutation else None,
            )
            await incr_weekly_count(db, seller_id, week)
        return True, lot_id, True
    except InsufficientBalance:
        fee_s = f"{listing_fee:,.2f}".replace(",", " ").rstrip("0").rstrip(".")
        return False, f"Нужно {fee_s} 🪙 на комиссию за размещение.", False
    except IdempotencyConflict:
        return False, "Этот запрос уже использован для другого лота.", False
    except Exception:
        return False, "Не удалось выставить лот. Попробуй ещё раз.", False


async def place_bid(
    db,
    lot_id: int,
    bidder_id: int,
    amount: float,
    chat_id: int | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Place or raise a bid.
    Returns: {"ok": bool, "error": str|None,
              "outbid_user_id": int|None, "outbid_amount": float,
              "is_buyout": bool}
    """
    if not math.isfinite(float(amount)) or amount <= 0:
        return {"ok": False, "error": "Сумма ставки указана неверно."}
    if amount > AUCTION_MAX_BID:
        return {"ok": False, "error": f"Максимальная ставка — {int(AUCTION_MAX_BID):,} 🪙.".replace(",", " ")}

    outbid_user_id = None
    outbid_amount = 0.0
    is_buyout = False

    async with db.connection.transaction():
        # One lock serializes every bid/finalization for this lot.  Previously
        # ``highest`` was read before the transaction and two bidders could both
        # become active leaders while only one reserve was coherent.
        async with db.execute(
            "SELECT * FROM auction_lots WHERE id = ? FOR UPDATE", (lot_id,)
        ) as cursor:
            lot_row = await cursor.fetchone()
        lot = dict(lot_row) if lot_row else None
        if not lot:
            return {"ok": False, "error": "Лот не найден."}

        effective_amount = float(amount)
        if lot.get("buyout") is not None and effective_amount >= float(lot["buyout"]):
            effective_amount = float(lot["buyout"])

        if idempotency_key:
            replay = await get_bid_by_request(db, bidder_id, idempotency_key)
            if replay:
                if int(replay["lot_id"]) != int(lot_id) or abs(float(replay["amount"]) - effective_amount) > 0.000001:
                    return {"ok": False, "error": "Этот запрос уже использован для другой ставки."}
                return {
                    "ok": True, "error": None, "outbid_user_id": None,
                    "outbid_amount": 0.0, "is_buyout": lot["status"] == "sold",
                    "extended": False, "lot": lot, "amount": float(replay["amount"]),
                    "applied": False,
                }

        if lot["status"] != "active":
            return {"ok": False, "error": "Лот уже закрыт."}
        ends = lot["ends_at"]
        if isinstance(ends, str):
            ends = datetime.strptime(ends, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        elif isinstance(ends, datetime) and ends.tzinfo is None:
            ends = ends.replace(tzinfo=timezone.utc)
        if ends <= datetime.now(timezone.utc):
            return {"ok": False, "error": "Аукцион истёк."}
        if bidder_id == lot["seller_id"]:
            return {"ok": False, "error": "Нельзя ставить на свой лот."}

        highest = await get_highest_bid(db, lot_id)
        min_required = (
            max(float(lot["min_bid"]), float(highest["amount"]) * (1 + AUCTION_MIN_BID_RAISE))
            if highest else float(lot["min_bid"])
        )
        if effective_amount < min_required:
            return {"ok": False, "error": f"Ставка должна быть ≥ {min_required:.0f} 🪙."}

        async with db.execute(
            "SELECT user_balance_mora FROM users WHERE user_tg_id = ? FOR UPDATE",
            (bidder_id,),
        ) as _c:
            _bal_row = await _c.fetchone()
        bal_mora = float(_bal_row[0]) if _bal_row else 0.0

        already_reserved = await get_reserve(db, bidder_id)
        own_bid = await get_user_active_bid(db, lot_id, bidder_id)
        own_bid_amount = own_bid["amount"] if own_bid else 0.0
        free_balance = bal_mora - already_reserved + own_bid_amount

        if free_balance < effective_amount:
            return {"ok": False, "error": f"Недостаточно Моры (нужно {effective_amount:.0f}, свободно {free_balance:.0f})."}

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
        await insert_bid(db, lot_id, bidder_id, effective_amount, idempotency_key)
        await add_reserve(db, bidder_id, effective_amount)

        # Buyout?
        is_buyout = lot.get("buyout") is not None and effective_amount >= float(lot["buyout"])
        if is_buyout:
            await _finalize_lot(db, lot, bidder_id, effective_amount, chat_id)

        # R5 «Молот Аукциона»: анти-снайп — ставка в последние 60с продлевает лот
        # на +60с (война ставок заканчивается только когда кто-то сдался, а не
        # «кто последний кликнул»). Суммарное продление капается 30 минутами.
        extended = False
        if not is_buyout:
            _remaining = (ends - datetime.now(timezone.utc)).total_seconds()
            if 0 < _remaining <= AUCTION_ANTISNIPE_WINDOW_SEC:
                _already = int(lot.get("extended_sec") or 0)
                if _already < AUCTION_MAX_EXTENSION_SEC:
                    await db.execute(
                        "UPDATE auction_lots SET "
                        "ends_at = ends_at + INTERVAL '1 second' * ?, "
                        "extended_sec = COALESCE(extended_sec, 0) + ? "
                        "WHERE id = ?",
                        (AUCTION_ANTISNIPE_EXTEND_SEC, AUCTION_ANTISNIPE_EXTEND_SEC, lot_id),
                    )
                    extended = True

    return {
        "ok": True,
        "error": None,
        "outbid_user_id": outbid_user_id,
        "outbid_amount": outbid_amount,
        "is_buyout": is_buyout,
        "extended": extended,
        "lot": lot,
        "amount": effective_amount,
        "applied": True,
    }


async def resolve_lot(db, lot_id: int) -> dict:
    """Resolve an expired lot. Returns info dict for notifications.
    Caller must send messages."""
    async with db.connection.transaction():
        async with db.execute(
            "SELECT * FROM auction_lots WHERE id = ? FOR UPDATE", (lot_id,)
        ) as cursor:
            row = await cursor.fetchone()
        lot = dict(row) if row else None
        if not lot or lot["status"] != "active":
            return {}
        highest = await get_highest_bid(db, lot_id)
        if highest:
            await _finalize_lot(db, lot, highest["bidder_id"], highest["amount"])
            result = {
                "status": "sold", "lot": lot,
                "winner_id": highest["bidder_id"], "final_price": highest["amount"],
            }
        else:
            await _restore_asset_escrow(db, lot)
            await update_lot_status(db, lot_id, "expired")
            result = {"status": "expired", "lot": lot, "winner_id": None}
    return result


async def cancel_lot(db, lot_id: int, user_id: int) -> tuple[bool, str]:
    async with db.connection.transaction():
        async with db.execute(
            "SELECT * FROM auction_lots WHERE id = ? FOR UPDATE", (lot_id,)
        ) as cursor:
            row = await cursor.fetchone()
        lot = dict(row) if row else None
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

        await _restore_asset_escrow(db, lot)
        await update_lot_status(db, lot_id, "cancelled")
    return True, "Лот отменён."


async def _finalize_lot(db, lot: dict, winner_id: int, price: float, chat_id: int | None = None):
    """Transfer item to winner, transfer mora (minus commission) to seller."""
    commission = round(price * AUCTION_COMMISSION, 2)
    seller_gain = round(price - commission, 2)

    # Unreserve winner's mora
    await remove_reserve(db, winner_id, price)

    # Deduct from winner
    await eco_repo.add_balance(db, winner_id, mora=-price, commit=False,
                               source="auction_buy", source_type="auction",
                               idempotency_key=f"auction-settle:{lot['id']}:buyer",
                               reference_type="auction_lot", reference_id=lot["id"],
                               note=f"lot={lot['id']}")

    # Give seller their cut
    await eco_repo.add_balance(db, lot["seller_id"], mora=seller_gain, commit=False,
                               source="auction_sale", source_type="auction",
                               idempotency_key=f"auction-settle:{lot['id']}:seller",
                               reference_type="auction_lot", reference_id=lot["id"],
                               metadata={"gross": price, "commission": commission},
                               note=f"lot={lot['id']}")

    # Transfer item to winner.
    # item_name is stored as "Display Name||real_item_id" by both bot and FastAPI handlers.
    # item_id_or_pet_id is a hash of the string id (numeric) — NOT the real id.
    # Always extract real item_id from item_name to avoid storing numeric hashes in inventory.
    if lot["item_type"] == "inventory":
        raw_name = lot.get("item_name", "") or ""
        parts = raw_name.split("||", 1)
        if len(parts) > 1:
            real_item_id = parts[1].strip()
        else:
            # Fallback: find item whose hash matches item_id_or_pet_id (legacy lots without || suffix)
            numeric_id = lot["item_id_or_pet_id"]
            real_item_id = next(
                (iid for iid in _ITEMS_REGISTRY if abs(hash(iid)) % (10 ** 9) == numeric_id),
                str(numeric_id),
            )
        await db.execute(
            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
            (winner_id, real_item_id, lot["quantity"], lot["quantity"]),
        )
    elif lot["item_type"] == "pet":
        await db.execute(
            "UPDATE pets SET owner_id = ?, placement = 'storage' WHERE id = ?",
            (winner_id, lot["item_id_or_pet_id"]),
        )

    await update_lot_status(db, lot["id"], "sold")
