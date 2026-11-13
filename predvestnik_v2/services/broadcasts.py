"""Рассылка от бота из админки: в чаты или игрокам в личку, всем или по сегменту.

Сегмент — набор условий (см. normalize_segment): все чаты / выбранные / активные за N дней; все игроки / VIP /
активные / новички / участники выбранных чатов / выбранные люди. Получатели фиксируются при запуске в
bot_broadcast_targets, поэтому у каждой рассылки есть отчёт «кому не дошло и почему», а прерванную (перезапуск,
остановка) можно продолжить, а недоставленным — отправить повторно. Рассылку можно отложить на время.

К сообщению можно приложить картинку (JPEG, PNG или WebP до 5 МБ): тогда текст становится подписью к ней (Telegram
ограничивает подпись 1024 знаками). Картинка хранится в базе (bot_broadcast_media) и загружается в Telegram один раз:
дальше всем уходит её file_id.

Рассылка идёт в фоне того же процесса, с паузой между сообщениями (лимиты Telegram). Игроки, которым бот не отвечает
(блокировка) или с глобальным баном, а также те, кто заблокировал бота в Telegram, и чаты, из которых бота удалили, рассылку не получают. Одновременно идёт одна рассылка.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from loguru import logger

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS bot_broadcasts (
        id          BIGSERIAL PRIMARY KEY,
        actor_id    BIGINT NOT NULL,
        audience    TEXT   NOT NULL,              -- chats | players
        text        TEXT   NOT NULL,
        request_id  TEXT,
        status      TEXT   NOT NULL DEFAULT 'running',   -- scheduled | running | done | stopped | interrupted
        total       INTEGER NOT NULL DEFAULT 0,
        sent        INTEGER NOT NULL DEFAULT 0,
        failed      INTEGER NOT NULL DEFAULT 0,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        finished_at TIMESTAMPTZ
    )""",
    "ALTER TABLE bot_broadcasts ADD COLUMN IF NOT EXISTS html BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE bot_broadcasts ADD COLUMN IF NOT EXISTS segment JSONB",
    "ALTER TABLE bot_broadcasts ADD COLUMN IF NOT EXISTS button_text TEXT",
    "ALTER TABLE bot_broadcasts ADD COLUMN IF NOT EXISTS button_url TEXT",
    "ALTER TABLE bot_broadcasts ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ",
    "ALTER TABLE bot_broadcasts ADD COLUMN IF NOT EXISTS parent_id BIGINT",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_broadcasts_request ON bot_broadcasts (actor_id, request_id) "
    "WHERE request_id IS NOT NULL",
    """CREATE TABLE IF NOT EXISTS bot_broadcast_targets (
        broadcast_id BIGINT NOT NULL,
        target_id    BIGINT NOT NULL,
        status       TEXT   NOT NULL DEFAULT 'pending',   -- pending | sent | failed
        error        TEXT,
        PRIMARY KEY (broadcast_id, target_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_bot_broadcast_targets_status ON bot_broadcast_targets (broadcast_id, status)",
    """CREATE TABLE IF NOT EXISTS bot_broadcast_media (
        id          BIGSERIAL PRIMARY KEY,
        sha256      TEXT   NOT NULL UNIQUE,
        mime        TEXT   NOT NULL,
        data        BYTEA  NOT NULL,
        file_id     TEXT,                          -- после первой отправки: Telegram хранит картинку у себя
        created_by  BIGINT NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "ALTER TABLE bot_broadcasts ADD COLUMN IF NOT EXISTS media_id BIGINT",
    """CREATE TABLE IF NOT EXISTS bot_broadcast_templates (
        id          BIGSERIAL PRIMARY KEY,
        title       TEXT NOT NULL,
        text        TEXT NOT NULL,
        html        BOOLEAN NOT NULL DEFAULT FALSE,
        button_text TEXT,
        button_url  TEXT,
        created_by  BIGINT NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        deleted_at  TIMESTAMPTZ
    )""",
    "ALTER TABLE bot_broadcast_templates ADD COLUMN IF NOT EXISTS media_id BIGINT",
)
KINDS = {"chats": "Чаты", "players": "Игроки в личку"}
AUDIENCES = {"chats": "Все чаты бота", "players": "Все игроки в личку"}
STATUS_TITLES = {"scheduled": "Запланирована", "running": "Идёт", "done": "Готово", "stopped": "Остановлена",
                 "interrupted": "Прервана перезапуском"}
ERROR_TITLES = {"blocked": "Заблокировали бота", "no_dialog": "Не открывали диалог с ботом",
                "chat_gone": "Бот удалён из чата или чата нет", "no_rights": "У бота нет прав писать в чате",
                "other": "Другая ошибка Telegram"}
PAUSE = {"chats": 0.35, "players": 0.05}
MAX_TEXT = 3500
MAX_CAPTION = 1024              # подпись к картинке в Telegram
MAX_MEDIA_BYTES = 5 * 1024 * 1024
MEDIA_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_IDS = 5000
TEMPLATES_MAX = 100

