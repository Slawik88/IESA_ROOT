"""FastAPI/routers/wallet.py — история транзакций кошелька."""
from fastapi import APIRouter, Depends, Query
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.wallet_log import get_recent

router = APIRouter(prefix="/wallet", tags=["wallet"])

_SOURCE_LABELS = {
    "expedition":       "⚔️ Экспедиция",
    "quest_reward":     "📋 Квест",
    "achievement_reward": "🏆 Достижение",
    "level_up":         "⬆️ Уровень",
    "pet_milestone":    "🐾 Питомец Ур.",
    "shop":             "🛒 Магазин",
    "daily_deal":       "🏷 Акция дня",
    "transfer_out":     "📤 Перевод (отправлен)",
    "transfer_in":      "📥 Перевод (получен)",
    "auction_win":      "🏛 Аукцион (покупка)",
    "auction_sell":     "🏛 Аукцион (продажа)",
    "exchange":         "💱 Обмен",
    "streak":           "🔥 Стрик",
    "gacha":            "🎲 Гача",
    "theme_shop":       "🎨 Тема",
    "contrabanda":      "🌑 Контрабанда",
    "achievement":      "🏆 Достижение",
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
            "created_at":     str(r.get("created_at", ""))[:16],
            "note":           r.get("note", ""),
        })
    return result
