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
from services.leveling import account_progress
from services.combat_power import calculate_cp
from services.formatting import safe_html
from services.vip import is_vip_active, get_vip_info
from services.cosmetics import get_active_cosmetics
from infrastructure.repositories.economy import get_item_quantity, remove_item
from infrastructure.repositories.users import set_nickname, get_first_seen
from infrastructure.repositories.achievements import get_achievement, get_all_achievements
from infrastructure.repositories import system_flags as _system_flags
from infrastructure.repositories import global_moderation as gmod_repo
from services.global_moderation import SANCTION_LABELS
from core.registry import ACHIEVEMENTS

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
        "COALESCE(u.account_xp, 0) AS account_xp, "
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

    _acc_prog = account_progress(int(row["account_xp"] or 0))
    # R1: Индекс Силы — свежий расчёт + обновление кэша (users.combat_power)
    _cp = await calculate_cp(db, user_id)
    await db.execute(
        "UPDATE users SET combat_power = ? WHERE user_tg_id = ?",
        (_cp["total"], user_id),
    )

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

    # whatsnew_seen_id вынесен из основного запроса и достаётся отдельно с мягкой
    # деградацией: колонка создаётся миграцией init_db, но на проде FastAPI работает
    # с lifespan="off", а деплой кода мог опередить рестарт бота с миграцией. Раньше
    # ссылка на неё в основном SELECT роняла ВЕСЬ /profile/me в 500 — теперь профиль
    # грузится, а поле деградирует в None (лента максимум разово покажет «Новое»).
    whatsnew_seen_id = None
    try:
        async with db.execute(
            "SELECT whatsnew_seen_id FROM users WHERE user_tg_id = ?", (user_id,)
        ) as c:
            _wn = await c.fetchone()
        whatsnew_seen_id = _wn[0] if _wn else None
    except Exception:
        raw = getattr(db, "connection", None)  # снять возможный aborted-tx
        if raw is not None:
            try:
                if raw.is_in_transaction():
                    await raw.execute("ROLLBACK")
            except Exception:
                pass

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
        # R0: уровень аккаунта — глобальный, экспоненциальная кривая.
        # xp_per_level оставлен для обратной совместимости фронта = цена ТЕКУЩЕГО уровня.
        "account_level": _acc_prog["level"],
        "account_xp":    int(row["account_xp"] or 0),
        "xp_into":       _acc_prog["xp_into"],
        "xp_to_next":    _acc_prog["xp_need"],
        "xp_per_level":  _acc_prog["xp_need"] or 1,
        "combat_power":  _cp["total"],
        "cp_breakdown":  _cp,
        "chats":        chats,
        "pets":         pets,
        "is_vip":       bool(row["is_vip"]),
        "tos_accepted": bool(row["tos_accepted"]),
        "global_rank":  row["global_rank"] or 0,
        "partner":      partner,
        "cosmetics":    await get_active_cosmetics(db, user_id),
        "system_flags": await _system_flags.get_all(db),
        "whatsnew_seen_id": whatsnew_seen_id,
    }


class WhatsNewSeenRequest(BaseModel):
    seen_id: str = ""


