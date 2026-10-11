"""Теги участников чата: подпись справа от имени в списке участников и в сообщениях («Сяо», «свлд Арлекино», «айно.мл.адм»).

Тег принадлежит человеку в конкретном чате (в другом чате он может быть другим), поэтому хранится в user_chat_stats.member_tag.
У администратора вместо тега Telegram показывает «звание» (custom_title) — для бота это то же самое, оба хранятся в одной колонке.

Откуда берём:
 - каждое сообщение в супергруппе несёт тег автора (Message.sender_tag): бесплатно, без запросов к Telegram;
 - событие chat_member (человек вошёл, ему сменили тег или права);
 - getChatMember: для тех, кто давно молчит. Так в чистке тег есть и у людей, которых бот ни разу не видел в чате.
Поля читаются «терпимо» (через model_extra): так бот работает и на aiogram, где тегов ещё нет в моделях.

Только добавление: колонка user_chat_stats.member_tag, purge_targets.member_tag и таблица истории. Ничего не удаляется."""
from __future__ import annotations

import re

from loguru import logger

MAX_LEN = 64            # Telegram разрешает до 16 символов тега, но звания и будущие правила шире: режем с запасом
HISTORY_KEEP = 30       # смен тега на игрока в карточке админки
CACHE_LIMIT = 100_000

STATEMENTS = (
    "ALTER TABLE user_chat_stats ADD COLUMN IF NOT EXISTS member_tag TEXT",
    "ALTER TABLE purge_targets ADD COLUMN IF NOT EXISTS member_tag TEXT",
    """CREATE TABLE IF NOT EXISTS member_tag_history (
        id      BIGSERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        value   TEXT   NOT NULL,
        seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",   # value = '' — тег сняли
    "CREATE INDEX IF NOT EXISTS idx_member_tag_history_user ON member_tag_history (user_id, id DESC)",
)

# Только обычные сообщения людей: в служебных («вошёл», «закрепил») Telegram может не присылать тег, и это не «тега нет».
CONTENT_TYPES = frozenset({
    "text", "photo", "video", "sticker", "voice", "document", "animation", "audio", "video_note", "poll", "contact",
    "location", "venue", "dice", "game",
})

_WS = re.compile(r"\s+")
_seen: dict[tuple[int, int], str | None] = {}   # (чат, игрок) -> тег, который уже лежит в базе


def clean(raw) -> str | None:
    """Тег для хранения: без переводов строк и невидимых пробелов; пустой — это «тега нет»."""
    if not isinstance(raw, str):
        return None
    text = _WS.sub(" ", raw.replace("​", "").replace("⁠", "").replace("﻿", "")).strip()
    return text[:MAX_LEN].strip() or None


def _field(obj, name: str):
    value = getattr(obj, name, None)
    if value is None:
        extra = getattr(obj, "model_extra", None) or {}
        value = extra.get(name)
    return value


def of_message(message) -> tuple[bool, str | None]:
    """(известно ли, тег автора). Неизвестно — в обычной группе (там тегов нет) и в служебных сообщениях."""
    if getattr(getattr(message, "chat", None), "type", None) != "supergroup" or getattr(message, "content_type", None) not in CONTENT_TYPES:
        return False, None
    return True, clean(_field(message, "sender_tag"))


def of_member(member) -> str | None:
    """Тег участника из ответа getChatMember или события chat_member: тег, а у администратора — его звание."""
    return clean(_field(member, "tag")) or clean(_field(member, "custom_title"))


def suffix(tag: str | None) -> str:
    """Тег после имени: « [Сяо]». Текст не экранирован: вставляя в HTML, экранируйте всю строку целиком."""
    return f" [{tag}]" if tag else ""


def with_tag(name: str, tag: str | None) -> str:
    return name + suffix(tag)


async def ensure_schema(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)


async def get(db, chat_id: int, user_id: int) -> str | None:
    async with db.execute(
        "SELECT member_tag FROM user_chat_stats WHERE chat_tg_id = ? AND user_tg_id = ?", (chat_id, user_id)) as cur:
        row = await cur.fetchone()
    return clean(row[0]) if row else None


async def many(db, chat_id: int, user_ids) -> dict[int, str]:
    """Теги группы людей одним запросом; у кого тега нет — нет и в ответе."""
    ids = list(dict.fromkeys(int(i) for i in user_ids))
    if not ids or not chat_id:
        return {}
    marks = ", ".join("?" for _ in ids)
    async with db.execute(
        f"SELECT user_tg_id, member_tag FROM user_chat_stats "
        f"WHERE chat_tg_id = ? AND member_tag IS NOT NULL AND user_tg_id IN ({marks})", (chat_id, *ids)) as cur:
        return {int(r[0]): t for r in await cur.fetchall() if (t := clean(r[1]))}


async def pairs(db, chat_user_pairs) -> dict[tuple[int, int], str]:
    """Теги по парам (чат, игрок): для журналов и жалоб, где у каждой записи свой чат."""
    uniq = list(dict.fromkeys((int(c), int(u)) for c, u in chat_user_pairs if c and u))
    if not uniq:
        return {}
    marks = ", ".join("(?, ?)" for _ in uniq)
    async with db.execute(
        f"SELECT chat_tg_id, user_tg_id, member_tag FROM user_chat_stats "
        f"WHERE member_tag IS NOT NULL AND (chat_tg_id, user_tg_id) IN ({marks})", tuple(x for pair in uniq for x in pair)) as cur:
        return {(int(r[0]), int(r[1])): t for r in await cur.fetchall() if (t := clean(r[2]))}


async def observe(db, chat_id: int, user_id: int, tag: str | None) -> bool:
    """Записать тег, если он изменился. Возвращает True, когда в базе что-то поменялось.

    Строка user_chat_stats уже должна быть (её заводит учёт сообщений и вход в чат). Тег — дополнение к учёту:
    любая его ошибка не должна терять сообщение, поэтому внутри точка сохранения и перехват."""
    key = (int(chat_id), int(user_id))
    tag = clean(tag)
    if key in _seen and _seen[key] == tag:
        return False
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT member_tag FROM user_chat_stats WHERE chat_tg_id = ? AND user_tg_id = ?", key) as cur:
                row = await cur.fetchone()
            if row is None:
                return False
            stored = clean(row[0])
            changed = stored != tag
            if changed:
                await db.execute("UPDATE user_chat_stats SET member_tag = ? WHERE chat_tg_id = ? AND user_tg_id = ?",
                                 (tag, *key))
                if tag or stored:
                    await db.execute("INSERT INTO member_tag_history (chat_id, user_id, value) VALUES (?, ?, ?)",
                                     (*key, tag or ""))
        if len(_seen) > CACHE_LIMIT:
            _seen.clear()
        _seen[key] = tag
        return changed
    except Exception as exc:
        logger.warning(f"member tag skipped for {chat_id}/{user_id}: {exc}")
        return False


async def observe_message(db, message) -> None:
    known, tag = of_message(message)
    if known and message.from_user:
        await observe(db, message.chat.id, message.from_user.id, tag)


async def fetch(bot, chat_id: int, user_id: int) -> tuple[bool, str | None]:
    """Спросить Telegram: (получилось ли узнать, тег). Ушедший из чата или недоступный — «не узнали»."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception as exc:
        logger.debug(f"getChatMember {chat_id}/{user_id}: {exc}")
        return False, None
    if getattr(member, "status", None) in ("left", "kicked"):
        return False, None
    return True, of_member(member)


async def refresh(bot, db, chat_id: int, user_id: int) -> tuple[bool, str | None]:
    """Узнать тег у Telegram и сохранить. Не получилось — вернётся то, что уже лежит в базе."""
    ok, tag = await fetch(bot, chat_id, user_id)
    if not ok:
        return False, await get(db, chat_id, user_id)
    await observe(db, chat_id, user_id, tag)
    return True, tag


async def find(db, chat_id: int, text: str, limit: int = 40) -> list[tuple[int, str | None, str]]:
    """Кто в чате с таким тегом (часть слова, без учёта регистра): [(id, ник, тег)]."""
    needle = clean(text)
    if not needle:
        return []
    like = "%" + needle.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username, s.member_tag FROM user_chat_stats s "
        "LEFT JOIN users u ON u.user_tg_id = s.user_tg_id "
        "WHERE s.chat_tg_id = ? AND COALESCE(s.is_left, FALSE) = FALSE AND COALESCE(s.is_bot, FALSE) = FALSE "
        "AND LOWER(s.member_tag) LIKE ? ESCAPE '\\' "
        "ORDER BY LOWER(s.member_tag), s.user_tg_id LIMIT ?", (chat_id, like, limit)) as cur:
        return [(int(r[0]), r[1], r[2]) for r in await cur.fetchall()]


