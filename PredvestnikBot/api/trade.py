# api/trade.py — P2P трейд-система (прямой обмен предметами между игроками)
#
# equipped values:
#   0 = free       1 = slot-equipped    2 = auction-locked    3 = trade-locked
#
# Таблица: trade_offers (создана в db.py::init_db)
# Все операции принятия (accept) — в единой asyncpg-транзакции.

from __future__ import annotations
import logging

_log = logging.getLogger(__name__)


async def offer_trade(
    from_user_id: int,
    to_user_id: int,
    item_id: int,
    price_mora: int = 0,
    price_crystals: int = 0,
) -> dict:
    """
    Игрок A предлагает предмет игроку B.
    price_mora / price_crystals — запрашиваемое вознаграждение (может быть 0).
    Блокирует предмет (equipped=3) немедленно.
    """
    from database.db import create_trade_offer
    return await create_trade_offer(
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        item_id=item_id,
        price_mora=price_mora,
        price_crystals=price_crystals,
    )


async def accept_trade(to_user_id: int, trade_id: int) -> dict:
    """
    Игрок B принимает предложение.
    Атомарно: предмет → B, оплата → A.
    """
    from database.db import accept_trade_offer
    result = await accept_trade_offer(to_user_id=to_user_id, trade_id=trade_id)
    # Уведомить обе стороны (best-effort)
    try:
        from database.db import postgres_connect
        async with postgres_connect() as db:
            row = await db.fetchone(
                "SELECT from_user_id FROM trade_offers WHERE id=$1", (trade_id,)
            )
        if row:
            from api.auction import _dm_user
            item_name = result.get("item_name", "предмет")
            await _dm_user(
                row["from_user_id"],
                f"✅ Игрок принял ваше трейд-предложение!\n"
                f"📦 <b>{item_name}</b> передан."
            )
    except Exception as _e:
        _log.debug("trade accept notify: %s", _e)
    return result


async def cancel_trade(from_user_id: int, trade_id: int) -> dict:
    """Инициатор отменяет своё предложение. Разблокирует предмет."""
    from database.db import cancel_trade_offer
    return await cancel_trade_offer(from_user_id=from_user_id, trade_id=trade_id)


async def decline_trade(to_user_id: int, trade_id: int) -> dict:
    """Получатель отклоняет предложение. Разблокирует предмет."""
    from database.db import decline_trade_offer
    return await decline_trade_offer(to_user_id=to_user_id, trade_id=trade_id)


async def list_trades(user_id: int) -> dict:
    """Вернуть входящие и исходящие активные предложения."""
    from database.db import get_user_trade_offers
    return await get_user_trade_offers(user_id=user_id)
