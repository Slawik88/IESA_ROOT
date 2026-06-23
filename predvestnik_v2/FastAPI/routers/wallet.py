"""FastAPI/routers/wallet.py — история транзакций кошелька."""
from fastapi import APIRouter, Depends, HTTPException, Query
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
    "auction_win":      "🏛 Аукцион (покупка)",
    "auction_sell":     "🏛 Аукцион (продажа)",
    "exchange":         "💱 Обмен",
    "exchange_mora_to_dia": "💱 Обмен",
    "streak":           "🔥 Стрик",
    "gacha":            "🎲 Гача",
    "theme_shop":       "🎨 Тема",
    "contrabanda":      "🌑 Контрабанда",
    "contrabanda_stake": "🌑 Контрабанда (ставка)",
    "contrabanda_refund": "🌑 Контрабанда (возврат)",
    "cult_ritual":      "🌑 Ритуал",
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
            # «Стало» (баланс после операции) — зафиксирован в момент записи лога.
            # «Было» фронт считает как (Стало − Изменение). ШАГ1.
            "mora_after":     float(r.get("balance_mora_after") or 0),
            "diamonds_after": float(r.get("balance_diamonds_after") or 0),
            "zarniki_after":  float(r.get("balance_zarniki_after") or 0),
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
):
    """Обменять ✨ Зарники на 🪙 Мору или 💎 Алмазы (необратимо, без лимита)."""
    if body.to not in ("mora", "diamonds"):
        raise HTTPException(status_code=400, detail="Некорректное направление обмена.")

    ok, message = await exchange_zarniki(db, user["id"], body.amount, body.to)
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    await db.commit()
    return {"ok": True, "message": message}