_tasks: dict[int, asyncio.Task] = {}
_cancel: set[int] = set()   # рассылки, которые остановили: отправка смотрит сюда перед каждым получателем
LOCK = 7710401   # одна рассылка за раз


class BroadcastError(Exception):
    pass


def pool_db_factory():
    """Асинхронный контекст, дающий соединение (на каждый шаг фоновой отправки своё).
    Ленивое (infrastructure/lazy_db.py): соединение берётся на первом SQL и отдаётся перед каждым вызовом Telegram,
    поэтому фоновые обходы (теги, новости образов, рассылки) не держат его, пока Telegram отвечает."""
    from infrastructure import lazy_db
    from infrastructure.database import get_pool

    def pool_db():
        return lazy_db.lazy_connection(get_pool(), source="background")
    return pool_db


async def ensure_schema(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)
    # Задачи прошлого процесса уже не идут: их можно продолжить кнопкой «Продолжить».
    if not _tasks:
        await db.execute("UPDATE bot_broadcasts SET status = 'interrupted', finished_at = NOW() WHERE status = 'running'")


# ── Сегменты ─────────────────────────────────────────────────────────────────

def visible_len(text: str, html: bool) -> int:
    """Сколько знаков насчитает Telegram: теги разметки не считаются, сущности (&amp;) — за один знак, длина — в единицах
    UTF-16, как у Telegram (эмодзи — обычно два знака)."""
    if html:
        import html as html_lib
        import re
        text = html_lib.unescape(re.sub(r"<[^>]*>", "", text))
    return len(text.encode("utf-16-le")) // 2


def check_text(text: str, html: bool, media_id: int | None) -> None:
    if not 1 <= len(text) <= MAX_TEXT:
        raise BroadcastError(f"Текст — от 1 до {MAX_TEXT} символов.")
    if media_id and visible_len(text, html) > MAX_CAPTION:
        raise BroadcastError(f"С картинкой текст становится подписью: не больше {MAX_CAPTION} знаков "
                             f"(сейчас {visible_len(text, html)}). Сократите текст или уберите картинку.")


# ── Картинка ─────────────────────────────────────────────────────────────────

def _sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def save_media(db, actor_id: int, data: bytes) -> int:
    """Сохранить картинку рассылки; та же картинка второй раз — тот же номер."""
    import hashlib
    if not data or len(data) > MAX_MEDIA_BYTES:
        raise BroadcastError(f"Картинка — до {MAX_MEDIA_BYTES // (1024 * 1024)} МБ.")
    mime = _sniff(data)
    if not mime:
        raise BroadcastError("Подойдёт картинка JPEG, PNG или WebP.")
    digest = hashlib.sha256(data).hexdigest()
    async with db.execute(
        "INSERT INTO bot_broadcast_media (sha256, mime, data, created_by) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (sha256) DO UPDATE SET sha256 = EXCLUDED.sha256 RETURNING id", (digest, mime, data, actor_id)) as cur:
        return int((await cur.fetchone())[0])


async def media(db, media_id: int | None) -> dict | None:
    if not media_id:
        return None
    async with db.execute("SELECT id, mime, data, file_id FROM bot_broadcast_media WHERE id = ?", (int(media_id),)) as cur:
        row = await cur.fetchone()
    return {"id": int(row[0]), "mime": row[1], "data": bytes(row[2]), "file_id": row[3]} if row else None


async def require_media(db, media_id) -> int | None:
    if not media_id:
        return None
    try:
        media_id = int(media_id)
    except (TypeError, ValueError):
        raise BroadcastError("Картинка не найдена: загрузите её ещё раз.")
    async with db.execute("SELECT 1 FROM bot_broadcast_media WHERE id = ?", (media_id,)) as cur:
        if not await cur.fetchone():
            raise BroadcastError("Картинка не найдена: загрузите её ещё раз.")
    return media_id


class Photo:
    """Картинка одной отправки: сначала файл, после первого успешного сообщения — file_id (его же запоминает база)."""

    def __init__(self, item: dict | None):
        self.item = item

    def __bool__(self) -> bool:
        return self.item is not None

    def payload(self):
        from aiogram.types import BufferedInputFile
        if self.item["file_id"]:
            return self.item["file_id"]
        return BufferedInputFile(self.item["data"], filename=f"broadcast.{MEDIA_TYPES.get(self.item['mime'], 'jpg')}")

    async def remember(self, message, pool_db=None, db=None) -> None:
        if self.item["file_id"] or not getattr(message, "photo", None):
            return
        self.item["file_id"] = message.photo[-1].file_id
        sql = "UPDATE bot_broadcast_media SET file_id = ? WHERE id = ? AND file_id IS NULL"
        try:
            if db is not None:
                await db.execute(sql, (self.item["file_id"], self.item["id"]))
            elif pool_db is not None:
                async with pool_db() as fresh:
                    await fresh.execute(sql, (self.item["file_id"], self.item["id"]))
        except Exception as exc:   # не запомнили — следующая отправка просто загрузит файл ещё раз
            logger.debug(f"broadcast media file_id not saved: {exc}")


