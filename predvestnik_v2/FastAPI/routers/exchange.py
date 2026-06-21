"""FastAPI/routers/exchange.py — постоянный обменник Моры ↔ Алмазов.

БЛОК 2.2: ивентовый обмен (B15) заменён на постоянный двусторонний обменник,
доступный из профиля по клику на 🪙/💎.

Квота — дневная, без миграций: ключ в user_exchange_quota.event_id =
  • дата YYYYMMDD  — для покупки (Мора → Алмазы);
  • -YYYYMMDD      — для продажи (Алмазы → Мора), отдельный неймспейс.
Новый день = новый ключ ⇒ авто-сброс лимита в полночь. Старые event-строки
(с настоящими event_id из exchange_events) сосуществуют безвредно.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.constants import (
    EXCHANGE_RATE_MORA_PER_DIAMOND, EXCHANGE_RATE_MORA_PER_DIAMOND_SELL,
    EXCHANGE_DAILY_CAP_DIAMONDS, EXCHANGE_SELL_DAILY_CAP_DIAMONDS,
    EXCHANGE_MIN_DIAMONDS_PER_REQUEST,
)
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.exchange import get_user_quota, add_quota

router = APIRouter(prefix="/exchange", tags=["exchange"])


def _buy_key() -> int:
    """Ключ дневной квоты покупки: YYYYMMDD."""
    return int(date.today().strftime("%Y%m%d"))


def _sell_key() -> int:
    """Ключ дневной квоты продажи: -YYYYMMDD (отдельный неймспейс от покупки)."""
    return -_buy_key()


@router.get("/")
async def exchange_status(db=Depends(get_db), user=Depends(require_tg_user)):
    """Статус постоянного обменника + остаток дневных квот в обе стороны."""
    bought = await get_user_quota(db, user["id"], _buy_key())
    sold = await get_user_quota(db, user["id"], _sell_key())
    bal = await eco_repo.get_balance(db, user["id"])
    return {
        "active":         True,  # обменник теперь доступен всегда
        "rate":           EXCHANGE_RATE_MORA_PER_DIAMOND,
        "sell_rate":      EXCHANGE_RATE_MORA_PER_DIAMOND_SELL,
        "min_diamonds":   EXCHANGE_MIN_DIAMONDS_PER_REQUEST,
        "daily_cap":      EXCHANGE_DAILY_CAP_DIAMONDS,
        "sell_daily_cap": EXCHANGE_SELL_DAILY_CAP_DIAMONDS,
        "used_today":     bought,
        "sold_today":     sold,
        "remaining":      max(0.0, EXCHANGE_DAILY_CAP_DIAMONDS - bought),
        "sell_remaining": max(0.0, EXCHANGE_SELL_DAILY_CAP_DIAMONDS - sold),
        "mora":           float(bal["user_balance_mora"] or 0),
        "diamonds":       float(bal["user_balance_diamonds"] or 0),
    }


class ConvertRequest(BaseModel):
    diamonds: float


@router.post("/convert")
async def convert(body: ConvertRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Купить Алмазы за Мору (3000🪙 → 1💎). Постоянно, дневной лимит."""
    diamonds = round(body.diamonds, 2)
    if diamonds < EXCHANGE_MIN_DIAMONDS_PER_REQUEST:
        raise HTTPException(400, f"Минимум {int(EXCHANGE_MIN_DIAMONDS_PER_REQUEST)} 💎.")

    key = _buy_key()
    # atomic: лочим строку игрока — параллельные обмены не уведут баланс в минус
    async with eco_repo.atomic(db, user["id"]):
        used = await get_user_quota(db, user["id"], key)
        remaining = EXCHANGE_DAILY_CAP_DIAMONDS - used
        if diamonds > remaining:
            raise HTTPException(400, f"Дневной лимит покупки: {remaining:.1f} 💎 осталось.")

        mora_needed = diamonds * EXCHANGE_RATE_MORA_PER_DIAMOND
        bal = await eco_repo.get_balance(db, user["id"])
        if bal["user_balance_mora"] < mora_needed:
            raise HTTPException(400, f"Нужно {mora_needed:,.0f} 🪙, есть {bal['user_balance_mora']:,.0f}.")

        await eco_repo.add_balance(db, user["id"], mora=-mora_needed, diamonds=diamonds,
                                   source="exchange_mora_to_dia")
        await add_quota(db, user["id"], key, diamonds)

    return {"ok": True, "mora_spent": mora_needed, "diamonds_gained": diamonds}


@router.post("/sell")
async def sell(body: ConvertRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Продать Алмазы за Мору (1💎 → 2000🪙, спред). Постоянно, дневной лимит."""
    diamonds = round(body.diamonds, 2)
    if diamonds < EXCHANGE_MIN_DIAMONDS_PER_REQUEST:
        raise HTTPException(400, f"Минимум {int(EXCHANGE_MIN_DIAMONDS_PER_REQUEST)} 💎.")

    key = _sell_key()
    async with eco_repo.atomic(db, user["id"]):
        used = await get_user_quota(db, user["id"], key)
        remaining = EXCHANGE_SELL_DAILY_CAP_DIAMONDS - used
        if diamonds > remaining:
            raise HTTPException(400, f"Дневной лимит продажи: {remaining:.1f} 💎 осталось.")

        bal = await eco_repo.get_balance(db, user["id"])
        if bal["user_balance_diamonds"] < diamonds:
            raise HTTPException(400, f"Нужно {diamonds:.0f} 💎, есть {bal['user_balance_diamonds']:.1f}.")

        mora_gained = diamonds * EXCHANGE_RATE_MORA_PER_DIAMOND_SELL
        await eco_repo.add_balance(db, user["id"], mora=mora_gained, diamonds=-diamonds,
                                   source="exchange_dia_to_mora")
        await add_quota(db, user["id"], key, diamonds)

    return {"ok": True, "mora_gained": mora_gained, "diamonds_spent": diamonds}
