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
    """Retired: no new asset escrow or monetary availability holds."""
    return False, "Старый аукцион закрыт.", False


async def place_bid(
    db,
    lot_id: int,
    bidder_id: int,
    amount: float,
    chat_id: int | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Retired on every adapter, including old bot callbacks."""
    return {"ok": False, "error": "Старый аукцион закрыт."}


async def resolve_lot(db, lot_id: int) -> dict:
    """No automatic legacy settlement; the reviewed operator migration owns it."""
    return {}


async def cancel_lot(db, lot_id: int, user_id: int) -> tuple[bool, str]:
    """Do not bypass the operator migration's partial-settlement checks."""
    return False, "Старый аукцион закрыт. Незавершённые лоты урегулируются автоматически."


async def _finalize_lot(db, lot: dict, winner_id: int, price: float, chat_id: int | None = None):
    """Retired settlement boundary; retained to reject stale internal callers."""
    raise RuntimeError("Legacy auction settlement is retired")
