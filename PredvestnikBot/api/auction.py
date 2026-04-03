# api/auction.py — Аукцион: полная логика
# Таблицы: auctions, auction_bids (созданы в db.py::init_db)
# Все функции async; вызываются из handlers/auction.py и miniapp_views.py
#
# Edge cases handled:
#  1. Предмет не в инвентаре продавца
#  2. Предмет экипирован — автоматически снимается при выставлении
#  3. Предмет уже на аукционе (проверка по item_id + status='active')
#  4. Повторная ставка от продавца — заблокировано
#  5. Ставка ниже минимума (current + 10%, не менее 5)
#  6. Недостаточно моры — валидация перед списанием
#  7. Перебитая ставка — возврат предыдущему участнику
#  8. Аукцион истёк без ставок — возврат предмета продавцу
#  9. Аукцион истёк со ставками — передача предмета победителю, мора продавцу минус 10%
# 10. Мгновенный выкуп — немедленная передача, минус 10% комиссия в казну
# 11. Отмена продавцом: без ставок — свободна, со ставками — возврат ставки и предмета
# 12. Минимальный инкремент ставки: max(5, current * 10%)
# 13. Race condition — FOR UPDATE lock на строке аукциона
# 14. Предмет удалён до финализации — аукцион завершается с возвратом
# 15. Продавец/покупатель вышел — обрабатывается gracefully
# 16. Достижения за первую продажу/выигрыш

from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from database.db import postgres_connect

logger = logging.getLogger(__name__)

AUCTION_DURATION_HOURS = 24        # Срок аукциона
COMMISSION_RATE        = 0.10      # 10% комиссия при продаже
MIN_START_PRICE        = 10        # Минимальная стартовая цена
MAX_ACTIVE_PER_USER    = 3         # Максимум активных лотов у одного продавца

# ─── Вспомогательные ──────────────────────────────────────────────────────────

def _min_increment(current_price: int) -> int:
    return max(5, int(current_price * 0.10))


async def _get_item(db, item_id: int, user_id: int, chat_id: int) -> dict | None:
    """Получить предмет из инвентаря, принадлежащий пользователю."""
    row = await db.fetchone(
        "SELECT * FROM gacha_inventory WHERE id=? AND user_id=?",
        (item_id, user_id)
    )
    return dict(row) if row else None


# ─── Вспомогательные: косметика ───────────────────────────────────────────────