def _int(value, low: int, high: int, what: str) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise BroadcastError(f"{what}: целое число.")
    if not low <= n <= high:
        raise BroadcastError(f"{what}: от {low} до {high}.")
    return n


def _ids(value, what: str) -> list[int]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise BroadcastError(f"{what}: список ID.")
    try:
        ids = sorted({int(x) for x in value if not isinstance(x, (bool, float))})
    except (TypeError, ValueError):
        raise BroadcastError(f"{what}: только числа.")
    if any(abs(i) >= 2 ** 63 for i in ids):   # больше BIGINT: база ответила бы ошибкой
        raise BroadcastError(f"{what}: слишком большое число.")
    if len(ids) > MAX_IDS:
        raise BroadcastError(f"{what}: не больше {MAX_IDS}.")
    return ids


def normalize_segment(raw, audience: str | None = None) -> dict:
    """Проверить и привести сегмент к каноническому виду. Пустые условия не сохраняются.

    kind: chats | players. chats — только эти чаты (для игроков: участники этих чатов). active_days — писали в
    чате за N дней (для игроков: писали хоть где-то). Только для игроков: vip (true/false), new_days (впервые
    замечены за N дней), min_messages, players (конкретные люди). target_ids — служебное: повтор недоставленным.
    """
    if raw and not isinstance(raw, dict):
        raise BroadcastError("Получатели: неверный формат.")
    raw = dict(raw or {})
    kind = str(raw.get("kind") or audience or "")
    if kind not in KINDS:
        raise BroadcastError("Нет таких получателей.")
    seg: dict = {"kind": kind}
    chats = _ids(raw.get("chats"), "Чаты")
    if chats:
        seg["chats"] = chats
    if kind == "chats":
        chat_kind = str(raw.get("chat_kind") or "")
        if chat_kind not in ("", "all", "main", "admin"):
            raise BroadcastError("Тип чатов: все, основные или админ-чаты.")
        if chat_kind in ("main", "admin"):
            seg["chat_kind"] = chat_kind
    if (days := _int(raw.get("active_days"), 1, 365, "Активность, дней")):
        seg["active_days"] = days
    if kind == "players":
        if raw.get("vip") in (True, False):
            seg["vip"] = bool(raw["vip"])
        if (days := _int(raw.get("new_days"), 1, 365, "Новички, дней")):
            seg["new_days"] = days
        if (n := _int(raw.get("min_messages"), 1, 10_000_000, "Сообщений не меньше")):
            seg["min_messages"] = n
        players = _ids(raw.get("players"), "Игроки")
        if players:
            seg["players"] = players
    targets = _ids(raw.get("target_ids"), "Получатели")
    if targets:
        seg["target_ids"] = targets
        if raw.get("retry_of"):
            seg["retry_of"] = _int(raw["retry_of"], 1, 2 ** 31, "Номер рассылки")
    return seg


def describe_segment(seg: dict) -> str:
    if seg.get("retry_of"):
        return f"Повтор недоставленным (рассылка №{seg['retry_of']}) · {len(seg.get('target_ids') or [])}"
    parts = []
    if seg["kind"] == "chats":
        chat_kind = seg.get("chat_kind")
        if seg.get("chats"):
            parts.append(f"выбранные чаты ({len(seg['chats'])})")
            if chat_kind == "main":
                parts.append("🏠 без админ-чатов")
            elif chat_kind == "admin":
                parts.append("🛡 только админ-чаты")
        elif chat_kind == "main":
            parts.append("основные чаты (🏠 без админ-чатов)")
        elif chat_kind == "admin":
            parts.append("только админ-чаты 🛡")
        else:
            parts.append("все чаты")
        if seg.get("active_days"):
            parts.append(f"писали за {seg['active_days']} дн.")
        return "Чаты: " + ", ".join(parts)
    if seg.get("players"):
        parts.append(f"выбранные игроки ({len(seg['players'])})")
    else:
        parts.append("все игроки")
    if seg.get("vip") is True:
        parts.append("VIP")
    elif seg.get("vip") is False:
        parts.append("без VIP")
    if seg.get("active_days"):
        parts.append(f"писали за {seg['active_days']} дн.")
    if seg.get("new_days"):
        parts.append(f"новички, {seg['new_days']} дн.")
    if seg.get("min_messages"):
        parts.append(f"от {seg['min_messages']} сообщений")
    if seg.get("chats"):
        parts.append(f"участники чатов ({len(seg['chats'])})")
    return "В личку: " + ", ".join(parts)


