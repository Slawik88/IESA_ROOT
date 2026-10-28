"""Глобальная модерация: бан во всех чатах бота и «бот не отвечает игроку».

Глобальный бан — строка chat_blacklist с chat_id = 0: при входе в любой чат бот сразу
выгоняет игрока (как и при бане в одном чате), а при наложении — банит во всех известных чатах.
Блокировка — таблица bot_user_blocks: бот молча игнорирует команды игрока во всех чатах и в личке,
сообщения при этом считаются как обычно.

Бан и снятие во всех чатах идут фоновым заданием (roadmap S03): раньше один HTTP-запрос админки банил
циклом по всем чатам десятки секунд. Запрос записывает решение (строка chat_id = 0, журнал) и запускает
задание; оно банит по BAN_PARALLEL чатов разом и ведёт счёт «N из M» (``job_view``). Задание живёт в памяти
процесса: деплой посреди него оставит часть чатов без бана, но глобальная строка уже записана, и бот выгонит
игрока при первом его появлении в любом чате. Прочную очередь строит S05.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass, field

from loguru import logger

GLOBAL_CHAT = 0
TTL = 15.0
BAN_PARALLEL = 4          # чатов одновременно: вызовы бана не ждут слота сообщений, но Telegram не любит залпы

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS bot_user_blocks (
        user_id    BIGINT PRIMARY KEY,
        reason     TEXT   NOT NULL DEFAULT '',
        until      TIMESTAMPTZ,
        blocked_by BIGINT,
        blocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
)

_blocked: set[int] = set()
_loaded_at = -1e9


async def ensure_schema(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)


def invalidate() -> None:
    global _loaded_at
    _loaded_at = -1e9


async def is_blocked(db, user_id: int) -> bool:
    global _blocked, _loaded_at
    if time.monotonic() - _loaded_at > TTL:
        async with db.execute("SELECT to_regclass('bot_user_blocks') IS NOT NULL") as cur:
            exists = (await cur.fetchone())[0]
        if exists:
            async with db.execute(
                "SELECT user_id FROM bot_user_blocks WHERE until IS NULL OR until > NOW()") as cur:
                _blocked = {int(r[0]) for r in await cur.fetchall()}
        else:
            _blocked = set()
        _loaded_at = time.monotonic()
    return int(user_id) in _blocked


async def block(db, user_id: int, actor_id: int, reason: str = "", days: int = 0) -> None:
    await db.execute(
        "INSERT INTO bot_user_blocks (user_id, reason, until, blocked_by) "
        "VALUES (?, ?, CASE WHEN ? > 0 THEN NOW() + make_interval(days => ?) END, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET reason = EXCLUDED.reason, until = EXCLUDED.until, "
        "blocked_by = EXCLUDED.blocked_by, blocked_at = NOW()",
        (user_id, reason[:200], days, days, actor_id))
    invalidate()


async def unblock(db, user_id: int) -> None:
    await db.execute("DELETE FROM bot_user_blocks WHERE user_id = ?", (user_id,))
    invalidate()


async def block_info(db, user_id: int) -> dict | None:
    async with db.execute(
        "SELECT reason, until, blocked_by, blocked_at FROM bot_user_blocks "
        "WHERE user_id = ? AND (until IS NULL OR until > NOW())", (user_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    return {"reason": row[0] or "", "until": row[1].isoformat() if row[1] else None, "by": row[2],
            "at": row[3].isoformat() if row[3] else None}


async def ban_info(db, user_id: int) -> dict | None:
    async with db.execute(
        "SELECT reason, added_by, added_at FROM chat_blacklist WHERE chat_id = ? AND user_id = ?",
        (GLOBAL_CHAT, user_id)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    return {"reason": row[0] or "", "by": row[1], "at": row[2].isoformat() if row[2] else None}


async def _known_chats(db) -> list[int]:
    async with db.execute("SELECT chat_id FROM chat_settings WHERE chat_id < 0 ORDER BY chat_id") as cur:
        return [int(r[0]) for r in await cur.fetchall()]


@dataclass
class Job:
    kind: str                  # "global_ban" или "global_unban"
    user_id: int
    total: int
    done: int = 0
    failed: int = 0
    finished: bool = False
    started_at: float = field(default_factory=time.time)

    def view(self) -> dict:
        return asdict(self)


_jobs: dict[tuple[str, int], Job] = {}           # последнее задание по (вид, игрок)
_tasks: dict[tuple[str, int], asyncio.Task] = {}


def job_view(kind: str, user_id: int) -> dict | None:
    job = _jobs.get((kind, int(user_id)))
    return job.view() if job else None


async def wait(job: Job, timeout: float) -> bool:
    """Дождаться конца задания не дольше timeout. Само задание это ожидание не отменяет."""
    task = _tasks.get((job.kind, job.user_id))
    if task is None or task.done():
        return job.finished
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout)
    except asyncio.TimeoutError:
        pass
    return job.finished


async def _stop(kind: str, user_id: int) -> None:
    """Stop a running job of the other kind first: an unban must not race a ban still in progress."""
    task = _tasks.get((kind, int(user_id)))
    if task is not None and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def _launch(job: Job, work) -> Job:
    key = (job.kind, job.user_id)
    previous = _tasks.get(key)
    if previous is not None and not previous.done():
        previous.cancel()      # повторное решение по тому же игроку заменяет незаконченное
    _jobs[key] = job
    task = asyncio.create_task(work, name=f"predvestnik:{job.kind}:{job.user_id}")
    _tasks[key] = task

    def finished(done: asyncio.Task) -> None:
        if _tasks.get(key) is done:
            _tasks.pop(key, None)
        if not done.cancelled() and done.exception() is not None:
            logger.error(f"{job.kind} {job.user_id} stopped: {done.exception()!r}")
    task.add_done_callback(finished)
    return job


async def _each_chat(job: Job, chat_ids: list[int], effect) -> None:
    gate = asyncio.Semaphore(BAN_PARALLEL)

    async def one(chat_id: int) -> None:
        async with gate:
            try:
                await effect(chat_id)
                job.done += 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:   # бота могли выгнать из чата или лишить прав
                logger.debug(f"{job.kind} {job.user_id} in {chat_id}: {exc}")
                job.failed += 1
    try:
        await asyncio.gather(*(one(chat_id) for chat_id in chat_ids))
    finally:
        job.finished = True


async def global_ban(bot, db, db_factory, user_id: int, actor_id: int, reason: str = "") -> Job:
    """Бан навсегда во всех чатах: решение записано сразу, сами баны идут фоновым заданием."""
    await _stop("global_unban", user_id)
    await db.execute(
        "INSERT INTO chat_blacklist (chat_id, user_id, reason, added_by, expires_at) VALUES (?, ?, ?, ?, NULL) "
        "ON CONFLICT (chat_id, user_id) DO UPDATE SET reason = EXCLUDED.reason, added_by = EXCLUDED.added_by, "
        "added_at = NOW(), expires_at = NULL",
        (GLOBAL_CHAT, user_id, reason or None, actor_id))
    await db.execute("UPDATE user_chat_stats SET is_left = TRUE WHERE user_tg_id = ?", (user_id,))
    await db.execute(
        "INSERT INTO moderation_logs (chat_id, user_id, admin_id, action, reason) VALUES (?, ?, ?, 'global_ban', ?)",
        (GLOBAL_CHAT, user_id, actor_id, reason or None))
    chats = await _known_chats(db)

    async def ban(chat_id: int) -> None:
        await bot.ban_chat_member(chat_id, user_id)
        # Запоминаем, где бан поставил именно глобальный бан: снимать будем только там.
        async with db_factory() as job_db:
            await job_db.execute(
                "INSERT INTO moderation_logs (chat_id, user_id, admin_id, action) VALUES (?, ?, ?, 'global_ban_chat')",
                (chat_id, user_id, actor_id))
    job = Job("global_ban", int(user_id), len(chats))
    return _launch(job, _each_chat(job, chats, ban))


async def global_unban(bot, db, user_id: int, actor_id: int) -> Job:
    """Снять глобальный бан только в тех чатах, где его поставил глобальный бан.

    Баны отдельных чатов — из бота (chat_blacklist) или руками в Telegram — остаются.
    """
    await _stop("global_ban", user_id)   # иначе чаты, до которых бан ещё не дошёл, забанятся после снятия
    async with db.execute(
        "SELECT added_at FROM chat_blacklist WHERE chat_id = ? AND user_id = ?", (GLOBAL_CHAT, user_id)) as cur:
        row = await cur.fetchone()
    since = row[0] if row else None
    await db.execute("DELETE FROM chat_blacklist WHERE chat_id = ? AND user_id = ?", (GLOBAL_CHAT, user_id))
    async with db.execute(
        "SELECT DISTINCT chat_id FROM moderation_logs WHERE user_id = ? AND action = 'global_ban_chat' "
        "AND (?::timestamp IS NULL OR created_at >= ?::timestamp - INTERVAL '1 minute')", (user_id, since, since)) as cur:
        banned_here = {int(r[0]) for r in await cur.fetchall()}
    async with db.execute(
        "SELECT chat_id FROM chat_blacklist WHERE user_id = ? AND chat_id <> ? "
        "AND (expires_at IS NULL OR expires_at > NOW())", (user_id, GLOBAL_CHAT)) as cur:
        keep = {int(r[0]) for r in await cur.fetchall()}
    await db.execute(
        "INSERT INTO moderation_logs (chat_id, user_id, admin_id, action) VALUES (?, ?, ?, 'global_unban')",
        (GLOBAL_CHAT, user_id, actor_id))
    chats = sorted(banned_here - keep)

    async def unban(chat_id: int) -> None:
        await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
    job = Job("global_unban", int(user_id), len(chats))
    return _launch(job, _each_chat(job, chats, unban))