def _parse_cosmetic_key(item_key: str) -> tuple[str, str]:
    """Разобрать 'frame:warrior' → ('frame', 'warrior')."""
    parts = item_key.split(":", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", item_key)


async def _user_owns_cosmetic(db, item_key: str, user_id: int, chat_id: int) -> bool:
    """Проверить что косметика принадлежит пользователю."""
    ctype, ckey = _parse_cosmetic_key(item_key)
    if ctype in ("frame", "cosmetic"):
        row = await db.fetchone(
            "SELECT id FROM shop_items WHERE user_id=? AND item_type=? AND item_value=? LIMIT 1",
            (user_id, ctype, ckey)
        )
        return row is not None
    elif ctype == "theme":
        row = await db.fetchone(
            "SELECT theme_key FROM user_themes WHERE user_id=? AND theme_key=?",
            (user_id, ckey)
        )
        return row is not None
    return False


async def _transfer_cosmetic_to_user(db, item_key: str, to_user_id: int, chat_id: int) -> None:
    """Передать косметику пользователю."""
    from database.db import postgres_connect as _pg  # noqa
    ctype, ckey = _parse_cosmetic_key(item_key)
    if ctype in ("frame", "cosmetic"):
        await db.execute(
            "INSERT INTO shop_items (user_id, chat_id, item_type, item_value, purchased_at, active)"
            " VALUES (?, 0, ?, ?, NOW(), 1)",
            (to_user_id, ctype, ckey)
        )
    elif ctype == "theme":
        await db.execute(
            "INSERT INTO user_themes (user_id, chat_id, theme_key, source, obtained_at)"
            " SELECT ?, 0, ?, 'auction', NOW()"
            " WHERE NOT EXISTS (SELECT 1 FROM user_themes WHERE user_id=? AND theme_key=?)",
            (to_user_id, ckey, to_user_id, ckey)
        )


async def _revoke_cosmetic_from_user(db, item_key: str, from_user_id: int, chat_id: int) -> None:
    """Отозвать косметику у пользователя (удалить одну запись)."""
    ctype, ckey = _parse_cosmetic_key(item_key)
    if ctype in ("frame", "cosmetic"):
        await db.execute(
            "DELETE FROM shop_items WHERE id = ("
            "  SELECT id FROM shop_items WHERE user_id=? AND item_type=? AND item_value=?"
            "  ORDER BY id LIMIT 1"
            ")",
            (from_user_id, ctype, ckey)
        )
    elif ctype == "theme":
        await db.execute(
            "DELETE FROM user_themes WHERE user_id=? AND theme_key=?",
            (from_user_id, ckey)
        )


# ─── Создание аукциона (косметика) ────────────────────────────────────────────

COSMETIC_RARITY_MAP = {"theme": "rare", "frame": "common", "cosmetic": "rare"}
COSMETIC_EMOJI_MAP  = {"theme": "🎨", "frame": "🖼", "cosmetic": "✨"}


async def create_cosmetic_auction(
    seller_id: int,
    chat_id: int,
    item_key: str,
    item_name: str,
    start_price: int,
    buyout_price: Optional[int] = None,
) -> dict:
    """
    Выставить косметику на аукцион.
    item_key формат: 'frame:warrior', 'cosmetic:name_glow', 'theme:fire'
    """
    if start_price < MIN_START_PRICE:
        raise ValueError(f"Минимальная стартовая цена: {MIN_START_PRICE} 🪙")
    if buyout_price is not None and buyout_price <= start_price:
        raise ValueError("Цена мгновенного выкупа должна быть выше стартовой цены")

    ctype, _ = _parse_cosmetic_key(item_key)
    if ctype not in ("frame", "cosmetic", "theme"):
        raise ValueError("Неверный тип косметики")

    async with postgres_connect() as db:
        # 1. Проверяем владение
        if not await _user_owns_cosmetic(db, item_key, seller_id, chat_id):
            raise ValueError("Косметика не найдена в вашем инвентаре")

        # 2. Проверяем что не уже на аукционе
        existing = await db.fetchone(
            "SELECT id FROM auctions WHERE item_id=0 AND item_key=? AND seller_id=? AND chat_id=? AND status='active'",
            (item_key, seller_id, chat_id)
        )
        if existing:
            raise ValueError("Этот предмет уже выставлен на аукцион")

        # 3. Проверяем лимит активных лотов
        active_count = await db.fetchone(
            "SELECT COUNT(*) AS cnt FROM auctions WHERE seller_id=? AND chat_id=? AND status='active'",
            (seller_id, chat_id)
        )
        if active_count and int(active_count["cnt"] or 0) >= MAX_ACTIVE_PER_USER:
            raise ValueError(f"Максимум {MAX_ACTIVE_PER_USER} активных лота одновременно")

        # 4. Отзываем косметику у продавца
        await _revoke_cosmetic_from_user(db, item_key, seller_id, chat_id)

        now = datetime.now(timezone.utc)
        ends_at = now + timedelta(hours=AUCTION_DURATION_HOURS)
        rarity  = COSMETIC_RARITY_MAP.get(ctype, "common")
        emoji   = COSMETIC_EMOJI_MAP.get(ctype, "✨")

        # 5. Создаём запись аукциона (item_id=0 — сигнал что это косметика)
        row = await db.fetchone(
            """INSERT INTO auctions
               (chat_id, seller_id, item_id, item_key, item_name, item_rarity, item_emoji,
                start_price, current_price, buyout_price, status, created_at, ends_at)
               VALUES (?,?,0,?,?,?,?,?,?,?,'active',?,?)
               RETURNING id""",
            (chat_id, seller_id, item_key, item_name,
             rarity, emoji, start_price, start_price, buyout_price,
             now, ends_at)
        )
        auction_id = row["id"]

    return {
        "ok":         True,
        "auction_id": auction_id,
        "item_name":  item_name,
        "ends_at":    ends_at.isoformat(),
    }


# ─── Создание аукциона ─────────────────────────────────────────────────────────

async def create_auction(
    seller_id: int,
    chat_id: int,
    item_id: int,
    start_price: int,
    buyout_price: Optional[int] = None,
) -> dict:
    """
    Выставить предмет на аукцион.
    Возвращает {ok, auction_id, item_name, ends_at} или raises ValueError.
    """
    if start_price < MIN_START_PRICE:
        raise ValueError(f"Минимальная стартовая цена: {MIN_START_PRICE} 🪙")
    if buyout_price is not None and buyout_price <= start_price:
        raise ValueError("Цена мгновенного выкупа должна быть выше стартовой цены")

    async with postgres_connect() as db:
        # 1. Проверяем что предмет существует и принадлежит продавцу
        item = await _get_item(db, item_id, seller_id, chat_id)
        if not item:
            raise ValueError("Предмет не найден в инвентаре")

        # 1b. 3-дневное правило владения: предмет должен быть в инвентаре ≥ 3 дня
        # Block 3: можно обойти тратой пропуска переноса
        acquired = item.get("acquired_at") or item.get("obtained_at")
        if acquired:
            if isinstance(acquired, str):
                from datetime import timezone as _tz
                acquired = datetime.fromisoformat(acquired.replace("Z", "+00:00"))
            if acquired.tzinfo is None:
                acquired = acquired.replace(tzinfo=timezone.utc)
            item_age_days = (datetime.now(timezone.utc) - acquired).total_seconds() / 86400
            if item_age_days < 3:
                days_left = 3 - int(item_age_days)
                # Check if user has transfer passes to bypass the rule
                from database.db import get_transfer_passes, use_transfer_pass
                transfer_passes = await get_transfer_passes(seller_id)
                if transfer_passes > 0:
                    # Use a transfer pass to bypass the 3-day rule
                    success = await use_transfer_pass(seller_id)
                    if success:
                        # Pass consumed successfully, continue with auction creation
                        pass
                    else:
                        raise ValueError(f"Нельзя выставить на аукцион — нужно владеть предметом ≥3 дня (ещё {days_left} дн. ✅)")
                else:
                    raise ValueError(f"Нельзя выставить на аукцион — нужно владеть предметом ≥3 дня (ещё {days_left} дн. ✅)\n💎 Купи «Пропуск переноса» за кристаллы для обхода!")

        # 2. Проверяем что предмет не уже на аукционе
        existing = await db.fetchone(
            "SELECT id FROM auctions WHERE item_id=? AND seller_id=? AND chat_id=? AND status='active'",
            (item_id, seller_id, chat_id)
        )
        if existing:
            raise ValueError("Этот предмет уже выставлен на аукцион")

        # 3. Проверяем лимит активных лотов
        active_count = await db.fetchone(
            "SELECT COUNT(*) AS cnt FROM auctions WHERE seller_id=? AND chat_id=? AND status='active'",
            (seller_id, chat_id)
        )
        if active_count and int(active_count["cnt"] or 0) >= MAX_ACTIVE_PER_USER:
            raise ValueError(f"Максимум {MAX_ACTIVE_PER_USER} активных лота одновременно")

        # 4. Если предмет экипирован — снимаем
        if item.get("equipped"):
            await db.execute(
                "UPDATE gacha_inventory SET equipped=0 WHERE id=?",
                (item_id,)
            )

        # 5. Помечаем предмет как "на аукционе" (equipped=2 — условное значение «заблокирован»)
        await db.execute(
            "UPDATE gacha_inventory SET equipped=2 WHERE id=? AND user_id=?",
            (item_id, seller_id)
        )

        now = datetime.now(timezone.utc)
        ends_at = now + timedelta(hours=AUCTION_DURATION_HOURS)

        item_emoji = _rarity_emoji(item.get("rarity", "common"))

        # 6. Создаём запись аукциона
        row = await db.fetchone(
            """INSERT INTO auctions
               (chat_id, seller_id, item_id, item_key, item_name, item_rarity, item_emoji,
                start_price, current_price, buyout_price, status, created_at, ends_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,'active',?,?)
               RETURNING id""",
            (chat_id, seller_id, item_id,
            item["item_key"], item["item_name"],
            item.get("rarity", "common"), item_emoji,
            start_price, start_price, buyout_price,
            now, ends_at)
        )
        auction_id = row["id"]
        await db.execute("UPDATE auctions SET id=id WHERE id=?", (auction_id,))  # flush

    # Достижение за первую продажу
    try:
        from api.achievements import check_and_award as _ach
        active_lots = await _count_user_auctions_total(seller_id, chat_id)
        await _ach(seller_id, chat_id, "auction_sell", active_lots)
    except Exception:
        pass

    return {
        "ok":        True,
        "auction_id": auction_id,
        "item_name":  item["item_name"],
        "ends_at":    ends_at.isoformat(),
    }


def _rarity_emoji(rarity: str) -> str:
    return {"legendary": "⭐", "rare": "💜", "common": "⚔️"}.get(rarity, "🎴")


async def _count_user_auctions_total(user_id: int, chat_id: int) -> int:
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT COUNT(*) AS cnt FROM auctions WHERE seller_id=? AND chat_id=?",
            (user_id, chat_id)
        )
        return int(row["cnt"] or 0) if row else 0


