"""Кто открыл админку и что ему можно."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from FastAPI.auth import verify_session_token, verify_webapp_data
from FastAPI.deps import get_db
from bot.chat.global_ranks import BOT_RANKS, CREATOR, bot_rank_name, get_bot_rank
from infrastructure.preprod import require_preprod_user

# Минимальная глобальная роль для раздела (1 тестер … 5 разработчик, 6 создатель).
SECTIONS: dict[str, tuple[str, int]] = {
    "people": ("Игроки и чаты", 2),
    "metrics": ("Метрики", 4),
    "promo": ("Промокоды", 5),
    "switches": ("Функции", 5),
    "settings": ("Настройки", 5),
}
router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"])


async def staff_user(x_init_data: str = Header(default=""), x_session_token: str = Header(default=""),
                     db=Depends(get_db)) -> dict:
    user_id = None
    if x_init_data:
        data = verify_webapp_data(x_init_data)
        user_id = int(data["id"]) if data else None
    if not user_id and x_session_token:
        user_id = verify_session_token(x_session_token)
    if not user_id:
        raise HTTPException(401, "Войдите через Telegram.")
    if not require_preprod_user(int(user_id)):
        raise HTTPException(403, "Тестовый стенд закрыт для этого аккаунта.")
    rank = await get_bot_rank(db, int(user_id))
    if rank <= 0:
        raise HTTPException(403, "Админка доступна только персоналу бота.")
    return {"id": int(user_id), "rank": rank}


def section(key: str):
    """Зависимость: пользователь с ролью не ниже нужной для раздела."""
    async def check(user=Depends(staff_user)) -> dict:
        if user["rank"] < SECTIONS[key][1]:
            raise HTTPException(403, f"Раздел «{SECTIONS[key][0]}» вам недоступен.")
        return user
    return check


@router.get("/me")
async def me(user=Depends(staff_user)):
    return {
        "user_id": user["id"], "rank": user["rank"], "rank_name": bot_rank_name(user["rank"]),
        "sections": [{"key": k, "title": t, "min_rank": r} for k, (t, r) in SECTIONS.items() if user["rank"] >= r],
        "ranks": [bot_rank_name(i) for i in range(len(BOT_RANKS))], "creator": user["rank"] >= CREATOR,
    }
