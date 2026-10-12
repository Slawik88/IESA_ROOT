"""Подключение бота к чату: что нужно боту, чтобы работать, как это проверить и где люди застревают.

Бот в чате без прав почти бесполезен: пока он не администратор, он не видит обычные сообщения (команды со словом «бот» не
срабатывают), не удаляет и не ограничивает. Поэтому после добавления бот ведёт владельца за руку: сообщение с чек-листом в
чате (само обновляется при выдаче прав), пошаговая настройка в личке, напоминания, если права так и не выдали.

Здесь только логика без Telegram-интерфейса: проверка чата, предложения по рангам, события для воронки и напоминания.
Интерфейс (тексты, кнопки) — bot/chat/onboarding.py. Только добавление таблиц, ничего не удаляется."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from loguru import logger

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS chat_onboarding (
        chat_id          BIGINT PRIMARY KEY,
        message_id       BIGINT,
        inviter_id       BIGINT,
        added_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        rights_ok_at     TIMESTAMPTZ,
        reminders        INTEGER NOT NULL DEFAULT 0,
        last_reminder_at TIMESTAMPTZ,
        left_at          TIMESTAMPTZ
    )""",
    """CREATE TABLE IF NOT EXISTS chat_onboarding_events (
        id      BIGSERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        user_id BIGINT,
        event   TEXT NOT NULL,
        detail  TEXT,
        at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",   # где люди застревают: кто и сколько раз нажимал «как выдать права», дошёл ли до конца
    # Когда бот впервые ответил на команду в чате: подтверждение, что он реально видит сообщения (NULL — ещё нет).
    "ALTER TABLE chat_onboarding ADD COLUMN IF NOT EXISTS first_command_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS idx_chat_onboarding_events_at ON chat_onboarding_events (at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_chat_onboarding_events_chat ON chat_onboarding_events (chat_id, id DESC)",
)

# Права, которые просим при добавлении по ссылке (?startgroup=…&admin=…): без них нет ни мута, ни чистки, ни закрытого чата.
INVITE_RIGHTS = "delete_messages+restrict_members"
REMIND_AFTER_HOURS = (1, 24)      # первое и второе напоминание, больше бот не напоминает
STAFF_RANKS = (                   # права администратора в Telegram -> ранг в боте (первое подходящее)
    ("can_promote_members", 6),   # назначает админов -> «Администратор»
    ("can_restrict_members", 4),  # мутит и банит -> «Модератор»
    ("can_delete_messages", 3),   # только удаляет -> «Младший модератор»
)

_ready = False


async def ensure_schema(db) -> None:
    global _ready
    for sql in STATEMENTS:
        await db.execute(sql)
    _ready = True


@dataclass
class Setup:
    chat_id: int
    title: str = ""
    present: bool = False       # бот в чате
    admin: bool = False
    can_delete: bool = False
    can_restrict: bool = False
    sees_all: bool = False      # видит все сообщения: администратор или в BotFather выключен режим приватности
    supergroup: bool = True
    live: bool = False          # данные только что получены от Telegram (иначе — то, что бот помнил с прошлого раза)
    owner_id: int | None = None
    owner_name: str | None = None
    admin_chat: dict | None = None   # {"id", "title"}
    staff: int = 0              # сколько человек с рангом (без владельца)
    verified: bool = True       # бот уже отвечал на команду в чате; у чатов, подключённых до мастера, проверять нечего

    @property
    def ready(self) -> bool:
        return self.present and self.admin and self.can_delete and self.can_restrict

    @property
    def missing(self) -> list[str]:
        """Чего не хватает боту, по-русски, в порядке выдачи прав."""
        if not self.present:
            return ["быть в чате"]
        out = []
        if not self.admin:
            out.append("быть администратором")
        if not self.can_delete:
            out.append("удалять сообщения")
        if not self.can_restrict:
            out.append("ограничивать участников")
        return out


async def inspect(bot, db, chat_id: int, persist: bool = True) -> Setup:
    """Проверить чат: права бота спрашиваем у Telegram, остальное берём из базы. Свежие права запоминаем (persist=False —
    не трогать записанное, например сразу после события о правах бота, которое уже записало их само)."""
    from bot.chat import ranks   # поздний импорт: bot.chat подключает и этот модуль
    s = Setup(chat_id=chat_id)
    me = None
    try:
        me = await bot.me()
        member = await bot.get_chat_member(chat_id, me.id)
        status = getattr(member, "status", "")
        s.live = True
        s.present = status in ("member", "administrator", "creator", "restricted")
        s.admin = status in ("administrator", "creator")
        owner_like = status == "creator"
        s.can_delete = s.admin and (owner_like or bool(getattr(member, "can_delete_messages", False)))
        s.can_restrict = s.admin and (owner_like or bool(getattr(member, "can_restrict_members", False)))
    except Exception as exc:   # чат недоступен (бота выгнали) или Telegram не ответил: берём то, что помним
        logger.debug(f"inspect {chat_id}: getChatMember failed: {exc}")
    async with db.execute(
        "SELECT chat_title, bot_left_at, bot_is_admin, bot_can_moderate, owner_override, owner_id "
        "FROM chat_settings WHERE chat_id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
    if row:
        s.title = row[0] or ""
        if not s.live:
            s.present = row[1] is None
            s.admin = bool(row[2])
            s.can_delete = s.can_restrict = bool(row[3])
    try:
        chat = await bot.get_chat(chat_id)
        s.title = getattr(chat, "title", None) or s.title
        s.supergroup = getattr(chat, "type", "supergroup") == "supergroup"
    except Exception:
        pass
    s.title = s.title or str(chat_id)
    s.sees_all = s.admin or bool(getattr(me, "can_read_all_group_messages", False))
    if s.live and persist:
        await db.execute(
            "INSERT INTO chat_settings (chat_id, chat_title, bot_is_admin, bot_can_moderate) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (chat_id) DO UPDATE SET bot_is_admin = EXCLUDED.bot_is_admin, "
            "bot_can_moderate = EXCLUDED.bot_can_moderate", (chat_id, s.title, s.admin, s.can_delete and s.can_restrict))
    s.owner_id = await ranks.get_owner(db, chat_id)
    if s.owner_id:
        async with db.execute("SELECT user_tg_username FROM users WHERE user_tg_id = ?", (s.owner_id,)) as cur:
            r = await cur.fetchone()
        s.owner_name = r[0] if r and r[0] else None
    async with db.execute(
        "SELECT l.admin_chat_id, c.chat_title FROM chat_links l LEFT JOIN chat_settings c ON c.chat_id = l.admin_chat_id "
        "WHERE l.main_chat_id = ?", (chat_id,)) as cur:
        link = await cur.fetchone()
    if link and link[0]:
        title = link[1]
        if not title:   # о служебном чате бот мог ни разу не слышать событий: название спрашиваем у Telegram
            try:
                title = getattr(await bot.get_chat(int(link[0])), "title", None)
            except Exception:
                title = None
        s.admin_chat = {"id": int(link[0]), "title": title or str(link[0])}
    async with db.execute(
        "SELECT COUNT(*) FROM user_chat_stats WHERE chat_tg_id = ? AND COALESCE(chat_rank, 0) > 0 "
        "AND COALESCE(is_left, FALSE) = FALSE AND user_tg_id <> COALESCE(?, 0)", (chat_id, s.owner_id)) as cur:
        s.staff = int((await cur.fetchone())[0])
    async with db.execute("SELECT first_command_at IS NOT NULL FROM chat_onboarding WHERE chat_id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
    s.verified = True if row is None else bool(row[0])
    return s


# ── Модераторы из администраторов Telegram ──────────────────────────────────

@dataclass(frozen=True)
class Proposal:
    user_id: int
    username: str | None
    name: str
    rank: int
    current: int


def rank_for_admin(member) -> int | None:
    """Какой ранг соответствует правам администратора в Telegram; None — права косметические, ранг не нужен."""
    for attr, rank in STAFF_RANKS:
        if getattr(member, attr, False):
            return rank
    return None


async def staff_proposals(bot, db, chat_id: int) -> list[Proposal] | None:
    """Администраторы Telegram, которым стоит дать ранг. None — Telegram не ответил."""
    try:
        admins = await bot.get_chat_administrators(chat_id)
    except Exception as exc:
        logger.debug(f"staff proposals {chat_id}: {exc}")
        return None
    out = []
    for a in admins:
        user = a.user
        if getattr(user, "is_bot", False) or a.status == "creator":
            continue
        rank = rank_for_admin(a)
        if rank is None:
            continue
        async with db.execute("SELECT chat_rank FROM user_chat_stats WHERE chat_tg_id = ? AND user_tg_id = ?",
                              (chat_id, user.id)) as cur:
            row = await cur.fetchone()
        current = int(row[0]) if row and row[0] is not None else 0
        if current >= rank:
            continue   # ранг уже есть и не ниже: понижать не будем
        name = (getattr(user, "full_name", None) or getattr(user, "first_name", None) or "").strip()
        out.append(Proposal(int(user.id), getattr(user, "username", None), name, rank, current))
    return sorted(out, key=lambda p: (-p.rank, (p.username or p.name).lower()))


async def apply_staff(db, chat_id: int, proposals: list[Proposal]) -> int:
    """Выдать предложенные ранги (только повышая). Игроков заводим в базе, чтобы в списках были ники."""
    from bot.chat import ranks
    done = 0
    for p in proposals:
        await db.execute(
            "INSERT INTO users (user_tg_id, user_tg_username, user_tg_name) VALUES (?, ?, ?) "
            "ON CONFLICT (user_tg_id) DO UPDATE SET user_tg_username = COALESCE(EXCLUDED.user_tg_username, users.user_tg_username), "
            "user_tg_name = COALESCE(users.user_tg_name, EXCLUDED.user_tg_name)",
            (p.user_id, p.username, p.name[:128] or None))
        await ranks.store_rank(db, chat_id, p.user_id, p.rank)
        done += 1
    return done


# ── Журнал шагов, воронка, напоминания ──────────────────────────────────────

async def log_event(db, chat_id: int, user_id: int | None, event: str, detail: str = "") -> None:
    """Запомнить шаг. Журнал — дополнение: его сбой не должен ломать подключение."""
    try:
        async with db.connection.transaction():
            await db.execute("INSERT INTO chat_onboarding_events (chat_id, user_id, event, detail) VALUES (?, ?, ?, ?)",
                             (chat_id, user_id, event, detail[:200] or None))
    except Exception as exc:
        logger.warning(f"onboarding event {event} skipped: {exc}")


async def claim(db, chat_id: int, inviter_id: int | None, ready: bool, restart_stale: bool = True) -> str:
    """Занять приветствие чата: "won" — вам отправлять сообщение, "recent" — его только что отправил другой обработчик
    (вход бота и /start приходят почти одновременно, дубля быть не должно), "exists" — чат уже подключён раньше.
    Заново приветствие разрешено, если бота убирали из чата. restart_stale=True ещё и через 10 минут: так событие входа
    переживает пропущенное событие ухода; /start от случайного участника запись давно подключённого чата не перезапускает."""
    stale = "OR chat_onboarding.added_at < NOW() - INTERVAL '10 minutes' " if restart_stale else ""
    async with db.execute(
        "INSERT INTO chat_onboarding (chat_id, inviter_id, rights_ok_at) VALUES (?, ?, CASE WHEN ? THEN NOW() END) "
        "ON CONFLICT (chat_id) DO UPDATE SET message_id = NULL, inviter_id = EXCLUDED.inviter_id, added_at = NOW(), "
        "rights_ok_at = EXCLUDED.rights_ok_at, reminders = 0, last_reminder_at = NULL, left_at = NULL, first_command_at = NULL "
        f"WHERE chat_onboarding.left_at IS NOT NULL {stale}"
        "RETURNING 1", (chat_id, inviter_id, ready)) as cur:
        if await cur.fetchall():
            _cmd_seen.pop(chat_id, None)   # подключаем заново: первая команда нужна снова
            return "won"
    async with db.execute("SELECT added_at > NOW() - INTERVAL '60 seconds' FROM chat_onboarding WHERE chat_id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
    return "recent" if row and row[0] else "exists"


_cmd_seen: dict[int, float] = {}   # чат -> до какого момента (monotonic) о командах не спрашиваем базу
_NO_RECORD_PAUSE = 3600.0


async def note_command(db, chat_id: int) -> bool:
    """Бот ответил на команду в чате: шаг «проверка» пройден. True — это первая команда после подключения.
    Базу трогаем, пока подтверждения нет; дальше (и для чатов без записи о подключении) спрашиваем не чаще раза в час."""
    now = time.monotonic()
    if _cmd_seen.get(chat_id, 0.0) > now:
        return False
    async with db.execute("UPDATE chat_onboarding SET first_command_at = NOW() WHERE chat_id = ? AND first_command_at IS NULL "
                          "AND left_at IS NULL RETURNING 1", (chat_id,)) as cur:
        flipped = bool(await cur.fetchall())
    _cmd_seen[chat_id] = now + _NO_RECORD_PAUSE
    return flipped


def add_url(username: str) -> str:
    """Ссылка «добавить бота в чат»: Telegram сам покажет выбор чата и сразу предложит нужные права администратора."""
    return f"https://t.me/{username}?startgroup=setup&admin={INVITE_RIGHTS}"


_MY_CHAT_COLS = "c.chat_id, c.chat_title, COALESCE(c.bot_is_admin, FALSE), COALESCE(c.bot_can_moderate, FALSE)"
_NOT_ADMIN_CHAT = "NOT EXISTS (SELECT 1 FROM chat_links l WHERE l.admin_chat_id = c.chat_id)"   # админ-чат — служебный, права ему не нужны
ADMIN_LOOKUP = 12     # у скольких чатов, где человек писал, спрашиваем Telegram, администратор ли он
ADMIN_TIMEOUT = 5.0


def _chat_row(r) -> dict:
    return {"id": int(r[0]), "title": r[1] or "Чат без названия", "admin": bool(r[2]), "ready": bool(r[3])}


async def my_chats(db, user_id: int, limit: int = 20, bot=None) -> list[dict]:
    """Чаты, где бот есть и которые этот человек может настраивать: владелец, добавивший бота, администратор бота (ранг 4+) и —
    если передан bot — администратор чата в Telegram (бота мог добавить кто-то другой): их находим среди чатов, где человек писал."""
    async with db.execute(
        f"SELECT {_MY_CHAT_COLS} FROM chat_settings c "
        f"WHERE c.chat_id < 0 AND c.bot_left_at IS NULL AND {_NOT_ADMIN_CHAT} AND ("
        "  COALESCE(c.owner_override, c.owner_id) = ? "
        "  OR EXISTS (SELECT 1 FROM chat_onboarding o WHERE o.chat_id = c.chat_id AND o.inviter_id = ? AND o.left_at IS NULL) "
        "  OR EXISTS (SELECT 1 FROM user_chat_stats s WHERE s.chat_tg_id = c.chat_id AND s.user_tg_id = ? "
        "             AND COALESCE(s.chat_rank, 0) >= 4 AND COALESCE(s.is_left, FALSE) = FALSE)) "
        "ORDER BY LOWER(COALESCE(c.chat_title, '')), c.chat_id LIMIT ?", (user_id, user_id, user_id, limit)) as cur:
        found = [_chat_row(r) for r in await cur.fetchall()]
    if bot is None or len(found) >= limit:
        return found
    have = [c["id"] for c in found] or [0]
    marks = ", ".join("?" for _ in have)
    async with db.execute(
        f"SELECT {_MY_CHAT_COLS} FROM chat_settings c JOIN user_chat_stats s ON s.chat_tg_id = c.chat_id AND s.user_tg_id = ? "
        f"WHERE c.chat_id < 0 AND c.bot_left_at IS NULL AND {_NOT_ADMIN_CHAT} AND COALESCE(s.is_left, FALSE) = FALSE "
        f"AND c.chat_id NOT IN ({marks}) ORDER BY s.last_message_at DESC NULLS LAST LIMIT ?",
        (user_id, *have, ADMIN_LOOKUP)) as cur:
        candidates = [_chat_row(r) for r in await cur.fetchall()]
    if not candidates:
        return found
    gate = asyncio.Semaphore(5)

    async def is_admin(chat: dict) -> bool:
        async with gate:
            try:
                member = await bot.get_chat_member(chat["id"], user_id)
            except Exception:   # noqa: BLE001 - чат недоступен или Telegram не ответил: считаем «не админ»
                return False
            return getattr(member, "status", "") in ("administrator", "creator")

    tasks = [asyncio.ensure_future(is_admin(c)) for c in candidates]
    done, pending = await asyncio.wait(tasks, timeout=ADMIN_TIMEOUT)
    for t in pending:
        t.cancel()
    extra = [c for c, t in zip(candidates, tasks) if t in done and not t.cancelled() and t.exception() is None and t.result()]
    return sorted(found + extra, key=lambda c: (c["title"].lower(), c["id"]))[:limit]


async def get(db, chat_id: int) -> dict | None:
    async with db.execute(
        "SELECT message_id, inviter_id, added_at, rights_ok_at, reminders, left_at FROM chat_onboarding WHERE chat_id = ?",
        (chat_id,)) as cur:
        r = await cur.fetchone()
    return ({"message_id": int(r[0]) if r[0] else None, "inviter_id": int(r[1]) if r[1] else None, "added_at": r[2],
             "rights_ok_at": r[3], "reminders": int(r[4]), "left_at": r[5]} if r else None)


async def set_message(db, chat_id: int, message_id: int) -> None:
    await db.execute("UPDATE chat_onboarding SET message_id = ? WHERE chat_id = ?", (message_id, chat_id))


async def set_ready(db, chat_id: int, ready: bool) -> bool:
    """Отметить момент, когда права появились (и пропали). True — состояние изменилось."""
    if ready:
        async with db.execute("UPDATE chat_onboarding SET rights_ok_at = NOW() WHERE chat_id = ? AND rights_ok_at IS NULL "
                              "RETURNING 1", (chat_id,)) as cur:
            return bool(await cur.fetchall())
    async with db.execute("UPDATE chat_onboarding SET rights_ok_at = NULL WHERE chat_id = ? AND rights_ok_at IS NOT NULL "
                          "RETURNING 1", (chat_id,)) as cur:
        return bool(await cur.fetchall())


async def mark_left(db, chat_id: int) -> None:
    await db.execute("UPDATE chat_onboarding SET left_at = NOW() WHERE chat_id = ? AND left_at IS NULL", (chat_id,))


async def reminder_candidates(db, limit: int = 20) -> list[dict]:
    """Чаты, где бота добавили, а прав так и не выдали: первое напоминание через час, второе через сутки, больше не будет."""
    first, second = REMIND_AFTER_HOURS
    async with db.execute(
        "SELECT chat_id, inviter_id, message_id, reminders FROM chat_onboarding WHERE rights_ok_at IS NULL AND left_at IS NULL "
        "AND ((reminders = 0 AND added_at < NOW() - make_interval(hours => ?)) "
        "  OR (reminders = 1 AND added_at < NOW() - make_interval(hours => ?))) ORDER BY added_at LIMIT ?",
        (first, second, limit)) as cur:
        return [{"chat_id": int(r[0]), "inviter_id": int(r[1]) if r[1] else None,
                 "message_id": int(r[2]) if r[2] else None, "reminders": int(r[3])} for r in await cur.fetchall()]


async def mark_reminded(db, chat_id: int) -> None:
    await db.execute("UPDATE chat_onboarding SET reminders = reminders + 1, last_reminder_at = NOW() WHERE chat_id = ?", (chat_id,))


EVENT_TITLES = {
    "added": "Бота добавили в чат",
    "welcome_failed": "Сообщение в чате не отправилось",
    "dm_sent": "Инструкция ушла в личку",
    "dm_failed": "Личку закрыта: инструкция не дошла",
    "rights_help": "Открыли «Как выдать права»",
    "trouble": "Открыли «Не получается»",
    "check": "Нажали «Проверить»",
    "rights_ok": "Права выданы",
    "rights_lost": "Права сняли",
    "staff_preview": "Посмотрели модераторов",
    "staff_applied": "Назначили модераторов",
    "admin_chat_code": "Взяли код админ-чата",
    "guide": "Открыли «Что я умею»",
    "reminder": "Отправлено напоминание",
    "left": "Бота убрали из чата",
    "denied": "Отказали в настройке (не админ)",
    "first_command": "Бот ответил на первую команду",
    "anon_hint": "Подсказка анонимному админу",
    "channel_added": "Бота добавили в канал",
}


async def funnel(db, days: int = 7) -> dict:
    """Сводка для админки: сколько чатов добавили, сколько дошло до прав и на каких шагах люди останавливаются."""
    days = max(1, min(int(days or 7), 90))
    async with db.execute(
        "SELECT COUNT(*), COUNT(rights_ok_at), COUNT(left_at) FILTER (WHERE rights_ok_at IS NULL), "
        "COUNT(*) FILTER (WHERE rights_ok_at IS NULL AND left_at IS NULL) FROM chat_onboarding "
        "WHERE added_at > NOW() - make_interval(days => ?)", (days,)) as cur:
        added, ready, gave_up, waiting = await cur.fetchone()
    async with db.execute(
        "SELECT event, COUNT(*), COUNT(DISTINCT chat_id) FROM chat_onboarding_events "
        "WHERE at > NOW() - make_interval(days => ?) GROUP BY event", (days,)) as cur:
        events = {r[0]: {"count": int(r[1]), "chats": int(r[2])} for r in await cur.fetchall()}
    async with db.execute(
        "SELECT o.chat_id, c.chat_title, o.added_at, o.reminders, o.inviter_id, u.user_tg_username FROM chat_onboarding o "
        "LEFT JOIN chat_settings c ON c.chat_id = o.chat_id LEFT JOIN users u ON u.user_tg_id = o.inviter_id "
        "WHERE o.rights_ok_at IS NULL AND o.left_at IS NULL ORDER BY o.added_at DESC LIMIT 15") as cur:
        stuck = [{"id": int(r[0]), "title": r[1] or str(r[0]), "added_at": r[2].isoformat() if r[2] else None,
                  "reminders": int(r[3]), "inviter": {"id": int(r[4]), "username": r[5]} if r[4] else None}
                 for r in await cur.fetchall()]
    return {"days": days, "added": int(added), "ready": int(ready), "gave_up": int(gave_up), "waiting": int(waiting),
            "events": [{"event": k, "title": EVENT_TITLES.get(k, k), **v} for k, v in
                       sorted(events.items(), key=lambda kv: list(EVENT_TITLES).index(kv[0]) if kv[0] in EVENT_TITLES else 99)],
            "stuck": stuck}
