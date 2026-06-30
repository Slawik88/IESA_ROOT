"""FastAPI/routers/profile.py — профиль игрока.
Тонкий адаптер: только вызовы infrastructure/, только JSON.
"""
import os
import base64
import time
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.streak import get_global_streak
from services.roles import GLOBAL_RANKS_MAP
from core.constants import NICKNAME_FREE_CHANGES_PER_MONTH
from services.formatting import safe_html
from services.vip import is_vip_active
from services.cosmetics import get_active_cosmetics
from infrastructure.repositories.economy import get_item_quantity, remove_item
from infrastructure.repositories.users import set_nickname
from infrastructure.repositories import system_flags as _system_flags

router = APIRouter(prefix="/profile", tags=["profile"])

# Кэш аватарок Telegram на процесс (Implementation Block 3): фото меняется редко,
# дёргать Bot API на каждый рендер профиля незачем. Значение — (data_uri|None, ts).
_AVATAR_CACHE: dict[int, tuple[str | None, float]] = {}
_AVATAR_TTL = 6 * 3600  # 6 часов


async def _fetch_tg_avatar(user_id: int) -> str | None:
    """getUserProfilePhotos → getFile → скачать → data URI (jpeg).
    None, если нет токена/фото/приватность скрыла. Токен бота наружу не отдаём —
    картинку проксируем через свой эндпоинт."""
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return None
    api = f"https://api.telegram.org/bot{token}"
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get(f"{api}/getUserProfilePhotos",
                            params={"user_id": user_id, "limit": 1})
            data = r.json()
            if not data.get("ok") or data["result"].get("total_count", 0) == 0:
                return None
            # photos[0] — самый свежий снимок (список размеров); берём наименьший
            file_id = data["result"]["photos"][0][0]["file_id"]
            r2 = await c.get(f"{api}/getFile", params={"file_id": file_id})
            fdata = r2.json()
            if not fdata.get("ok"):
                return None
            file_path = fdata["result"]["file_path"]
            r3 = await c.get(f"https://api.telegram.org/file/bot{token}/{file_path}")
            if r3.status_code != 200 or not r3.content:
                return None
            b64 = base64.b64encode(r3.content).decode()
            return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return None


@router.get("/avatar")
async def my_avatar(db=Depends(get_db), user=Depends(require_tg_user)):
    """Аватарка из Telegram (data URI) — перк активного VIP. Иначе avatar=null.
    Кэш на процесс (6ч). Картинка проксируется, токен бота на фронт не уходит."""
    user_id = user["id"]
    if not await is_vip_active(db, user_id):
        return {"avatar": None, "vip": False}
    now = time.time()
    cached = _AVATAR_CACHE.get(user_id)
    if cached and now - cached[1] < _AVATAR_TTL:
        return {"avatar": cached[0], "vip": True}
    avatar = await _fetch_tg_avatar(user_id)
    _AVATAR_CACHE[user_id] = (avatar, now)
    return {"avatar": avatar, "vip": True}

# Единый источник правды для названий глобальных рангов — services/roles.py
# (та же таблица, что использует бот через get_global_rank_name).
_RANK_NAMES = GLOBAL_RANKS_MAP

_MIN_NICK_LEN = 2
_MAX_NICK_LEN = 20


@router.get("/me")
async def my_profile(db=Depends(get_db), user=Depends(require_tg_user)):
    """Полный профиль текущего пользователя."""
    user_id = user["id"]

    async with db.execute(
        "SELECT u.user_tg_id, u.user_tg_username, u.global_rank, "
        "u.user_balance_mora, u.user_balance_diamonds, "
        "COALESCE(u.user_balance_dark_mora, 0) AS user_balance_dark_mora, "
        "COALESCE(u.user_balance_zarniki, 0) AS user_balance_zarniki, "
        "(u.tos_accepted_at IS NOT NULL) AS tos_accepted, "
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

    # Партнёр по браку (как в боте: существование строки в marriages = в браке,
    # нет отдельной колонки status — см. infrastructure/repositories/marriages.get_user_marriage)
    async with db.execute(
        "SELECT p2.user_tg_username "
        "FROM marriages m "
        "JOIN users p2 ON p2.user_tg_id = CASE "
        "  WHEN m.user1_id = ? THEN m.user2_id ELSE m.user1_id END "
        "WHERE m.user1_id = ? OR m.user2_id = ? "
        "ORDER BY m.marriage_date DESC LIMIT 1",
        (user_id, user_id, user_id),
    ) as c:
        partner_row = await c.fetchone()
    partner = partner_row[0] if partner_row else None

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
        "tos_accepted": bool(row["tos_accepted"]),
        "global_rank":  row["global_rank"] or 0,
        "partner":      partner,
        "cosmetics":    await get_active_cosmetics(db, user_id),
        "system_flags": await _system_flags.get_all(db),
    }


