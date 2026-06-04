"""FastAPI/routers/profile.py — профиль игрока.
Тонкий адаптер: только вызовы infrastructure/, только JSON.
"""
from fastapi import APIRouter, Depends, HTTPException
from FastAPI.deps import get_db, require_tg_user

router = APIRouter(prefix="/profile", tags=["profile"])

_RANK_NAMES = {
    0: "👤 Пользователь",
    1: "⭐ Почётный участник",
    2: "🛡 Модератор",
    3: "🌌 Разработчик",
}


@router.get("/me")
async def my_profile(db=Depends(get_db), user=Depends(require_tg_user)):
    """Полный профиль текущего пользователя."""
    user_id = user["id"]

    async with db.execute(
        "SELECT user_tg_id, user_tg_username, global_rank, "
        "user_balance_mora, user_balance_diamonds "
        "FROM users WHERE user_tg_id = ?",
        (user_id,),
    ) as c:
        row = await c.fetchone()

    if not row:
        raise HTTPException(404, "Профиль не найден. Напишите боту чтобы зарегистрироваться.")

    # Топ-5 чатов по активности
    async with db.execute(
        "SELECT ucs.chat_tg_id, cs.chat_title, ucs.user_level, ucs.user_xp, "
        "ucs.user_messages_count_all_time, ucs.local_rank "
        "FROM user_chat_stats ucs "
        "LEFT JOIN chat_settings cs ON cs.chat_id = ucs.chat_tg_id "
        "WHERE ucs.user_tg_id = ? AND ucs.is_left = FALSE "
        "ORDER BY ucs.user_messages_count_all_time DESC LIMIT 5",
        (user_id,),
    ) as c:
        chats = [dict(r) for r in await c.fetchall()]

    # Питомцы
    async with db.execute(
        "SELECT id, name, species_id, rarity, placement, fatigue, "
        "COALESCE(pet_level, 1) AS pet_level "
        "FROM pets WHERE owner_id = ?",
        (user_id,),
    ) as c:
        pets = [dict(r) for r in await c.fetchall()]

    # Стрик (максимальный по всем чатам)
    async with db.execute(
        "SELECT MAX(streak) AS streak, MAX(last_login) AS last_login "
        "FROM daily_login WHERE user_id = ?",
        (user_id,),
    ) as c:
        streak_row = await c.fetchone()

    # Достижения
    async with db.execute(
        "SELECT COUNT(*) FROM achievements WHERE user_id = ? AND level > 0",
        (user_id,),
    ) as c:
        ach_count = (await c.fetchone())[0]

    return {
        "user_id":      user_id,
        "username":     row["user_tg_username"],
        "rank":         _RANK_NAMES.get(row["global_rank"] or 0, "👤 Пользователь"),
        "mora":         float(row["user_balance_mora"] or 0),
        "diamonds":     float(row["user_balance_diamonds"] or 0),
        "streak":       (dict(streak_row)["streak"] or 0) if streak_row else 0,
        "achievements": ach_count,
        "chats":        chats,
        "pets":         pets,
    }