@router.post("/whatsnew-seen")
async def set_whatsnew_seen(body: WhatsNewSeenRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Отметить ленту «Что нового» прочитанной до записи seen_id (сервер — источник
    правды вместо localStorage, который Telegram WebView не гарантирует сохранным)."""
    # Мягко: если колонки ещё нет на этом процессе (деплой опередил миграцию бота),
    # не роняем запрос — отметка «прочитано» просто не сохранится до появления колонки.
    try:
        await db.execute(
            "UPDATE users SET whatsnew_seen_id = ? WHERE user_tg_id = ?",
            (body.seen_id, user["id"]),
        )
        await db.commit()
    except Exception:
        raw = getattr(db, "connection", None)
        if raw is not None:
            try:
                if raw.is_in_transaction():
                    await raw.execute("ROLLBACK")
            except Exception:
                pass
        return {"ok": False, "pending_migration": True}
    return {"ok": True}


@router.get("/u/{target_id}")
async def public_profile(target_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    """Глобальный публичный профиль игрока (БЛОК19 Часть3, GlobalUserProfile).
    БЕЗ балансов (приватны) — только публичная витрина: ранг, уровень, стрик, ачивки,
    клан, питомцы, надетая косметика."""
    async with db.execute(
        "SELECT u.user_tg_id, u.user_tg_username, u.global_rank, "
        "COALESCE(u.account_xp, 0) AS account_xp, "
        "(v.user_id IS NOT NULL) AS is_vip "
        "FROM users u "
        "LEFT JOIN vip_subscriptions v ON v.user_id = u.user_tg_id AND v.expires_at > NOW() "
        "WHERE u.user_tg_id = ?",
        (target_id,),
    ) as c:
        row = await c.fetchone()
    if not row:
        raise HTTPException(404, "Игрок не найден.")

    # R0: публичный уровень — уровень аккаунта (та же кривая, что в /me и боте)
    async with db.execute(
        "SELECT COALESCE(SUM(user_messages_count_all_time), 0) AS msgs "
        "FROM user_chat_stats WHERE user_tg_id = ?",
        (target_id,),
    ) as c:
        agg = dict(await c.fetchone())
    agg["lvl"] = account_progress(int(row["account_xp"] or 0))["level"]

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

    # Глобальные санкции (варн/ресракт/бан) видны ВСЕМ в публичном профиле —
    # прозрачность модерации, а не только приватный блок экономических команд.
    sanction_row = await gmod_repo.get_active_restriction(db, "user", target_id)
    sanction = None
    if sanction_row:
        sanction = {
            "type":       sanction_row["sanction_type"],   # "restrict" | "ban"
            "label":      SANCTION_LABELS.get(sanction_row["sanction_type"], sanction_row["sanction_type"]),
            "reason":     sanction_row.get("reason"),
            "expires_at": sanction_row["expires_at"].isoformat() if sanction_row.get("expires_at") else None,
        }

    # Локальные санкции (варны/мут по чатам, где ещё состоит) — суммарно, без
    # привязки к конкретному чату (профиль глобальный). Более мягкий сигнал,
    # чем глобальная санкция выше, но тоже должен быть виден всем.
    async with db.execute(
        "SELECT COALESCE(SUM(warnings), 0) AS total_warnings, "
        "MAX(CASE WHEN muted_until > NOW() THEN muted_until END) AS mute_until "
        "FROM user_chat_stats WHERE user_tg_id = ? AND is_left = FALSE",
        (target_id,),
    ) as c:
        chat_sanc = dict(await c.fetchone())
    mute_until = chat_sanc.get("mute_until")

    # «Настоящий профиль»: партнёр по браку (публично, как и в /me), побед в дуэлях
    # (raw-прогресс метрики duel_wins, не капается порогами ачивки), лучшая ачивка
    # (по уровню, для престиж-бейджа), VIP-тир (не просто корона), этаж Врат (лучший
    # пройденный), дата первого сообщения (стаж игрока) — см. brainstorm 2026-07-23.
    async with db.execute(
        "SELECT p2.user_tg_username "
        "FROM marriages m "
        "JOIN users p2 ON p2.user_tg_id = CASE "
        "  WHEN m.user1_id = ? THEN m.user2_id ELSE m.user1_id END "
        "WHERE m.user1_id = ? OR m.user2_id = ? "
        "ORDER BY m.marriage_date DESC LIMIT 1",
        (target_id, target_id, target_id),
    ) as c:
        partner_row = await c.fetchone()
    partner = partner_row[0] if partner_row else None

    duel_ach = await get_achievement(db, target_id, "duelist")
    duel_wins = int(duel_ach["progress"]) if duel_ach else 0

    all_ach = await get_all_achievements(db, target_id)
    best_achievement = None
    best_level = 0
    for aid, a in all_ach.items():
        if a["level"] > best_level and aid in ACHIEVEMENTS:
            best_level = a["level"]
            best_achievement = {"icon": ACHIEVEMENTS[aid]["icon"], "name": ACHIEVEMENTS[aid]["name"], "level": a["level"]}

    vip_info = await get_vip_info(db, target_id)

    async with db.execute(
        "SELECT MAX(ref_id) FROM battles WHERE user_id = ? AND mode = 'gates' AND status = 'won'",
        (target_id,),
    ) as c:
        gates_row = await c.fetchone()
    gates_floor = int(gates_row[0]) if gates_row and gates_row[0] else 0

    joined_date = await get_first_seen(db, target_id)

    return {
        "user_id":      target_id,
        "username":     row["user_tg_username"] or f"id{target_id}",
        "rank":         _RANK_NAMES.get(row["global_rank"] or 0, "👤 Пользователь"),
        "global_rank":  row["global_rank"] or 0,
        "level":        agg["lvl"],
        "combat_power": (await calculate_cp(db, target_id))["total"],
        "messages":     int(agg["msgs"] or 0),
        "streak":       streak,
        "achievements": ach,
        "achievements_total": len(ACHIEVEMENTS),
        "best_achievement": best_achievement,
        "is_vip":       bool(row["is_vip"]),
        "vip_tier_label": vip_info["tier_label"] if vip_info else None,
        "gates_floor":  gates_floor,
        "joined_date":  joined_date,
        "partner":      partner,
        "duel_wins":    duel_wins,
        "pets":         pets,
        "clan":         ({"name": clan["name"], "tag": clan["tag"],
                          "emblem": clan["emblem"], "role": clan["role"]} if clan else None),
        "cosmetics":    await get_active_cosmetics(db, target_id),
        "sanction":     sanction,
        "chat_warnings": int(chat_sanc.get("total_warnings") or 0),
        "muted_until":   mute_until.isoformat() if mute_until else None,
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


# ── R6 «Умный Пульс»: настройки персональных DM-уведомлений ────────────────────
# Закрывает дыру БЛОК 36.1: раньше vip_expiry/bp_reminder нельзя было отключить
# нигде (бот-хендлер мёртв, веб-UI не существовал).

class NotifPrefRequest(BaseModel):
    category: str
    enabled: bool


@router.get("/notification-prefs")
async def get_notification_prefs(db=Depends(get_db), user=Depends(require_tg_user)):
    from core.constants import NOTIFICATION_CATEGORIES
    from infrastructure.repositories import notifications as notif_repo
    prefs = await notif_repo.get_prefs(db, user["id"])
    return {
        "categories": [
            {"key": k, "label": v, "enabled": prefs.get(k, True)}
            for k, v in NOTIFICATION_CATEGORIES.items()
        ]
    }


@router.post("/notification-prefs")
async def set_notification_pref(body: NotifPrefRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    from core.constants import NOTIFICATION_CATEGORIES
    from infrastructure.repositories import notifications as notif_repo
    if body.category not in NOTIFICATION_CATEGORIES:
        raise HTTPException(400, "Неизвестная категория уведомлений.")
    await notif_repo.set_pref(db, user["id"], body.category, body.enabled)
    return {"ok": True, "category": body.category, "enabled": body.enabled}