@router.get("/u/{target_id}")
async def public_profile(target_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    """Глобальный публичный профиль игрока (БЛОК19 Часть3, GlobalUserProfile).
    БЕЗ балансов (приватны) — только публичная витрина: ранг, уровень, стрик, ачивки,
    клан, питомцы, надетая косметика."""
    async with db.execute(
        "SELECT u.user_tg_id, u.user_tg_username, u.global_rank, "
        "(v.user_id IS NOT NULL) AS is_vip "
        "FROM users u "
        "LEFT JOIN vip_subscriptions v ON v.user_id = u.user_tg_id AND v.expires_at > NOW() "
        "WHERE u.user_tg_id = ?",
        (target_id,),
    ) as c:
        row = await c.fetchone()
    if not row:
        raise HTTPException(404, "Игрок не найден.")

    async with db.execute(
        "SELECT COALESCE(MAX(user_level), 1) AS lvl, "
        "COALESCE(SUM(user_messages_count_all_time), 0) AS msgs "
        "FROM user_chat_stats WHERE user_tg_id = ?",
        (target_id,),
    ) as c:
        agg = dict(await c.fetchone())

    async with db.execute(
        "SELECT name, species_id, rarity, placement, COALESCE(pet_level, 1) AS pet_level "
        "FROM pets WHERE owner_id = ? "
        "ORDER BY (placement = 'active') DESC, COALESCE(pet_level,1) DESC LIMIT 12",
        (target_id,),
    ) as c:
        pets = [dict(r) for r in await c.fetchall()]

    streak_row = await get_global_streak(db, target_id)
    streak = streak_row["streak"]
    async with db.execute(
        "SELECT COUNT(*) FROM achievements WHERE user_id = ? AND level > 0", (target_id,)
    ) as c:
        ach = (await c.fetchone())[0]

    from infrastructure.repositories import clans as clans_repo
    clan = await clans_repo.get_user_clan(db, target_id)
    return {
        "user_id":      target_id,
        "username":     row["user_tg_username"] or f"id{target_id}",
        "rank":         _RANK_NAMES.get(row["global_rank"] or 0, "👤 Пользователь"),
        "global_rank":  row["global_rank"] or 0,
        "level":        agg["lvl"],
        "messages":     int(agg["msgs"] or 0),
        "streak":       streak,
        "achievements": ach,
        "is_vip":       bool(row["is_vip"]),
        "pets":         pets,
        "clan":         ({"name": clan["name"], "tag": clan["tag"],
                          "emblem": clan["emblem"], "role": clan["role"]} if clan else None),
        "cosmetics":    await get_active_cosmetics(db, target_id),
    }


class NicknameRequest(BaseModel):
    chat_id: int
    nickname: str


@router.post("/set-nickname")
async def set_nickname_endpoint(body: NicknameRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Установить ник в чате (2–20 символов, без HTML-тегов)."""
    nick = body.nickname.strip()
    user_id = user["id"]
    chat_id = body.chat_id

    if len(nick) < _MIN_NICK_LEN:
        raise HTTPException(400, f"Ник слишком короткий. Минимум {_MIN_NICK_LEN} символа.")
    if len(nick) > _MAX_NICK_LEN:
        raise HTTPException(400, f"Ник слишком длинный. Максимум {_MAX_NICK_LEN} символов.")
    if safe_html(nick) != nick:
        raise HTTPException(400, "Ник содержит недопустимые символы (< > & \").")
    if chat_id == 0:
        raise HTTPException(400, "Нужен ID чата.")

    async with db.execute(
        "SELECT 1 FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (user_id, chat_id),
    ) as c:
        if not await c.fetchone():
            raise HTTPException(400, "Вы не состоите в этом чате.")

    # Uniqueness check (case-insensitive, per chat)
    async with db.execute(
        "SELECT user_id FROM user_nicknames WHERE chat_id = ? AND LOWER(nickname) = LOWER(?)",
        (chat_id, nick),
    ) as c:
        existing = await c.fetchone()
    if existing and existing[0] != user_id:
        raise HTTPException(400, "Этот ник уже занят в данном чате.")

    # Monthly change limit — VIP = unlimited, zarniki_nickname_token = bypass
    is_vip = await is_vip_active(db, user_id)
    use_token = False
    count = 0
    reset_at = None
    if not is_vip:
        async with db.execute(
            "SELECT nickname_changes_count, nickname_changes_reset_at "
            "FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
        # nickname_changes_reset_at — TIMESTAMP без зоны (naive); asyncpg падает
        # с "can't subtract offset-naive and offset-aware datetimes" при записи
        # aware-значения в naive-колонку. now/reset_at держим naive — сравниваем
        # только .year/.month (это просто int-атрибуты, awareness не важна).
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        count = row[0] if row else 0
        reset_at = row[1] if row else now
        if reset_at.tzinfo is not None:
            reset_at = reset_at.replace(tzinfo=None)
        if not reset_at or (now.year, now.month) != (reset_at.year, reset_at.month):
            count = 0
            reset_at = now
        if count >= NICKNAME_FREE_CHANGES_PER_MONTH:
            if await get_item_quantity(db, user_id, "zarniki_nickname_token") > 0:
                use_token = True
            else:
                raise HTTPException(
                    400,
                    f"Лимит смены ника исчерпан ({NICKNAME_FREE_CHANGES_PER_MONTH}/мес в этом чате). "
                    "Сброс в начале следующего месяца. "
                    "Оформи VIP или используй Жетон смены ника.",
                )

    await set_nickname(db, user_id, chat_id, nick)
    if not is_vip:
        if use_token:
            await remove_item(db, user_id, "zarniki_nickname_token", 1)
        else:
            await db.execute(
                "INSERT INTO user_chat_stats "
                "(user_tg_id, chat_tg_id, nickname_changes_count, nickname_changes_reset_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (user_tg_id, chat_tg_id) DO UPDATE "
                "SET nickname_changes_count = ?, nickname_changes_reset_at = ?",
                (user_id, chat_id, count + 1, reset_at, count + 1, reset_at),
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
