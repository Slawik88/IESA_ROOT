"""
infrastructure/repositories/ai_assistant.py
Кулдаун + дневной кап для ИИ-помощника (services/ai_assistant.py). Каждый вопрос —
платный внешний вызов Gemini API, поэтому лимиты жёстче обычных игровых кулдаунов
(паттерн — infrastructure/repositories/dark_mora.py + games.py::daily_winnings).
"""
from datetime import datetime, timezone

from infrastructure.pg_adapter import PGAdapter


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def get_usage_today(db: PGAdapter, user_id: int) -> tuple[int, datetime | None]:
    """Returns (вопросов сегодня, время последнего вопроса)."""
    async with db.execute(
        "SELECT count, last_query_at FROM ai_assistant_usage WHERE user_id = ? AND day = ?",
        (user_id, _today()),
    ) as c:
        row = await c.fetchone()
    if not row:
        return 0, None
    count, last_at = row[0], row[1]
    if isinstance(last_at, str) and last_at:
        last_at = datetime.strptime(last_at[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    elif last_at is not None and last_at.tzinfo is None:
        last_at = last_at.replace(tzinfo=timezone.utc)
    return count, last_at


async def register_query(db: PGAdapter, user_id: int) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        "INSERT INTO ai_assistant_usage (user_id, day, count, last_query_at) "
        "VALUES (?, ?, 1, ?) "
        "ON CONFLICT (user_id, day) DO UPDATE SET "
        "count = ai_assistant_usage.count + 1, last_query_at = EXCLUDED.last_query_at",
        (user_id, _today(), now),
    )