# ─── Ставка ───────────────────────────────────────────────────────────────────

async def place_bid(
    bidder_id: int,
    chat_id: int,
    auction_id: int,
    amount: int,
) -> dict:
    """
    Сделать ставку на аукцион.
    Возвращает {ok, new_price, outbid_user_id, outbid_amount} или raises ValueError.
    """
    async with postgres_connect() as db:
        # FOR UPDATE: блокируем строку от гонок
        auction = await db.fetchone(
            "SELECT * FROM auctions WHERE id=? AND chat_id=? FOR UPDATE",
            (auction_id, chat_id)
        )
        if not auction:
            raise ValueError("Аукцион не найден")
        if auction["status"] != "active":
            raise ValueError("Аукцион уже завершён")
        if datetime.now(timezone.utc) > auction["ends_at"].replace(tzinfo=timezone.utc) if hasattr(auction["ends_at"], 'replace') else auction["ends_at"]:
            raise ValueError("Аукцион уже истёк")

        # Нельзя ставить на свой лот
        if auction["seller_id"] == bidder_id:
            raise ValueError("Нельзя делать ставки на собственный лот")

        # Минимальная ставка
        min_bid = auction["current_price"] + _min_increment(auction["current_price"])
        if amount < min_bid:
            raise ValueError(f"Минимальная ставка: {min_bid} 🪙 (текущая {auction['current_price']} + 10%)")

        # Проверяем мору покупателя
        mora_row = await db.fetchone(
            "SELECT COALESCE(balance, 0) AS balance FROM users WHERE user_id=?",
            (bidder_id,)
        )
        balance = int(mora_row["balance"] or 0) if mora_row else 0
        if balance < amount:
            raise ValueError(f"Недостаточно Моры. У тебя: {balance} 🪙, нужно: {amount} 🪙")

        # Списываем с покупателя
        await db.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
            (amount, bidder_id, amount)
        )

        outbid_user_id   = auction["highest_bidder_id"]
        outbid_amount    = auction["current_price"] if auction["bid_count"] > 0 else 0

        # Возвращаем предыдущую ставку
        if outbid_user_id and outbid_user_id != bidder_id and outbid_amount > 0:
            await db.execute(
                "UPDATE users SET balance=COALESCE(balance,0)+? WHERE user_id=?",
                (outbid_amount, outbid_user_id)
            )

        # Обновляем аукцион
        await db.execute(
            """UPDATE auctions SET current_price=?, highest_bidder_id=?, bid_count=bid_count+1
               WHERE id=?""",
            (amount, bidder_id, auction_id)
        )

        # Логируем ставку
        await db.execute(
            "INSERT INTO auction_bids (auction_id, bidder_id, chat_id, amount) VALUES (?,?,?,?)",
            (auction_id, bidder_id, chat_id, amount)
        )

    return {
        "ok":             True,
        "new_price":      amount,
        "outbid_user_id": outbid_user_id,
        "outbid_amount":  outbid_amount,
    }


