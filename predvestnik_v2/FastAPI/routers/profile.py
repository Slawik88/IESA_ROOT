"""FastAPI/routers/profile.py — профиль игрока.
Тонкий адаптер: только вызовы infrastructure/, только JSON.
"""
import os
import json
import base64
import time
import asyncio
from datetime import date, datetime, timedelta, timezone
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.streak import get_global_streak
from services.roles import GLOBAL_RANKS_MAP
from core.constants import NICKNAME_FREE_CHANGES_PER_MONTH
from services.leveling import account_progress
from services.formatting import safe_html
from services.vip import is_vip_active, get_vip_info
from services.cosmetics import get_active_cosmetics, get_fitting_cosmetics
from services.global_skins_v1 import state as global_skin_state
from infrastructure.repositories.economy import get_item_quantity, remove_item
from infrastructure.repositories.users import set_nickname, get_first_seen
from infrastructure.repositories.achievements import get_all_achievements
from infrastructure.repositories import system_flags as _system_flags
from infrastructure.repositories import global_moderation as gmod_repo
from services.global_moderation import SANCTION_LABELS
from core.registry import ACHIEVEMENTS
from core.sky_v1 import NODE_BY_ID, SIGIL_IDS
from infrastructure.repositories import sky_v1 as sky_repo
from infrastructure.repositories import public_profiles_v1 as public_profiles
from infrastructure.repositories import echo_shards_v1 as echo_shards
from infrastructure.repositories import achievements_v1 as achievements_v1_repo
from infrastructure.repositories import mafia_v1 as mafia_v1_repo
from infrastructure.repositories import minesweeper_v2 as minesweeper_v2_repo
from infrastructure.repositories import pets_v1 as pets_v1_repo
from infrastructure.repositories import rhythm_v2 as rhythm_v2_repo
from core import achievements_v1 as achievement_rules

router = APIRouter(prefix="/profile", tags=["profile"])

# Кэш аватарок Telegram на процесс (Implementation Block 3): фото меняется редко,
# дёргать Bot API на каждый рендер профиля незачем. Значение — (data_uri|None, ts).
_AVATAR_CACHE: dict[int, tuple[str | None, float]] = {}
_AVATAR_TTL = 6 * 3600  # 6 часов


async def _sky_sigil(db, user_id: int) -> dict | None:
    """Public cosmetic projection; never materializes feats or progression."""
    if not await is_vip_active(db, user_id):
        return None
    try:
        allocated, sigil, _, _ = sky_repo.decode(await sky_repo.get_state(db, int(user_id)))
    except Exception:
        return None
    if sigil not in SIGIL_IDS or sigil not in allocated:
        return None
    node = NODE_BY_ID[sigil]
    return {"id": sigil, "name": node["name"], "branch": node["branch"]}


async def _supporter_badge(db, user_id: int) -> dict | None:
    # Supporter seals are cosmetic too: ownership is retained, but they are not
    # displayed on a public profile while the VIP display entitlement is idle.
    if not await is_vip_active(db, user_id):
        return None
    try:
        from services.supporter_cosmetics_v1 import active_public
        return await active_public(db, int(user_id))
    except Exception:
        return None


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


async def _vip_avatar(db, user_id: int) -> str | None:
    """Data-URI аватарки Telegram, если у игрока АКТИВНЫЙ VIP (перк); иначе None.
    Кэш на процесс (6ч), картинка уже проксирована в data-URI (токен бота наружу
    не уходит). Используется и для своего профиля (/avatar), и для публичной
    карточки чужого VIP-игрока (/u/{id}) — VIP оплатил, аватарку показываем везде."""
    if not await is_vip_active(db, user_id):
        return None
    now = time.time()
    cached = _AVATAR_CACHE.get(user_id)
    if cached and now - cached[1] < _AVATAR_TTL:
        return cached[0]
    avatar = await _fetch_tg_avatar(user_id)
    _AVATAR_CACHE[user_id] = (avatar, now)
    return avatar


