"""FastAPI/routers/admin.py — панель модератора."""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.moderation import (
    get_chat_settings, update_chat_settings, add_warn, remove_warn,
    log_moderation_action, set_immunity,
)

router = APIRouter(prefix="/admin", tags=["admin"])

_LOCAL_RANK_NAMES = {
    0: "👤 Пользователь", 1: "👁 Модератор", 2: "👮 Мл.Админ",
    3: "👮 Админ", 4: "🕵️ Ст.Админ", 5: "👑 Совладелец", 6: "👑 Владелец",
}


async def _get_actor_rank(db, user_id: int, chat_id: int) -> int:
    async with db.execute(
        "SELECT local_rank FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (user_id, chat_id),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0


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
    """Чаты где у пользователя есть права модератора (local_rank >= 1)."""
    async with db.execute(
        "SELECT ucs.chat_tg_id, COALESCE(cs.chat_title, CAST(ucs.chat_tg_id AS TEXT)) AS chat_title, "
        "ucs.local_rank "
        "FROM user_chat_stats ucs "
        "LEFT JOIN chat_settings cs ON cs.chat_id = ucs.chat_tg_id "
        "WHERE ucs.user_tg_id = ? AND ucs.local_rank >= 1 AND ucs.is_left = FALSE "
        "ORDER BY ucs.local_rank DESC",
        (user["id"],),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]
    for r in rows:
        r["rank_name"] = _LOCAL_RANK_NAMES.get(r["local_rank"], "?")
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
        f"ucs.user_messages_count_all_time, ucs.last_message_at, ucs.muted_until "
        f"FROM user_chat_stats ucs "
        f"LEFT JOIN users u ON u.user_tg_id = ucs.user_tg_id "
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
        r["muted_until"] = str(r["muted_until"]) if r.get("muted_until") else None
        r["immune_until"] = str(r["immune_until"]) if r.get("immune_until") else None
        r["last_message_at"] = str(r["last_message_at"]) if r.get("last_message_at") else None

    return {"users": rows, "total": total, "page": page, "page_size": page_size}


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
    target_rank = trow[0] if trow else 0

    if actor_rank <= target_rank:
        raise HTTPException(403, "Нельзя применить действие к пользователю с таким же или более высоким рангом.")

    action = body.action
    _required = {"warn": "rank_warn", "unwarn": "rank_warn",
                 "mute": "rank_mute", "unmute": "rank_mute",
                 "kick": "rank_kick", "ban": "rank_ban", "unban": "rank_ban",
                 "immune": "rank_immune"}
    req_key = _required.get(action)
    if req_key and actor_rank < settings.get(req_key, 99):
        raise HTTPException(403, f"Недостаточно прав для действия '{action}'.")

    tg_result = None
    now = datetime.now(timezone.utc)

    if action == "warn":
        new_warnings = await add_warn(db, chat_id, body.user_id, user["id"], body.reason)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "warn")
        try:
            await db.execute(
                "UPDATE moderation_logs SET reason = ? WHERE chat_id = ? AND user_id = ? "
                "AND admin_id = ? AND action = 'warn' AND created_at > NOW() - INTERVAL '5 seconds'",
                (body.reason, chat_id, body.user_id, user["id"]),
            )
            await db.commit()
        except Exception:
            pass
        return {"ok": True, "new_warnings": new_warnings}

    elif action == "unwarn":
        new_warnings = await remove_warn(db, chat_id, body.user_id)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "unwarn")
        await db.commit()
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
        await log_moderation_action(db, chat_id, body.user_id, user["id"], f"mute_{duration}m")
        await db.commit()

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
            await db.commit()
        except Exception:
            pass
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "unmute")
        await db.commit()

    elif action == "kick":
        tg_result = await _tg_call("banChatMember", chat_id=chat_id, user_id=body.user_id)
        # unban immediately to allow rejoining
        await _tg_call("unbanChatMember", chat_id=chat_id, user_id=body.user_id, only_if_banned=True)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "kick")
        await db.commit()

    elif action == "ban":
        tg_result = await _tg_call("banChatMember", chat_id=chat_id, user_id=body.user_id)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "ban")
        await db.commit()

    elif action == "unban":
        tg_result = await _tg_call("unbanChatMember", chat_id=chat_id, user_id=body.user_id, only_if_banned=True)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], "unban")
        await db.commit()

    elif action == "immune":
        duration = body.duration_minutes or 1440
        until = (now + timedelta(minutes=duration)).strftime("%Y-%m-%d %H:%M:%S")
        await set_immunity(db, chat_id, body.user_id, 1, until)
        await log_moderation_action(db, chat_id, body.user_id, user["id"], f"immune_{duration}m")
        await db.commit()

    else:
        raise HTTPException(400, f"Неизвестное действие: {action}")

    return {"ok": True, "telegram_ok": (tg_result or {}).get("ok", False)}


@router.get("/{chat_id}/logs")
async def admin_logs(
    chat_id: int,
    page: int = Query(1, ge=1),
    db=Depends(get_db),
    user=Depends(require_tg_user),
):
    await _require_admin(db, user["id"], chat_id)
    page_size = 25
    offset = (page - 1) * page_size

    async with db.execute(
        "SELECT ml.id, ml.user_id, ml.admin_id, ml.action, ml.reason, ml.created_at, "
        "u.user_tg_username AS target_name, a.user_tg_username AS admin_name "
        "FROM moderation_logs ml "
        "LEFT JOIN users u ON ml.user_id = u.user_tg_id "
        "LEFT JOIN users a ON ml.admin_id = a.user_tg_id "
        "WHERE ml.chat_id = ? "
        "ORDER BY ml.created_at DESC LIMIT ? OFFSET ?",
        (chat_id, page_size, offset),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]

    async with db.execute(
        "SELECT COUNT(*) FROM moderation_logs WHERE chat_id = ?", (chat_id,)
    ) as c:
        total = (await c.fetchone())[0]

    for r in rows:
        r["created_at"] = str(r["created_at"])

    return {"logs": rows, "total": total, "page": page, "page_size": page_size}