# ─── Мгновенный выкуп ─────────────────────────────────────────────────────────

async def buyout_auction(buyer_id: int, chat_id: int, auction_id: int) -> dict:
    """
    Мгновенный выкуп по buyout_price.
    Возвращает {ok, item_name, price_paid, seller_received} или raises ValueError.
    """
    async with postgres_connect() as db:
        auction = await db.fetchone(
            "SELECT * FROM auctions WHERE id=? AND chat_id=? FOR UPDATE",
            (auction_id, chat_id)
        )
        if not auction:
            raise ValueError("Аукцион не найден")
        if auction["status"] != "active":
            raise ValueError("Аукцион уже завершён")
        if not auction["buyout_price"]:
            raise ValueError("Мгновенный выкуп недоступен для этого лота")
        if auction["seller_id"] == buyer_id:
            raise ValueError("Нельзя выкупить собственный лот")

        buyout = int(auction["buyout_price"])

        # Проверяем мору покупателя
        mora_row = await db.fetchone(
            "SELECT COALESCE(balance, 0) AS balance FROM users WHERE user_id=?",
            (buyer_id,)
        )
        balance = int(mora_row["balance"] or 0) if mora_row else 0
        if balance < buyout:
            raise ValueError(f"Недостаточно Моры. Нужно {buyout} 🪙, у тебя {balance} 🪙")

        # Списываем с покупателя
        await db.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
            (buyout, buyer_id, buyout)
        )

        # Возвращаем ставку предыдущему участнику если есть
        prev_bidder = auction["highest_bidder_id"]
        prev_amount = auction["current_price"] if auction["bid_count"] > 0 else 0
        if prev_bidder and prev_bidder != buyer_id and prev_amount > 0:
            await db.execute(
                "UPDATE users SET balance=COALESCE(balance,0)+? WHERE user_id=?",
                (prev_amount, prev_bidder)
            )

        # 10% комиссия → казна
        commission = max(1, int(buyout * COMMISSION_RATE))
        seller_gets = buyout - commission
        from database.db import add_to_treasury
        await add_to_treasury(chat_id, commission, "auction", buyer_id)

        # Продавцу — выручка
        await db.execute(
            "UPDATE users SET balance=COALESCE(balance,0)+?, total_earned=COALESCE(total_earned,0)+? WHERE user_id=?",
            (seller_gets, seller_gets, auction["seller_id"])
        )

        # Передаём предмет покупателю
        item_id = auction["item_id"]
        if item_id == 0:
            # Косметика — передаём через отдельную логику
            await _transfer_cosmetic_to_user(db, auction["item_key"], buyer_id, chat_id)
        else:
            item_exists = await db.fetchone(
                "SELECT id FROM gacha_inventory WHERE id=? AND user_id=?",
                (item_id, auction["seller_id"])
            )
            if item_exists:
                await db.execute(
                    "UPDATE gacha_inventory SET user_id=?, equipped=0 WHERE id=?",
                    (buyer_id, item_id)
                )

        # Завершаем аукцион
        await db.execute(
            "UPDATE auctions SET status='sold', highest_bidder_id=?, current_price=?, finished_at=NOW() WHERE id=?",
            (buyer_id, buyout, auction_id)
        )

    # Достижения
    try:
        from api.achievements import check_and_award as _ach
        wins = await _count_user_wins(buyer_id, chat_id)
        await _ach(buyer_id, chat_id, "auction_win", wins)
    except Exception:
        pass

    return {
        "ok":              True,
        "item_name":       auction["item_name"],
        "price_paid":      buyout,
        "seller_received": seller_gets,
    }