async def recipients(db, seg: dict) -> list[int]:
    from bot.chat.tracking import local_now
    where: list[str] = []
    args: list = []
    if seg["kind"] == "chats":
        sql = "SELECT c.chat_id FROM chat_settings c WHERE c.chat_id < 0 AND c.bot_left_at IS NULL"
        if seg.get("chats"):
            where.append("c.chat_id = ANY(?::bigint[])")
            args.append(seg["chats"])
        if seg.get("chat_kind") == "main":
            where.append("NOT EXISTS (SELECT 1 FROM chat_links l WHERE l.admin_chat_id = c.chat_id)")
        elif seg.get("chat_kind") == "admin":
            where.append("EXISTS (SELECT 1 FROM chat_links l WHERE l.admin_chat_id = c.chat_id)")
        if seg.get("active_days"):
            since = (local_now().date() - timedelta(days=seg["active_days"] - 1)).isoformat()
            where.append("EXISTS (SELECT 1 FROM daily_user_stats d WHERE d.chat_id = c.chat_id AND d.date >= ?)")
            args.append(since)
        if seg.get("target_ids"):
            where.append("c.chat_id = ANY(?::bigint[])")
            args.append(seg["target_ids"])
        order = "ORDER BY c.chat_id"
    else:
        sql = ("SELECT u.user_tg_id FROM users u WHERE u.user_tg_id > 0 AND u.dm_blocked_at IS NULL AND u.deleted_at IS NULL "
               "AND NOT EXISTS (SELECT 1 FROM bot_user_blocks b WHERE b.user_id = u.user_tg_id "
               "AND (b.until IS NULL OR b.until > NOW())) "
               "AND NOT EXISTS (SELECT 1 FROM chat_blacklist g WHERE g.chat_id = 0 AND g.user_id = u.user_tg_id)")
        if seg.get("players"):
            where.append("u.user_tg_id = ANY(?::bigint[])")
            args.append(seg["players"])
        if seg.get("target_ids"):
            where.append("u.user_tg_id = ANY(?::bigint[])")
            args.append(seg["target_ids"])
        if seg.get("chats"):
            where.append("EXISTS (SELECT 1 FROM user_chat_stats s WHERE s.user_tg_id = u.user_tg_id "
                         "AND s.chat_tg_id = ANY(?::bigint[]) AND NOT COALESCE(s.is_left, FALSE))")
            args.append(seg["chats"])
        if seg.get("active_days"):
            where.append("EXISTS (SELECT 1 FROM user_chat_stats s WHERE s.user_tg_id = u.user_tg_id "
                         "AND s.last_message_at >= NOW() - make_interval(days => ?))")
            args.append(seg["active_days"])
        if seg.get("vip") is not None:
            where.append(("" if seg["vip"] else "NOT ") + "EXISTS (SELECT 1 FROM vip_subscriptions v "
                         "WHERE v.user_id = u.user_tg_id AND v.expires_at > NOW())")
        if seg.get("new_days"):
            where.append("(SELECT MIN(s.joined_at) FROM user_chat_stats s WHERE s.user_tg_id = u.user_tg_id) "
                         ">= NOW() - make_interval(days => ?)")
            args.append(seg["new_days"])
        if seg.get("min_messages"):
            where.append("(SELECT COALESCE(SUM(s.user_messages_count_all_time), 0) FROM user_chat_stats s "
                         "WHERE s.user_tg_id = u.user_tg_id) >= ?")
            args.append(seg["min_messages"])
        order = "ORDER BY u.user_tg_id"
    if where:
        sql += " AND " + " AND ".join(where)
    async with db.execute(f"{sql} {order}", tuple(args)) as cur:
        return [int(r[0]) for r in await cur.fetchall()]


async def audience_sizes(db) -> dict[str, int]:
    return {k: len(await recipients(db, {"kind": k})) for k in KINDS}


async def preview(db, raw, audience: str | None = None) -> dict:
    seg = normalize_segment(raw, audience)
    return {"segment": seg, "title": describe_segment(seg), "count": len(await recipients(db, seg))}


# ── Кнопка и шаблоны ─────────────────────────────────────────────────────────

def normalize_button(raw) -> tuple[str, str] | None:
    """Кнопка-ссылка под сообщением: (подпись, адрес) или None."""
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise BroadcastError("Кнопка: неверный формат.")
    if not (raw.get("text") or raw.get("url")):
        return None
    text, url = str(raw.get("text") or "").strip(), str(raw.get("url") or "").strip()
    if not text or not url:
        raise BroadcastError("Кнопка: нужны и подпись, и ссылка.")
    if len(text) > 64:
        raise BroadcastError("Подпись кнопки — до 64 символов.")
    if not (url.startswith("https://") or url.startswith("tg://")) or len(url) > 512 or " " in url:
        raise BroadcastError("Ссылка кнопки: https://… или tg://…, без пробелов.")
    return text, url


def _markup(button_text, button_url):
    if not button_text or not button_url:
        return None
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=button_text, url=button_url)]])


async def templates(db) -> list[dict]:
    async with db.execute(
        "SELECT id, title, text, html, button_text, button_url, media_id FROM bot_broadcast_templates "
        "WHERE deleted_at IS NULL ORDER BY id DESC LIMIT ?", (TEMPLATES_MAX,)) as cur:
        return [{"id": int(r[0]), "title": r[1], "text": r[2], "html": bool(r[3]),
                 "button": {"text": r[4], "url": r[5]} if r[4] and r[5] else None,
                 "media_id": int(r[6]) if r[6] else None} for r in await cur.fetchall()]


