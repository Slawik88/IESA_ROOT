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

import asyncio
import re
import time

from loguru import logger

from services import membership

MAX_LEN = 64            # Telegram разрешает до 16 символов тега, но звания и будущие правила шире: режем с запасом
HISTORY_KEEP = 30       # смен тега на игрока в карточке админки
CACHE_LIMIT = 100_000
BACKFILL_BATCH = 40     # людей за один проход фонового обхода
BACKFILL_PAUSE = 0.35   # секунд между запросами: около трёх в секунду, это далеко от лимита Telegram
TAG_RECHECK_DAYS = 14   # тег молчащего обход перепроверяет раз в две недели (членство — каждые сутки)
DENIED_PAUSE = 6 * 3600 # чат, где Telegram отказал (бот не админ, список скрыт), пропускаем на шесть часов
FRESH_LIMIT = 25        # сколько незнакомых строк списка дозапрашиваем при показе
FRESH_TIMEOUT = 6.0

STATEMENTS = (
    "ALTER TABLE user_chat_stats ADD COLUMN IF NOT EXISTS member_tag TEXT",
    "ALTER TABLE purge_targets ADD COLUMN IF NOT EXISTS member_tag TEXT",
    "ALTER TABLE user_chat_stats ADD COLUMN IF NOT EXISTS member_tag_checked_at TIMESTAMPTZ",   # когда тег последний раз подтвердил Telegram
    "ALTER TABLE user_chat_stats ADD COLUMN IF NOT EXISTS membership_checked_at TIMESTAMPTZ",   # когда Telegram подтвердил «в чате» или «ушёл»
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
_denied: dict[int, float] = {}                  # чат -> до какого момента (monotonic) его не спрашиваем


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
    любая его ошибка не должна терять сообщение, поэтому внутри точка сохранения и перехват.
    Первое подтверждение (даже «тега нет») ставит отметку member_tag_checked_at: по ней фоновый обход понимает, кого уже спрашивал."""
    key = (int(chat_id), int(user_id))
    tag = clean(tag)
    if key in _seen and _seen[key] == tag:
        return False
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT member_tag, member_tag_checked_at FROM user_chat_stats WHERE chat_tg_id = ? AND user_tg_id = ?", key) as cur:
                row = await cur.fetchone()
            if row is None:
                return False
            stored = clean(row[0])
            changed = stored != tag
            if changed or row[1] is None:
                await db.execute("UPDATE user_chat_stats SET member_tag = ?, member_tag_checked_at = NOW() "
                                 "WHERE chat_tg_id = ? AND user_tg_id = ?", (tag, *key))
            if changed and (tag or stored):
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
    if getattr(member, "status", None) in ("left", "kicked") or getattr(getattr(member, "user", None), "is_bot", False):
        return False, None
    return True, of_member(member)


async def refresh(bot, db, chat_id: int, user_id: int) -> tuple[bool, str | None]:
    """Узнать тег у Telegram и сохранить. Не получилось — вернётся то, что уже лежит в базе."""
    ok, tag = await fetch(bot, chat_id, user_id)
    if not ok:
        return False, await get(db, chat_id, user_id)
    await observe(db, chat_id, user_id, tag)
    return True, tag


async def probe(bot, chat_id: int, user_id: int) -> tuple[str, str | None]:
    """Спросить Telegram и разобрать исход: ("ok", тег) | ("gone", None) — человека в чате нет |
    ("bot", None) — это бот, тегов и чистки у ботов нет | ("denied", None) — Telegram отказал по чату |
    ("retry", None) — временная ошибка, стоит повторить позже."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception as exc:
        name = type(exc).__name__
        text = str(exc).lower()
        if name == "TelegramRetryAfter" or name in ("TelegramNetworkError", "TelegramServerError", "TimeoutError", "ClientError"):
            return "retry", None
        if any(m in text for m in ("user not found", "participant_id_invalid", "user_id_invalid", "member not found")):
            return "gone", None
        if name in ("TelegramForbiddenError", "TelegramBadRequest", "TelegramUnauthorizedError"):
            return "denied", None
        logger.debug(f"getChatMember {chat_id}/{user_id}: {exc}")
        return "retry", None
    if getattr(getattr(member, "user", None), "is_bot", False):
        return "bot", None
    status = getattr(member, "status", None)
    if status in ("left", "kicked") or (status == "restricted" and getattr(member, "is_member", True) is False):
        return "gone", None   # замученный, который вышел, для Telegram всё ещё «restricted», но is_member = False
    return "ok", of_member(member)


async def settle(db, chat_id: int, user_id: int, state: str, tag: str | None, *, update_tag: bool = True) -> bool:
    """Применить исход probe. True — вопрос по этому человеку закрыт (больше не спрашивать до срока перепроверки).
    update_tag=False — спрашивали только «в чате ли он»: тег, известный из его сообщений, не трогаем."""
    if state == "ok":
        if update_tag:
            await observe(db, chat_id, user_id, tag)
        try:
            await db.execute("UPDATE user_chat_stats SET membership_checked_at = NOW() "
                             "WHERE chat_tg_id = ? AND user_tg_id = ?", (chat_id, user_id))
            await db.commit()
        except Exception as exc:
            logger.warning(f"membership mark skipped for {chat_id}/{user_id}: {exc}")
        return True
    if state == "bot":   # признак «бот» сохраняем: больше этого человека не спрашиваем и в чистку/топы он не попадает
        from services import chat_bots
        await chat_bots.mark(db, user_id)
        return True
    if state == "gone":   # Telegram: в чате нет. Тег не меняем; из топов, неактивов и чистки человек уходит
        try:
            # Где бот не админ, Telegram не обязан честно отвечать про участников: там пометку ставят только
            # события и служебные сообщения, а здесь лишь запоминаем, что спрашивали.
            await db.execute(
                "UPDATE user_chat_stats s SET member_tag_checked_at = NOW(), membership_checked_at = NOW(), "
                "is_left = COALESCE(s.is_left, FALSE) OR COALESCE((SELECT c.bot_is_admin FROM chat_settings c WHERE c.chat_id = s.chat_tg_id), TRUE) "
                "WHERE s.chat_tg_id = ? AND s.user_tg_id = ?", (chat_id, user_id))
            await db.commit()
        except Exception as exc:
            logger.warning(f"member tag mark skipped for {chat_id}/{user_id}: {exc}")
        return True
    if state == "denied":
        _denied[int(chat_id)] = time.monotonic() + DENIED_PAUSE
    return False


def _chat_open(chat_id: int) -> bool:
    return _denied.get(int(chat_id), 0.0) <= time.monotonic()


async def ensure_fresh(bot, db, chat_id: int, user_ids, limit: int = FRESH_LIMIT) -> set[int]:
    """Перед показом списка спросить Telegram о тех, кого бот ещё не проверял или давно не сверял, пока они молчат:
    чтобы теги были видны сразу, а ушедшие не висели в списке. Спрашивает параллельно, ждёт не дольше FRESH_TIMEOUT;
    ошибки молчит. Возвращает, кого Telegram в чате не нашёл: список стоит перечитать без них."""
    if bot is None or not chat_id or int(chat_id) >= 0 or not _chat_open(chat_id):
        return set()
    ids = list(dict.fromkeys(int(i) for i in user_ids))
    if not ids:
        return set()
    marks = ", ".join("?" for _ in ids)
    stale = f"NOW() - INTERVAL '{membership.RECHECK_HOURS} hours'"
    async with db.execute(
        f"SELECT user_tg_id, member_tag_checked_at IS NULL FROM user_chat_stats WHERE chat_tg_id = ? AND COALESCE(is_bot, FALSE) = FALSE "
        f"AND COALESCE(is_left, FALSE) = FALSE AND (member_tag_checked_at IS NULL OR membership_checked_at IS NULL "
        f"OR (membership_checked_at < {stale} AND COALESCE(last_message_at, TIMESTAMP '2000-01-01') < {stale})) "
        f"AND user_tg_id IN ({marks})", (chat_id, *ids)) as cur:
        rows = (await cur.fetchall())[:limit]
    todo, tag_unknown = [int(r[0]) for r in rows], {int(r[0]) for r in rows if r[1]}
    if not todo:
        return set()
    gate = asyncio.Semaphore(6)

    async def ask(uid: int):
        async with gate:
            return uid, await probe(bot, chat_id, uid)

    # The probes run in child tasks, where the owner-only release before Telegram (bot/middlewares/db.py)
    # cannot fire; give the connection back here for the whole network wait (up to FRESH_TIMEOUT).
    await db.release_if_idle()
    try:
        answers = await asyncio.wait_for(asyncio.gather(*(ask(u) for u in todo)), FRESH_TIMEOUT)
    except Exception as exc:
        logger.debug(f"tags ensure_fresh {chat_id}: {exc}")
        return set()
    for uid, (state, tag) in answers:
        await settle(db, chat_id, uid, state, tag, update_tag=uid in tag_unknown)
    return {uid for uid, (state, _) in answers if state == "gone"}


async def many_fresh(bot, db, chat_id: int, user_ids) -> dict[int, str]:
    """Теги группы людей для показа: сначала дозапрашиваем неизвестных, потом читаем из базы."""
    ids = list(dict.fromkeys(int(i) for i in user_ids))
    await ensure_fresh(bot, db, chat_id, ids)
    return await many(db, chat_id, ids)


async def backfill_batch(bot, db, limit: int = BACKFILL_BATCH) -> int:
    """Один проход фонового обхода: спросить Telegram, в чате ли человек (и какой у него тег). Сначала те, кого ещё
    не сверяли, затем молчащие дольше суток — раз в сутки; первыми идут дольше всех молчащие: среди них ушедшие.
    Кто пишет, тот в чате, его не спрашиваем. Берутся только чаты, где бот админ.
    Возвращает, сколько человек разобрано; 0 — делать пока нечего."""
    async with db.execute(
        "SELECT s.chat_tg_id, s.user_tg_id, "
        f"(s.member_tag_checked_at IS NULL OR s.member_tag_checked_at < NOW() - INTERVAL '{TAG_RECHECK_DAYS} days') "
        "FROM user_chat_stats s "
        "JOIN chat_settings c ON c.chat_id = s.chat_tg_id "
        "WHERE s.chat_tg_id < 0 AND c.bot_left_at IS NULL AND COALESCE(c.bot_is_admin, TRUE) = TRUE "
        "AND COALESCE(s.is_left, FALSE) = FALSE AND COALESCE(s.is_bot, FALSE) = FALSE "
        f"AND (s.membership_checked_at IS NULL OR s.membership_checked_at < NOW() - INTERVAL '{membership.RECHECK_HOURS} hours') "
        f"AND (s.membership_checked_at IS NULL OR COALESCE(s.last_message_at, TIMESTAMP '2000-01-01') < NOW() - INTERVAL '{membership.RECHECK_HOURS} hours') "
        "ORDER BY (s.membership_checked_at IS NULL) DESC, s.last_message_at ASC NULLS FIRST LIMIT ?",
        (limit * 4,)) as cur:
        rows = [(int(r[0]), int(r[1]), bool(r[2])) for r in await cur.fetchall()]
    done = 0
    for chat_id, user_id, tag_due in rows:
        if done >= limit:
            break
        if not _chat_open(chat_id):
            continue
        state, tag = await probe(bot, chat_id, user_id)
        if state == "retry":   # лимит Telegram или сеть: заканчиваем проход, обход продолжится позже
            break
        if await settle(db, chat_id, user_id, state, tag, update_tag=tag_due):
            done += 1
        await asyncio.sleep(BACKFILL_PAUSE)
    return done


async def backfill_task(bot, db_factory, first_delay: float = 90.0) -> None:
    """Фоновый обход: пока у кого-то в чатах, где бот админ, тег не проверен, понемногу спрашивает Telegram."""
    await asyncio.sleep(first_delay)   # не мешаем запуску
    logger.info("Фоновый обход тегов запущен.")
    while True:
        done = 0
        try:
            async with db_factory() as db:
                done = await backfill_batch(bot, db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"member tags backfill error: {exc}")
        await asyncio.sleep(5 if done else 900)


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
