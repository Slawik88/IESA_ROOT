"""FastAPI/routers/wallet.py — история транзакций кошелька."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.wallet_log import get_recent
from infrastructure.repositories.economy import exchange_zarniki

router = APIRouter(prefix="/wallet", tags=["wallet"])

_SOURCE_LABELS = {
    "expedition":       "⚔️ Экспедиция",
    "quest_reward":     "📋 Квест",
    "achievement_reward": "🏆 Достижение",
    "level_up":         "⬆️ Уровень",
    "pet_milestone":    "🐾 Питомец Ур.",
    "shop":             "🛒 Магазин",
    "shop_purchase":    "🛒 Магазин",
    "daily_deal":       "🏷 Акция дня",
    "daily_deal_purchase": "🏷 Акция дня",
    "transfer_out":     "📤 Перевод (отправлен)",
    "transfer_in":      "📥 Перевод (получен)",
    # БЛОК 36.2-фикс: реальные source — auction_buy/auction_sale (не win/sell)
    "auction_buy":      "🏛 Аукцион (покупка)",
    "auction_sale":     "🏛 Аукцион (продажа)",
    "auction_listing_fee": "🏛 Аукцион (листинг-сбор)",
    "exchange":         "💱 Обмен",
    "exchange_mora_to_dia": "💱 Старый обмен Моры на Алмазы",
    "exchange_dia_to_mora": "💱 Старый обмен Алмазов на Мору",
    "zarniki_exchange": "💱 Старый обмен Зарников",
    "paid_exchange":    "💱 Зарники → Мора",
    "stars_purchase":  "⭐ Покупка Зарников",
    "referral_commission": "🤝 Старая реферальная комиссия",
    "streak":           "🔥 Стрик",
    "streak_daily":     "🔥 Стрик",
    "streak_block_end": "🔥 Стрик (блок)",
    "streak_recovery":  "🔥 Стрик (восстановление)",
    # БЛОК 36.2-фикс: актуальные source списаний за крутку — gacha_mora/gacha_diamond
    "gacha_mora":       "🎲 Гача (крутка за Мору)",
    "gacha_diamond":    "🎲 Гача (алмазная крутка)",
    "gacha_drop":       "🎁 Гача-дроп",
    "theme_shop":       "🎨 Тема",
    "contrabanda":      "🌑 Контрабанда",
    "contrabanda_stake": "🌑 Контрабанда (ставка)",
    "contrabanda_refund": "🌑 Контрабанда (возврат)",
    "cult_ritual":      "🌑 Ритуал",
    "theme_purchase":   "🎭 Тема профиля",
    "cosmetic_purchase": "🎨 Косметика",
    "cosmetic_lineup_purchase": "🎨 Коллекция косметики",
    "cosmetic_many_purchase": "🎨 Набор косметики",
    "cosmetic_gift_purchase": "🎁 Подарок косметики",
    "cosmetic_chest_purchase": "🎁 Сундук косметики",
    "shadow_merchant":  "🕴 Теневой Торговец",
    "shadow_relic":     "🕴 Теневая реликвия",
    "achievement":      "🏆 Достижение",
    "crypto_buy":       "📈 Биржа (покупка)",
    "crypto_sell":      "📉 Биржа (продажа)",
}


@router.get("/history")
async def wallet_history(
    limit: int = Query(default=50, le=100),
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    """Последние транзакции кошелька."""
    rows = await get_recent(db, user["id"], n=limit)
    result = []
    for r in rows:
        source = r.get("source", "")
        label = _SOURCE_LABELS.get(source, source or "Система")
        result.append({
            "id":             r.get("id"),
            "label":          label,
            "source":         source,
            "delta_mora":     float(r.get("delta_mora") or 0),
            "delta_diamonds": float(r.get("delta_diamonds") or 0),
            "delta_zarniki":  float(r.get("delta_zarniki") or 0),
            "delta_dark_mora": float(r.get("delta_dark_mora") or 0),
            # «Стало» (баланс после операции) — зафиксирован в момент записи лога.
            # «Было» фронт считает как (Стало − Изменение). ШАГ1.
            "mora_after":     float(r.get("balance_mora_after") or 0),
            "diamonds_after": float(r.get("balance_diamonds_after") or 0),
            "zarniki_after":  float(r.get("balance_zarniki_after") or 0),
            "dark_mora_after": float(r.get("balance_dark_mora_after") or 0),
            "created_at":     str(r.get("created_at", ""))[:16],
            "note":           r.get("note", ""),
        })
    return result


class ExchangeZarnikiRequest(BaseModel):
    amount: float = Field(gt=0)
    to: str


@router.post("/exchange-zarniki")
async def exchange_zarniki_endpoint(
    body: ExchangeZarnikiRequest,
    db=Depends(get_db),
    user=Depends(require_tg_user),
    request_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Необратимо обменять целые Зарники только на Мору."""
    if body.to != "mora":
        raise HTTPException(400, "Алмазы за Зарники не продаются.")
    if request_key is None or not request_key.strip() or len(request_key.strip()) > 120:
        raise HTTPException(400, "Idempotency-Key должен содержать 1–120 символов.")
    ok, message = await exchange_zarniki(
        db, user["id"], body.amount, body.to,
        idempotency_key=request_key.strip(),
    )
    if not ok:
        raise HTTPException(400, message)
    await db.commit()
    return {"ok": True, "message": message}