async def _count_user_wins(user_id: int, chat_id: int) -> int:
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT COUNT(*) AS cnt FROM auctions WHERE highest_bidder_id=? AND chat_id=? AND status='sold'",
            (user_id, chat_id)
        )
        return int(row["cnt"] or 0) if row else 0


# ─── Отмена аукциона ──────────────────────────────────────────────────────────

async def cancel_auction(seller_id: int, chat_id: int, auction_id: int) -> dict:
    """
    Продавец отменяет аукцион.
    Без ставок — бесплатно. Со ставками — штраф 5% от стартовой цены (минимум 5).
    Возвращает {ok, item_name, refunded_bidder_id, refunded_amount} или raises ValueError.
    """
    async with postgres_connect() as db:
        auction = await db.fetchone(
            "SELECT * FROM auctions WHERE id=? AND seller_id=? AND chat_id=? FOR UPDATE",
            (auction_id, seller_id, chat_id)
        )
        if not auction:
            raise ValueError("Аукцион не найден или не принадлежит вам")
        if auction["status"] != "active":
            raise ValueError("Аукцион уже завершён")

        refunded_bidder_id = None
        refunded_amount    = 0

        # Если есть ставки — вернуть последнюю
        if auction["bid_count"] > 0 and auction["highest_bidder_id"]:
            refunded_bidder_id = auction["highest_bidder_id"]
            refunded_amount    = int(auction["current_price"])
            await db.execute(
                "UPDATE users SET balance=COALESCE(balance,0)+? WHERE user_id=?",
                (refunded_amount, refunded_bidder_id)
            )
            # Штраф продавцу
            penalty = max(5, int(auction["start_price"] * 0.05))
            await db.execute(
                "UPDATE users SET balance=GREATEST(0, COALESCE(balance,0)-?) WHERE user_id=?",
                (penalty, seller_id)
            )

        # Разблокировать предмет
        if auction["item_id"] == 0:
            # Косметика — вернуть продавцу
            await _transfer_cosmetic_to_user(db, auction["item_key"], seller_id, chat_id)
        else:
            await db.execute(
                "UPDATE gacha_inventory SET equipped=0 WHERE id=? AND user_id=?",
                (auction["item_id"], seller_id)
            )

        # Закрыть аукцион
        await db.execute(
            "UPDATE auctions SET status='cancelled', finished_at=NOW() WHERE id=?",
            (auction_id,)
        )

    return {
        "ok":                 True,
        "item_name":          auction["item_name"],
        "refunded_bidder_id": refunded_bidder_id,
        "refunded_amount":    refunded_amount,
    }