async def save_template(db, actor_id: int, title: str, text: str, html: bool, button, media_id=None) -> int:
    title, text = (title or "").strip(), (text or "").strip()
    if not 1 <= len(title) <= 60:
        raise BroadcastError("Название шаблона — от 1 до 60 символов.")
    media_id = await require_media(db, media_id)
    check_text(text, html, media_id)
    btn = normalize_button(button)
    async with db.execute("SELECT COUNT(*) FROM bot_broadcast_templates WHERE deleted_at IS NULL") as cur:
        if int((await cur.fetchone())[0]) >= TEMPLATES_MAX:
            raise BroadcastError("Слишком много шаблонов: удалите ненужные.")
    async with db.execute(
        "INSERT INTO bot_broadcast_templates (title, text, html, button_text, button_url, created_by, media_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
        (title, text, bool(html), btn[0] if btn else None, btn[1] if btn else None, actor_id, media_id)) as cur:
        return int((await cur.fetchone())[0])


async def delete_template(db, template_id: int) -> bool:
    async with db.execute("UPDATE bot_broadcast_templates SET deleted_at = NOW() WHERE id = ? AND deleted_at IS NULL "
                          "RETURNING id", (template_id,)) as cur:
        return await cur.fetchone() is not None


# ── Список и отчёт ───────────────────────────────────────────────────────────

_COLUMNS = ("b.id, b.actor_id, u.user_tg_username, b.audience, b.text, b.status, b.total, b.sent, b.failed, "
            "b.created_at, b.finished_at, b.html, b.segment::text, b.button_text, b.button_url, b.scheduled_at, b.media_id")


def _item(r) -> dict:
    import json
    seg = json.loads(r[12]) if r[12] else {"kind": r[3]}
    return {"id": int(r[0]), "actor": f"@{r[2]}" if r[2] else f"id{r[1]}", "audience": r[3],
            "audience_title": describe_segment(seg) if r[12] else AUDIENCES.get(r[3], r[3]), "segment": seg,
            "text": r[4], "status": r[5], "status_title": STATUS_TITLES.get(r[5], r[5]), "total": int(r[6]),
            "sent": int(r[7]), "failed": int(r[8]), "created_at": r[9].isoformat() if r[9] else None,
            "finished_at": r[10].isoformat() if r[10] else None, "html": bool(r[11]),
            "button": {"text": r[13], "url": r[14]} if r[13] and r[14] else None,
            "scheduled_at": r[15].isoformat() if r[15] else None, "media_id": int(r[16]) if r[16] else None}


async def listing(db, limit: int = 20) -> list[dict]:
    async with db.execute(
        f"SELECT {_COLUMNS} FROM bot_broadcasts b LEFT JOIN users u ON u.user_tg_id = b.actor_id "
        "ORDER BY b.id DESC LIMIT ?", (limit,)) as cur:
        return [_item(r) for r in await cur.fetchall()]


async def get(db, broadcast_id: int) -> dict | None:
    async with db.execute(
        f"SELECT {_COLUMNS} FROM bot_broadcasts b LEFT JOIN users u ON u.user_tg_id = b.actor_id WHERE b.id = ?",
        (broadcast_id,)) as cur:
        r = await cur.fetchone()
    return _item(r) if r else None


async def report(db, broadcast_id: int, sample: int = 30) -> dict | None:
    """Отчёт: сколько ждёт, дошло, не дошло, причины, и кому не дошло (первые `sample`)."""
    item = await get(db, broadcast_id)
    if not item:
        return None
    async with db.execute("SELECT status, COUNT(*) FROM bot_broadcast_targets WHERE broadcast_id = ? GROUP BY status",
                          (broadcast_id,)) as cur:
        by_status = {r[0]: int(r[1]) for r in await cur.fetchall()}
    async with db.execute(
        "SELECT COALESCE(error, 'other'), COUNT(*) FROM bot_broadcast_targets WHERE broadcast_id = ? AND status = 'failed' "
        "GROUP BY 1 ORDER BY 2 DESC", (broadcast_id,)) as cur:
        reasons = [{"code": r[0].split(":")[0], "title": ERROR_TITLES.get(r[0].split(":")[0], r[0]), "count": int(r[1])}
                   for r in await cur.fetchall()]
    merged: dict[str, dict] = {}
    for x in reasons:   # «other: текст» группируем в «другая ошибка»
        m = merged.setdefault(x["code"], {"code": x["code"], "title": ERROR_TITLES.get(x["code"], x["code"]), "count": 0})
        m["count"] += x["count"]
    async with db.execute(
        "SELECT t.target_id, COALESCE(t.error, 'other'), u.user_tg_username, c.chat_title FROM bot_broadcast_targets t "
        "LEFT JOIN users u ON u.user_tg_id = t.target_id LEFT JOIN chat_settings c ON c.chat_id = t.target_id "
        "WHERE t.broadcast_id = ? AND t.status = 'failed' ORDER BY t.target_id LIMIT ?", (broadcast_id, sample)) as cur:
        failed = [{"id": int(r[0]), "reason": ERROR_TITLES.get(r[1].split(":")[0], r[1]),
                   "name": r[3] or (f"@{r[2]}" if r[2] else str(r[0]))} for r in await cur.fetchall()]
    return {"broadcast": item, "pending": by_status.get("pending", 0), "sent": by_status.get("sent", 0),
            "failed": by_status.get("failed", 0), "reasons": sorted(merged.values(), key=lambda x: -x["count"]),
            "failed_sample": failed}


