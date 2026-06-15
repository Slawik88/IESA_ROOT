"""FastAPI/routers/profile.py — профиль игрока.
Тонкий адаптер: только вызовы infrastructure/, только JSON.
"""
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from FastAPI.deps import get_db, require_tg_user
from services.roles import GLOBAL_RANKS_MAP

router = APIRouter(prefix="/profile", tags=["profile"])

# Единый источник правды для названий глобальных рангов — services/roles.py
# (та же таблица, что использует бот через get_global_rank_name).
_RANK_NAMES = GLOBAL_RANKS_MAP


@router.get("/me")
async def my_profile(db=Depends(get_db), user=Depends(require_tg_user)):
    """Полный профиль текущего пользователя."""
    user_id = user["id"]

    async with db.execute(
        "SELECT u.user_tg_id, u.user_tg_username, u.global_rank, "
        "u.user_balance_mora, u.user_balance_diamonds, "
        "COALESCE(u.user_balance_dark_mora, 0) AS user_balance_dark_mora, "
        "COALESCE(u.user_balance_zarniki, 0) AS user_balance_zarniki, "
        "(v.user_id IS NOT NULL) AS is_vip "
        "FROM users u "
        "LEFT JOIN vip_subscriptions v ON v.user_id = u.user_tg_id AND v.expires_at > NOW() "
        "WHERE u.user_tg_id = ?",
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
        "dark_mora":    float(row["user_balance_dark_mora"] or 0),
        "zarniki":      float(row["user_balance_zarniki"] or 0),
        "streak":       (dict(streak_row)["streak"] or 0) if streak_row else 0,
        "achievements": ach_count,
        "chats":        chats,
        "pets":         pets,
        "is_vip":       bool(row["is_vip"]),
        "global_rank":  row["global_rank"] or 0,
    }


_NICK_RE = re.compile(r"^[\w\s\-\.]{1,32}$", re.UNICODE)


class NicknameRequest(BaseModel):
    chat_id: int
    nickname: str


@router.post("/set-nickname")
async def set_nickname_endpoint(body: NicknameRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Установить ник в чате (1–32 символа, буквы/цифры/пробел/дефис/точка)."""
    nick = body.nickname.strip()
    if not nick or len(nick) > 32:
        raise HTTPException(400, "Ник: 1–32 символа.")
    if not _NICK_RE.match(nick):
        raise HTTPException(400, "Ник содержит недопустимые символы.")
    if body.chat_id == 0:
        raise HTTPException(400, "Нужен ID чата.")

    async with db.execute(
        "SELECT 1 FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (user["id"], body.chat_id),
    ) as c:
        if not await c.fetchone():
            raise HTTPException(400, "Вы не состоите в этом чате.")

    # Uniqueness check (case-insensitive, per chat)
    async with db.execute(
        "SELECT user_id FROM user_nicknames WHERE chat_id = ? AND LOWER(nickname) = LOWER(?)",
        (body.chat_id, nick),
    ) as c:
        existing = await c.fetchone()
    if existing and existing[0] != user["id"]:
        raise HTTPException(400, "Этот ник уже занят в данном чате.")

    await db.execute(
        "INSERT INTO user_nicknames (user_id, chat_id, nickname) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, chat_id) DO UPDATE SET nickname = EXCLUDED.nickname, set_at = NOW()",
        (user["id"], body.chat_id, nick),
    )
    await db.commit()
    return {"ok": True, "nickname": nick}


@router.get("/nickname")
async def get_nickname_endpoint(chat_id: int = 0, db=Depends(get_db), user=Depends(require_tg_user)):
    """Текущий ник пользователя в чате."""
    if chat_id == 0:
        return {"nickname": None}
    async with db.execute(
        "SELECT nickname FROM user_nicknames WHERE user_id = ? AND chat_id = ?",
        (user["id"], chat_id),
    ) as c:
        row = await c.fetchone()
    return {"nickname": row[0] if row else None}
