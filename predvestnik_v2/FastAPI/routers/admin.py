"""FastAPI/routers/admin.py — панель модератора."""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.moderation import (
    get_chat_settings, update_chat_settings, add_warn, remove_warn,
    log_moderation_action, set_immunity, get_left_users,
)
from infrastructure.repositories.blacklist import (
    get_chat_blacklist, add_to_chat_blacklist, remove_from_chat_blacklist,
)
from infrastructure.repositories.chat import set_local_rank
from infrastructure.repositories.routing import get_admin_chat
from services import roles

router = APIRouter(prefix="/admin", tags=["admin"])

DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", "0") or 0)

_LOCAL_RANK_NAMES = {
    0: "👤 Пользователь", 1: "👁 Модератор", 2: "👮 Мл.Админ",
    3: "👮 Админ", 4: "🕵️ Ст.Админ", 5: "👑 Совладелец", 6: "👑 Владелец",
}


async def _get_actor_rank(db, user_id: int, chat_id: int) -> int:
    # 8.0: Developer bypass — панель работает в ЛЮБОМ чате даже без строки user_chat_stats
    if DEVELOPER_ID and user_id == DEVELOPER_ID:
        return 6  # Владелец в любом чате
    async with db.execute(
        "SELECT local_rank FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (user_id, chat_id),
    ) as c:
        row = await c.fetchone()
    # row[0] может быть NULL у старых строк (как и ucs.local_rank в admin_users) —
    # без `or 0` `_require_admin` сравнивает None < 1 → TypeError → 500.
    return (row[0] or 0) if row else 0


async def _require_admin(db, user_id: int, chat_id: int) -> int:
    rank = await _get_actor_rank(db, user_id, chat_id)
    if rank < 1:
        raise HTTPException(403, "Нет прав модератора в этом чате.")
    return rank


async def _tg_call(method: str, **kwargs) -> dict:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return {"ok": False, "error": "no token"}
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/{method}", json=kwargs)
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/my-chats")
async def my_admin_chats(db=Depends(get_db), user=Depends(require_tg_user)):
    """Только РЕАЛЬНЫЕ группы (chat_id < 0, есть название), где пользователь
    состоит (is_left=FALSE) и имеет права модератора (local_rank >= 1).
    Без «фантомных чатов-цифр» и без показа всех чатов бота.
    Размечает связь Основная↔Админская группа (chat_links)."""
    async with db.execute(
        "SELECT ucs.chat_tg_id, COALESCE(cs.chat_title, CAST(ucs.chat_tg_id AS TEXT)) AS chat_title, "
        "ucs.local_rank, lk.admin_chat_id "
        "FROM user_chat_stats ucs "
        "LEFT JOIN chat_settings cs ON cs.chat_id = ucs.chat_tg_id "
        "LEFT JOIN chat_links lk ON lk.main_chat_id = ucs.chat_tg_id "
        "WHERE ucs.user_tg_id = ? AND ucs.local_rank >= 1 AND ucs.is_left = FALSE "
        "AND ucs.chat_tg_id < 0 AND cs.chat_title IS NOT NULL "
        "ORDER BY ucs.local_rank DESC",
        (user["id"],),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]

    chat_ids = [r["chat_tg_id"] for r in rows]
    # Какие из этих чатов сами являются админ-чатами для какой-то основной группы
    serves: dict = {}
    if chat_ids:
        ph = ",".join("?" * len(chat_ids))
        async with db.execute(
            f"SELECT main_chat_id, admin_chat_id FROM chat_links WHERE admin_chat_id IN ({ph})",
            tuple(chat_ids),
        ) as c:
            for lk in await c.fetchall():
                serves[lk["admin_chat_id"]] = lk["main_chat_id"]

    # Заголовки связанных чатов (основных и админских)
    linked_ids = {r["admin_chat_id"] for r in rows if r["admin_chat_id"]} | set(serves.values())
    titles: dict = {}
    if linked_ids:
        ph = ",".join("?" * len(linked_ids))
        async with db.execute(
            f"SELECT chat_id, chat_title FROM chat_settings WHERE chat_id IN ({ph})",
            tuple(linked_ids),
        ) as c:
            titles = {x["chat_id"]: (x["chat_title"] or str(x["chat_id"])) for x in await c.fetchall()}

    for r in rows:
        r["rank_name"] = _LOCAL_RANK_NAMES.get(r["local_rank"], "?")
        if r["chat_tg_id"] in serves:               # это админ-чат для основной группы
            r["role"] = "admin"
            r["linked_title"] = titles.get(serves[r["chat_tg_id"]])
        elif r["admin_chat_id"]:                     # это основная группа с привязанным админ-чатом
            r["role"] = "main"
            r["linked_title"] = titles.get(r["admin_chat_id"])
        else:
            r["role"] = "plain"
            r["linked_title"] = None
    return {"chats": rows}