# ── Создание, запуск, остановка ──────────────────────────────────────────────

@dataclass
class Created:
    id: int
    new: bool          # False — тот же request_id уже был
    total: int
    scheduled: bool


def _parse_when(value) -> datetime | None:
    if not value:
        return None
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise BroadcastError("Время: формат ГГГГ-ММ-ДДTЧЧ:ММ.")
    when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    if when <= datetime.now(timezone.utc) + timedelta(seconds=30):
        raise BroadcastError("Время отправки должно быть в будущем.")
    if when > datetime.now(timezone.utc) + timedelta(days=60):
        raise BroadcastError("Отложить можно не больше чем на 60 дней.")
    return when


async def _insert_targets(db, broadcast_id: int, targets: list[int]) -> None:
    await db.execute("INSERT INTO bot_broadcast_targets (broadcast_id, target_id) "
                     "SELECT ?, unnest(?::bigint[]) ON CONFLICT DO NOTHING", (broadcast_id, targets))


async def _check_free(db) -> None:
    async with db.execute("SELECT 1 FROM bot_broadcasts WHERE status = 'running'") as cur:
        if await cur.fetchone():
            raise BroadcastError("Уже идёт другая рассылка. Дождитесь её или остановите.")


async def precheck(db, actor_id: int, audience: str | None, text: str, request_id: str = "", *, segment=None,
                   scheduled_at=None, html: bool = False, media_id=None) -> bool:
    """Те же проверки, что у create, но ничего не создаёт: нужны до пробной отправки администратору, чтобы отказ
    не оставлял ему лишнее сообщение. True — рассылка с таким request_id уже есть (повторный запрос)."""
    seg = normalize_segment(segment, audience)
    check_text(text, html, await require_media(db, media_id))
    when = _parse_when(scheduled_at)
    if request_id:
        async with db.execute("SELECT 1 FROM bot_broadcasts WHERE actor_id = ? AND request_id = ?",
                              (actor_id, request_id)) as cur:
            if await cur.fetchone():
                return True
    if not when:
        await _check_free(db)
        if not await recipients(db, seg):
            raise BroadcastError("Некому отправлять.")
    return False


async def create(db, actor_id: int, audience: str | None, text: str, request_id: str = "", html: bool = False, *,
                 segment=None, button=None, scheduled_at=None, parent_id: int | None = None, media_id=None) -> Created:
    """Создать рассылку: сразу запускаемую (получатели фиксируются здесь) или отложенную (получатели — в момент отправки).
    Повтор того же request_id возвращает уже созданную."""
    seg = normalize_segment(segment, audience)
    media_id = await require_media(db, media_id)
    check_text(text, html, media_id)
    btn = normalize_button(button)
    when = _parse_when(scheduled_at)
    cols = (actor_id, seg["kind"], text, request_id or None, bool(html), __import__("json").dumps(seg), parent_id, media_id)
    btn_cols = (btn[0] if btn else None, btn[1] if btn else None)
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(?)", (LOCK,))
        if request_id:
            async with db.execute("SELECT id, total, status FROM bot_broadcasts WHERE actor_id = ? AND request_id = ?",
                                  (actor_id, request_id)) as cur:
                row = await cur.fetchone()
            if row:
                return Created(int(row[0]), False, int(row[1]), row[2] == "scheduled")
        if when:
            async with db.execute(
                "INSERT INTO bot_broadcasts (actor_id, audience, text, request_id, html, segment, parent_id, media_id, button_text, "
                "button_url, status, scheduled_at) VALUES (?, ?, ?, ?, ?, ?::jsonb, ?, ?, ?, ?, 'scheduled', ?) RETURNING id",
                (*cols, *btn_cols, when)) as cur:
                return Created(int((await cur.fetchone())[0]), True, 0, True)
        await _check_free(db)
        targets = await recipients(db, seg)
        if not targets:
            raise BroadcastError("Некому отправлять.")
        async with db.execute(
            "INSERT INTO bot_broadcasts (actor_id, audience, text, request_id, html, segment, parent_id, media_id, button_text, "
            "button_url, total) VALUES (?, ?, ?, ?, ?, ?::jsonb, ?, ?, ?, ?, ?) RETURNING id",
            (*cols, *btn_cols, len(targets))) as cur:
            bid = int((await cur.fetchone())[0])
        await _insert_targets(db, bid, targets)
    return Created(bid, True, len(targets), False)


async def stop(db, broadcast_id: int) -> bool:
    """Остановить идущую или отменить запланированную."""
    async with db.execute(
        "UPDATE bot_broadcasts SET status = 'stopped', finished_at = NOW() WHERE id = ? "
        "AND status IN ('running', 'scheduled') RETURNING id", (broadcast_id,)) as cur:
        stopped = await cur.fetchone() is not None
    if stopped:
        _cancel.add(broadcast_id)   # идущая отправка прервётся на следующем получателе, а не доделает пачку из двадцати
    return stopped