@router.get("/avatar")
async def my_avatar(db=Depends(get_db), user=Depends(require_tg_user)):
    """Аватарка из Telegram (data URI) — перк активного VIP. Иначе avatar=null."""
    vip = await is_vip_active(db, user["id"])
    avatar = await _vip_avatar(db, user["id"]) if vip else None
    return {"avatar": avatar, "vip": vip}

# Единый источник правды для названий глобальных рангов — services/roles.py
# (та же таблица, что использует бот через get_global_rank_name).
_RANK_NAMES = GLOBAL_RANKS_MAP

_MIN_NICK_LEN = 2
_MAX_NICK_LEN = 20
_PROFILE_TABLES_READY = False
_PROFILE_TABLES_LOCK = asyncio.Lock()


async def _ensure_profile_tables(db) -> None:
    """Rolling-deploy guard for profile readers when ASGI lifespan is off."""
    global _PROFILE_TABLES_READY
    if _PROFILE_TABLES_READY:
        return
    async with _PROFILE_TABLES_LOCK:
        if _PROFILE_TABLES_READY:
            return
        for ensure in (
            rhythm_v2_repo.ensure_tables,
            minesweeper_v2_repo.ensure_tables,
            mafia_v1_repo.ensure_tables,
            pets_v1_repo.ensure_tables,
            achievements_v1_repo.ensure_tables,
        ):
            await ensure(db)
        _PROFILE_TABLES_READY = True


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


async def _profile_pets(db, user_id: int) -> list[dict]:
    """Current pet-v1 projection without legacy fatigue/placement fields."""
    async with db.execute(
        "SELECT p.name,p.rarity,COALESCE(s.level,1) AS level,"
        "(pv.active_pet_id=p.id) AS active "
        "FROM pets p "
        "LEFT JOIN pet_v1_state s ON s.user_id=p.owner_id AND s.pet_id=p.id "
        "LEFT JOIN pet_v1_profiles pv ON pv.user_id=p.owner_id "
        "WHERE p.owner_id=? ORDER BY (pv.active_pet_id=p.id) DESC,p.created_at,p.id LIMIT 24",
        (int(user_id),),
    ) as cursor:
        return [
            {
                "name": row["name"] or "Питомец",
                "rarity": row["rarity"],
                "level": int(row["level"] or 1),
                "active": bool(row["active"]),
            }
            for row in await cursor.fetchall()
        ]


async def _achievement_paths(db, user_id: int) -> dict:
    """Small public-safe summary of the current 1–40 achievement families."""
    async with db.execute(
        "SELECT family,completed_events,active_weeks,level "
        "FROM achievement_v1_progress WHERE user_id=?",
        (int(user_id),),
    ) as cursor:
        rows = {str(row["family"]): dict(row) for row in await cursor.fetchall()}
    families = []
    for family, definition in achievement_rules.FAMILIES.items():
        row = rows.get(family) or {}
        families.append({
            "id": family,
            "title": definition["title"],
            "level": int(row.get("level") or 0),
            "max_level": achievement_rules.MAX_LEVEL,
            "completed_events": int(row.get("completed_events") or 0),
            "active_weeks": int(row.get("active_weeks") or 0),
        })
    return {"total_levels": sum(item["level"] for item in families), "families": families}


