"""История ников и имён игрока: кем он был в Telegram раньше (раздел «Игроки и чаты»).

Пишется из потока сообщений в чатах, только когда ник или имя изменились. Данные те же, что
видят все в Telegram: никаких устройств и адресов не собирается.
"""
from __future__ import annotations

from loguru import logger

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS user_name_history (
        id      BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        kind    TEXT   NOT NULL,
        value   TEXT   NOT NULL,
        seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_user_name_history_user ON user_name_history (user_id, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_user_name_history_value ON user_name_history (kind, lower(value))",
)
KINDS = ("username", "name")
KEEP = 50              # записей на игрока в карточке не больше; в базе остаются все

_ready = False
_seen: dict[int, dict[str, str]] = {}      # user_id -> последние записанные ник и имя (чтобы не ходить в базу на каждое сообщение)


async def ensure_schema(db) -> None:
    global _ready
    for sql in STATEMENTS:
        await db.execute(sql)
    _ready = True


async def _last(db, user_id: int) -> dict[str, str]:
    async with db.execute(
        "SELECT DISTINCT ON (kind) kind, value FROM user_name_history WHERE user_id = ? ORDER BY kind, id DESC",
        (user_id,)) as cur:
        return {r[0]: r[1] for r in await cur.fetchall()}


async def record(db, user_id: int, username: str | None, name: str | None) -> None:
    """Записать ник и имя, если они отличаются от последних записанных. Никогда не мешает основной работе бота."""
    fresh = {"username": (username or "").strip(), "name": (name or "").strip()[:128]}
    known = _seen.get(user_id)
    if known is not None and all(not fresh[k] or fresh[k] == known.get(k) for k in KINDS):
        return
    try:
        async with db.connection.transaction():
            if not _ready:
                await ensure_schema(db)
            last = await _last(db, user_id)
            for kind in KINDS:
                if fresh[kind] and fresh[kind] != last.get(kind):
                    await db.execute("INSERT INTO user_name_history (user_id, kind, value) VALUES (?, ?, ?)",
                                     (user_id, kind, fresh[kind]))
                    last[kind] = fresh[kind]
        _seen[user_id] = last
    except Exception as exc:   # история — дополнение, из-за неё сообщение терять нельзя
        logger.warning(f"name history skipped for {user_id}: {exc}")


async def of_user(db, user_id: int, limit: int = KEEP) -> list[dict]:
    if not _ready:
        await ensure_schema(db)
    async with db.execute(
        "SELECT kind, value, seen_at FROM user_name_history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit)) as cur:
        return [{"kind": r[0], "value": r[1], "at": r[2].isoformat() if r[2] else None} for r in await cur.fetchall()]