async def resume(db, broadcast_id: int) -> int:
    """Продолжить прерванную или остановленную рассылку для тех, кому ещё не отправлено. Возвращает, сколько осталось."""
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(?)", (LOCK,))
        await _check_free(db)
        async with db.execute("SELECT status FROM bot_broadcasts WHERE id = ?", (broadcast_id,)) as cur:
            row = await cur.fetchone()
        if not row or row[0] not in ("interrupted", "stopped"):
            raise BroadcastError("Продолжить можно только остановленную или прерванную рассылку.")
        async with db.execute("SELECT COUNT(*) FROM bot_broadcast_targets WHERE broadcast_id = ? AND status = 'pending'",
                              (broadcast_id,)) as cur:
            left = int((await cur.fetchone())[0])
        if not left:
            raise BroadcastError("Всем уже отправлено.")
        await db.execute("UPDATE bot_broadcasts SET status = 'running', finished_at = NULL WHERE id = ?", (broadcast_id,))
    _cancel.discard(broadcast_id)
    return left


async def retry_failed(db, actor_id: int, broadcast_id: int) -> Created:
    """Новая рассылка того же сообщения тем, кому не дошло."""
    item = await get(db, broadcast_id)
    if not item:
        raise BroadcastError("Рассылка не найдена.")
    async with db.execute("SELECT target_id FROM bot_broadcast_targets WHERE broadcast_id = ? AND status = 'failed' "
                          "ORDER BY target_id", (broadcast_id,)) as cur:
        ids = [int(r[0]) for r in await cur.fetchall()]
    if not ids:
        raise BroadcastError("Недоставленных нет.")
    seg = {"kind": item["segment"]["kind"], "target_ids": ids, "retry_of": broadcast_id}
    return await create(db, actor_id, None, item["text"], "", item["html"], segment=seg, button=item["button"],
                        parent_id=broadcast_id, media_id=item["media_id"])


# ── Отправка ─────────────────────────────────────────────────────────────────

def reason_of(exc: Exception) -> str:
    text = str(exc).lower()
    if "blocked by the user" in text or "user is deactivated" in text:
        return "blocked"
    if "can't initiate" in text or "have no rights to send a message" in text:
        return "no_dialog"
    if "chat not found" in text or "kicked" in text or "not a member" in text or "chat was deleted" in text:
        return "chat_gone"
    if "not enough rights" in text or "need administrator" in text or "have no rights" in text:
        return "no_rights"
    return "other: " + str(exc)[:120]


async def send(bot, chat_id: int, text: str, html: bool, markup=None, photo: Photo | None = None):
    if photo:
        return await bot.send_photo(chat_id, photo.payload(), caption=text, parse_mode="HTML" if html else None,
                                    reply_markup=markup)
    return await bot.send_message(chat_id, text, parse_mode="HTML" if html else None, disable_web_page_preview=True,
                                  reply_markup=markup)


async def _flush(db, broadcast_id: int, results: list[tuple[int, str, str | None]]) -> None:
    if results:
        await db.execute(
            "UPDATE bot_broadcast_targets t SET status = v.status, error = v.error FROM "
            "(SELECT unnest(?::bigint[]) AS id, unnest(?::text[]) AS status, unnest(?::text[]) AS error) v "
            "WHERE t.broadcast_id = ? AND t.target_id = v.id",
            ([r[0] for r in results], [r[1] for r in results], [r[2] for r in results], broadcast_id))
    await db.execute(
        "UPDATE bot_broadcasts SET sent = (SELECT COUNT(*) FROM bot_broadcast_targets WHERE broadcast_id = ? AND status = 'sent'), "
        "failed = (SELECT COUNT(*) FROM bot_broadcast_targets WHERE broadcast_id = ? AND status = 'failed') WHERE id = ?",
        (broadcast_id, broadcast_id, broadcast_id))