# ─── Финализация истёкших аукционов (планировщик) ─────────────────────────────

async def finalize_expired_auctions(bot=None) -> list[dict]:
    """
    Закрыть все истёкшие активные аукционы.
    Вызывается из планировщика каждый час.
    Возвращает список завершённых аукционов для уведомлений.
    """
    now = datetime.now(timezone.utc)
    finalized = []

    async with postgres_connect() as db:
        expired = await db.fetch(
            "SELECT * FROM auctions WHERE status='active' AND ends_at <= ?",
            (now,)
        )

    for auction in expired:
        auction = dict(auction)
        auction_id = auction["id"]
        chat_id    = auction["chat_id"]
        seller_id  = auction["seller_id"]
        item_id    = auction["item_id"]

        if auction["bid_count"] == 0 or not auction["highest_bidder_id"]:
            # Нет ставок — возврат предмета продавцу
            try:
                async with postgres_connect() as db:
                    if item_id == 0:
                        await _transfer_cosmetic_to_user(db, auction["item_key"], seller_id, chat_id)
                    else:
                        await db.execute(
                            "UPDATE gacha_inventory SET equipped=0 WHERE id=? AND user_id=?",
                            (item_id, seller_id)
                        )
                    await db.execute(
                        "UPDATE auctions SET status='expired', finished_at=? WHERE id=?",
                        (now, auction_id)
                    )
                finalized.append({**auction, "result": "expired_no_bids"})
            except Exception as e:
                logger.error("Auction finalize error (no bids) #%s: %s", auction_id, e)
        else:
            # Есть ставки — передача предмета победителю
            winner_id = auction["highest_bidder_id"]
            final_price = int(auction["current_price"])
            commission  = max(1, int(final_price * COMMISSION_RATE))
            seller_gets = final_price - commission

            try:
                async with postgres_connect() as db:
                    if item_id == 0:
                        # Косметика — передаём победителю
                        await _transfer_cosmetic_to_user(db, auction["item_key"], winner_id, chat_id)
                    else:
                        # Проверяем что предмет ещё у продавца
                        item_exists = await db.fetchone(
                            "SELECT id FROM gacha_inventory WHERE id=? AND user_id=?",
                            (item_id, seller_id)
                        )
                        if item_exists:
                            await db.execute(
                                "UPDATE gacha_inventory SET user_id=?, equipped=0 WHERE id=?",
                                (winner_id, item_id)
                            )
                        else:
                            # Предмет удалён — возвращаем ставку победителю
                            await db.execute(
                                "UPDATE users SET balance=COALESCE(balance,0)+? WHERE user_id=?",
                                (final_price, winner_id)
                            )
                            await db.execute(
                                "UPDATE auctions SET status='expired', finished_at=? WHERE id=?",
                                (now, auction_id)
                            )
                            finalized.append({**auction, "result": "expired_item_missing"})
                            continue

                    # Мора продавцу (минус комиссия)
                    await db.execute(
                        "UPDATE users SET balance=COALESCE(balance,0)+?, total_earned=COALESCE(total_earned,0)+? WHERE user_id=?",
                        (seller_gets, seller_gets, seller_id)
                    )
                    # Комиссия → казна
                    from database.db import add_to_treasury
                    await add_to_treasury(chat_id, commission, "auction", winner_id)

                    # Завершаем аукцион
                    await db.execute(
                        "UPDATE auctions SET status='sold', finished_at=? WHERE id=?",
                        (now, auction_id)
                    )

                finalized.append({**auction, "result": "sold", "winner_id": winner_id,
                                   "seller_gets": seller_gets, "commission": commission})

                # Достижение за выигрыш
                try:
                    from api.achievements import check_and_award as _ach
                    wins = await _count_user_wins(winner_id, chat_id)
                    await _ach(winner_id, chat_id, "auction_win", wins)
                except Exception:
                    pass

            except Exception as e:
                logger.error("Auction finalize error #%s: %s", auction_id, e)

    # Уведомления
    if bot and finalized:
        for a in finalized:
            try:
                cid = a["chat_id"]
                if a["result"] == "sold":
                    winner_id  = a.get("winner_id")
                    item_name  = a.get("item_name", "?")
                    s_gets     = a.get("seller_gets", 0)
                    f_price    = a.get("current_price", 0)
                    await bot.send_message(
                        cid,
                        f"🔨 <b>Аукцион завершён!</b>\n\n"
                        f"📦 <b>{item_name}</b>\n"
                        f"🏆 Победитель: <a href='tg://user?id={winner_id}'>Предвестник</a>\n"
                        f"💰 Продавец получил: <b>{s_gets} 🪙</b> (финальная цена {f_price} 🪙)",
                        parse_mode="HTML",
                    )
                elif a["result"] == "expired_no_bids":
                    await bot.send_message(
                        cid,
                        f"📦 Аукцион «<b>{a.get('item_name', '?')}</b>» истёк без ставок. "
                        f"Предмет возвращён продавцу.",
                        parse_mode="HTML",
                    )
            except Exception as e:
                logger.debug("Auction notify error: %s", e)

    return finalized


