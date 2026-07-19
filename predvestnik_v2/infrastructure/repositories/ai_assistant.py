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


# ── Одноразовые действия, предложенные ИИ (ai_pending_actions) ────────────────
# Кнопка подтверждения несёт только id строки; исполнение забирает строку
# атомарным UPDATE — двойной клик/гонка/рестарт не дают повторного исполнения.
PENDING_ACTION_TTL_MIN = 10


async def create_pending_action(
    db: PGAdapter, user_id: int, chat_id: int, action_type: str, payload: str,
) -> int:
    """payload — уже сериализованный JSON (сервис отвечает за содержимое)."""
    async with db.execute(
        "INSERT INTO ai_pending_actions (user_id, chat_id, action_type, payload) "
        "VALUES (?, ?, ?, ?) RETURNING id",
        (user_id, chat_id, action_type, payload),
    ) as c:
        row = await c.fetchone()
    await db.commit()
    return int(row[0])


async def consume_pending_action(db: PGAdapter, action_id: int, user_id: int) -> str | None:
    """Атомарно забрать действие на исполнение. None = уже исполнено, чужое или
    протухло (старше PENDING_ACTION_TTL_MIN). Возвращает payload (JSON-строку)."""
    async with db.execute(
        "UPDATE ai_pending_actions SET executed = TRUE "
        "WHERE id = ? AND user_id = ? AND executed = FALSE "
        f"AND created_at > NOW() - INTERVAL '{int(PENDING_ACTION_TTL_MIN)} minutes' "
        "RETURNING payload",
        (action_id, user_id),
    ) as c:
        row = await c.fetchone()
    if not row:
        return None
    await db.commit()
    return row[0]