async def run(bot, pool_db, broadcast_id: int, audience: str, text: str, html: bool = False, markup=None,
              media_id: int | None = None) -> None:
    """Отправка тем, кому ещё не отправлено. pool_db — асинхронный контекст, дающий соединение (на каждый шаг своё)."""
    from aiogram.exceptions import TelegramRetryAfter
    photo = None
    if media_id:
        async with pool_db() as db:
            photo = Photo(await media(db, media_id))
    while True:
        async with pool_db() as db:
            async with db.execute("SELECT status FROM bot_broadcasts WHERE id = ?", (broadcast_id,)) as cur:
                row = await cur.fetchone()
            if not row or row[0] != "running":
                return
            async with db.execute(
                "SELECT target_id FROM bot_broadcast_targets WHERE broadcast_id = ? AND status = 'pending' "
                "ORDER BY target_id LIMIT 20", (broadcast_id,)) as cur:
                batch = [int(r[0]) for r in await cur.fetchall()]
        if not batch:
            break
        results: list[tuple[int, str, str | None]] = []
        for target in batch:
            if broadcast_id in _cancel:
                break
            outcome: tuple[str, str | None] = ("failed", "other")
            for attempt in range(2):
                try:
                    message = await send(bot, target, text, html, markup, photo)
                    if photo:
                        await photo.remember(message, pool_db=pool_db)
                    outcome = ("sent", None)
                    break
                except TelegramRetryAfter as exc:
                    if attempt:
                        outcome = ("failed", "other: Telegram просит подождать")
                        break
                    await asyncio.sleep(min(float(exc.retry_after), 60) + 1)
                except Exception as exc:   # игрок не начинал диалог с ботом, бот выгнан из чата и т.п.
                    logger.debug(f"broadcast {broadcast_id} -> {target}: {exc}")
                    outcome = ("failed", reason_of(exc))
                    break
            results.append((target, *outcome))
            if len(results) >= 5:   # записываем итог каждые пять отправок: после перезапуска повторно уйдёт не больше четырёх
                async with pool_db() as db:
                    await _flush(db, broadcast_id, results)
                results = []
            await asyncio.sleep(PAUSE.get(audience, 0.1))
        async with pool_db() as db:
            await _flush(db, broadcast_id, results)
    async with pool_db() as db:
        await db.execute("UPDATE bot_broadcasts SET status = 'done', finished_at = NOW() WHERE id = ? AND status = 'running'",
                         (broadcast_id,))
        await _flush(db, broadcast_id, [])


def start(bot, pool_db, broadcast_id: int, audience: str, text: str, html: bool = False, button=None,
          media_id: int | None = None) -> asyncio.Task:
    running = _tasks.get(broadcast_id)
    if running and not running.done():   # «Остановить» и сразу «Продолжить»: старая отправка ещё жива и подхватит остаток сама
        return running
    markup = _markup(*(button or (None, None))) if not isinstance(button, dict) else _markup(button.get("text"), button.get("url"))

    async def guarded():
        try:
            for _ in range(3):
                await run(bot, pool_db, broadcast_id, audience, text, html, markup, media_id)
                async with pool_db() as db:   # остановили и тут же продолжили, пока цикл выходил: доделываем остаток
                    async with db.execute("SELECT 1 FROM bot_broadcasts b WHERE b.id = ? AND b.status = 'running' AND EXISTS "
                                          "(SELECT 1 FROM bot_broadcast_targets t WHERE t.broadcast_id = b.id AND t.status = 'pending')",
                                          (broadcast_id,)) as cur:
                        if not await cur.fetchone():
                            break
        except Exception as exc:
            logger.exception(f"broadcast {broadcast_id} crashed: {exc}")
            async with pool_db() as db:
                await db.execute("UPDATE bot_broadcasts SET status = 'interrupted', finished_at = NOW() "
                                 "WHERE id = ? AND status = 'running'", (broadcast_id,))
        finally:
            _tasks.pop(broadcast_id, None)
    task = asyncio.get_running_loop().create_task(guarded())
    _tasks[broadcast_id] = task
    return task


async def launch(bot, pool_db, broadcast_id: int) -> None:
    """Запустить фоновую отправку уже созданной (идущей) рассылки."""
    async with pool_db() as db:
        item = await get(db, broadcast_id)
    if item:
        start(bot, pool_db, broadcast_id, item["audience"], item["text"], item["html"], item["button"], item["media_id"])


async def launch_due(bot, pool_db) -> int | None:
    """Запустить запланированную рассылку, время которой пришло (если сейчас ничего не идёт). Возвращает её номер."""
    async with pool_db() as db:
        async with db.connection.transaction():
            await db.execute("SELECT pg_advisory_xact_lock(?)", (LOCK,))
            async with db.execute("SELECT 1 FROM bot_broadcasts WHERE status = 'running'") as cur:
                if await cur.fetchone():
                    return None
            async with db.execute(
                "SELECT id, segment::text, audience FROM bot_broadcasts WHERE status = 'scheduled' AND scheduled_at <= NOW() "
                "ORDER BY scheduled_at, id LIMIT 1 FOR UPDATE") as cur:
                row = await cur.fetchone()
            if not row:
                return None
            import json
            bid = int(row[0])
            targets = await recipients(db, normalize_segment(json.loads(row[1]) if row[1] else None, row[2]))
            if not targets:
                await db.execute("UPDATE bot_broadcasts SET status = 'done', finished_at = NOW(), total = 0 WHERE id = ?", (bid,))
                return None
            await _insert_targets(db, bid, targets)
            await db.execute("UPDATE bot_broadcasts SET status = 'running', total = ? WHERE id = ?", (len(targets), bid))
    await launch(bot, pool_db, bid)
    return bid


async def scheduler(bot, pool_db, interval: float = 20.0) -> None:
    """Фоновый цикл: раз в `interval` секунд запускает наступившие запланированные рассылки."""
    while True:
        try:
            await launch_due(bot, pool_db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"broadcast scheduler: {exc}")
            if "does not exist" in str(exc):   # таблиц ещё нет (веб запущен без бота) — создаём и пробуем дальше
                try:
                    async with pool_db() as db:
                        await ensure_schema(db)
                except Exception as inner:
                    logger.warning(f"broadcast schema: {inner}")
        await asyncio.sleep(interval)