# ─── Просмотр активных аукционов ──────────────────────────────────────────────

async def get_active_auctions(chat_id: int, limit: int = 20, offset: int = 0) -> list[dict]:
    """Вернуть активные аукционы в чате."""
    async with postgres_connect() as db:
        rows = await db.fetch(
            """SELECT a.*, u.full_name AS seller_name
               FROM auctions a
               LEFT JOIN users u ON u.user_id = a.seller_id
               WHERE a.chat_id=? AND a.status='active'
               ORDER BY a.ends_at ASC
               LIMIT ? OFFSET ?""",
            (chat_id, limit, offset)
        )
    result = []
    for row in rows:
        d = dict(row)
        ends_at = d.get("ends_at")
        if ends_at:
            now = datetime.now(timezone.utc)
            if hasattr(ends_at, "replace"):
                ends_at_aware = ends_at.replace(tzinfo=timezone.utc) if ends_at.tzinfo is None else ends_at
            else:
                ends_at_aware = ends_at
            remaining = max(0, int((ends_at_aware - now).total_seconds()))
            d["remaining_seconds"] = remaining
            h, rem = divmod(remaining, 3600)
            m = rem // 60
            d["remaining_str"] = f"{h}ч {m}м" if h else f"{m}м"
        d["min_bid"] = d["current_price"] + _min_increment(d["current_price"])
        result.append(d)
    return result


