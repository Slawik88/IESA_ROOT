"""Админка: поиск игроков и чатов, их карточки и журнал действий персонала.

Только чтение существующих таблиц плюс одна новая — bot_admin_actions (журнал того,
что персонал сделал из админки: роль, баланс, VIP, блокировка, настройки чата).
Модерация в чатах (мут, бан, кик, варны) пишется в moderation_logs, как и из чата.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from bot.chat import ranks
from bot.chat.global_ranks import bot_rank_name, get_bot_rank
from bot.chat.tracking import local_now
from infrastructure.repositories import skins_v3 as skins_v3_repo
from services import skins_v3, admin_avatars, feature_switches, global_moderation, member_tags, name_history, staff_watch
from services import reports as reports_service
from services import vip as vip_service
from core.marks_v1 import GRANTABLE

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
    "chat_rank": "Ранг участника чата", "chat_rights": "Права рангов чата", "rank": "Глобальная роль", "mark_grant": "Выдана регалия", "mark_revoke": "Снята регалия", "balance": "Баланс", "vip": "VIP", "block": "Бот не отвечает", "unblock": "Бот снова отвечает",
    "global_ban": "Бан во всех чатах", "global_unban": "Снят бан во всех чатах",
    "close": "Чат закрыт", "open": "Чат открыт", "warn_limit": "Лимит варнов", "message": "Сообщение от бота",
    "leave": "Бот вышел из чата", "mute": "Мут", "unmute": "Снят мут", "kick": "Кик", "ban": "Бан", "unban": "Снят бан",
    "warn": "Варн", "unwarn": "Снят варн", "unwarn_all": "Сняты все варны", "shield": "Защита", "unshield": "Снята защита",
    "immune": "Иммунитет", "unimmune": "Снят иммунитет", "close_chat": "Чат закрыт", "open_chat": "Чат открыт",
    "promo_create": "Промокод создан", "promo_update": "Промокод изменён", "promo_active": "Промокод включён или выключен",
    "promo_bulk": "Пачка промокодов создана",
    "switch": "Выключатель", "transfer": "Валюты для переводов", "report_settings": "Настройки жалоб", "digest_settings": "Ежедневный отчёт владельцу",
    "note_add": "Заметка об игроке", "note_remove": "Заметка убрана",
    "watch_add": "Игрок поставлен на контроль", "watch_remove": "Игрок снят с контроля",
    "sessions_revoke": "Завершены сессии админки", "grant": "Права ролей изменены", "owner_access": "Вход владельцев чатов", "owner_block": "Доступ владельца отозван или возвращён",
    "report_in_work": "Жалоба взята в работу", "report_resolved": "Жалоба: нарушение подтверждено",
    "report_rejected": "Жалоба отклонена", "broadcast": "Рассылка", "broadcast_stop": "Рассылка остановлена или отменена",
    "broadcast_resume": "Рассылка продолжена", "broadcast_template": "Шаблон рассылки",
    "journal_export": "Выгрузка журнала", "dm": "Сообщение в личку", "skin_grant": "Выдан образ", "skin_revoke": "Забран образ", "purge_start": "Чистка начата", "purge_finish": "Чистка закончена", "purge_reconcile": "Чистка: решение сверено с Telegram",
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
    "SELECT u.user_tg_id, u.user_tg_username, COALESCE(u.bot_rank, 0), COALESCE(s.total, 0), s.last, u.user_tg_name "
    "FROM users u LEFT JOIN (SELECT user_tg_id, SUM(user_messages_count_all_time) AS total, "
    "MAX(last_message_at) AS last FROM user_chat_stats GROUP BY user_tg_id) s ON s.user_tg_id = u.user_tg_id ")
# The same row for a search by ID or name: totals of the found players only, not GROUP BY over the whole table
# (S04, 1M synthetic rows: 60 -> 31 ms). The full list keeps _PLAYER_SQL: there one pass is cheaper than a lookup per player.
_FOUND_PLAYER_SQL = (
    "SELECT u.user_tg_id, u.user_tg_username, COALESCE(u.bot_rank, 0), COALESCE(s.total, 0), s.last, u.user_tg_name "
    "FROM users u LEFT JOIN LATERAL (SELECT SUM(user_messages_count_all_time) AS total, MAX(last_message_at) AS last "
    "FROM user_chat_stats WHERE user_tg_id = u.user_tg_id) s ON TRUE ")
_CHAT_SQL = (
    "SELECT c.chat_id, c.chat_title, COALESCE(s.members, 0), COALESCE(s.total, 0), s.last "
    "FROM chat_settings c LEFT JOIN (SELECT chat_tg_id, COUNT(*) FILTER (WHERE NOT COALESCE(is_left, FALSE)) AS members, "
    "SUM(user_messages_count_all_time) AS total, MAX(last_message_at) AS last FROM user_chat_stats "
    "GROUP BY chat_tg_id) s ON s.chat_tg_id = c.chat_id ")


def _player_row(r) -> dict:
    return {"id": int(r[0]), "username": r[1], "rank_name": bot_rank_name(int(r[2])) if r[2] else "",
            "messages": int(r[3]), "last": _iso(r[4]), "name": r[5] or ""}


async def _with_tags(db, players: list[dict], per_player: int = 3) -> list[dict]:
    """К найденным игрокам — их теги в чатах (до per_player разных): по ним тоже ищут, и по ним узнают человека."""
    ids = [p["id"] for p in players]
    for p in players:
        p["tags"] = []
    if not ids:
        return players
    marks = ", ".join("?" for _ in ids)
    async with db.execute(
        f"SELECT user_tg_id, member_tag FROM user_chat_stats WHERE member_tag IS NOT NULL AND user_tg_id IN ({marks}) "
        f"ORDER BY last_message_at DESC NULLS LAST", tuple(ids)) as cur:
        rows = await cur.fetchall()
    by_id = {p["id"]: p for p in players}
    for uid, tag in rows:
        tags = by_id[int(uid)]["tags"]
        if tag and tag not in tags and len(tags) < per_player:
            tags.append(tag)
    return players


def _chat_row(r) -> dict:
    return {"id": int(r[0]), "title": r[1] or str(r[0]), "members": int(r[2]), "messages": int(r[3]), "last": _iso(r[4])}


# Быстрые фильтры поиска игроков: название и условие по таблице users (u).
FILTERS = {
    "vip": "VIP",
    "banned": "С баном",
    "warned": "С варнами",
    "new": "Новые за 7 дней",
    "watch": "На контроле",
    "staff": "Персонал",
}
FILTER_LIMIT = 30
SEARCH_PAGE = 20
# Фильтры с числом или игроком: «idle:30» — не писал 30+ дней, «active:7» — писал за 7 дней,
# «silent» — ни разу не писал в чатах с ботом, «linked:<id>» — возможные связи игрока (как в его карточке).
PARAM_FILTERS = {"idle": "Не писали {n}+ дн.", "active": "Писали за {n} дн.", "linked": "Связи игрока id{n}"}
FILTER_DAYS_MAX = 366


def _uses_last(flt: str) -> bool:
    """Фильтр по последнему сообщению (s.last из общей статистики игрока)."""
    parsed = _param_filter(flt)
    return bool(parsed and parsed[0] in ("idle", "active"))


def _param_filter(flt: str) -> tuple[str, int] | None:
    """«idle:30» → ("idle", 30); чужое или вне границ → None."""
    kind, _, raw = flt.partition(":")
    if kind not in PARAM_FILTERS or not raw.isdecimal() or len(raw) > 15:
        return None
    n = int(raw)
    if kind != "linked" and not 1 <= n <= FILTER_DAYS_MAX:
        return None
    return kind, n


def filter_title(flt: str) -> str:
    if flt in FILTERS:
        return FILTERS[flt]
    if flt == "silent":
        return "Ни разу не писали"
    parsed = _param_filter(flt)
    return PARAM_FILTERS[parsed[0]].format(n=parsed[1]) if parsed else ""


def is_known_filter(flt: str) -> bool:
    return flt in FILTERS or flt == "silent" or _param_filter(flt) is not None


async def _filter_cond(db, flt: str) -> tuple[str, tuple]:
    """Условие любого фильтра (кроме регалий): именованные — из _filter_sql, с числом — здесь."""
    if flt == "silent":
        return ("NOT EXISTS (SELECT 1 FROM user_chat_stats x WHERE x.user_tg_id = u.user_tg_id "
                "AND COALESCE(x.user_messages_count_all_time, 0) > 0)"), ()
    parsed = _param_filter(flt)
    if not parsed:
        return _filter_sql(flt)
    kind, n = parsed
    if kind == "idle":
        return "s.last < NOW() - make_interval(days => ?)", (n,)
    if kind == "active":
        return "s.last >= NOW() - make_interval(days => ?)", (n,)
    found = await linked(db, n)
    ids = {u["id"] for key in ("same_username", "same_name") for u in found[key]} | {u["id"] for u in found["invited"]["items"]}
    if found["invited_by"]:
        ids.add(found["invited_by"]["id"])
    return "u.user_tg_id = ANY(?::bigint[])", (sorted(ids),)


async def _with_status(db, players: list[dict]) -> list[dict]:
    """К найденным — бан, мут и варны сейчас: видно в списке, не открывая карточку. Пачкой по всем найденным."""
    ids = [p["id"] for p in players]
    for p in players:
        p["status"] = {"ban": False, "global_ban": False, "mute": False, "warns": 0}
    if not ids:
        return players
    by_id = {p["id"]: p["status"] for p in players}
    async with db.execute(
        "SELECT user_id, bool_or(chat_id = ?), bool_or(chat_id <> ?) FROM chat_blacklist WHERE user_id = ANY(?::bigint[]) "
        "AND (expires_at IS NULL OR expires_at > NOW()) GROUP BY user_id",
        (global_moderation.GLOBAL_CHAT, global_moderation.GLOBAL_CHAT, ids)) as cur:
        for uid, global_ban, ban in await cur.fetchall():
            by_id[int(uid)].update(global_ban=bool(global_ban), ban=bool(ban))
    async with db.execute(
        "SELECT DISTINCT user_tg_id FROM user_chat_stats WHERE user_tg_id = ANY(?::bigint[]) AND muted_until > NOW()",
        (ids,)) as cur:
        for (uid,) in await cur.fetchall():
            by_id[int(uid)]["mute"] = True
    async with db.execute(
        "SELECT user_id, COUNT(*) FROM user_warnings WHERE user_id = ANY(?::bigint[]) AND revoked_at IS NULL "
        "AND (expires_at IS NULL OR expires_at > NOW()) GROUP BY user_id", (ids,)) as cur:
        for uid, n in await cur.fetchall():
            by_id[int(uid)]["warns"] = int(n)
    return players


def _page(players: list[dict], total: int, offset: int, limit: int) -> dict:
    return {"players": players, "chats": [], "total": total, "offset": offset, "limit": limit,
            "next_offset": offset + limit if offset + limit < total else None}


def _filter_sql(flt: str) -> tuple[str, tuple]:
    """Условие фильтра и его параметры; пустой фильтр — без условия."""
    if flt == "vip":
        return "EXISTS (SELECT 1 FROM vip_subscriptions v WHERE v.user_id = u.user_tg_id AND v.expires_at > NOW())", ()
    if flt == "banned":   # бан в любом чате или глобальный (он лежит в том же списке под чатом 0)
        return ("EXISTS (SELECT 1 FROM chat_blacklist b WHERE b.user_id = u.user_tg_id "
                "AND (b.expires_at IS NULL OR b.expires_at > NOW()))"), ()
    if flt == "warned":
        return ("EXISTS (SELECT 1 FROM user_warnings w WHERE w.user_id = u.user_tg_id AND w.revoked_at IS NULL "
                "AND (w.expires_at IS NULL OR w.expires_at > NOW()))"), ()
    if flt == "new":   # впервые появился не раньше 7 дней назад: ни записи в чате, ни сообщения раньше
        cutoff = (local_now().date() - timedelta(days=7)).isoformat()
        return ("EXISTS (SELECT 1 FROM user_chat_stats x WHERE x.user_tg_id = u.user_tg_id) "
                "AND NOT EXISTS (SELECT 1 FROM user_chat_stats x WHERE x.user_tg_id = u.user_tg_id "
                "AND (x.joined_at < NOW() - INTERVAL '7 days' OR x.membership_since < NOW() - INTERVAL '7 days')) "
                "AND NOT EXISTS (SELECT 1 FROM daily_user_stats d WHERE d.user_id = u.user_tg_id AND d.date < ?)"), (cutoff,)
    if flt == "watch":
        return "EXISTS (SELECT 1 FROM bot_staff_watch t WHERE t.user_id = u.user_tg_id AND t.removed_at IS NULL)", ()
    if flt == "staff":
        return "COALESCE(u.bot_rank, 0) > 0", ()
    return "", ()


def is_mark_filter(flt: str) -> bool:
    return flt in {"needs_staff_mark", "manual_marks", "no_manual_marks"} or any(
        flt == f"{prefix}:{mark}" for prefix in ("marked", "missing") for mark in GRANTABLE)


async def _mark_search(db, q: str, flt: str, offset: int) -> dict:
    """A paged review queue; no automatic/manual awards are inferred here."""
    from infrastructure.repositories import marks_v1
    from bot.config import config
    await marks_v1.ensure_tables(db)
    params = []
    manual = "EXISTS (SELECT 1 FROM player_marks_v1 m WHERE m.user_id=u.user_tg_id AND m.mark_id=ANY(?::text[]))"
    if flt == "needs_staff_mark":
        # Keep creator override consistent with get_bot_rank; testers have no
        # staff badge recommendation and never enter this queue.
        role = "CASE WHEN u.user_tg_id=? THEN 6 ELSE COALESCE(u.bot_rank,0) END"
        expected = f"CASE ({role}) WHEN 2 THEN 'helper' WHEN 3 THEN 'helper' WHEN 4 THEN 'senior_helper' WHEN 5 THEN 'developer' WHEN 6 THEN 'developer' END"
        cond = f"({expected}) IS NOT NULL AND NOT EXISTS (SELECT 1 FROM player_marks_v1 m WHERE m.user_id=u.user_tg_id AND m.mark_id=({expected}))"
        params = [config.developer_id, config.developer_id]
    elif flt in {"manual_marks", "no_manual_marks"}:
        cond = ("NOT " if flt == "no_manual_marks" else "") + manual
        params = [list(GRANTABLE)]
    else:
        mode, mark = flt.split(":", 1)
        cond = ("NOT " if mode == "missing" else "") + "EXISTS (SELECT 1 FROM player_marks_v1 m WHERE m.user_id=u.user_tg_id AND m.mark_id=?)"
        params = [mark]
    where = "u.deleted_at IS NULL AND (" + cond + ")"
    if q:
        if q.isdecimal() and len(q) <= 15:
            where += " AND u.user_tg_id=?"
            params.append(int(q))
        else:
            where += " AND (u.user_tg_username ILIKE ? OR u.user_tg_name ILIKE ?)"
            params.extend([_like(q.lstrip('@')), _like(q)])
    async with db.execute("SELECT COUNT(*) FROM users u WHERE " + where, tuple(params)) as c:
        total = int((await c.fetchone())[0])
    async with db.execute(_PLAYER_SQL + "WHERE " + where + " ORDER BY s.last DESC NULLS LAST,u.user_tg_id LIMIT ? OFFSET ?",
                          (*params, FILTER_LIMIT, offset)) as c:
        players = await _with_tags(db, [_player_row(r) for r in await c.fetchall()])
    return {"players": players, "chats": [], "total": total, "offset": offset, "limit": FILTER_LIMIT,
            "next_offset": offset + FILTER_LIMIT if offset + FILTER_LIMIT < total else None}


async def search(db, q: str, limit: int = 20, flt: str = "", offset: int = 0, paged: bool = False, linked_ok: bool = True) -> dict:
    """Поиск людей и чатов; к найденным людям — подписанная ссылка на фото (у всех игроков) и бан/мут/варны сейчас.
    paged — страницы у любого поиска и фильтра (total, offset, next_offset); без него ответ прежний.
    linked_ok — можно ли «связи игрока» (их видят со старшего хелпера, как в карточке); нельзя — фильтр не применяется."""
    if flt.startswith("linked:") and not linked_ok:
        flt = ""
    data = await _search(db, q, limit=limit, flt=flt, offset=offset, paged=paged)
    await _with_status(db, data.get("players") or [])
    admin_avatars.attach(data.get("players") or [])
    if flt and (flt in FILTERS or (paged and is_known_filter(flt))):   # подпись — только у фильтра, который применился
        data["filter_title"] = filter_title(flt)
    return data


async def _paged_search(db, q: str, flt: str, offset: int) -> dict:
    """Страница игроков по фильтру и/или тексту: 30 по фильтру без текста, 20 по тексту. Чаты — только без фильтра.
    Всего найдено считается в том же запросе (COUNT(*) OVER()): второй проход по 100k игроков стоил столько же, сколько поиск."""
    cond, cparams = await _filter_cond(db, flt) if flt else ("", ())
    where, params, order = [cond] if cond else [], list(cparams), "s.last DESC NULLS LAST, u.user_tg_id"
    chats: list[dict] = []
    if q:
        digits = q.lstrip("-")
        if digits.isdecimal() and len(digits) <= 15:
            where.append("u.user_tg_id = ?")
            params.append(int(digits))
        else:
            name = q.lstrip("@")
            where.append("(u.user_tg_username ILIKE ? OR u.user_tg_name ILIKE ? "
                         "OR EXISTS (SELECT 1 FROM user_chat_stats t WHERE t.user_tg_id = u.user_tg_id AND t.member_tag ILIKE ?))")
            params += [_like(name), _like(q), _like(q)]
            order = ("lower(u.user_tg_username) = lower(?) DESC, lower(COALESCE(u.user_tg_name, '')) = lower(?) DESC, "
                     "COALESCE(s.total, 0) DESC, u.user_tg_id")
        if not flt:
            chats = await _find_chats(db, q)
    elif not flt:
        return await _search(db, q)
    limit = SEARCH_PAGE if q else FILTER_LIMIT
    sql_where = " AND ".join(where) or "TRUE"
    # «Не писал / писал за N дней» отбирают по последнему сообщению: один проход по статистике дешевле, чем по игроку отдельно.
    base = _PLAYER_SQL if _uses_last(flt) else _FOUND_PLAYER_SQL
    order_params = (q.lstrip("@"), q) if order.startswith("lower") else ()
    async with db.execute(base.replace(" FROM users u ", ", COUNT(*) OVER() FROM users u ", 1) +
                          f"WHERE {sql_where} ORDER BY {order} LIMIT ? OFFSET ?", (*params, *order_params, limit, offset)) as cur:
        rows = await cur.fetchall()
    if rows:
        total = int(rows[0][6])
    else:   # страница за концом списка: сколько всего, узнаём отдельно
        async with db.execute(f"SELECT COUNT(*) FROM ({base}WHERE {sql_where}) q", tuple(params)) as cur:
            total = int((await cur.fetchone())[0])
    players = await _with_tags(db, [_player_row(r) for r in rows])
    return {**_page(players, total, offset, limit), "chats": chats}


async def _find_chats(db, q: str, limit: int = 20) -> list[dict]:
    """Чаты по ID (любая запись: -100…, -…, без минуса) или по куску названия."""
    digits = q.lstrip("-")
    if digits.isdecimal() and len(digits) <= 15:   # длиннее — не ID (и не влезет в BIGINT)
        n = int(digits)
        ids = {n, -n} | ({-1000000000000 - n} if not q.startswith("-100") else set())
        marks = ", ".join("?" for _ in ids)
        async with db.execute(_CHAT_SQL + f"WHERE c.chat_id IN ({marks})", tuple(ids)) as cur:
            return [_chat_row(r) for r in await cur.fetchall()]
    async with db.execute(
        _CHAT_SQL + "WHERE c.chat_title ILIKE ? ORDER BY COALESCE(s.total, 0) DESC LIMIT ?", (_like(q), limit)) as cur:
        return [_chat_row(r) for r in await cur.fetchall()]


async def _search(db, q: str, limit: int = 20, flt: str = "", offset: int = 0, paged: bool = False) -> dict:
    """Игроки и чаты по ID, @нику (можно кусок), имени из Telegram или нику в чате; чаты по названию.
    Пустой запрос — самые свежие по активности. flt — быстрый фильтр игроков (FILTERS): чаты тогда не ищутся."""
    q = (q or "").strip()
    offset = max(0, min(int(offset), 1_000_000))
    if is_mark_filter(flt):
        return await _mark_search(db, q, flt, offset)
    if flt and is_known_filter(flt):
        await staff_watch.ensure_once(db)   # фильтр «на контроле» читает таблицу, которой на свежей базе ещё может не быть
    if paged:
        return await _paged_search(db, q, flt if is_known_filter(flt) else "", offset)
    flt = flt if flt in FILTERS else ""
    cond, cparams = _filter_sql(flt)
    if not q:
        where = cond or "s.last IS NOT NULL"
        async with db.execute(_PLAYER_SQL + f"WHERE {where} ORDER BY s.last DESC NULLS LAST, u.user_tg_id LIMIT ?",
                              (*cparams, FILTER_LIMIT if flt else limit)) as cur:
            players = await _with_tags(db, [_player_row(r) for r in await cur.fetchall()])
        if flt:
            async with db.execute(f"SELECT COUNT(*) FROM users u WHERE {cond}", cparams) as cur:
                return {"players": players, "chats": [], "total": int((await cur.fetchone())[0])}
        async with db.execute(_CHAT_SQL + "WHERE c.chat_id < 0 ORDER BY s.last DESC NULLS LAST LIMIT ?", (limit,)) as cur:
            chats = [_chat_row(r) for r in await cur.fetchall()]
        return {"players": players, "chats": chats}
    tail = f" AND {cond}" if cond else ""
    digits = q.lstrip("-")
    if digits.isdecimal() and len(digits) <= 15:   # длиннее — не ID (и не влезет в BIGINT)
        async with db.execute(_FOUND_PLAYER_SQL + "WHERE u.user_tg_id = ?" + tail, (int(digits), *cparams)) as cur:
            players = await _with_tags(db, [_player_row(r) for r in await cur.fetchall()])
        return {"players": players, "chats": [] if flt else await _find_chats(db, q, limit)}
    name = q.lstrip("@")
    async with db.execute(
        _FOUND_PLAYER_SQL + "WHERE (u.user_tg_username ILIKE ? OR u.user_tg_name ILIKE ? "
        "OR EXISTS (SELECT 1 FROM user_chat_stats t WHERE t.user_tg_id = u.user_tg_id AND t.member_tag ILIKE ?))" + tail +
        " ORDER BY lower(u.user_tg_username) = lower(?) DESC, lower(COALESCE(u.user_tg_name, '')) = lower(?) DESC, "
        "COALESCE(s.total, 0) DESC LIMIT ?", (_like(name), _like(q), _like(q), *cparams, name, q, limit)) as cur:
        players = await _with_tags(db, [_player_row(r) for r in await cur.fetchall()])
    return {"players": players, "chats": [] if flt else await _find_chats(db, q, limit)}


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
    if action in ("mark_grant", "mark_revoke"):
        return str(d.get("mark", ""))
    if action == "warn_limit":
        return str(d.get("value", ""))
    if action in ("message", "dm"):
        return f"«{d.get('text', '')}»"
    if action in ("skin_grant", "skin_revoke"):
        return f"«{d.get('name', d.get('skin', ''))}»"
    if action in ("watch_add", "watch_remove"):
        return ""
    if action == "sessions_revoke":
        return "у всех сотрудников" if d.get("all") else ""
    if action == "promo_bulk":
        return f"{d.get('count', 0)} шт. · {d.get('first', '')}… · {d.get('rewards', '')}"
    if action.startswith("promo_"):
        return str(d.get("code", "")) + (" · выключен" if action == "promo_active" and not d.get("active") else
                                         " · включён" if action == "promo_active" else "")
    if action == "switch":
        where = "везде" if not d.get("chat") else f"в чате {d['chat']}"
        return f"{d.get('feature', '')} {where} → {'включено' if d.get('enabled') else 'выключено'}"
    if action == "transfer":
        return ", ".join(d.get("currencies") or []) or "переводы выключены"
    if action == "digest_settings":
        return f"{'включён' if d.get('enabled') else 'выключен'}, в {d.get('hour', 9)}:00"
    if action == "report_settings":
        parts = ["админ-чат" if d.get("to_admin_chat") else "", f"личка модераторам чата с ранга {d['dm_chat_rank']}" if d.get("dm_chat_rank") else "",
                 f"личка персоналу с роли {d['dm_staff_rank']}" if d.get("dm_staff_rank") else "",
                 f"автора видят с роли {d.get('reporter_min_rank', '')}"]
        return "; ".join(x for x in parts if x)
    if action.startswith("report_"):
        return f"№{d.get('report', '')}"
    if action == "broadcast":
        head = f"{d.get('audience', '')}, " + ("отложена" if d.get("scheduled") else f"{d.get('total', 0)} получ.")
        return head + (f": «{d['text']}»" if d.get("text") else "")
    if action == "broadcast_resume":
        return f"№{d.get('broadcast', '')}, осталось {d.get('left', 0)}"
    if action == "broadcast_template":
        return ("удалён №" + str(d.get("template", ""))) if d.get("removed") else f"«{d.get('title', '')}»"
    if action == "journal_export":
        return f"за {_days(d.get('days', 0))}, строк: {d.get('rows', 0)}"
    if action == "broadcast_stop":
        return f"№{d.get('broadcast', '')}"
    return ""


def _details(extra) -> dict:
    """Подробности записи журнала: у действий админки это JSON, у модерации чата — просто причина (она может начинаться с «{»)."""
    if not extra:
        return {}
    if extra.startswith("{"):
        try:
            data = json.loads(extra)
            if isinstance(data, dict):
                return data
        except ValueError:
            pass
    return {"reason": extra}


async def history(db, *, user_id: int | None = None, chat_id: int | None = None, limit: int = 40) -> list[dict]:
    col = "user_id" if user_id is not None else "chat_id"
    key = user_id if user_id is not None else chat_id
    async with db.execute(
        f"SELECT actor_id, action, user_id, chat_id, details::text, created_at FROM bot_admin_actions WHERE {col} = ? "
        f"UNION ALL SELECT admin_id, action, user_id, chat_id, reason, created_at::timestamptz FROM moderation_logs "
        f"WHERE {col} = ? AND action <> 'global_ban_chat' ORDER BY 6 DESC LIMIT ?", (key, key, limit)) as cur:
        rows = await cur.fetchall()
    names = await _names(db, [r[0] for r in rows] + [r[2] for r in rows])
    titles = await _chat_titles(db, [r[3] for r in rows])
    tags = await member_tags.pairs(db, [(r[3], r[2]) for r in rows])
    out = []
    for actor, action, uid, cid, extra, at in rows:
        details = _details(extra)
        out.append({
            "action": action, "title": ACTION_TITLES.get(action, action), "text": describe(action, details),
            "reason": str(details.get("reason") or ""), "at": _iso(at),
            "actor": {"id": actor, "username": names.get(int(actor)) if actor else None},
            "user": {"id": uid, "username": names.get(int(uid)) if uid else None,
                     "tag": tags.get((int(cid), int(uid))) if cid else None} if uid else None,
            "chat": {"id": cid, "title": titles.get(int(cid)) if cid else None} if cid else None,
        })
    return out


# Общая лента действий персонала: действия сгруппированы по видам.
FEED_KINDS = {
    "moderation": ("Модерация", ("mute", "unmute", "kick", "ban", "unban", "warn", "unwarn", "unwarn_all", "global_ban",
                                 "global_unban", "block", "unblock", "shield", "unshield", "immune", "unimmune", "close",
                                 "open", "close_chat", "open_chat", "warn_limit")),
    "players": ("Игроки", ("balance", "vip", "rank", "mark_grant", "mark_revoke", "note_add", "note_remove", "watch_add", "watch_remove",
                           "dm", "skin_grant", "skin_revoke")),
    "chats": ("Чаты", ("message", "leave")),
    "promo": ("Промокоды", ("promo_create", "promo_update", "promo_active", "promo_bulk")),
    "switches": ("Функции", ("switch",)),
    "settings": ("Настройки", ("transfer", "report_settings", "digest_settings", "sessions_revoke", "grant", "owner_access", "owner_block", "journal_export")),
    "broadcast": ("Рассылка", ("broadcast", "broadcast_stop", "broadcast_resume", "broadcast_template")),
    "reports": ("Жалобы", ("report_in_work", "report_resolved", "report_rejected")),
    "purge": ("Чистка", ("purge_start", "purge_finish", "purge_reconcile")),
}
FEED_DAYS_MAX = 90
EXPORT_MAX_ROWS = 5000


async def _feed_rows(db, *, kind: str, actor_id: int | None, user_id: int | None, chat_id: int | None, days: int,
                     cursor: datetime | None, limit: int) -> list:
    """Строки ленты: действия из админки и модерация из чатов вместе, новые сверху."""
    actions = FEED_KINDS[kind][1] if kind in FEED_KINDS else tuple(a for _, acts in FEED_KINDS.values() for a in acts)
    marks = ", ".join("?" for _ in actions)

    def cond(actor_col: str, cast: str = "") -> tuple[str, list]:
        sql, args = f"action IN ({marks}) AND created_at > (NOW() - make_interval(days => ?)){cast}", [*actions, days]
        for col, value in ((actor_col, actor_id), ("user_id", user_id), ("chat_id", chat_id)):
            if value:
                sql += f" AND {col} = ?"
                args.append(value)
        if cursor:
            sql += f" AND created_at < ?::timestamptz{cast}"
            args.append(cursor)
        return sql, args

    c1, a1 = cond("actor_id")
    # moderation_logs.created_at is a plain TIMESTAMP: cast the bound, not the column, so the index on created_at works
    c2, a2 = cond("admin_id", "::timestamp")
    async with db.execute(
        f"SELECT actor_id, action, user_id, chat_id, details::text, created_at FROM bot_admin_actions WHERE {c1} "
        f"UNION ALL SELECT admin_id, action, user_id, chat_id, reason, created_at::timestamptz FROM moderation_logs "
        f"WHERE {c2} ORDER BY 6 DESC LIMIT ?", (*a1, *a2, limit)) as cur:
        return await cur.fetchall()


async def feed(db, *, kind: str = "", actor_id: int | None = None, user_id: int | None = None, chat_id: int | None = None,
               days: int = 7, before: str = "", limit: int = 30) -> dict:
    """Лента всех действий персонала за период; можно сузить до игрока или чата (из их карточки — одним касанием).
    before — время последней записи прошлой страницы."""
    days = max(1, min(int(days or 7), FEED_DAYS_MAX))
    limit = max(1, min(int(limit or 30), 100))
    cursor = None
    if before:   # asyncpg ждёт datetime, а не строку; битый курсор — ValueError, роутер начнёт с начала
        cursor = datetime.fromisoformat(before.replace("Z", "+00:00").replace(" ", "+"))   # «+» в адресе без кодирования приходит пробелом
        if cursor.tzinfo is None:
            cursor = cursor.replace(tzinfo=timezone.utc)
    rows = await _feed_rows(db, kind=kind, actor_id=actor_id, user_id=user_id, chat_id=chat_id, days=days, cursor=cursor,
                            limit=limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    names = await _names(db, [r[0] for r in rows] + [r[2] for r in rows])
    titles = await _chat_titles(db, [r[3] for r in rows])
    tags = await member_tags.pairs(db, [(r[3], r[2]) for r in rows])
    items = []
    for actor, action, uid, cid, extra, at in rows:
        details = _details(extra)
        kind_of = next((k for k, (_, acts) in FEED_KINDS.items() if action in acts), "")
        item = {
            "action": action, "kind": kind_of, "title": ACTION_TITLES.get(action, action), "text": describe(action, details),
            "reason": str(details.get("reason") or ""), "at": _iso(at),
            "actor": {"id": actor, "username": names.get(int(actor)) if actor else None},
            "user": {"id": uid, "username": names.get(int(uid)) if uid else None,
                     "tag": tags.get((int(cid), int(uid))) if cid else None} if uid else None,
            "chat": {"id": cid, "title": titles.get(int(cid)) if cid else None} if cid else None}
        for person in (item["actor"], item["user"]):   # лица в ленте: кто сделал и с кем
            if person:
                person["avatar"] = admin_avatars.avatar_url(person["id"])
        items.append(item)
    async with db.execute(
        "SELECT DISTINCT actor_id FROM bot_admin_actions WHERE actor_id IS NOT NULL AND created_at > NOW() - INTERVAL '90 days' "
        "UNION SELECT DISTINCT admin_id FROM moderation_logs WHERE admin_id IS NOT NULL "
        "AND created_at > (NOW() - INTERVAL '90 days')::timestamp LIMIT 100") as cur:
        actor_ids = [int(r[0]) for r in await cur.fetchall()]
    actor_names = await _names(db, actor_ids)
    return {"items": items, "more": more, "next": items[-1]["at"] if more and items else "",
            "kinds": [{"key": k, "title": t} for k, (t, _) in FEED_KINDS.items()],
            "actors": sorted(({"id": i, "username": actor_names.get(i)} for i in actor_ids), key=lambda a: (a["username"] or "~", a["id"]))}


async def export_csv(db, *, kind: str = "", actor_id: int | None = None, user_id: int | None = None,
                     chat_id: int | None = None, days: int = 7) -> tuple[str, int]:
    """Журнал за период (до 90 дней, до 5000 строк) таблицей CSV для Excel: текст и сколько строк вошло."""
    import csv
    import io
    days = max(1, min(int(days or 7), FEED_DAYS_MAX))
    rows = await _feed_rows(db, kind=kind, actor_id=actor_id, user_id=user_id, chat_id=chat_id, days=days, cursor=None,
                            limit=EXPORT_MAX_ROWS)
    names = await _names(db, [r[0] for r in rows] + [r[2] for r in rows])
    titles = await _chat_titles(db, [r[3] for r in rows])
    def cell(value) -> str:   # текст игроков и чатов не должен стать формулой в Excel
        text = str(value)
        return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text

    out = io.StringIO()
    table = csv.writer(out, delimiter=";")
    table.writerow(["Когда (UTC)", "Действие", "Суть", "Причина", "Кто", "ID кто", "Игрок", "ID игрока", "Чат", "ID чата"])
    for actor, action, uid, cid, extra, at in rows:
        details = _details(extra)
        table.writerow([at.strftime("%Y-%m-%d %H:%M:%S") if at else "", ACTION_TITLES.get(action, action), cell(describe(action, details)),
                        cell(details.get("reason") or ""), cell(names.get(int(actor)) or "" if actor else "бот"), actor or "",
                        cell(names.get(int(uid)) or "" if uid else ""), uid or "", cell(titles.get(int(cid)) or "" if cid else ""), cid or ""])
    return "\ufeff" + out.getvalue(), len(rows)   # BOM: Excel открывает русский текст без кракозябр


# ── Карточка игрока ──────────────────────────────────────────────────────────

async def player(db, uid: int) -> dict | None:
    async with db.execute(
        "SELECT user_tg_username, COALESCE(user_balance_mora, 0), COALESCE(user_balance_diamonds, 0), "
        "COALESCE(user_balance_zarniki, 0), COALESCE(is_sponsor, FALSE), deleted_at, user_tg_name "
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
        "CASE WHEN s.muted_until = 'infinity' THEN NULL ELSE s.muted_until END, s.member_tag, "
        "COALESCE(s.is_immune, FALSE), CASE WHEN s.immune_until > NOW() THEN s.immune_until END "
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
    for cid, title, total, last, left, muted, muted_until, tag, immune, shield_until in rows:
        cid = int(cid)
        local_rank = await ranks.get_rank(db, cid, uid)
        chats.append({"id": cid, "title": title or str(cid), "messages": int(total), "last": _iso(last), "tag": member_tags.clean(tag),
                      "left": bool(left), "muted": bool(muted), "muted_until": _iso(muted_until),
                      "immune": bool(immune), "shield_until": _iso(shield_until),
                      "ban": bans.get(cid), "warns": warns.get(cid, 0),
                      "rank_name": ranks.rank_name(local_rank), "local_rank": local_rank})
    for cid, title in extra_titles.items():   # забанен в чате, где не писал
        chats.append({"id": cid, "title": title or str(cid), "messages": 0, "last": None, "left": True,
                      "muted": False, "muted_until": None, "immune": False, "shield_until": None, "ban": bans[cid], "warns": warns.get(cid, 0),
                      "rank_name": ranks.rank_name(0), "local_rank":0, "tag": None})

    names = await _names(db, [family["partner"]] if family and family["partner"] else [])
    if family and family["partner"]:
        family["partner_username"] = names.get(family["partner"])
    return {
        "id": uid, "username": u[0], "name": u[6] or "", "avatar": admin_avatars.avatar_url(uid),
        "look": await skins_v3.own_look(db, uid) if vip else None,
        "rank": rank, "rank_name": bot_rank_name(rank), "sponsor": bool(u[4]),
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
        "watch": await staff_watch.info(db, uid),
        "names": await name_history.of_user(db, uid, 20),
        "tag_history": await member_tags.history(db, uid, 20),
    }


WALLET_LIMIT = 20
_WALLET_CURRENCIES = {"mora": "🪙 Мора", "diamonds": "💎 Алмазы", "dark_mora": "🌑 Тёмная мора", "zarniki": "✨ Зарники",
                      "essence": "🔮 Эссенция"}


def _amount(value) -> str:
    """Сумма строкой без лишних нулей (деньги не через float): 250.000000 → «250», 1.50 → «1.5»."""
    text = format(value, "f") if not isinstance(value, str) else value
    return text.rstrip("0").rstrip(".") if "." in text else text


async def wallet(db, uid: int, limit: int = WALLET_LIMIT) -> list[dict]:
    """Последние движения валют игрока (общий журнал валют и журнал Эссенции): когда, сколько, откуда. Только чтение."""
    from services.bot_metrics import reason_title
    out: list[dict] = []
    for table, sql in (("economic_ledger", "SELECT currency, delta, balance_after, reason_code, created_at FROM economic_ledger "
                                           "WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?"),
                       ("skins_v3_essence_ledger", "SELECT 'essence', delta, balance_after, reason, created_at FROM skins_v3_essence_ledger "
                                                   "WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?")):
        async with db.execute("SELECT to_regclass(?) IS NOT NULL", (table,)) as cur:
            if not (await cur.fetchone())[0]:   # на свежей базе журнала ещё нет: карточка открывается без истории
                continue
        async with db.execute(sql, (uid, limit)) as cur:
            rows = await cur.fetchall()
        out += [{"currency": _WALLET_CURRENCIES.get(str(c), str(c)), "code": str(c), "delta": _amount(d), "after": _amount(a),
                 "reason": reason_title(str(r)), "at": _iso(at)} for c, d, a, r, at in rows]
    out.sort(key=lambda x: x["at"] or "", reverse=True)
    return out[:limit]


LINKED_LIMIT = 10

# Что показывать в «Настройках чата»: ранги действий модерации (с какого ранга в чате разрешено).
_RANK_COLUMNS = (("rank_warn", "Варн"), ("rank_mute", "Мут"), ("rank_kick", "Кик"), ("rank_ban", "Бан"),
                 ("rank_shield", "Защита"), ("rank_immune", "Иммунитет"))
_FLAG_COLUMNS = (("events_enabled", "События чата", 1), ("echo_events_enabled", "Эхо-события", 0),
                 ("nsfw_warps_allowed", "Варпы 18+", 1), ("include_in_global_top", "Участие в общем топе", 1))


async def chat_settings_summary(db, cid: int) -> dict:
    """Настройки чата одним взглядом: кто что может, чистка, модули, флаги. Только чтение."""
    from core.chat_modules import CHAT_MODULES
    cols = [c for c, _ in _RANK_COLUMNS] + [c for c, _, _ in _FLAG_COLUMNS] + list(CHAT_MODULES) + [
        "is_purging", "purge_min_rank", "purge_action_rank", "shield_duration_days"]
    async with db.execute(f"SELECT {', '.join(f'COALESCE({c}::int, 0)' for c in cols)} FROM chat_settings WHERE chat_id = ?", (cid,)) as cur:
        row = await cur.fetchone()
    if not row:
        return {}
    v = dict(zip(cols, row))
    rights = await ranks.rights_map(db, cid)
    return {
        "ranks": [{"key": c, "title": t, "rank": rights[c.removeprefix("rank_")], "name": ranks.rank_name(rights[c.removeprefix("rank_")])} for c, t in _RANK_COLUMNS],
        "purge": {"on": bool(v["is_purging"]), "min_rank": ranks.rank_name(int(v["purge_min_rank"])),
                  "action_rank": ranks.rank_name(int(v["purge_action_rank"]))},
        "shield_days": int(v["shield_duration_days"]),
        "flags": [{"title": t, "on": bool(v[c])} for c, t, _ in _FLAG_COLUMNS],
        "modules": [{"key": k, "icon": m["icon"], "name": m["name"], "on": bool(v[k])} for k, m in CHAT_MODULES.items()],
    }


ATTENTION_KINDS = {"no_rights": "Бот без прав модерации", "quiet": "Тихо 30 дней", "left": "Бота удалили"}
ATTENTION_LIMIT = 50


async def chats_attention(db, kind: str = "") -> dict:
    """Чаты, где что-то не так: бот без прав модерации, нет сообщений 30 дней, бота удалили. kind пустой — все проблемы."""
    quiet_since = (local_now().date() - timedelta(days=29)).isoformat()
    async with db.execute(
        "SELECT c.chat_id, c.chat_title, c.bot_left_at IS NOT NULL AS left_, "
        "(c.bot_left_at IS NULL AND (c.bot_can_moderate = FALSE OR c.bot_is_admin = FALSE)) AS no_rights, "
        "(c.bot_left_at IS NULL AND NOT EXISTS (SELECT 1 FROM daily_user_stats d WHERE d.chat_id = c.chat_id AND d.date >= ?)) AS quiet, "
        "COALESCE(s.members, 0), s.last FROM chat_settings c LEFT JOIN (SELECT chat_tg_id, "
        "COUNT(*) FILTER (WHERE NOT COALESCE(is_left, FALSE)) AS members, MAX(last_message_at) AS last "
        "FROM user_chat_stats GROUP BY chat_tg_id) s ON s.chat_tg_id = c.chat_id WHERE c.chat_id < 0",
        (quiet_since,)) as cur:
        rows = await cur.fetchall()
    items = []
    for cid, title, left_, no_rights, quiet, members, last in rows:
        problems = [k for k, on in (("left", left_), ("no_rights", no_rights), ("quiet", quiet)) if on]
        if problems and (not kind or kind in problems):
            items.append({"id": int(cid), "title": title or str(cid), "members": int(members), "last": _iso(last),
                          "problems": [{"key": k, "title": ATTENTION_KINDS[k]} for k in problems]})
    items.sort(key=lambda x: (-x["members"], x["id"]))
    return {"items": items[:ATTENTION_LIMIT], "total": len(items), "kinds": ATTENTION_KINDS}


PEOPLE_ATTENTION_LIMIT = 6


async def people_attention(db, *, reports_on: bool = True, limit: int = PEOPLE_ATTENTION_LIMIT) -> dict:
    """Кто требует внимания прямо сейчас: бан во всех чатах, повторные жалобы, контроль персонала.

    Каждая строка — человек и одна причина открыть его карточку: сначала баны, затем жалобы,
    затем контроль. Повторные жалобы считает служба жалоб (3+ за 30 дней, отклонённые не в счёт),
    и видны они только тому, кому открыт раздел «Жалобы» (reports_on). Один человек — одна строка.
    """
    limit = max(1, min(int(limit or PEOPLE_ATTENTION_LIMIT), 50))
    items: list[dict] = []
    seen: set[int] = set()

    def add(uid, username, name, flag, kind, note, at, label):
        uid = int(uid)
        if uid in seen:
            return
        seen.add(uid)
        items.append({"id": uid, "username": username or None, "name": name or "",
                      "avatar": admin_avatars.avatar_url(uid), "flag": flag, "flag_kind": kind,
                      "note": note or "", "at": at.isoformat() if hasattr(at, "isoformat") else at,
                      "at_label": label})

    async with db.execute(
        "SELECT b.user_id, u.user_tg_username, u.user_tg_name, b.reason, b.added_at FROM chat_blacklist b "
        "LEFT JOIN users u ON u.user_tg_id = b.user_id "
        "WHERE b.chat_id = ? AND (b.expires_at IS NULL OR b.expires_at > NOW()) ORDER BY b.added_at DESC LIMIT ?",
        (global_moderation.GLOBAL_CHAT, limit)) as cur:
        for uid, username, name, reason, at in await cur.fetchall():
            add(uid, username, name or ("@" + username if username else None), "🚫 бан во всех чатах", "bad",
                f"причина: {str(reason)[:80]}" if reason else "", at, "забанен")
    if reports_on:
        for r in await reports_service.repeat_offenders(db, limit=limit):
            bits = []
            if r["open"]:
                bits.append(f"в работе: {r['open']}")
            if r["confirmed"]:
                bits.append(f"подтверждено: {r['confirmed']}")
            add(r["id"], None, r["name"], f"⚠️ жалоб: {r['reports']}", "warn",
                " · ".join(bits) or "ещё не разобраны", r["last"], "последняя жалоба")
    await staff_watch.ensure_once(db)
    async with db.execute(
        "SELECT t.user_id, u.user_tg_username, u.user_tg_name, t.reason, t.added_at FROM bot_staff_watch t "
        "LEFT JOIN users u ON u.user_tg_id = t.user_id WHERE t.removed_at IS NULL ORDER BY t.added_at DESC LIMIT ?",
        (limit,)) as cur:
        for uid, username, name, reason, at in await cur.fetchall():
            add(uid, username, name or ("@" + username if username else None), "👁 на контроле", "warn",
                f"причина: {str(reason)[:80]}" if reason else "", at, "на контроле с")
    return {"items": items[:limit], "total": len(items)}


async def linked(db, uid: int) -> dict:
    """Возможные связи между аккаунтами по тому, что и так видно в Telegram и в приглашениях бота.
    Устройства и адреса не собираются. Совпадение — повод присмотреться, а не доказательство."""
    await name_history.ensure_schema(db)
    async with db.execute(
        "SELECT DISTINCT h2.user_id, u.user_tg_username, h2.value FROM user_name_history h1 "
        "JOIN user_name_history h2 ON h2.kind = 'username' AND lower(h2.value) = lower(h1.value) AND h2.user_id <> h1.user_id "
        "LEFT JOIN users u ON u.user_tg_id = h2.user_id WHERE h1.user_id = ? AND h1.kind = 'username' "
        "ORDER BY h2.user_id LIMIT ?", (uid, LINKED_LIMIT)) as cur:
        same_username = [{"id": int(r[0]), "username": r[1], "value": r[2]} for r in await cur.fetchall()]
    async with db.execute(
        "SELECT o.user_tg_id, o.user_tg_username, o.user_tg_name FROM users me JOIN users o "
        "ON lower(o.user_tg_name) = lower(me.user_tg_name) AND o.user_tg_id <> me.user_tg_id "
        "WHERE me.user_tg_id = ? AND char_length(me.user_tg_name) >= 6 ORDER BY o.user_tg_id LIMIT ?", (uid, LINKED_LIMIT)) as cur:
        same_name = [{"id": int(r[0]), "username": r[1], "name": r[2]} for r in await cur.fetchall()]
    async with db.execute(
        "SELECT i.user_tg_id, i.user_tg_username FROM users me JOIN users i ON i.user_tg_id = me.referred_by "
        "WHERE me.user_tg_id = ?", (uid,)) as cur:
        row = await cur.fetchone()
    invited_by = {"id": int(row[0]), "username": row[1]} if row else None
    async with db.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (uid,)) as cur:
        invited_total = int((await cur.fetchone())[0])
    async with db.execute(
        "SELECT user_tg_id, user_tg_username FROM users WHERE referred_by = ? ORDER BY user_tg_id DESC LIMIT ?",
        (uid, LINKED_LIMIT)) as cur:
        invited = [{"id": int(r[0]), "username": r[1]} for r in await cur.fetchall()]
    return {"same_username": same_username, "same_name": same_name, "invited_by": invited_by,
            "invited": {"total": invited_total, "items": invited}}


# ── Карточка чата ────────────────────────────────────────────────────────────

SANCTION_KINDS = ("bans", "mutes", "warns")
SANCTION_PAGE = 20
_SANCTION_SQL = {
    "bans": ("FROM chat_blacklist WHERE chat_id = ? AND (expires_at IS NULL OR expires_at > NOW())",
             "SELECT user_id, reason, CASE WHEN expires_at = 'infinity' THEN NULL ELSE expires_at END ",
             "ORDER BY added_at DESC, user_id"),
    "mutes": ("FROM user_chat_stats WHERE chat_tg_id = ? AND muted_until > NOW()",
              "SELECT user_tg_id, CASE WHEN muted_until = 'infinity' THEN NULL ELSE muted_until END ",
              "ORDER BY muted_until, user_tg_id"),
}


async def chat_sanctions(db, cid: int, kind: str, offset: int = 0, limit: int = SANCTION_PAGE) -> dict:
    """Страница действующих банов, мутов или варнов чата; total — сколько всего, next — откуда брать дальше."""
    offset = max(0, int(offset))
    if kind == "warns":
        where = "FROM user_warnings WHERE chat_id = ? AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > NOW())"
        async with db.execute(f"SELECT COUNT(DISTINCT user_id) {where}", (cid,)) as cur:
            total = int((await cur.fetchone())[0])
        async with db.execute(f"SELECT user_id, COUNT(*) {where} GROUP BY user_id ORDER BY 2 DESC, user_id LIMIT ? OFFSET ?",
                              (cid, limit, offset)) as cur:
            items = [{"user": int(r[0]), "count": int(r[1])} for r in await cur.fetchall()]
    elif kind in _SANCTION_SQL:
        where, select, order = _SANCTION_SQL[kind]
        async with db.execute(f"SELECT COUNT(*) {where}", (cid,)) as cur:
            total = int((await cur.fetchone())[0])
        async with db.execute(f"{select}{where} {order} LIMIT ? OFFSET ?", (cid, limit, offset)) as cur:
            rows = await cur.fetchall()
        items = ([{"user": int(r[0]), "reason": r[1] or "", "until": _iso(r[2])} for r in rows] if kind == "bans"
                 else [{"user": int(r[0]), "until": _iso(r[1])} for r in rows])
    else:
        raise ValueError(kind)
    names = await _names(db, [x["user"] for x in items])
    tags = await member_tags.many(db, cid, [x["user"] for x in items])
    for x in items:
        x["username"] = names.get(x["user"])
        x["tag"] = tags.get(x["user"])
    return {"items": items, "total": total, "next": offset + len(items) if offset + len(items) < total else None}


async def chat(db, cid: int) -> dict | None:
    async with db.execute(
        "SELECT chat_title, owner_id, COALESCE(is_closed, FALSE), COALESCE(max_warnings, 3), bot_left_at, "
        "bot_is_admin, bot_can_moderate FROM chat_settings WHERE chat_id = ?", (cid,)) as cur:
        c = await cur.fetchone()
    if not c:
        return None
    today = local_now().date()
    async with db.execute(
        "SELECT COUNT(*) FILTER (WHERE NOT COALESCE(is_left, FALSE) AND NOT COALESCE(is_bot, FALSE)), "
        "COALESCE(SUM(user_messages_count_all_time) FILTER (WHERE NOT COALESCE(is_bot, FALSE)), 0) "
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
        "AND NOT COALESCE(s.is_bot, FALSE) "
        "ORDER BY s.user_messages_count_all_time DESC NULLS LAST LIMIT 10", (cid,)) as cur:
        top = [{"id": int(r[0]), "username": r[1], "messages": int(r[2] or 0)} for r in await cur.fetchall()]
    top_tags = await member_tags.many(db, cid, [x["id"] for x in top])
    for x in top:
        x["tag"] = top_tags.get(x["id"])
    async with db.execute(
        "SELECT COUNT(*) FROM user_chat_stats WHERE chat_tg_id = ? AND NOT COALESCE(is_left, FALSE) "
        "AND COALESCE(member_tag, '') <> ''", (cid,)) as cur:
        tagged = int((await cur.fetchone())[0])

    sanctions = {kind: await chat_sanctions(db, cid, kind) for kind in SANCTION_KINDS}
    names = await _names(db, [c[1]] if c[1] else [])

    async with db.execute(
        "SELECT l.admin_chat_id, s.chat_title FROM chat_links l LEFT JOIN chat_settings s ON s.chat_id = l.admin_chat_id "
        "WHERE l.main_chat_id = ?", (cid,)) as cur:
        link = await cur.fetchone()
    off = (await feature_switches.state(db, cid))["chat"]
    return {
        "id": cid, "title": c[0] or str(cid), "closed": bool(c[2]), "warn_limit": int(c[3]),
        "settings": await chat_settings_summary(db, cid),
        "bot": {"left_at": c[4].isoformat() if c[4] else None, "is_admin": c[5], "can_moderate": c[6]},   # None — бот ещё не сообщал
        "owner": {"id": int(c[1]), "username": names.get(int(c[1]))} if c[1] else None,
        "admin_chat": {"id": int(link[0]), "title": link[1] or str(link[0])} if link else None,
        "members": int(members), "tagged": tagged, "messages": {"total": int(total), **stats}, "top": top,
        "sanctions": sanctions,
        "switched_off": [{"key": k, "reason": v["reason"]} for k, v in off.items()],
    }
