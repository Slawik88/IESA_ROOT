"""Админка: поиск игроков и чатов, их карточки и журнал действий персонала.

Только чтение существующих таблиц плюс одна новая — bot_admin_actions (журнал того,
что персонал сделал из админки: роль, баланс, VIP, блокировка, настройки чата).
Модерация в чатах (мут, бан, кик, варны) пишется в moderation_logs, как и из чата.
"""
from __future__ import annotations

import json
from datetime import timedelta

from bot.chat import ranks
from bot.chat.global_ranks import bot_rank_name, get_bot_rank
from bot.chat.tracking import local_now
from infrastructure.repositories import skins_v3 as skins_v3_repo
from services import feature_switches, global_moderation
from services import vip as vip_service

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS bot_admin_actions (
        id         BIGSERIAL PRIMARY KEY,
        actor_id   BIGINT NOT NULL,
        action     TEXT   NOT NULL,
        user_id    BIGINT,
        chat_id    BIGINT,
        details    JSONB  NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS bot_admin_actions_user_idx ON bot_admin_actions (user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS bot_admin_actions_chat_idx ON bot_admin_actions (chat_id, created_at DESC)",
)

# Подписи действий в журнале: и из админки, и из чата (moderation_logs).
ACTION_TITLES = {
    "rank": "Глобальная роль", "balance": "Баланс", "vip": "VIP", "block": "Бот не отвечает", "unblock": "Бот снова отвечает",
    "global_ban": "Бан во всех чатах", "global_unban": "Снят бан во всех чатах",
    "close": "Чат закрыт", "open": "Чат открыт", "warn_limit": "Лимит варнов", "message": "Сообщение от бота",
    "leave": "Бот вышел из чата", "mute": "Мут", "unmute": "Снят мут", "kick": "Кик", "ban": "Бан", "unban": "Снят бан",
    "warn": "Варн", "unwarn": "Снят варн", "unwarn_all": "Сняты все варны", "shield": "Защита", "unshield": "Снята защита",
    "immune": "Иммунитет", "unimmune": "Снят иммунитет", "close_chat": "Чат закрыт", "open_chat": "Чат открыт",
}


async def ensure_schema(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)


async def audit(db, actor_id: int, action: str, *, user_id: int | None = None, chat_id: int | None = None,
                details: dict | None = None) -> None:
    await db.execute(
        "INSERT INTO bot_admin_actions (actor_id, action, user_id, chat_id, details) VALUES (?, ?, ?, ?, ?::jsonb)",
        (actor_id, action, user_id, chat_id, json.dumps(details or {}, ensure_ascii=False)))


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


async def _names(db, ids) -> dict[int, str | None]:
    ids = list(dict.fromkeys(int(i) for i in ids if i))
    if not ids:
        return {}
    marks = ", ".join("?" for _ in ids)
    async with db.execute(f"SELECT user_tg_id, user_tg_username FROM users WHERE user_tg_id IN ({marks})",
                          tuple(ids)) as cur:
        return {int(r[0]): r[1] for r in await cur.fetchall()}


async def _chat_titles(db, ids) -> dict[int, str | None]:
    ids = list(dict.fromkeys(int(i) for i in ids if i))
    if not ids:
        return {}
    marks = ", ".join("?" for _ in ids)
    async with db.execute(f"SELECT chat_id, chat_title FROM chat_settings WHERE chat_id IN ({marks})",
                          tuple(ids)) as cur:
        return {int(r[0]): r[1] for r in await cur.fetchall()}


# ── Поиск ────────────────────────────────────────────────────────────────────

_PLAYER_SQL = (
    "SELECT u.user_tg_id, u.user_tg_username, COALESCE(u.bot_rank, 0), COALESCE(s.total, 0), s.last "
    "FROM users u LEFT JOIN (SELECT user_tg_id, SUM(user_messages_count_all_time) AS total, "
    "MAX(last_message_at) AS last FROM user_chat_stats GROUP BY user_tg_id) s ON s.user_tg_id = u.user_tg_id ")
_CHAT_SQL = (
    "SELECT c.chat_id, c.chat_title, COALESCE(s.members, 0), COALESCE(s.total, 0), s.last "
    "FROM chat_settings c LEFT JOIN (SELECT chat_tg_id, COUNT(*) FILTER (WHERE NOT COALESCE(is_left, FALSE)) AS members, "
    "SUM(user_messages_count_all_time) AS total, MAX(last_message_at) AS last FROM user_chat_stats "
    "GROUP BY chat_tg_id) s ON s.chat_tg_id = c.chat_id ")


def _player_row(r) -> dict:
    return {"id": int(r[0]), "username": r[1], "rank_name": bot_rank_name(int(r[2])) if r[2] else "",
            "messages": int(r[3]), "last": _iso(r[4])}


def _chat_row(r) -> dict:
    return {"id": int(r[0]), "title": r[1] or str(r[0]), "members": int(r[2]), "messages": int(r[3]), "last": _iso(r[4])}


async def search(db, q: str, limit: int = 20) -> dict:
    """Игроки и чаты по ID, @нику или названию. Пустой запрос — самые свежие по активности."""
    q = (q or "").strip()
    if not q:
        async with db.execute(_PLAYER_SQL + "WHERE s.last IS NOT NULL ORDER BY s.last DESC LIMIT ?", (limit,)) as cur:
            players = [_player_row(r) for r in await cur.fetchall()]
        async with db.execute(_CHAT_SQL + "WHERE c.chat_id < 0 ORDER BY s.last DESC NULLS LAST LIMIT ?", (limit,)) as cur:
            chats = [_chat_row(r) for r in await cur.fetchall()]
        return {"players": players, "chats": chats}
    digits = q.lstrip("-")
    if digits.isdigit():
        n = int(q)
        ids = {n, -n} | ({-1000000000000 - abs(n)} if not q.startswith("-100") else set())
        marks = ", ".join("?" for _ in ids)
        async with db.execute(_PLAYER_SQL + "WHERE u.user_tg_id = ?", (abs(n),)) as cur:
            players = [_player_row(r) for r in await cur.fetchall()]
        async with db.execute(_CHAT_SQL + f"WHERE c.chat_id IN ({marks})", tuple(ids)) as cur:
            chats = [_chat_row(r) for r in await cur.fetchall()]
        return {"players": players, "chats": chats}
    name = q.lstrip("@")
    async with db.execute(
        _PLAYER_SQL + "WHERE u.user_tg_username ILIKE ? ORDER BY lower(u.user_tg_username) = lower(?) DESC, "
        "COALESCE(s.total, 0) DESC LIMIT ?", (_like(name), name, limit)) as cur:
        players = [_player_row(r) for r in await cur.fetchall()]
    async with db.execute(
        _CHAT_SQL + "WHERE c.chat_title ILIKE ? ORDER BY COALESCE(s.total, 0) DESC LIMIT ?", (_like(q), limit)) as cur:
        chats = [_chat_row(r) for r in await cur.fetchall()]
    return {"players": players, "chats": chats}


# ── Журнал ───────────────────────────────────────────────────────────────────

def _days(n: int) -> str:
    n = int(n)
    word = "день" if n % 10 == 1 and n % 100 != 11 else ("дня" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "дней")
    return f"{n} {word}"


def describe(action: str, d: dict) -> str:
    """Суть записи журнала одной строкой (без причины — она отдельно)."""
    if action == "balance":
        amount = str(d.get("amount", ""))
        return f"{d.get('currency', '')} {'' if amount.startswith('-') else '+'}{amount}"
    if action == "vip":
        return f"+{_days(d.get('days', 0))}"
    if action == "block":
        return f"на {_days(d['days'])}" if d.get("days") else "пока не снимут"
    if action == "rank":
        return f"{d.get('from', '')} → {d.get('to', '')}"
    if action == "warn_limit":
        return str(d.get("value", ""))
    if action == "message":
        return f"«{d.get('text', '')}»"
    return ""


async def history(db, *, user_id: int | None = None, chat_id: int | None = None, limit: int = 40) -> list[dict]:
    col = "user_id" if user_id is not None else "chat_id"
    key = user_id if user_id is not None else chat_id
    async with db.execute(
        f"SELECT actor_id, action, user_id, chat_id, details::text, created_at FROM bot_admin_actions WHERE {col} = ? "
        f"UNION ALL SELECT admin_id, action, user_id, chat_id, reason, created_at::timestamptz FROM moderation_logs "
        f"WHERE {col} = ? ORDER BY 6 DESC LIMIT ?", (key, key, limit)) as cur:
        rows = await cur.fetchall()
    names = await _names(db, [r[0] for r in rows] + [r[2] for r in rows])
    titles = await _chat_titles(db, [r[3] for r in rows])
    out = []
    for actor, action, uid, cid, extra, at in rows:
        details = {}
        if extra and extra.startswith("{"):
            try:
                details = json.loads(extra)
            except ValueError:
                details = {}
        elif extra:
            details = {"reason": extra}
        out.append({
            "action": action, "title": ACTION_TITLES.get(action, action), "text": describe(action, details),
            "reason": str(details.get("reason") or ""), "at": _iso(at),
            "actor": {"id": actor, "username": names.get(int(actor)) if actor else None},
            "user": {"id": uid, "username": names.get(int(uid)) if uid else None} if uid else None,
            "chat": {"id": cid, "title": titles.get(int(cid)) if cid else None} if cid else None,
        })
    return out


# ── Карточка игрока ──────────────────────────────────────────────────────────

async def player(db, uid: int) -> dict | None:
    async with db.execute(
        "SELECT user_tg_username, COALESCE(user_balance_mora, 0), COALESCE(user_balance_diamonds, 0), "
        "COALESCE(user_balance_zarniki, 0), COALESCE(is_sponsor, FALSE), deleted_at "
        "FROM users WHERE user_tg_id = ?", (uid,)) as cur:
        u = await cur.fetchone()
    if not u:
        return None
    rank = await get_bot_rank(db, uid)
    vip = await vip_service.get_vip_info(db, uid)
    today = local_now().date()

    from bot.chat.family import family_of
    from bot.chat.streak import streak_of
    fam = await family_of(db, uid)
    family = None
    if fam:
        partner = fam.partner_of(uid) if fam.is_parent(uid) else None
        family = {"partner": partner, "since": _iso(fam.since), "children": len(fam.children),
                  "parents": fam.parents, "is_parent": fam.is_parent(uid)}
    current, best, _ = await streak_of(db, uid, today)
    async with db.execute(
        "SELECT COUNT(*), COALESCE(SUM(level), 0) FROM chat_achievement_levels WHERE user_id = ? AND level > 0",
        (uid,)) as cur:
        ach = await cur.fetchone()
    async with db.execute(
        "SELECT COALESCE(SUM(message_count) FILTER (WHERE date = ?), 0), COALESCE(SUM(message_count), 0) "
        "FROM daily_user_stats WHERE user_id = ? AND date >= ?",
        (today.isoformat(), uid, (today - timedelta(days=6)).isoformat())) as cur:
        msg_today, msg_week = await cur.fetchone()

    async with db.execute(
        "SELECT s.chat_tg_id, c.chat_title, COALESCE(s.user_messages_count_all_time, 0), s.last_message_at, "
        "COALESCE(s.is_left, FALSE), COALESCE(s.muted_until > NOW(), FALSE), "
        "CASE WHEN s.muted_until = 'infinity' THEN NULL ELSE s.muted_until END "
        "FROM user_chat_stats s LEFT JOIN chat_settings c ON c.chat_id = s.chat_tg_id "
        "WHERE s.user_tg_id = ? AND s.chat_tg_id < 0 ORDER BY s.last_message_at DESC NULLS LAST LIMIT 100",
        (uid,)) as cur:
        rows = await cur.fetchall()
    async with db.execute(
        "SELECT chat_id, reason, CASE WHEN expires_at = 'infinity' THEN NULL ELSE expires_at END FROM chat_blacklist "
        "WHERE user_id = ? AND chat_id <> 0 AND (expires_at IS NULL OR expires_at > NOW())", (uid,)) as cur:
        bans = {int(r[0]): {"reason": r[1] or "", "until": _iso(r[2])} for r in await cur.fetchall()}
    async with db.execute(
        "SELECT chat_id, COUNT(*) FROM user_warnings WHERE user_id = ? AND revoked_at IS NULL "
        "AND (expires_at IS NULL OR expires_at > NOW()) GROUP BY chat_id", (uid,)) as cur:
        warns = {int(r[0]): int(r[1]) for r in await cur.fetchall()}
    seen = {int(r[0]) for r in rows}
    extra_titles = await _chat_titles(db, [c for c in bans if c not in seen])
    chats = []
    for cid, title, total, last, left, muted, muted_until in rows:
        cid = int(cid)
        chats.append({"id": cid, "title": title or str(cid), "messages": int(total), "last": _iso(last),
                      "left": bool(left), "muted": bool(muted), "muted_until": _iso(muted_until),
                      "ban": bans.get(cid), "warns": warns.get(cid, 0),
                      "rank_name": ranks.rank_name(await ranks.get_rank(db, cid, uid))})
    for cid, title in extra_titles.items():   # забанен в чате, где не писал
        chats.append({"id": cid, "title": title or str(cid), "messages": 0, "last": None, "left": True,
                      "muted": False, "muted_until": None, "ban": bans[cid], "warns": warns.get(cid, 0),
                      "rank_name": ranks.rank_name(0)})

    names = await _names(db, [family["partner"]] if family and family["partner"] else [])
    if family and family["partner"]:
        family["partner_username"] = names.get(family["partner"])
    return {
        "id": uid, "username": u[0], "rank": rank, "rank_name": bot_rank_name(rank), "sponsor": bool(u[4]),
        "deleted_at": _iso(u[5]),
        "balances": {"mora": float(u[1]), "diamonds": float(u[2]), "zarniki": float(u[3]),
                     "essence": await skins_v3_repo.essence_balance(db, uid)},
        "vip": {"until": _iso(vip["expires_at"]), "days_left": vip["days_left"]} if vip else None,
        "family": family, "streak": {"current": current, "best": best},
        "achievements": {"count": int(ach[0]), "levels": int(ach[1])},
        "messages": {"today": int(msg_today), "week": int(msg_week), "total": sum(c["messages"] for c in chats)},
        "chats": chats,
        "global_ban": await global_moderation.ban_info(db, uid),
        "blocked": await global_moderation.block_info(db, uid),
    }


# ── Карточка чата ────────────────────────────────────────────────────────────

async def chat(db, cid: int) -> dict | None:
    async with db.execute(
        "SELECT chat_title, owner_id, COALESCE(is_closed, FALSE), COALESCE(max_warnings, 3) "
        "FROM chat_settings WHERE chat_id = ?", (cid,)) as cur:
        c = await cur.fetchone()
    if not c:
        return None
    today = local_now().date()
    async with db.execute(
        "SELECT COUNT(*) FILTER (WHERE NOT COALESCE(is_left, FALSE)), COALESCE(SUM(user_messages_count_all_time), 0) "
        "FROM user_chat_stats WHERE chat_tg_id = ?", (cid,)) as cur:
        members, total = await cur.fetchone()
    stats = {}
    for key, days in (("today", 0), ("week", 6), ("month", 29)):
        async with db.execute(
            "SELECT COALESCE(SUM(message_count), 0), COUNT(DISTINCT user_id) FROM daily_user_stats "
            "WHERE chat_id = ? AND date >= ?", (cid, (today - timedelta(days=days)).isoformat())) as cur:
            m, a = await cur.fetchone()
        stats[key] = {"messages": int(m), "active": int(a)}
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username, s.user_messages_count_all_time FROM user_chat_stats s "
        "LEFT JOIN users u ON u.user_tg_id = s.user_tg_id WHERE s.chat_tg_id = ? AND NOT COALESCE(s.is_left, FALSE) "
        "ORDER BY s.user_messages_count_all_time DESC NULLS LAST LIMIT 10", (cid,)) as cur:
        top = [{"id": int(r[0]), "username": r[1], "messages": int(r[2] or 0)} for r in await cur.fetchall()]

    async with db.execute(
        "SELECT user_id, reason, CASE WHEN expires_at = 'infinity' THEN NULL ELSE expires_at END FROM chat_blacklist "
        "WHERE chat_id = ? AND (expires_at IS NULL OR expires_at > NOW()) ORDER BY added_at DESC LIMIT 100",
        (cid,)) as cur:
        bans = [{"user": int(r[0]), "reason": r[1] or "", "until": _iso(r[2])} for r in await cur.fetchall()]
    async with db.execute(
        "SELECT user_tg_id, CASE WHEN muted_until = 'infinity' THEN NULL ELSE muted_until END FROM user_chat_stats "
        "WHERE chat_tg_id = ? AND muted_until > NOW() ORDER BY muted_until LIMIT 100", (cid,)) as cur:
        mutes = [{"user": int(r[0]), "until": _iso(r[1])} for r in await cur.fetchall()]
    async with db.execute(
        "SELECT user_id, COUNT(*) FROM user_warnings WHERE chat_id = ? AND revoked_at IS NULL "
        "AND (expires_at IS NULL OR expires_at > NOW()) GROUP BY user_id ORDER BY 2 DESC LIMIT 100", (cid,)) as cur:
        warns = [{"user": int(r[0]), "count": int(r[1])} for r in await cur.fetchall()]
    names = await _names(db, [x["user"] for x in bans + mutes + warns] + ([c[1]] if c[1] else []))
    for x in bans + mutes + warns:
        x["username"] = names.get(x["user"])

    async with db.execute(
        "SELECT l.admin_chat_id, s.chat_title FROM chat_links l LEFT JOIN chat_settings s ON s.chat_id = l.admin_chat_id "
        "WHERE l.main_chat_id = ?", (cid,)) as cur:
        link = await cur.fetchone()
    off = (await feature_switches.state(db, cid))["chat"]
    return {
        "id": cid, "title": c[0] or str(cid), "closed": bool(c[2]), "warn_limit": int(c[3]),
        "owner": {"id": int(c[1]), "username": names.get(int(c[1]))} if c[1] else None,
        "admin_chat": {"id": int(link[0]), "title": link[1] or str(link[0])} if link else None,
        "members": int(members), "messages": {"total": int(total), **stats}, "top": top,
        "sanctions": {"bans": bans, "mutes": mutes, "warns": warns},
        "switched_off": [{"key": k, "reason": v["reason"]} for k, v in off.items()],
    }
