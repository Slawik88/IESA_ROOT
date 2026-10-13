"""Маршруты владельцев чатов (ADM-02, этап 2).

Владелец — отдельный принципал (`kind="owner"`, `rank=0`), а не ранг: ни `section()`, ни числовые проверки сотрудников
его не пропускают. Здесь всё устроено по умолчанию «закрыто»: отдельные запросы, каждый с `chat_id = ?` из области,
и только то, что владелец может и командами «бот …» в своём чате. Данных игрока вне чата (баланс, заметки, связи,
другие чаты) тут нет вообще, поиск по базе и массовые операции не предусмотрены.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from loguru import logger

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import guard, identify
from FastAPI.routers.bot_admin.safe import AdminRoute
from bot.chat import moderation
from bot.chat.access import is_developer
from bot.chat.global_ranks import get_bot_rank
from services import admin_access, admin_people, admin_security, owner_access

router = APIRouter(prefix="/bot-admin/api/owner", tags=["bot-admin-owner"], route_class=AdminRoute)

CHAT_ACTIONS = {"close": "Закрыть чат", "open": "Открыть чат", "warn_limit": "Лимит варнов"}
MEMBER_ACTIONS = ("warn", "mute", "unmute", "kick", "ban", "unban", "unwarn_all")
LIFTING = ("unmute", "unban", "unwarn_all")   # снятие санкции можно и с того, кто уже вышел из чата
LIST_LIMIT = 50


def _bot():
    from FastAPI.routers.bot_admin.people import get_bot
    return get_bot()


async def owner_user(x_init_data: str = Header(default=""), x_session_token: str = Header(default=""),
                     db=Depends(get_db)) -> dict:
    user_id = await identify(x_init_data, x_session_token, db)
    if not await owner_access.enabled(db):
        raise HTTPException(403, "Вход для владельцев чатов пока не открыт.")
    if await owner_access.is_blocked(db, user_id):
        raise HTTPException(403, "Доступ закрыт.")
    chats = await owner_access.verified_chats(db, _bot(), user_id)
    if not chats:
        raise HTTPException(403, "В админку входят владельцы чатов, где работает бот. Ваших чатов не найдено.")
    principal = admin_access.owner_principal(user_id, [c["id"] for c in chats])
    principal["chat_list"] = chats
    return principal


guard(owner_user)


def _int(data: dict, key: str, default: int = 0) -> int:
    try:
        return int(data.get(key) if data.get(key) not in (None, "") else default)
    except (TypeError, ValueError):
        raise HTTPException(400, "Нужно целое число.")


def _duration(data: dict):
    from datetime import timedelta
    minutes = _int(data, "minutes")
    if minutes < 0 or minutes > 366 * 24 * 60:
        raise HTTPException(400, "Срок — от 1 минуты до года (или 0 — навсегда).")
    return timedelta(minutes=minutes) if minutes else None


def _reason(data: dict) -> str:
    return str(data.get("reason") or "").strip()[:200]


def _telegram_error(exc: Exception) -> HTTPException:
    logger.warning(f"bot-admin owner telegram call failed: {exc}")   # подробности только в журнал сервера
    text = str(exc)
    if "not enough rights" in text or "administrator" in text:
        return HTTPException(409, "У бота нет прав администратора в этом чате.")
    return HTTPException(409, "Telegram не выполнил действие. Попробуйте позже.")


@router.get("/me")
async def owner_me(user=Depends(owner_user)):
    return {"user_id": user["id"], "kind": "owner", "chats": user["chat_list"], "max_chats": owner_access.MAX_CHATS,
            "chat_actions": [{"key": k, "title": t} for k, t in CHAT_ACTIONS.items()],
            "member_actions": list(MEMBER_ACTIONS)}


@router.get("/chat/{cid}")
async def owner_chat(cid: int, user=Depends(owner_user), db=Depends(get_db)):
    """Карточка своего чата: настройки, число участников, текущие санкции. Только данные этого чата."""
    admin_access.require_chat(user, cid)
    async with db.execute(
        "SELECT chat_title, COALESCE(is_closed, FALSE), COALESCE(max_warnings, 3), bot_is_admin, bot_can_moderate "
        "FROM chat_settings WHERE chat_id = ?", (cid,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Чат не найден.")
    async with db.execute("SELECT COUNT(*) FROM user_chat_stats WHERE chat_tg_id = ? AND NOT COALESCE(is_left, FALSE)",
                          (cid,)) as cur:
        members = int((await cur.fetchone())[0])
    async with db.execute(
        "SELECT b.user_id, u.user_tg_username, b.reason, b.expires_at FROM chat_blacklist b "
        "LEFT JOIN users u ON u.user_tg_id = b.user_id WHERE b.chat_id = ? AND (b.expires_at IS NULL OR b.expires_at > NOW()) "
        "ORDER BY b.added_at DESC LIMIT ?", (cid, LIST_LIMIT)) as cur:
        bans = [{"id": int(r[0]), "username": r[1], "reason": r[2], "until": r[3].isoformat() if r[3] else None}
                for r in await cur.fetchall()]
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username, s.muted_until FROM user_chat_stats s "
        "LEFT JOIN users u ON u.user_tg_id = s.user_tg_id WHERE s.chat_tg_id = ? AND s.muted_until > NOW() "
        "ORDER BY s.muted_until DESC LIMIT ?", (cid, LIST_LIMIT)) as cur:
        mutes = [{"id": int(r[0]), "username": r[1], "until": None if str(r[2]).startswith("infinity") else r[2].isoformat()}
                 for r in await cur.fetchall()]
    async with db.execute(
        "SELECT w.user_id, u.user_tg_username, COUNT(*) FROM user_warnings w LEFT JOIN users u ON u.user_tg_id = w.user_id "
        "WHERE w.chat_id = ? AND w.revoked_at IS NULL AND (w.expires_at IS NULL OR w.expires_at > NOW()) "
        "GROUP BY w.user_id, u.user_tg_username ORDER BY COUNT(*) DESC LIMIT ?", (cid, LIST_LIMIT)) as cur:
        warns = [{"id": int(r[0]), "username": r[1], "count": int(r[2])} for r in await cur.fetchall()]
    return {"id": cid, "title": row[0] or f"Чат {cid}", "closed": bool(row[1]), "max_warnings": int(row[2]),
            "bot": {"is_admin": bool(row[3]), "can_moderate": bool(row[4])}, "members": members,
            "sanctions": {"bans": bans, "mutes": mutes, "warns": warns}}


@router.post("/chat/{cid}/action")
async def owner_chat_action(cid: int, data: dict = Body(...), user=Depends(owner_user), db=Depends(get_db)):
    action = str(data.get("action") or "")
    if action not in CHAT_ACTIONS:
        raise HTTPException(400, "Неизвестное действие.")
    admin_access.require_chat(user, cid)
    admin_security.rate_limit(user, action)
    if action in ("close", "open"):
        await db.execute("UPDATE chat_settings SET is_closed = ? WHERE chat_id = ?", (action == "close", cid))
        await admin_people.audit(db, user["id"], action, chat_id=cid, details={"as": "owner"})
        return {"ok": True, "message": "Чат закрыт: пишут только ранги с правом." if action == "close" else "Чат открыт."}
    limit = _int(data, "value")
    if not 1 <= limit <= 20:
        raise HTTPException(400, "Лимит варнов — от 1 до 20.")
    await db.execute("UPDATE chat_settings SET max_warnings = ? WHERE chat_id = ?", (limit, cid))
    await admin_people.audit(db, user["id"], "warn_limit", chat_id=cid, details={"value": limit, "as": "owner"})
    return {"ok": True, "message": f"Лимит варнов: {limit}."}


async def _check_target(db, bot, user: dict, cid: int, uid: int, action: str) -> None:
    """Цель действия владельца: участник этого чата (или носитель санкции для снятия), без роли в боте, не бот, не он сам."""
    if uid == user["id"]:
        raise HTTPException(403, "К себе действия не применяются.")
    if is_developer(uid) or await get_bot_rank(db, uid) > 0:
        raise HTTPException(403, "Этот игрок защищён: действия с ним доступны только персоналу бота.")
    try:
        me = await bot.me()
    except Exception as exc:   # noqa: BLE001
        raise _telegram_error(exc)
    if uid == me.id:
        raise HTTPException(403, "К самому боту это не применяется.")
    async with db.execute(
        "SELECT NOT COALESCE(is_left, FALSE), COALESCE(muted_until > NOW(), FALSE) FROM user_chat_stats "
        "WHERE chat_tg_id = ? AND user_tg_id = ?", (cid, uid)) as cur:
        row = await cur.fetchone()
    present = bool(row and row[0])
    if not present:
        if action not in LIFTING:
            raise HTTPException(404, "Игрок не найден в этом чате.")
        sanction = bool(row and row[1])
        if not sanction:
            async with db.execute("SELECT 1 FROM chat_blacklist WHERE chat_id = ? AND user_id = ? "
                                  "AND (expires_at IS NULL OR expires_at > NOW())", (cid, uid)) as cur:
                sanction = await cur.fetchone() is not None
        if not sanction:
            async with db.execute("SELECT 1 FROM user_warnings WHERE chat_id = ? AND user_id = ? AND revoked_at IS NULL "
                                  "AND (expires_at IS NULL OR expires_at > NOW())", (cid, uid)) as cur:
                sanction = await cur.fetchone() is not None
        if not sanction:
            raise HTTPException(404, "Игрок не найден в этом чате.")
    block = await moderation.rank_block(db, cid, user["id"], uid)   # чатовые ранги, как у команд «бот …»
    if block:
        raise HTTPException(403, block.replace("⛔ ", ""))


@router.post("/chat/{cid}/member/{uid}/action")
async def owner_member_action(cid: int, uid: int, data: dict = Body(...), user=Depends(owner_user), db=Depends(get_db)):
    action = str(data.get("action") or "")
    if action not in MEMBER_ACTIONS:
        raise HTTPException(400, "Неизвестное действие.")
    admin_access.require_chat(user, cid)
    bot = _bot()
    await _check_target(db, bot, user, cid, uid, action)
    admin_security.rate_limit(user, action)
    actor, reason = user["id"], _reason(data)
    try:
        if action == "mute":
            await moderation.do_mute(bot, db, cid, uid, actor, _duration(data), reason)
        elif action == "unmute":
            await moderation.do_unmute(bot, db, cid, uid, actor)
        elif action == "kick":
            await moderation.do_kick(bot, db, cid, uid, actor, reason)
        elif action == "ban":
            await moderation.do_ban(bot, db, cid, uid, actor, _duration(data), reason)
        elif action == "unban":
            await moderation.do_unban(bot, db, cid, uid, actor)
        elif action == "warn":
            count, limit = await moderation.do_warn(db, cid, uid, actor, _duration(data), reason)
            await admin_people.audit(db, actor, action, user_id=uid, chat_id=cid, details={"reason": reason, "as": "owner"})
            return {"ok": True, "message": f"Варн выдан ({count}/{limit})."}
        elif action == "unwarn_all":
            n = await moderation.revoke_all_warns(db, cid, uid, actor)
            await admin_people.audit(db, actor, action, user_id=uid, chat_id=cid, details={"as": "owner"})
            return {"ok": True, "message": f"Снято варнов: {n}."}
    except HTTPException:
        raise
    except Exception as exc:   # noqa: BLE001
        raise _telegram_error(exc)
    await admin_people.audit(db, actor, action, user_id=uid, chat_id=cid, details={"reason": reason, "as": "owner"})
    return {"ok": True, "message": "Готово."}