async def listing(db, chat_id: int, limit: int = 60) -> tuple[int, list[tuple[int, str | None, str]]]:
    """Все, у кого в чате есть тег: (сколько всего, первые limit по алфавиту тега)."""
    base = ("FROM user_chat_stats s LEFT JOIN users u ON u.user_tg_id = s.user_tg_id "
            "WHERE s.chat_tg_id = ? AND COALESCE(s.is_left, FALSE) = FALSE AND COALESCE(s.is_bot, FALSE) = FALSE "
            "AND s.member_tag IS NOT NULL AND s.member_tag <> ''")
    async with db.execute(f"SELECT COUNT(*) {base}", (chat_id,)) as cur:
        total = int((await cur.fetchone())[0])
    async with db.execute(
        f"SELECT s.user_tg_id, u.user_tg_username, s.member_tag {base} ORDER BY LOWER(s.member_tag), s.user_tg_id LIMIT ?",
        (chat_id, limit)) as cur:
        return total, [(int(r[0]), r[1], r[2]) for r in await cur.fetchall()]


async def history(db, user_id: int, limit: int = HISTORY_KEEP) -> list[dict]:
    async with db.execute(
        "SELECT h.chat_id, c.chat_title, h.value, h.seen_at FROM member_tag_history h "
        "LEFT JOIN chat_settings c ON c.chat_id = h.chat_id WHERE h.user_id = ? ORDER BY h.id DESC LIMIT ?",
        (user_id, limit)) as cur:
        return [{"chat_id": int(r[0]), "chat_title": r[1], "tag": r[2] or None, "at": r[3].isoformat() if r[3] else None}
                for r in await cur.fetchall()]