async def _game_results(db, user_id: int, *, include_private: bool) -> dict:
    """Results from the three approved games; Rhythm trust stays explicit."""
    async with db.execute(
        "SELECT "
        "COUNT(*) FILTER (WHERE status='finished' AND integrity_status='clear') AS verified_runs,"
        "MAX(score) FILTER (WHERE status='finished' AND integrity_status='clear') AS best_verified_score,"
        "COUNT(*) FILTER (WHERE status='finished' AND integrity_status<>'clear') AS unranked_runs "
        "FROM rhythm_v2_runs WHERE user_id=?",
        (int(user_id),),
    ) as cursor:
        rhythm = dict(await cursor.fetchone())
    rhythm_view = {
        "verified_runs": int(rhythm.get("verified_runs") or 0),
        "best_verified_score": int(rhythm["best_verified_score"]) if rhythm.get("best_verified_score") is not None else None,
    }
    if include_private:
        rhythm_view["personal_unranked_runs"] = int(rhythm.get("unranked_runs") or 0)

    async with db.execute(
        "SELECT COUNT(*) FILTER (WHERE status IN ('won','lost')) AS played,"
        "COUNT(*) FILTER (WHERE status='won') AS wins,"
        "MIN(elapsed_ms) FILTER (WHERE status='won' AND difficulty='easy') AS easy_best_ms,"
        "MIN(elapsed_ms) FILTER (WHERE status='won' AND difficulty='normal') AS normal_best_ms,"
        "MIN(elapsed_ms) FILTER (WHERE status='won' AND difficulty='hard') AS hard_best_ms "
        "FROM minesweeper_v2_runs WHERE user_id=?",
        (int(user_id),),
    ) as cursor:
        mines = dict(await cursor.fetchone())

    async with db.execute(
        "SELECT COUNT(*) FILTER (WHERE m.phase='finished') AS played,"
        "COUNT(*) FILTER (WHERE m.phase='finished' AND "
        "((m.winner='mafia' AND p.role IN ('mafia','don')) OR "
        "(m.winner='town' AND p.role IN ('citizen','doctor','detective')))) AS wins "
        "FROM mafia_v1_players p JOIN mafia_v1_matches m ON m.id=p.match_id WHERE p.user_id=?",
        (int(user_id),),
    ) as cursor:
        mafia = dict(await cursor.fetchone())

    def _best(key: str) -> int | None:
        return int(mines[key]) if mines.get(key) is not None else None

    return {
        "rhythm": rhythm_view,
        "minesweeper": {
            "played": int(mines.get("played") or 0),
            "wins": int(mines.get("wins") or 0),
            "best_ms": {"easy": _best("easy_best_ms"), "normal": _best("normal_best_ms"), "hard": _best("hard_best_ms")},
        },
        "mafia": {"played": int(mafia.get("played") or 0), "wins": int(mafia.get("wins") or 0)},
    }


async def _compensation_receipt(db, user_id: int) -> dict | None:
    compensation = None
    try:
        # This one-off migration table is intentionally absent from a fresh
        # isolated database. Avoid an error-level query on every profile poll.
        async with db.execute(
            "SELECT to_regclass('retirement_compensation_receipts_v2')"
        ) as c:
            if not (await c.fetchone())[0]:
                return None
        async with db.execute(
            "SELECT to_jsonb(r) FROM retirement_compensation_receipts_v2 r "
            "WHERE user_id=? ORDER BY applied_at DESC LIMIT 1",
            (user_id,),
        ) as c:
            compensation_row = await c.fetchone()
        if compensation_row:
            raw_compensation = compensation_row[0]
            compensation = json.loads(raw_compensation) if isinstance(raw_compensation, str) else dict(raw_compensation)
            compensation["applied_at"] = _iso(compensation["applied_at"])
            compensation["zarniki_added"] = sum(int(compensation[key] or 0) for key in (
                "cosmetics_zarniki", "themes_zarniki", "donate_inventory_zarniki",
                "retired_exchange_zarniki"))
            compensation["vip_preserved_days"] = round(int(compensation.get("vip_preserved_seconds") or 0) / 86400, 2)
            compensation["vip_bonus_days"] = round(int(compensation.get("vip_bonus_seconds") or 0) / 86400, 2)
    except Exception:
        # The one-off production receipt table may not exist in an older
        # isolated database. Compensation UI is optional; profile is not.
        raw = getattr(db, "connection", None)
        if raw is not None:
            try:
                if raw.is_in_transaction():
                    await raw.execute("ROLLBACK")
            except Exception:
                pass

    return compensation