@router.get("/{chat_id}/dashboard")
async def admin_dashboard(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    settings = await get_chat_settings(db, chat_id)

    async with db.execute(
        "SELECT COUNT(*) FROM user_chat_stats WHERE chat_tg_id = ? AND is_left = FALSE", (chat_id,)
    ) as c:
        member_count = (await c.fetchone())[0]

    async with db.execute(
        "SELECT COUNT(*) FROM user_chat_stats WHERE chat_tg_id = ? AND warnings > 0 AND is_left = FALSE",
        (chat_id,),
    ) as c:
        warned_count = (await c.fetchone())[0]

    async with db.execute(
        "SELECT COUNT(*) FROM moderation_logs WHERE chat_id = ? AND action = 'ban'", (chat_id,)
    ) as c:
        ban_count = (await c.fetchone())[0]

    async with db.execute(
        "SELECT COUNT(*) FROM user_chat_stats "
        "WHERE chat_tg_id = ? AND last_message_at > NOW() - INTERVAL '24 hours' AND is_left = FALSE",
        (chat_id,),
    ) as c:
        active_today = (await c.fetchone())[0]

    return {
        "my_rank": actor_rank,
        "my_rank_name": _LOCAL_RANK_NAMES.get(actor_rank, "?"),
        "member_count": member_count,
        "warned_count": warned_count,
        "ban_count": ban_count,
        "active_today": active_today,
        "can_warn": actor_rank >= settings.get("rank_warn", 2),
        "can_mute": actor_rank >= settings.get("rank_mute", 3),
        "can_kick": actor_rank >= settings.get("rank_kick", 4),
        "can_ban":  actor_rank >= settings.get("rank_ban",  5),
    }


@router.get("/{chat_id}/users")
async def admin_users(
    chat_id: int,
    page: int = Query(1, ge=1),
    search: str = Query("", max_length=64),
    sort: str = Query("messages"),
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    settings = await get_chat_settings(db, chat_id)
    page_size = 20
    offset = (page - 1) * page_size

    sort_col = {
        "messages": "ucs.user_messages_count_all_time DESC",
        "level": "ucs.user_level DESC",
        "rank": "ucs.local_rank DESC",
        "warns": "ucs.warnings DESC",
    }.get(sort, "ucs.user_messages_count_all_time DESC")

    search_clause = ""
    params: list = [chat_id]
    if search:
        search_clause = " AND (LOWER(u.user_tg_username) LIKE LOWER(?) OR CAST(ucs.user_tg_id AS TEXT) LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]

    query = (
        f"SELECT ucs.user_tg_id, u.user_tg_username, ucs.user_level, ucs.user_xp, "
        f"ucs.local_rank, ucs.warnings, ucs.is_immune, ucs.immune_until, ucs.is_left, "
        f"ucs.user_messages_count_all_time, ucs.last_message_at, ucs.muted_until, ucs.joined_at, "
        f"(v.user_id IS NOT NULL) AS is_vip "
        f"FROM user_chat_stats ucs "
        f"LEFT JOIN users u ON u.user_tg_id = ucs.user_tg_id "
        f"LEFT JOIN vip_subscriptions v ON v.user_id = ucs.user_tg_id AND v.expires_at > NOW() "
        f"WHERE ucs.chat_tg_id = ? {search_clause} "
        f"ORDER BY {sort_col} LIMIT {page_size} OFFSET {offset}"
    )
    async with db.execute(query, params) as c:
        rows = [dict(r) for r in await c.fetchall()]

    count_query = f"SELECT COUNT(*) FROM user_chat_stats ucs LEFT JOIN users u ON u.user_tg_id = ucs.user_tg_id WHERE ucs.chat_tg_id = ?{search_clause}"
    async with db.execute(count_query, params[:1] + params[1:]) as c:
        total = (await c.fetchone())[0]

    for r in rows:
        r["rank_name"] = _LOCAL_RANK_NAMES.get(r["local_rank"] or 0, "?")
        r["can_act"] = actor_rank > (r["local_rank"] or 0)
        r["can_warn"] = r["can_act"] and actor_rank >= settings.get("rank_warn", 2)
        r["can_mute"] = r["can_act"] and actor_rank >= settings.get("rank_mute", 3)
        r["can_kick"] = r["can_act"] and actor_rank >= settings.get("rank_kick", 4)
        r["can_ban"]  = r["can_act"] and actor_rank >= settings.get("rank_ban",  5)
        # 8.4: щит/иммунитет — отдельные пороги
        r["can_shield"] = r["can_act"] and actor_rank >= settings.get("rank_shield", 4)
        r["can_immune"] = r["can_act"] and actor_rank >= settings.get("rank_immune", 5)
        # 8.2: смена ранга
        r["can_set_rank"] = r["can_act"]
        r["muted_until"] = str(r["muted_until"]) if r.get("muted_until") else None
        r["immune_until"] = str(r["immune_until"]) if r.get("immune_until") else None
        r["last_message_at"] = str(r["last_message_at"]) if r.get("last_message_at") else None
        r["joined_at"] = str(r["joined_at"]) if r.get("joined_at") else None

    return {"users": rows, "total": total, "page": page, "page_size": page_size,
            "max_assignable_rank": actor_rank - 1}


@router.get("/{chat_id}/settings")
async def admin_get_settings(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    await _require_admin(db, user["id"], chat_id)
    return await get_chat_settings(db, chat_id)


class SettingsUpdateRequest(BaseModel):
    shield_duration_days: Optional[int] = None
    max_warnings: Optional[int] = None
    rank_warn: Optional[int] = None
    rank_mute: Optional[int] = None
    rank_kick: Optional[int] = None
    rank_ban: Optional[int] = None
    # 8.3: недостающие пороги рангов (бот их уже читает/пишет в той же chat_settings)
    rank_shield: Optional[int] = None
    rank_immune: Optional[int] = None
    rank_duel: Optional[int] = None
    rank_marriage: Optional[int] = None
    rank_give: Optional[int] = None
    purge_min_rank: Optional[int] = None
    purge_action_rank: Optional[int] = None
    rank_chat_lock: Optional[int] = None
    events_enabled: Optional[int] = None
    module_shop: Optional[int] = None
    module_gacha: Optional[int] = None
    module_expeditions: Optional[int] = None
    module_auction: Optional[int] = None
    module_games: Optional[int] = None
    module_exchange: Optional[int] = None
    module_quests: Optional[int] = None
    module_zoo: Optional[int] = None
    module_warps: Optional[int] = None
    module_daily_deal: Optional[int] = None
    nsfw_warps_allowed: Optional[int] = None


@router.post("/{chat_id}/settings")
async def admin_update_settings(
    chat_id: int, body: SettingsUpdateRequest,
    db=Depends(get_db), user=Depends(require_tg_user)
):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    if actor_rank < 4:
        raise HTTPException(403, "Требуется ранг Старший Админ (4) для изменения настроек.")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return {"ok": True}
    await update_chat_settings(db, chat_id, **updates)
    return {"ok": True}


class ActionRequest(BaseModel):
    user_id: int
    action: str   # warn / unwarn / mute / unmute / kick / ban / unban / immune
    duration_minutes: Optional[int] = None
    reason: Optional[str] = None


@router.post("/{chat_id}/action")
async def admin_action(
    chat_id: int, body: ActionRequest,
    db=Depends(get_db), user=Depends(require_tg_user)
):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    settings = await get_chat_settings(db, chat_id)

    # Get target rank for anti-peer check
    async with db.execute(
        "SELECT local_rank FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (body.user_id, chat_id),
    ) as c:
        trow = await c.fetchone()
    # `or 0`: local_rank может быть NULL у старых строк (как в admin_set_rank) —
    # иначе actor_rank <= target_rank ниже кидает TypeError на int <= None.
    target_rank = (trow[0] or 0) if trow else 0

    if actor_rank <= target_rank:
        raise HTTPException(403, "Нельзя применить действие к пользователю с таким же или более высоким рангом.")

    action = body.action
    if action == "immune":
        action = "shield"  # 8.4: старое имя action — алиас щита (так фронт не ломается)
    _required = {"warn": "rank_warn", "unwarn": "rank_warn",
                 "mute": "rank_mute", "unmute": "rank_mute",
                 "kick": "rank_kick", "ban": "rank_ban", "unban": "rank_ban",
                 # 8.4: щит (временный) и иммунитет (постоянный) — разные пороги
                 "shield": "rank_shield", "unshield": "rank_shield",
                 "set_immune": "rank_immune", "unset_immune": "rank_immune"}
    req_key = _required.get(action)
    if req_key and actor_rank < settings.get(req_key, 99):
        raise HTTPException(403, f"Недостаточно прав для действия '{action}'.")

    tg_result = None
    now = datetime.now(timezone.utc)

    if action == "warn":
        new_warnings = await add_warn(db, chat_id, body.user_id, user["id"], body.reason)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "warn", body.reason)
        return {"ok": True, "new_warnings": new_warnings}

    elif action == "unwarn":
        new_warnings = await remove_warn(db, chat_id, body.user_id)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "unwarn", body.reason)
        return {"ok": True, "new_warnings": new_warnings}

    elif action == "mute":
        duration = body.duration_minutes or 60
        until_ts = int((now + timedelta(minutes=duration)).timestamp())
        until_str = (now + timedelta(minutes=duration)).strftime("%Y-%m-%d %H:%M:%S")
        tg_result = await _tg_call(
            "restrictChatMember",
            chat_id=chat_id, user_id=body.user_id,
            permissions={"can_send_messages": False,
                         "can_send_audios": False, "can_send_documents": False,
                         "can_send_photos": False, "can_send_videos": False,
                         "can_send_video_notes": False, "can_send_voice_notes": False,
                         "can_send_polls": False, "can_send_other_messages": False},
            until_date=until_ts,
        )
        try:
            await db.execute(
                "UPDATE user_chat_stats SET muted_until = ? WHERE user_tg_id = ? AND chat_tg_id = ?",
                (until_str, body.user_id, chat_id),
            )
            await db.commit()
        except Exception:
            pass
        await log_moderation_action(db, chat_id, body.user_id, user["id"], f"mute_{duration}m", body.reason)

    elif action == "unmute":
        tg_result = await _tg_call(
            "restrictChatMember",
            chat_id=chat_id, user_id=body.user_id,
            permissions={"can_send_messages": True, "can_send_audios": True,
                         "can_send_documents": True, "can_send_photos": True,
                         "can_send_videos": True, "can_send_video_notes": True,
                         "can_send_voice_notes": True, "can_send_polls": True,
                         "can_send_other_messages": True, "can_add_web_page_previews": True},
        )
        try:
            await db.execute(
                "UPDATE user_chat_stats SET muted_until = NULL WHERE user_tg_id = ? AND chat_tg_id = ?",
                (body.user_id, chat_id),
            )
        except Exception:
            pass
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "unmute", body.reason)

    elif action == "kick":
        tg_result = await _tg_call("banChatMember", chat_id=chat_id, user_id=body.user_id)
        await _tg_call("unbanChatMember", chat_id=chat_id, user_id=body.user_id, only_if_banned=True)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "kick", body.reason)

    elif action == "ban":
        tg_result = await _tg_call("banChatMember", chat_id=chat_id, user_id=body.user_id)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "ban", body.reason)

    elif action == "unban":
        tg_result = await _tg_call("unbanChatMember", chat_id=chat_id, user_id=body.user_id, only_if_banned=True)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "unban", body.reason)

    elif action == "shield":
        # Щит (временный): immune_until = дата, is_immune не трогаем — как бот «защита» (moderation.py:307)
        duration = body.duration_minutes or 1440
        until = (now + timedelta(minutes=duration)).strftime("%Y-%m-%d %H:%M:%S")
        await set_immunity(db, chat_id, body.user_id, 0, until)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], f"shield_{duration}m", body.reason)

    elif action == "unshield":
        await set_immunity(db, chat_id, body.user_id, 0, None)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "unshield", body.reason)

    elif action == "set_immune":
        # Иммунитет (постоянный): is_immune=1, immune_until=NULL — как бот «иммунитет» (moderation.py:268)
        await set_immunity(db, chat_id, body.user_id, 1, None)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "immune_on", body.reason)

    elif action == "unset_immune":
        await set_immunity(db, chat_id, body.user_id, 0, None)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "immune_off", body.reason)

    else:
        raise HTTPException(400, f"Неизвестное действие: {action}")

    return {"ok": True, "telegram_ok": (tg_result or {}).get("ok", False)}


