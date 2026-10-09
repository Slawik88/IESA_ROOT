"""Рассылка от бота из админки: во все чаты или игрокам в личку.

Рассылка идёт в фоне того же процесса, с паузой между сообщениями (лимиты Telegram),
и после каждого сообщения сохраняет прогресс. Если процесс перезапустился посреди рассылки,
она помечается «прервана» и не продолжается сама: повторить можно новой рассылкой.
Игроки, которым бот не отвечает (блокировка) или с глобальным баном, рассылку не получают.
"""
from __future__ import annotations

import asyncio

from loguru import logger

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS bot_broadcasts (
        id          BIGSERIAL PRIMARY KEY,
        actor_id    BIGINT NOT NULL,
        audience    TEXT   NOT NULL,              -- chats | players
        text        TEXT   NOT NULL,
        request_id  TEXT,
        status      TEXT   NOT NULL DEFAULT 'running',   -- running | done | stopped | interrupted
        total       INTEGER NOT NULL DEFAULT 0,
        sent        INTEGER NOT NULL DEFAULT 0,
        failed      INTEGER NOT NULL DEFAULT 0,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        finished_at TIMESTAMPTZ
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_broadcasts_request ON bot_broadcasts (actor_id, request_id) "
    "WHERE request_id IS NOT NULL",
)
AUDIENCES = {"chats": "Все чаты бота", "players": "Все игроки в личку"}
STATUS_TITLES = {"running": "Идёт", "done": "Готово", "stopped": "Остановлена", "interrupted": "Прервана перезапуском"}
PAUSE = {"chats": 0.35, "players": 0.05}

_tasks: dict[int, asyncio.Task] = {}


class BroadcastError(Exception):
    pass


async def ensure_schema(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)
    # Задачи прошлого процесса уже не идут.
    if not _tasks:
        await db.execute("UPDATE bot_broadcasts SET status = 'interrupted', finished_at = NOW() WHERE status = 'running'")


async def recipients(db, audience: str) -> list[int]:
    if audience == "chats":
        sql = "SELECT chat_id FROM chat_settings WHERE chat_id < 0 ORDER BY chat_id"
    else:
        sql = ("SELECT u.user_tg_id FROM users u WHERE u.user_tg_id > 0 "
               "AND NOT EXISTS (SELECT 1 FROM bot_user_blocks b WHERE b.user_id = u.user_tg_id "
               "AND (b.until IS NULL OR b.until > NOW())) "
               "AND NOT EXISTS (SELECT 1 FROM chat_blacklist g WHERE g.chat_id = 0 AND g.user_id = u.user_tg_id) "
               "ORDER BY u.user_tg_id")
    async with db.execute(sql) as cur:
        return [int(r[0]) for r in await cur.fetchall()]


async def audience_sizes(db) -> dict[str, int]:
    return {k: len(await recipients(db, k)) for k in AUDIENCES}


async def listing(db, limit: int = 20) -> list[dict]:
    async with db.execute(
        "SELECT b.id, b.actor_id, u.user_tg_username, b.audience, b.text, b.status, b.total, b.sent, b.failed, "
        "b.created_at, b.finished_at FROM bot_broadcasts b LEFT JOIN users u ON u.user_tg_id = b.actor_id "
        "ORDER BY b.id DESC LIMIT ?", (limit,)) as cur:
        rows = await cur.fetchall()
    return [{"id": int(r[0]), "actor": f"@{r[2]}" if r[2] else f"id{r[1]}", "audience": r[3],
             "audience_title": AUDIENCES.get(r[3], r[3]), "text": r[4], "status": r[5],
             "status_title": STATUS_TITLES.get(r[5], r[5]), "total": int(r[6]), "sent": int(r[7]),
             "failed": int(r[8]), "created_at": r[9].isoformat() if r[9] else None,
             "finished_at": r[10].isoformat() if r[10] else None} for r in rows]


async def create(db, actor_id: int, audience: str, text: str, request_id: str = "") -> tuple[int, bool, list[int]]:
    """(id, новая ли, получатели). Повтор того же request_id возвращает уже созданную."""
    if audience not in AUDIENCES:
        raise BroadcastError("Нет таких получателей.")
    if not 1 <= len(text) <= 3500:
        raise BroadcastError("Текст — от 1 до 3500 символов.")
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(7710401)")   # одна рассылка за раз
        if request_id:
            async with db.execute("SELECT id FROM bot_broadcasts WHERE actor_id = ? AND request_id = ?",
                                  (actor_id, request_id)) as cur:
                row = await cur.fetchone()
            if row:
                return int(row[0]), False, []
        async with db.execute("SELECT 1 FROM bot_broadcasts WHERE status = 'running'") as cur:
            if await cur.fetchone():
                raise BroadcastError("Уже идёт другая рассылка. Дождитесь её или остановите.")
        targets = await recipients(db, audience)
        if not targets:
            raise BroadcastError("Некому отправлять.")
        async with db.execute(
            "INSERT INTO bot_broadcasts (actor_id, audience, text, request_id, total) VALUES (?, ?, ?, ?, ?) RETURNING id",
            (actor_id, audience, text, request_id or None, len(targets))) as cur:
            bid = int((await cur.fetchone())[0])
    return bid, True, targets


async def stop(db, broadcast_id: int) -> bool:
    async with db.execute(
        "UPDATE bot_broadcasts SET status = 'stopped', finished_at = NOW() WHERE id = ? AND status = 'running' "
        "RETURNING id", (broadcast_id,)) as cur:
        return await cur.fetchone() is not None


async def run(bot, pool_db, broadcast_id: int, audience: str, text: str, targets: list[int]) -> None:
    """Отправка. pool_db — асинхронный контекст, дающий соединение (на каждый шаг своё)."""
    from aiogram.exceptions import TelegramRetryAfter
    sent = failed = 0
    for i, target in enumerate(targets):
        if i % 20 == 0:
            async with pool_db() as db:
                async with db.execute("SELECT status FROM bot_broadcasts WHERE id = ?", (broadcast_id,)) as cur:
                    row = await cur.fetchone()
            if not row or row[0] != "running":
                return
        for attempt in range(2):
            try:
                await bot.send_message(target, text, disable_web_page_preview=True)
                sent += 1
                break
            except TelegramRetryAfter as exc:
                if attempt:
                    failed += 1
                    break
                await asyncio.sleep(min(float(exc.retry_after), 60) + 1)
            except Exception as exc:   # игрок не начинал диалог с ботом, бот выгнан из чата и т.п.
                logger.debug(f"broadcast {broadcast_id} -> {target}: {exc}")
                failed += 1
                break
        if i % 10 == 9 or i == len(targets) - 1:
            async with pool_db() as db:
                await db.execute("UPDATE bot_broadcasts SET sent = ?, failed = ? WHERE id = ?",
                                 (sent, failed, broadcast_id))
        await asyncio.sleep(PAUSE.get(audience, 0.1))
    async with pool_db() as db:
        await db.execute("UPDATE bot_broadcasts SET status = 'done', finished_at = NOW(), sent = ?, failed = ? "
                         "WHERE id = ? AND status = 'running'", (sent, failed, broadcast_id))


def start(bot, pool_db, broadcast_id: int, audience: str, text: str, targets: list[int]) -> asyncio.Task:
    async def guarded():
        try:
            await run(bot, pool_db, broadcast_id, audience, text, targets)
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