async def _sanctions(db, user_id: int, *, include_private: bool) -> dict:
    """Owner-approved public projection; moderator/database identifiers omitted."""
    active_row = await gmod_repo.get_active_restriction(db, "user", int(user_id))
    active = None
    if active_row:
        active = {
            "type": active_row["sanction_type"],
            "label": SANCTION_LABELS.get(active_row["sanction_type"], active_row["sanction_type"]),
            **({"reason": active_row.get("reason")} if include_private else {}),
            "expires_at": _iso(active_row.get("expires_at")),
        }
    async with db.execute(
        "SELECT sanction_type,reason,created_at,expires_at,revoked_at "
        "FROM global_sanctions WHERE target_type='user' AND target_id=? "
        "ORDER BY id DESC LIMIT ?",
        (int(user_id), 50 if include_private else 20),
    ) as cursor:
        sanction_rows = [dict(row) for row in await cursor.fetchall()]
    history = [
        {
            "type": item["sanction_type"],
            "label": SANCTION_LABELS.get(item["sanction_type"], item["sanction_type"]),
            **({"reason": item.get("reason")} if include_private else {}),
            "created_at": _iso(item.get("created_at")),
            "expires_at": _iso(item.get("expires_at")),
            "revoked_at": _iso(item.get("revoked_at")),
        }
        for item in sanction_rows
    ]
    async with db.execute(
        "SELECT COALESCE(SUM(warnings),0) AS total_warnings,"
        "MAX(CASE WHEN muted_until>NOW() THEN muted_until END) AS mute_until "
        "FROM user_chat_stats WHERE user_tg_id=? AND is_left=FALSE",
        (int(user_id),),
    ) as cursor:
        chat = dict(await cursor.fetchone())
    return {
        "active_global": active,
        "history": history,
        "chat_warning_total": int(chat.get("total_warnings") or 0),
        "chat_mute_until": _iso(chat.get("mute_until")),
    }


@router.get("/me")
async def my_profile(db=Depends(get_db), user=Depends(require_tg_user)):
    """Полный профиль текущего пользователя."""
    user_id = user["id"]
    await _ensure_profile_tables(db)

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

    pets = await _profile_pets(db, user_id)

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
        "WHERE (m.user1_id = ? OR m.user2_id = ?) AND m.ended_at IS NULL "
        "ORDER BY m.marriage_date DESC LIMIT 1",
        (user_id, user_id, user_id),
    ) as c:
        partner_row = await c.fetchone()
    partner = partner_row[0] if partner_row else None

    async with db.execute(
        "SELECT COALESCE(SUM(user_messages_count_all_time),0) AS messages_all_time "
        "FROM user_chat_stats WHERE user_tg_id=?",
        (user_id,),
    ) as c:
        activity_row = dict(await c.fetchone())
    vip_info = await get_vip_info(db, user_id)
    joined_date = await get_first_seen(db, user_id)

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
        "echo_shards":  await echo_shards.get_balance(db, user_id),
        "streak":       (dict(streak_row)["streak"] or 0) if streak_row else 0,
        "achievements": ach_count,
        # R0: уровень аккаунта — глобальный, экспоненциальная кривая.
        # xp_per_level оставлен для обратной совместимости фронта = цена ТЕКУЩЕГО уровня.
        "account_level": _acc_prog["level"],
        "account_xp":    int(row["account_xp"] or 0),
        "xp_into":       _acc_prog["xp_into"],
        "xp_to_next":    _acc_prog["xp_need"],
        "xp_per_level":  _acc_prog["xp_need"] or 1,
        # Legacy CP is intentionally unavailable: it must not be recalculated
        # from retired units or presented as power in Reconstruction.
        "combat_power":  None,
        "cp_breakdown":  None,
        "chats":        chats,
        "pets":         pets,
        "is_vip":       bool(row["is_vip"]),
        "avatar":       await _vip_avatar(db, user_id),
        "tos_accepted": bool(row["tos_accepted"]),
        "global_rank":  row["global_rank"] or 0,
        "partner":      partner,
        "messages_all_time": int(activity_row.get("messages_all_time") or 0),
        "joined_date": _iso(joined_date),
        "vip": {
            "tier": vip_info["tier"],
            "label": vip_info["tier_label"],
            "days_left": vip_info["days_left"],
            "expires_at": _iso(vip_info["expires_at"]),
        } if vip_info else None,
        "compensation": await _compensation_receipt(db, user_id),
        "sanctions": await _sanctions(db, user_id, include_private=True),
        "game_results": await _game_results(db, user_id, include_private=True),
        "achievement_paths": await _achievement_paths(db, user_id),
        "cosmetics":    await get_active_cosmetics(db, user_id),
        "global_skin": await global_skin_state(db, user_id),
        "system_flags": await _system_flags.get_all(db),
        "whatsnew_seen_id": whatsnew_seen_id,
        "sky_sigil": await _sky_sigil(db, user_id),
        "supporter_badge": await _supporter_badge(db, user_id),
    }


