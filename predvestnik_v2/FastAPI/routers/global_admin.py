"""FastAPI/routers/global_admin.py — раздел "Глобальная модерация" (Implementation Block 7).
Гейт по global_rank (НЕ local_rank) — отдельный, более высокий уровень доступа,
не привязанный к конкретному чату.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories import global_moderation as gm_repo
from infrastructure.repositories import users as users_repo
from services import global_moderation as gmod
from services.roles import GLOBAL_RANKS_MAP, LOCAL_RANKS_MAP, DEVELOPER_GLOBAL_RANK

router = APIRouter(prefix="/admin/global", tags=["global_admin"])


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


class _BotShim:
    """services.global_moderation вызывает bot.send_message() (интерфейс aiogram.Bot);
    у FastAPI нет live aiogram.Bot — отправка через raw HTTP, как _tg_call в admin.py."""

    async def send_message(self, chat_id: int, text: str) -> None:
        await _tg_call("sendMessage", chat_id=chat_id, text=text)


_bot = _BotShim()


async def _require_global(db, user_id: int) -> int:
    """Возвращает global_rank или 403, если < 1.
    DEVELOPER_ID не требует особого случая — db_middleware уже выставляет ему global_rank=3."""
    # `or 0`: у старых строк users.global_rank может быть NULL — без этого
    # `rank < 1` на None кидает TypeError → 500 (см. admin.py::_get_actor_rank).
    rank = await users_repo.get_global_rank(db, user_id) or 0
    if rank < 1:
        raise HTTPException(403, "Нет прав глобальной модерации.")
    return rank


def _global_flags(actor_rank: int) -> dict:
    return {
        "can_warn": actor_rank >= 1,
        "can_restrict": actor_rank >= 2,
        "can_ban": actor_rank >= 3,
        "can_manage_ranks": actor_rank >= DEVELOPER_GLOBAL_RANK,
    }


def _is_active(revoked_at, expires_at) -> bool:
    if revoked_at is not None:
        return False
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc)


async def _fetch_usernames(db, user_ids: set[int]) -> dict[int, str | None]:
    if not user_ids:
        return {}
    ph = ",".join("?" * len(user_ids))
    async with db.execute(
        f"SELECT user_tg_id, user_tg_username FROM users WHERE user_tg_id IN ({ph})",
        tuple(user_ids),
    ) as c:
        return {row["user_tg_id"]: row["user_tg_username"] for row in await c.fetchall()}


async def _fetch_chat_titles(db, chat_ids: set[int]) -> dict[int, str | None]:
    if not chat_ids:
        return {}
    ph = ",".join("?" * len(chat_ids))
    async with db.execute(
        f"SELECT chat_id, chat_title FROM chat_settings WHERE chat_id IN ({ph})",
        tuple(chat_ids),
    ) as c:
        return {row["chat_id"]: row["chat_title"] for row in await c.fetchall()}


async def _enrich_sanctions(db, rows: list[dict]) -> list[dict]:
    user_ids: set[int] = set()
    chat_ids: set[int] = set()
    for r in rows:
        if r["target_type"] == "user":
            user_ids.add(r["target_id"])
        else:
            chat_ids.add(r["target_id"])
        if r["issued_by"]:
            user_ids.add(r["issued_by"])
        if r["revoked_by"]:
            user_ids.add(r["revoked_by"])

    usernames = await _fetch_usernames(db, user_ids)
    chat_titles = await _fetch_chat_titles(db, chat_ids)

    out = []
    for r in rows:
        d = dict(r)
        if d["target_type"] == "user":
            uname = usernames.get(d["target_id"])
            d["target_name"] = f"@{uname}" if uname else f"ID{d['target_id']}"
        else:
            d["target_name"] = chat_titles.get(d["target_id"]) or f"Chat {d['target_id']}"
        for key in ("issued_by", "revoked_by"):
            uid = d.get(key)
            if uid:
                uname = usernames.get(uid)
                d[f"{key}_name"] = f"@{uname}" if uname else f"ID{uid}"
            else:
                d[f"{key}_name"] = None
        d["is_active"] = _is_active(d["revoked_at"], d["expires_at"])
        for key in ("created_at", "expires_at", "revoked_at"):
            d[key] = str(d[key]) if d[key] else None
        out.append(d)
    return out


async def _enrich_appeals(db, rows: list[dict]) -> list[dict]:
    user_ids: set[int] = set()
    sanction_ids: set[int] = set()
    for r in rows:
        user_ids.add(r["user_id"])
        if r["resolved_by"]:
            user_ids.add(r["resolved_by"])
        sanction_ids.add(r["sanction_id"])

    usernames = await _fetch_usernames(db, user_ids)

    sanctions: dict[int, dict] = {}
    if sanction_ids:
        ph = ",".join("?" * len(sanction_ids))
        async with db.execute(
            f"SELECT * FROM global_sanctions WHERE id IN ({ph})", tuple(sanction_ids)
        ) as c:
            for row in await c.fetchall():
                sanctions[row["id"]] = dict(row)

    out = []
    for r in rows:
        d = dict(r)
        uname = usernames.get(d["user_id"])
        d["user_name"] = f"@{uname}" if uname else f"ID{d['user_id']}"
        if d["resolved_by"]:
            rname = usernames.get(d["resolved_by"])
            d["resolved_by_name"] = f"@{rname}" if rname else f"ID{d['resolved_by']}"
        else:
            d["resolved_by_name"] = None
        s = sanctions.get(d["sanction_id"])
        if s:
            d["sanction_type"] = s["sanction_type"]
            d["sanction_reason"] = s["reason"]
            d["sanction_target_type"] = s["target_type"]
            d["sanction_target_id"] = s["target_id"]
            d["sanction_active"] = _is_active(s["revoked_at"], s["expires_at"])
        for key in ("created_at", "resolved_at"):
            d[key] = str(d[key]) if d[key] else None
        out.append(d)
    return out


# ── 1. Все чаты ────────────────────────────────────────────────────────────────
@router.get("/chats")
async def global_chats(db=Depends(get_db), user=Depends(require_tg_user)):
    actor_rank = await _require_global(db, user["id"])
    # Только реальные группы (chat_id<0, есть название), где сам модератор СОСТОИТ —
    # чтобы не вываливать сотни чужих чатов и не показывать «фантомные чаты-цифры».
    async with db.execute(
        "SELECT cs.chat_id, COALESCE(cs.chat_title, CAST(cs.chat_id AS TEXT)) AS chat_title, "
        "lk.admin_chat_id, "
        "(SELECT COUNT(*) FROM user_chat_stats u2 WHERE u2.chat_tg_id = cs.chat_id "
        "AND u2.local_rank = 0 AND u2.is_left = FALSE) AS member_count "
        "FROM chat_settings cs "
        "JOIN user_chat_stats ucs ON ucs.chat_tg_id = cs.chat_id "
        "  AND ucs.user_tg_id = ? AND ucs.is_left = FALSE "
        "LEFT JOIN chat_links lk ON lk.main_chat_id = cs.chat_id "
        "WHERE cs.chat_id < 0 AND cs.chat_title IS NOT NULL "
        "ORDER BY cs.chat_title",
        (user["id"],),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]

    chat_ids = [r["chat_id"] for r in rows]
    serves: dict = {}
    if chat_ids:
        ph = ",".join("?" * len(chat_ids))
        async with db.execute(
            f"SELECT main_chat_id, admin_chat_id FROM chat_links WHERE admin_chat_id IN ({ph})",
            tuple(chat_ids),
        ) as c:
            for lk in await c.fetchall():
                serves[lk["admin_chat_id"]] = lk["main_chat_id"]
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
        if r["chat_id"] in serves:
            r["role"] = "admin"; r["linked_title"] = titles.get(serves[r["chat_id"]])
        elif r["admin_chat_id"]:
            r["role"] = "main"; r["linked_title"] = titles.get(r["admin_chat_id"])
        else:
            r["role"] = "plain"; r["linked_title"] = None
    return {"chats": rows, **_global_flags(actor_rank)}


# ── 2. Участники любого чата ─────────────────────────────────────────────────────
@router.get("/chats/{chat_id}/members")
async def global_chat_members(
    chat_id: int,
    page: int = Query(1, ge=1),
    search: str = Query("", max_length=64),
    sort: str = Query("messages"),
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_global(db, user["id"])
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
        f"COALESCE(u.global_rank, 0) AS global_rank, (v.user_id IS NOT NULL) AS is_vip "
        f"FROM user_chat_stats ucs "
        f"LEFT JOIN users u ON u.user_tg_id = ucs.user_tg_id "
        f"LEFT JOIN vip_subscriptions v ON v.user_id = ucs.user_tg_id AND v.expires_at > NOW() "
        f"WHERE ucs.chat_tg_id = ? {search_clause} "
        f"ORDER BY {sort_col} LIMIT {page_size} OFFSET {offset}"
    )
    async with db.execute(query, params) as c:
        rows = [dict(r) for r in await c.fetchall()]

    count_query = f"SELECT COUNT(*) FROM user_chat_stats ucs LEFT JOIN users u ON u.user_tg_id = ucs.user_tg_id WHERE ucs.chat_tg_id = ?{search_clause}"
    async with db.execute(count_query, params) as c:
        total = (await c.fetchone())[0]

    flags = _global_flags(actor_rank)
    for r in rows:
        r["rank_name"] = LOCAL_RANKS_MAP.get(r["local_rank"] or 0, "?")
        r["global_rank_name"] = GLOBAL_RANKS_MAP.get(r["global_rank"] or 0, "?")
        can_act = actor_rank > (r["global_rank"] or 0)
        r["can_act"] = can_act
        r["can_warn"] = can_act and flags["can_warn"]
        r["can_restrict"] = can_act and flags["can_restrict"]
        r["can_ban"] = can_act and flags["can_ban"]
        r["muted_until"] = str(r["muted_until"]) if r.get("muted_until") else None
        r["immune_until"] = str(r["immune_until"]) if r.get("immune_until") else None
        r["last_message_at"] = str(r["last_message_at"]) if r.get("last_message_at") else None
        r["joined_at"] = str(r["joined_at"]) if r.get("joined_at") else None

    return {"members": rows, "total": total, "page": page, "page_size": page_size, **flags}


# ── 3. Активные ограничения ──────────────────────────────────────────────────────
@router.get("/sanctions")
async def global_sanctions_list(
    sanction_type: Optional[str] = Query(None, alias="type"),
    active_only: bool = Query(True),
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_global(db, user["id"])
    if sanction_type and sanction_type not in ("warn", "restrict", "ban"):
        raise HTTPException(400, "type должен быть 'warn', 'restrict' или 'ban'.")
    rows = await (gm_repo.list_active(db, sanction_type) if active_only else gm_repo.list_all(db, sanction_type))
    enriched = await _enrich_sanctions(db, rows)
    return {"sanctions": enriched, **_global_flags(actor_rank)}


# ── 4. Выдать санкцию ─────────────────────────────────────────────────────────────
class IssueSanctionRequest(BaseModel):
    target_type: str       # 'user' | 'chat'
    target_id: int
    sanction_type: str     # 'warn' | 'restrict' | 'ban'
    reason: Optional[str] = None            # admin_audit B1: до 9999 символов
    duration_days: Optional[int] = None     # None = бессрочно
    notify: str = "all"                     # 'all' | 'none' | id чата строкой
    photo_ids: list[str] = []               # file_id фото-доказательств


@router.post("/sanctions")
async def global_sanctions_issue(
    body: IssueSanctionRequest,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_global(db, user["id"])
    if body.target_type not in ("user", "chat"):
        raise HTTPException(400, "target_type должен быть 'user' или 'chat'.")
    if body.sanction_type not in ("warn", "restrict", "ban"):
        raise HTTPException(400, "sanction_type должен быть 'warn', 'restrict' или 'ban'.")

    target_global_rank = 0
    if body.target_type == "user":
        target_global_rank = await users_repo.get_global_rank(db, body.target_id)

    expires_at = None
    if body.duration_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.duration_days)

    import json as _json
    ok, msg, sanction_id = await gmod.issue_global_sanction(
        db, _bot, user["id"], actor_rank, body.target_type, body.target_id,
        body.sanction_type, body.reason, expires_at, target_global_rank,
        photos_json=_json.dumps(body.photo_ids or []),
    )
    if not ok:
        raise HTTPException(403, msg)

    dm_ok, notified = False, 0
    if body.target_type == "user":
        # admin_audit B1: инструкция нарушителю в ЛС — всегда; чаты — по выбору
        sanction = await gm_repo.get_sanction_by_id(db, sanction_id)
        dm_ok = await gmod.send_appeal_instruction(db, body.target_id, sanction or {})
        if body.notify == "all":
            notified = await gmod.send_sanction_notices(db, sanction_id, "all")
        elif body.notify not in ("none", "", None):
            try:
                notified = await gmod.send_sanction_notices(db, sanction_id, [int(body.notify)])
            except (TypeError, ValueError):
                pass
    return {"ok": True, "message": msg, "sanction_id": sanction_id,
            "dm_instruction_sent": dm_ok, "chats_notified": notified}


# ── 4.1 admin_audit B1: диалоги апелляций и история дел игрока ────────────────────
class AppealReplyRequest(BaseModel):
    text: str
    photo_ids: list[str] = []


@router.get("/appeals/{appeal_id}/thread")
async def global_appeal_thread(appeal_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    await _require_global(db, user["id"])
    appeal = await gm_repo.get_appeal_by_id(db, appeal_id)
    if not appeal:
        raise HTTPException(404, "Апелляция не найдена.")
    thread = await gm_repo.appeal_thread(db, appeal_id)
    sanction = await gm_repo.get_sanction_by_id(db, appeal["sanction_id"])
    return {"appeal": appeal, "thread": thread, "sanction": sanction}


@router.post("/appeals/{appeal_id}/reply")
async def global_appeal_reply(appeal_id: int, body: AppealReplyRequest,
                              db=Depends(get_db), user=Depends(require_tg_user)):
    await _require_global(db, user["id"])
    ok, msg = await gmod.staff_reply_appeal(db, appeal_id, user["id"],
                                            body.text, body.photo_ids or [])
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


class AppealCloseRequest(BaseModel):
    resolution: Optional[str] = None
    status: str = "closed"    # closed | accepted | rejected


@router.post("/appeals/{appeal_id}/close")
async def global_appeal_close(appeal_id: int, body: AppealCloseRequest,
                              db=Depends(get_db), user=Depends(require_tg_user)):
    actor_rank = await _require_global(db, user["id"])
    appeal = await gm_repo.get_appeal_by_id(db, appeal_id)
    if not appeal:
        raise HTTPException(404, "Апелляция не найдена.")
    sanction = await gm_repo.get_sanction_by_id(db, appeal["sanction_id"])
    if body.status == "accepted" and sanction and sanction["sanction_type"] == "ban" \
            and actor_rank < DEVELOPER_GLOBAL_RANK:
        raise HTTPException(403, "Принять апелляцию на бан может только Разработчик.")
    ok, msg = await gmod.close_appeal(db, appeal_id, user["id"],
                                      body.resolution, body.status)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.get("/user-case/{target_id}")
async def global_user_case(target_id: int, db=Depends(get_db), user=Depends(require_tg_user)):
    """История дел игрока: все санкции (+фото) и все апелляции с полными нитями —
    admin_audit B1: «клик по игроку → вся история лично с этим игроком»."""
    await _require_global(db, user["id"])
    case = await gm_repo.user_case(db, target_id)
    uname = await users_repo.get_user_name(db, target_id)
    return {"user_id": target_id, "username": uname, **case}


@router.get("/tg-photo/{file_id}")
async def global_tg_photo(file_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    """Прокси фото-вложений (file_id → байты) для просмотра в админке сайта."""
    await _require_global(db, user["id"])
    token = os.getenv("BOT_TOKEN", "")
    info = await _tg_call("getFile", file_id=file_id)
    path = (info.get("result") or {}).get("file_path")
    if not path:
        raise HTTPException(404, "Файл не найден в Telegram.")
    from fastapi.responses import Response as _Resp
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"https://api.telegram.org/file/bot{token}/{path}")
    return _Resp(r.content, media_type="image/jpeg")


# ── 5. Снять санкцию ──────────────────────────────────────────────────────────────
@router.post("/sanctions/{sanction_id}/revoke")
async def global_sanctions_revoke(
    sanction_id: int,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_global(db, user["id"])
    ok, msg = await gmod.revoke_global_sanction(db, _bot, user["id"], actor_rank, sanction_id)
    if not ok:
        raise HTTPException(403, msg)
    return {"ok": True, "message": msg}


# ── 6. История санкций цели ───────────────────────────────────────────────────────
@router.get("/sanctions/search")
async def global_sanctions_search(
    target_type: str = Query(...),
    target_id: int = Query(...),
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_global(db, user["id"])
    if target_type not in ("user", "chat"):
        raise HTTPException(400, "target_type должен быть 'user' или 'chat'.")
    rows = await gm_repo.list_sanctions(db, target_type, target_id, active_only=False)
    enriched = await _enrich_sanctions(db, rows)
    return {"sanctions": enriched, **_global_flags(actor_rank)}


# ── 7. Общий журнал ───────────────────────────────────────────────────────────────
@router.get("/log")
async def global_log(
    page: int = Query(1, ge=1),
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_global(db, user["id"])
    page_size = 25
    offset = (page - 1) * page_size

    async with db.execute(
        "SELECT * FROM global_sanctions ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (page_size, offset),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]
    async with db.execute("SELECT COUNT(*) FROM global_sanctions") as c:
        total = (await c.fetchone())[0]

    enriched = await _enrich_sanctions(db, rows)
    return {"logs": enriched, "total": total, "page": page, "page_size": page_size, **_global_flags(actor_rank)}


# ── 8. Апелляции ──────────────────────────────────────────────────────────────────
@router.get("/appeals")
async def global_appeals_list(
    status: Optional[str] = Query(None),
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_global(db, user["id"])
    if status and status not in ("pending", "accepted", "rejected"):
        raise HTTPException(400, "status должен быть 'pending', 'accepted' или 'rejected'.")
    rows = await gm_repo.list_appeals(db, status)
    enriched = await _enrich_appeals(db, rows)
    return {"appeals": enriched, **_global_flags(actor_rank)}


# ── 9. Решение по апелляции ────────────────────────────────────────────────────────
class ResolveAppealRequest(BaseModel):
    action: str  # 'accept' | 'reject'


@router.post("/appeals/{appeal_id}/resolve")
async def global_appeals_resolve(
    appeal_id: int, body: ResolveAppealRequest,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_global(db, user["id"])
    if body.action not in ("accept", "reject"):
        raise HTTPException(400, "action должен быть 'accept' или 'reject'.")

    appeal = await gm_repo.get_appeal_by_id(db, appeal_id)
    if not appeal:
        raise HTTPException(404, "Апелляция не найдена.")
    if appeal["status"] != "pending":
        raise HTTPException(400, "Апелляция уже рассмотрена.")

    if body.action == "reject":
        await gm_repo.resolve_appeal(db, appeal_id, "rejected", user["id"])
        return {"ok": True, "message": "❌ Апелляция отклонена."}

    sanction = await gm_repo.get_sanction_by_id(db, appeal["sanction_id"])
    if not sanction:
        raise HTTPException(404, "Связанная санкция не найдена.")
    if sanction["sanction_type"] == "ban" and actor_rank < DEVELOPER_GLOBAL_RANK:
        raise HTTPException(403, "Снятие бана по апелляции — только Разработчик.")

    if sanction["revoked_at"] is None:
        ok, msg = await gmod.revoke_global_sanction(db, _bot, user["id"], actor_rank, appeal["sanction_id"])
        if not ok:
            raise HTTPException(403, msg)

    await gm_repo.resolve_appeal(db, appeal_id, "accepted", user["id"])
    return {"ok": True, "message": "✅ Апелляция принята, санкция снята."}


# ── 10. Управление штатом ──────────────────────────────────────────────────────────
class SetRankRequest(BaseModel):
    user_id: int
    global_rank: int


@router.post("/ranks")
async def global_set_rank(
    body: SetRankRequest,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    actor_rank = await _require_global(db, user["id"])
    if actor_rank < DEVELOPER_GLOBAL_RANK:
        raise HTTPException(403, "Назначение глобальных рангов — только для Разработчика.")
    if body.global_rank not in (0, 1, 2):
        raise HTTPException(400, "global_rank должен быть 0 (снять), 1 (Хелпер) или 2 (Ст. хелпер).")
    await users_repo.set_global_rank(db, body.user_id, body.global_rank)
    return {"ok": True, "rank_name": GLOBAL_RANKS_MAP.get(body.global_rank, "?")}