async def get_auction_detail(auction_id: int, chat_id: int) -> dict | None:
    """Полная информация об аукционе с историей ставок."""
    async with postgres_connect() as db:
        auction = await db.fetchone(
            "SELECT * FROM auctions WHERE id=? AND chat_id=?",
            (auction_id, chat_id)
        )
        if not auction:
            return None
        bids = await db.fetch(
            """SELECT ab.amount, ab.bid_at, u.full_name
               FROM auction_bids ab
               LEFT JOIN users u ON u.user_id = ab.bidder_id
               WHERE ab.auction_id=?
               ORDER BY ab.bid_at DESC LIMIT 10""",
            (auction_id,)
        )
    d = dict(auction)
    d["bids_history"] = [dict(b) for b in bids]
    d["min_bid"] = d["current_price"] + _min_increment(d["current_price"])
    return d


async def get_user_auctions(user_id: int, chat_id: int) -> dict:
    """Мои лоты и мои ставки."""
    async with postgres_connect() as db:
        my_lots = await db.fetch(
            "SELECT * FROM auctions WHERE seller_id=? AND chat_id=? AND status='active' ORDER BY created_at DESC LIMIT 10",
            (user_id, chat_id)
        )
        my_bids = await db.fetch(
            """SELECT a.id, a.item_name, a.current_price, a.status, a.ends_at,
                      a.highest_bidder_id,
                      (SELECT MAX(amount) FROM auction_bids WHERE auction_id=a.id AND bidder_id=?) AS my_bid
               FROM auctions a
               WHERE a.chat_id=? AND EXISTS (
                   SELECT 1 FROM auction_bids WHERE auction_id=a.id AND bidder_id=?
               )
               ORDER BY a.created_at DESC LIMIT 10""",
            (user_id, chat_id, user_id)
        )
    return {
        "my_lots": [dict(r) for r in my_lots],
        "my_bids": [dict(r) for r in my_bids],
    }