@router.get("/me/chat-tracker")
async def my_chat_tracker(
    limit: int = 20,
    offset: int = 0,
    query: str = "",
    sort: str = "recent",
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    """Private, paged activity tracker for the current player's active chats.

    A tracker row is deliberately scoped by ``user_tg_id = current user``. It
    describes the player's own activity and moderation state in that chat; it
    is not a chat directory and never returns another member's statistics.
    """
    query = str(query or "").strip()
    sort_orders = {
        "recent": "ucs.last_message_at DESC NULLS LAST, ucs.user_messages_count_all_time DESC, ucs.chat_tg_id ASC",
        "week": "ucs.user_messages_count_per_week DESC, ucs.last_message_at DESC NULLS LAST, ucs.chat_tg_id ASC",
        "messages": "ucs.user_messages_count_all_time DESC, ucs.last_message_at DESC NULLS LAST, ucs.chat_tg_id ASC",
        "rank": "ucs.local_rank DESC NULLS LAST, ucs.last_message_at DESC NULLS LAST, ucs.chat_tg_id ASC",
    }
    if not 1 <= limit <= 30 or offset < 0 or len(query) > 64 or sort not in sort_orders:
        raise HTTPException(400, "Некорректные параметры страницы трекера.")
    user_id = int(user["id"])
    async with db.execute(
        "SELECT COUNT(*) AS chat_count, "
        "COALESCE(SUM(user_messages_count_all_time), 0) AS messages_all_time, "
        "COALESCE(SUM(user_messages_count_per_week), 0) AS messages_week "
        "FROM user_chat_stats WHERE user_tg_id = ? AND is_left = FALSE",
        (user_id,),
    ) as cursor:
        summary = dict(await cursor.fetchone())
    search_sql = " AND LOWER(COALESCE(cs.chat_title, '')) LIKE ? ESCAPE '\\'" if query else ""
    escaped_query = query.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    search_args = (f"%{escaped_query}%",) if query else ()
    async with db.execute(
        "SELECT COUNT(*) FROM user_chat_stats ucs "
        "LEFT JOIN chat_settings cs ON cs.chat_id=ucs.chat_tg_id "
        "WHERE ucs.user_tg_id=? AND ucs.is_left=FALSE" + search_sql,
        (user_id, *search_args),
    ) as cursor:
        filtered_count = int((await cursor.fetchone())[0] or 0)
    async with db.execute(
        "SELECT ucs.chat_tg_id, "
        "COALESCE(NULLIF(BTRIM(cs.chat_title), ''), 'Чат без названия') AS chat_title, "
        "ucs.user_level, ucs.user_xp, ucs.local_rank, "
        "ucs.user_messages_count_per_day, ucs.user_messages_count_per_week, "
        "ucs.user_messages_count_per_month, ucs.user_messages_count_all_time, "
        "ucs.last_message_at, ucs.membership_since, ucs.joined_at, "
        "ucs.warnings, ucs.muted_until "
        "FROM user_chat_stats ucs "
        "LEFT JOIN chat_settings cs ON cs.chat_id = ucs.chat_tg_id "
        "WHERE ucs.user_tg_id = ? AND ucs.is_left = FALSE " + search_sql +
        " ORDER BY " + sort_orders[sort] + " "
        "LIMIT ? OFFSET ?",
        (user_id, *search_args, limit, offset),
    ) as cursor:
        chats = [dict(row) for row in await cursor.fetchall()]
    chat_ids = [int(row["chat_tg_id"]) for row in chats]
    activity_dates: dict[int, set[date]] = {chat_id: set() for chat_id in chat_ids}
    sanction_history: dict[int, list[dict]] = {chat_id: [] for chat_id in chat_ids}
    if chat_ids:
        placeholders = ",".join("?" for _ in chat_ids)
        async with db.execute(
            f"SELECT chat_id,date FROM daily_user_stats WHERE user_id=? AND chat_id IN ({placeholders})",
            (user_id, *chat_ids),
        ) as cursor:
            for row in await cursor.fetchall():
                try:
                    activity_dates[int(row["chat_id"])].add(date.fromisoformat(str(row["date"])[:10]))
                except (TypeError, ValueError):
                    continue
        async with db.execute(
            "SELECT chat_id,action,created_at FROM ("
            "SELECT chat_id,action,created_at,ROW_NUMBER() OVER (PARTITION BY chat_id ORDER BY created_at DESC,id DESC) AS row_no "
            f"FROM moderation_logs WHERE user_id=? AND chat_id IN ({placeholders})"
            ") own_history WHERE row_no<=5 ORDER BY chat_id,created_at DESC",
            (user_id, *chat_ids),
        ) as cursor:
            for row in await cursor.fetchall():
                sanction_history[int(row["chat_id"])].append({
                    "action": str(row["action"] or "moderation"),
                    "created_at": _iso(row["created_at"]),
                })
    today = datetime.now(timezone.utc).date()
    for row in chats:
        chat_id = int(row.pop("chat_tg_id"))
        days = activity_dates.get(chat_id, set())
        cursor_day = today if today in days else today - timedelta(days=1)
        streak = 0
        while cursor_day in days:
            streak += 1
            cursor_day -= timedelta(days=1)
        row["activity_streak_days"] = streak
        row["sanction_history"] = sanction_history.get(chat_id, [])
    return {
        "summary": {
            "chat_count": int(summary["chat_count"] or 0),
            "messages_all_time": int(summary["messages_all_time"] or 0),
            "messages_week": int(summary["messages_week"] or 0),
        },
        "query": query,
        "sort": sort,
        "filtered_count": filtered_count,
        "items": chats,
        "next_offset": offset + len(chats) if offset + len(chats) < filtered_count else None,
    }


@router.get("/me/fitting-cosmetics")
async def my_fitting_cosmetics(db=Depends(get_db), user=Depends(require_tg_user)):
    """Private saved-look projection for the fitting room.

    This endpoint intentionally cannot inspect another player.  It is the only
    place where a non-VIP owner may see stored cosmetic identifiers and CSS;
    public profile endpoints always use the VIP-filtered projection.
    """
    return await get_fitting_cosmetics(db, int(user["id"]))


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


@router.get("/public/{profile_ref}")
async def public_profile(profile_ref: str, db=Depends(get_db), user=Depends(require_tg_user)):
    """Глобальная карточка игрока с owner-approved прозрачной статистикой.

    Это сознательно не «обрезанная визитка»: игра показывает другим игрокам те же
    игровые показатели, что видит владелец. Технические идентификаторы, данные
    сессии, платёжные идентификаторы и служебные поля модерации не возвращаются.
    """
    await _ensure_profile_tables(db)
    target_id = await public_profiles.resolve_reference(db, profile_ref=profile_ref)
    if target_id is None:
        raise HTTPException(404, "Игрок не найден.")
    async with db.execute(
        "SELECT u.user_tg_id, u.user_tg_username, u.global_rank, "
        "u.user_balance_mora, u.user_balance_diamonds, "
        "u.user_balance_dark_mora, u.user_balance_zarniki, "
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
    public_progress = account_progress(int(row["account_xp"] or 0))
    agg["lvl"] = public_progress["level"]

    pets = await _profile_pets(db, target_id)

    streak_row = await get_global_streak(db, target_id)
    streak = streak_row["streak"]
    async with db.execute(
        "SELECT COUNT(*) FROM achievements WHERE user_id = ? AND level > 0", (target_id,)
    ) as c:
        ach = (await c.fetchone())[0]

    from infrastructure.repositories import clans as clans_repo
    clan = await clans_repo.get_user_clan(db, target_id)

    sanctions = await _sanctions(db, target_id, include_private=False)

    # Партнёр, историческая лучшая ачивка, VIP и стаж остаются видимыми; игровые
    # результаты ниже берутся только из трёх утверждённых v1/v2 систем.
    async with db.execute(
        "SELECT 1 "
        "FROM marriages m "
        "JOIN users p2 ON p2.user_tg_id = CASE "
        "  WHEN m.user1_id = ? THEN m.user2_id ELSE m.user1_id END "
        "WHERE (m.user1_id = ? OR m.user2_id = ?) AND m.ended_at IS NULL "
        "ORDER BY m.marriage_date DESC LIMIT 1",
        (target_id, target_id, target_id),
    ) as c:
        partner_row = await c.fetchone()
    partner = "Есть" if partner_row else None

    all_ach = await get_all_achievements(db, target_id)
    best_achievement = None
    best_level = 0
    for aid, a in all_ach.items():
        if a["level"] > best_level and aid in ACHIEVEMENTS:
            best_level = a["level"]
            best_achievement = {"icon": ACHIEVEMENTS[aid]["icon"], "name": ACHIEVEMENTS[aid]["name"], "level": a["level"]}

    vip_info = await get_vip_info(db, target_id)

    joined_date = await get_first_seen(db, target_id)

    return {
        "profile_ref":  profile_ref,
        "display_name": public_profiles.display_name(row["user_tg_username"], profile_ref),
        "rank":         _RANK_NAMES.get(row["global_rank"] or 0, "👤 Пользователь"),
        "balances": {
            "mora": float(row["user_balance_mora"] or 0),
            "diamonds": float(row["user_balance_diamonds"] or 0),
            "dark_mora": float(row["user_balance_dark_mora"] or 0),
            "zarniki": float(row["user_balance_zarniki"] or 0),
            "echo_shards": await echo_shards.get_balance(db, target_id),
        },
        "account_level": agg["lvl"],
        "account_xp": int(row["account_xp"] or 0),
        "xp_into": int(public_progress["xp_into"]),
        "xp_to_next": int(public_progress["xp_need"]),
        "messages_all_time": int(agg["msgs"] or 0),
        "streak":       streak,
        "achievements": ach,
        "pets": pets,
        "clan": ({
            "name": clan.get("name"),
            "tag": clan.get("tag"),
            "emblem": clan.get("emblem"),
            "role": clan.get("role"),
        } if clan else None),
        "partner": partner,
        "best_achievement": best_achievement,
        "joined_date": _iso(joined_date),
        "sanctions": sanctions,
        "game_results": await _game_results(db, target_id, include_private=False),
        "achievement_paths": await _achievement_paths(db, target_id),
        "is_vip":       bool(row["is_vip"]),
        "vip": {
            "tier": vip_info["tier"],
            "label": vip_info["tier_label"],
            "days_left": vip_info["days_left"],
        } if vip_info else None,
        # VIP оплатил живую аватарку — показываем её и в его публичной карточке
        # (раньше у чужого VIP там висела только корона-заглушка).
        "avatar":       await _vip_avatar(db, target_id),
        "cosmetics":    await get_active_cosmetics(db, target_id),
        "sky_sigil":     await _sky_sigil(db, target_id),
        "supporter_badge": await _supporter_badge(db, target_id),
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


# ── Настройки актуальных персональных DM-уведомлений ───────────────────────────

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