@router.get("/{chat_id}/logs")
async def admin_logs(
    chat_id: int,
    page: int = Query(1, ge=1),
    action: str = Query("", max_length=16),
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    await _require_admin(db, user["id"], chat_id)
    page_size = 25
    offset = (page - 1) * page_size

    # 8.6: фильтр ?action=ban / ?action=kick — те же данные, что бот-команды «баны»/«кики»
    action_clause = ""
    params: list = [chat_id]
    if action:
        if action not in ("ban", "kick", "warn", "unwarn", "unban", "mute", "unmute"):
            raise HTTPException(400, "Недопустимый фильтр action.")
        if action == "mute":
            action_clause = " AND ml.action LIKE 'mute_%'"
        else:
            action_clause = " AND ml.action = ?"
            params.append(action)

    async with db.execute(
        "SELECT ml.id, ml.user_id, ml.admin_id, ml.action, ml.reason, ml.created_at, "
        "u.user_tg_username AS target_name, a.user_tg_username AS admin_name, "
        "(vu.user_id IS NOT NULL) AS target_is_vip, (va.user_id IS NOT NULL) AS admin_is_vip "
        "FROM moderation_logs ml "
        "LEFT JOIN users u ON ml.user_id = u.user_tg_id "
        "LEFT JOIN users a ON ml.admin_id = a.user_tg_id "
        "LEFT JOIN vip_subscriptions vu ON vu.user_id = ml.user_id AND vu.expires_at > NOW() "
        "LEFT JOIN vip_subscriptions va ON va.user_id = ml.admin_id AND va.expires_at > NOW() "
        f"WHERE ml.chat_id = ?{action_clause} "
        "ORDER BY ml.created_at DESC LIMIT ? OFFSET ?",
        (*params, page_size, offset),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]

    async with db.execute(
        f"SELECT COUNT(*) FROM moderation_logs ml WHERE ml.chat_id = ?{action_clause}", params
    ) as c:
        total = (await c.fetchone())[0]

    for r in rows:
        r["created_at"] = str(r["created_at"])

    return {"logs": rows, "total": total, "page": page, "page_size": page_size}


# ── Открыть / закрыть чат целиком (с сайта) ─────────────────────────────────────
_OPEN_PERMS_WEB = {"can_send_messages": True, "can_send_audios": True,
                   "can_send_documents": True, "can_send_photos": True,
                   "can_send_videos": True, "can_send_video_notes": True,
                   "can_send_voice_notes": True, "can_send_polls": True,
                   "can_send_other_messages": True, "can_add_web_page_previews": True}


class ChatLockRequest(BaseModel):
    open: bool


@router.post("/{chat_id}/chat-lock")
async def admin_chat_lock(chat_id: int, body: ChatLockRequest,
                          db=Depends(get_db), user=Depends(require_tg_user)):
    """Открыть/закрыть чат целиком. Порог — rank_chat_lock (как у бот +чат/-чат)."""
    actor_rank = await _require_admin(db, user["id"], chat_id)
    settings = await get_chat_settings(db, chat_id)
    if actor_rank < settings.get("rank_chat_lock", 4):
        raise HTTPException(403, "Недостаточно прав для открытия/закрытия чата.")
    perms = _OPEN_PERMS_WEB if body.open else {"can_send_messages": False}
    res = await _tg_call("setChatPermissions", chat_id=chat_id, permissions=perms)
    if not res.get("ok"):
        raise HTTPException(502, "Не удалось изменить права чата (бот не админ?).")
    return {"ok": True, "open": body.open}


# ── 8.6: Вышедшие из чата ───────────────────────────────────────────────────────
@router.get("/{chat_id}/left")
async def admin_left_users(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    await _require_admin(db, user["id"], chat_id)
    rows = await get_left_users(db, chat_id)
    return {"left": rows}


# ── 8.1: Чёрный список чата ─────────────────────────────────────────────────────
class BlacklistAddRequest(BaseModel):
    user_id: int
    reason: Optional[str] = None


async def _require_blacklist_rank(db, user_id: int, chat_id: int) -> int:
    """ЧС по тяжести близок к бану — порог rank_ban."""
    actor_rank = await _require_admin(db, user_id, chat_id)
    settings = await get_chat_settings(db, chat_id)
    if actor_rank < settings.get("rank_ban", 5):
        raise HTTPException(403, "Требуется ранг для бана (rank_ban), чтобы управлять ЧС.")
    return actor_rank


@router.get("/{chat_id}/blacklist")
async def admin_blacklist(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    await _require_blacklist_rank(db, user["id"], chat_id)
    entries = await get_chat_blacklist(db, chat_id)
    # Обогащаем юзернеймами одним запросом
    ids = {e["user_id"] for e in entries} | {e["added_by"] for e in entries if e["added_by"]}
    names: dict = {}
    if ids:
        ph = ",".join("?" * len(ids))
        async with db.execute(
            f"SELECT user_tg_id, user_tg_username FROM users WHERE user_tg_id IN ({ph})",
            tuple(ids),
        ) as c:
            names = {r["user_tg_id"]: r["user_tg_username"] for r in await c.fetchall()}
    for e in entries:
        e["username"] = names.get(e["user_id"])
        e["added_by_name"] = names.get(e["added_by"])
        e["added_at"] = str(e["added_at"]) if e.get("added_at") else None
    return {"blacklist": entries}


@router.post("/{chat_id}/blacklist")
async def admin_blacklist_add(
    chat_id: int, body: BlacklistAddRequest,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_blacklist_rank(db, user["id"], chat_id)
    # anti-peer как в /action
    async with db.execute(
        "SELECT local_rank FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (body.user_id, chat_id),
    ) as c:
        trow = await c.fetchone()
    # `or 0`: local_rank может быть NULL у старых строк (как в admin_set_rank) —
    # иначе actor_rank <= target_rank ниже кидает TypeError на int <= None.
    target_rank = (trow[0] or 0) if trow else 0
    if actor_rank <= target_rank:
        raise HTTPException(403, "Нельзя внести в ЧС пользователя с таким же или более высоким рангом.")

    await add_to_chat_blacklist(db, chat_id, body.user_id, body.reason, user["id"])
    await log_moderation_action(db, chat_id, body.user_id, user["id"], "blacklist_add", body.reason)
    await db.commit()
    return {"ok": True}


@router.delete("/{chat_id}/blacklist/{user_id}")
async def admin_blacklist_remove(
    chat_id: int, user_id: int,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    await _require_blacklist_rank(db, user["id"], chat_id)
    removed = await remove_from_chat_blacklist(db, chat_id, user_id)
    if removed:
        await log_moderation_action(db, chat_id, user_id, user["id"], "blacklist_remove", None)
    await db.commit()
    return {"ok": True, "removed": removed}


# ── 8.2: Управление рангами ─────────────────────────────────────────────────────
class SetRankRequest(BaseModel):
    new_rank: int


@router.post("/{chat_id}/users/{user_id}/rank")
async def admin_set_rank(
    chat_id: int, user_id: int, body: SetRankRequest,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_admin(db, user["id"], chat_id)
    if body.new_rank not in roles.LOCAL_RANKS_MAP:
        raise HTTPException(400, "Недопустимый ранг.")

    async with db.execute(
        "SELECT local_rank FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (user_id, chat_id),
    ) as c:
        trow = await c.fetchone()
    if not trow:
        raise HTTPException(404, "Пользователь не найден в этом чате.")
    target_rank = trow[0] or 0

    ok, err = roles.can_assign_local_rank(
        user["id"], actor_rank, target_rank, body.new_rank, DEVELOPER_ID)
    if not ok:
        raise HTTPException(403, err)

    await set_local_rank(db, user_id, chat_id, body.new_rank)
    await log_moderation_action(db, chat_id, user_id, user["id"], f"rank_{body.new_rank}", None)
    await db.commit()
    return {"ok": True, "new_rank": body.new_rank,
            "rank_name": _LOCAL_RANK_NAMES.get(body.new_rank, "?")}


# ── 8.5: Чистка (purge) — сайт запускает/останавливает, досье остаются в Telegram ──
class PurgeStartRequest(BaseModel):
    start_date: Optional[str] = None   # YYYY-MM-DD
    end_date: Optional[str] = None
    norm: Optional[int] = None


@router.get("/{chat_id}/purge/status")
async def admin_purge_status(chat_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    await _require_admin(db, user["id"], chat_id)
    settings = await get_chat_settings(db, chat_id)
    admin_chat_id = await get_admin_chat(db, chat_id)
    return {"purge_min_rank": settings.get("purge_min_rank", 4),
            "purge_action_rank": settings.get("purge_action_rank", 2),
            "has_admin_chat": bool(admin_chat_id)}


def _warn_cb(action: str, target_id: int, chat_id: int) -> str:
    """Совпадает с упаковкой aiogram CallbackData(prefix='warn_act') полей
    action/target_id/chat_id — кнопки вердикта обрабатывает process_warn_action в боте."""
    return f"warn_act:{action}:{target_id}:{chat_id}"


@router.post("/{chat_id}/purge/start")
async def admin_purge_start(
    chat_id: int, body: PurgeStartRequest,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    """Чистка с сайта = ТОЛЬКО сводка + досье с кнопками. Чат НЕ блокируется,
    бот НЕ выполняет действий над юзерами автоматически. Сводка и досье уходят
    в админ-чат (если привязан), иначе в основной чат."""
    actor_rank = await _require_admin(db, user["id"], chat_id)
    settings = await get_chat_settings(db, chat_id)
    if actor_rank < settings.get("rank_kick", 4):
        raise HTTPException(403, "Чистка требует ранга для кика (rank_kick).")

    now = datetime.now(timezone.utc)
    try:
        end_d = datetime.strptime(body.end_date, "%Y-%m-%d") if body.end_date else now
        start_d = datetime.strptime(body.start_date, "%Y-%m-%d") if body.start_date \
            else end_d - timedelta(days=7)
    except ValueError:
        raise HTTPException(400, "Даты — в формате YYYY-MM-DD.")
    norm = body.norm if body.norm and body.norm > 0 else 50
    start_date, end_date = start_d.strftime("%Y-%m-%d"), end_d.strftime("%Y-%m-%d")
    purge_min_rank = settings.get("purge_min_rank", 4)
    admin_chat_id = await get_admin_chat(db, chat_id)
    dest = admin_chat_id or chat_id

    # Сбор статистики (без блокировки чата и без действий над юзерами)
    async with db.execute(
        """SELECT u.user_tg_id as id, u.user_tg_username as username,
               s.local_rank, s.is_immune, s.immune_until, s.warnings, s.joined_at,
               COALESCE(SUM(d.message_count), 0) as msg_sum
           FROM user_chat_stats s
           LEFT JOIN users u ON s.user_tg_id = u.user_tg_id
           LEFT JOIN daily_user_stats d ON s.user_tg_id = d.user_id
                AND d.chat_id = s.chat_tg_id AND d.date BETWEEN ? AND ?
           WHERE s.chat_tg_id = ? AND s.is_left = FALSE
           GROUP BY u.user_tg_id""",
        (start_date, end_date, chat_id),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]

    passed, failed_users, protected, admins = [], [], [], []
    for u in rows:
        uname = u["username"] or f"ID {u['id']}"
        shielded = False
        if u["immune_until"]:
            iu = u["immune_until"]
            if iu.tzinfo is None:
                iu = iu.replace(tzinfo=timezone.utc)
            shielded = iu > now
        if (u["local_rank"] or 0) >= purge_min_rank:
            admins.append(f"├ 👑 {uname} ({u['msg_sum']} msg)")
        elif u["is_immune"] == 1 or shielded:
            protected.append(f"├ 🛡 {uname} ({u['msg_sum']} msg)")
        elif u["msg_sum"] >= norm:
            passed.append(f"├ ✅ {uname} ({u['msg_sum']} msg)")
        else:
            failed_users.append(u)

    report = (f"🧹 <b>СВОДКА ЧИСТКИ</b> <i>(с сайта)</i>\n"
              f"📅 Период: <code>{start_date} — {end_date}</code>\n"
              f"🎯 Норма: <code>{norm} сообщений</code>\n\n")
    failed_lines = [f"├ ❌ {u['username'] or ('ID '+str(u['id']))} ({u['msg_sum']} msg)" for u in failed_users]
    for title, lst in ((f"👑 Администрация (ранг ≥ {purge_min_rank})", admins),
                       (f"Прошли норму ({len(passed)})", passed),
                       (f"Под защитой ({len(protected)})", protected),
                       (f"❌ НЕ ПРОШЛИ ({len(failed_lines)})", failed_lines)):
        if lst:
            lst[-1] = lst[-1].replace("├", "└")
            report += f"<b>{title}:</b>\n" + "\n".join(lst) + "\n\n"
    if not failed_users:
        report += "<b>❌ НЕ ПРОШЛИ:</b>\n└ <i>Таких нет, все молодцы!</i>"
    if len(report) > 4000:
        report = report[:4000] + "\n... [Список обрезан]"
    await _tg_call("sendMessage", chat_id=dest, text=report, parse_mode="HTML")

    # Досье на не прошедших норму — с кнопками вердикта (обрабатывает бот, гейт по purge_action_rank).
    for u in failed_users[:50]:
        joined = ""
        if u.get("joined_at"):
            joined = f" · с {str(u['joined_at'])[:10]}"
        dossier = (
            f"🗂 <b>ДОСЬЕ:</b> <a href=\"tg://user?id={u['id']}\">"
            f"{u['username'] or ('ID '+str(u['id']))}</a>\n"
            f"├ Сообщений за период: <b>{u['msg_sum']}</b> из {norm}\n"
            f"└ Текущие варны: <b>{u.get('warnings', 0)}</b>{joined}\n\n"
            f"<i>Выберите меру (нажать может ранг ≥ {settings.get('purge_action_rank', 2)}):</i>"
        )
        kb = {"inline_keyboard": [
            [{"text": "⚠️ Варн", "callback_data": _warn_cb("warn_only", u["id"], chat_id)},
             {"text": "👢 Кик", "callback_data": _warn_cb("kick", u["id"], chat_id)}],
            [{"text": "🔨 Бан", "callback_data": _warn_cb("ban", u["id"], chat_id)},
             {"text": "🕊 Пропустить", "callback_data": "delete_dossier"}],
        ]}
        await _tg_call("sendMessage", chat_id=dest, text=dossier,
                       reply_markup=kb, parse_mode="HTML")
        await asyncio.sleep(0.1)

    return {"ok": True, "passed": len(passed), "failed": len(failed_users),
            "protected": len(protected), "admins": len(admins),
            "routed_to_admin_chat": bool(admin_chat_id)}
