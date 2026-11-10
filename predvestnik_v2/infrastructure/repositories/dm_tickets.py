"""Доступ к данным обращений игроков к администрации из лички (S23b)."""
from __future__ import annotations


async def _ready(db) -> bool:
    """Готово, когда есть последняя по порядку таблица (dm_ticket_cards добавлена в S23d к уже существующей dm_tickets)."""
    async with db.execute("SELECT to_regclass('dm_ticket_cards') IS NOT NULL") as c:
        row = await c.fetchone()
    return bool(row and row[0])


async def ensure_schema(db) -> None:
    """Повторный вызов ничего не меняет; установка под общим замком (параллельный DDL в PostgreSQL не сериализуется)."""
    if await _ready(db):
        return
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('ensure_schema:dm_tickets', 0))")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS dm_tickets (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'answered', 'closed')),
                answer TEXT,
                handled_by BIGINT,
                handled_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_dm_tickets_open ON dm_tickets (created_at) WHERE status = 'new'")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_dm_tickets_user ON dm_tickets (user_id, created_at DESC)")
        # Какому сотруднику и когда ушла карточка нового обращения: предел карточек в час (S23d). Строки старше суток не нужны.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS dm_ticket_cards (
                ticket_id BIGINT NOT NULL REFERENCES dm_tickets (id) ON DELETE CASCADE,
                staff_id BIGINT NOT NULL,
                sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (ticket_id, staff_id)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_dm_ticket_cards_staff ON dm_ticket_cards (staff_id, sent_at)")


_COLUMNS = "t.id, t.user_id, t.text, t.status, t.answer, t.handled_by, t.handled_at, t.created_at, u.user_tg_username, u.user_tg_name"
_JOIN = "FROM dm_tickets t LEFT JOIN users u ON u.user_tg_id = t.user_id"


def _row(r) -> dict:
    return {"id": int(r[0]), "user_id": int(r[1]), "text": r[2], "status": r[3], "answer": r[4],
            "handled_by": int(r[5]) if r[5] else None, "handled_at": r[6], "created_at": r[7],
            "username": r[8], "name": r[9]}


async def get(db, ticket_id: int) -> dict | None:
    async with db.execute(f"SELECT {_COLUMNS} {_JOIN} WHERE t.id = ?", (int(ticket_id),)) as c:
        row = await c.fetchone()
    return _row(row) if row else None


async def counts_for(db, user_id: int) -> tuple[int, int]:
    """(новых за сутки, сейчас ждут ответа)."""
    async with db.execute(
        "SELECT COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 day'), COUNT(*) FILTER (WHERE status = 'new') "
        "FROM dm_tickets WHERE user_id = ?", (int(user_id),),
    ) as c:
        row = await c.fetchone()
    return int(row[0] or 0), int(row[1] or 0)


async def add(db, user_id: int, text: str) -> int:
    async with db.execute("INSERT INTO dm_tickets (user_id, text) VALUES (?, ?) RETURNING id", (int(user_id), text)) as c:
        return int((await c.fetchone())[0])


async def settle(db, ticket_id: int, status: str, staff_id: int, answer: str | None = None) -> bool:
    """Закрыть обращение, только если оно ещё ждёт ответа: второй ответ или закрытие не пройдут (False)."""
    async with db.execute(
        "UPDATE dm_tickets SET status = ?, answer = ?, handled_by = ?, handled_at = NOW() "
        "WHERE id = ? AND status = 'new' RETURNING id", (status, answer, int(staff_id), int(ticket_id)),
    ) as c:
        return await c.fetchone() is not None


async def open_list(db, limit: int, offset: int = 0) -> list[dict]:
    async with db.execute(f"SELECT {_COLUMNS} {_JOIN} WHERE t.status = 'new' ORDER BY t.created_at, t.id LIMIT ? OFFSET ?",
                          (int(limit), int(offset))) as c:
        return [_row(r) for r in await c.fetchall()]


async def open_total(db) -> int:
    async with db.execute("SELECT COUNT(*) FROM dm_tickets WHERE status = 'new'") as c:
        return int((await c.fetchone())[0])


async def cards_in_window(db, staff_id: int, *, window_minutes: int, keep_hours: int) -> int:
    """Сколько карточек сотрудник получил за окно. Заодно чистит его учёт старше keep_hours.
    Вызывать внутри транзакции: замок на сотрудника держится до записи новой карточки."""
    await db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?, 0))", (f"dm_ticket_cards:{int(staff_id)}",))
    await db.execute("DELETE FROM dm_ticket_cards WHERE staff_id = ? AND sent_at < NOW() - make_interval(hours => ?)", (int(staff_id), int(keep_hours)))
    async with db.execute("SELECT COUNT(*) FROM dm_ticket_cards WHERE staff_id = ? AND sent_at > NOW() - make_interval(mins => ?)",
                          (int(staff_id), int(window_minutes))) as c:
        return int((await c.fetchone())[0] or 0)


async def add_card(db, ticket_id: int, staff_id: int) -> None:
    await db.execute("INSERT INTO dm_ticket_cards (ticket_id, staff_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (int(ticket_id), int(staff_id)))


async def release_card(db, ticket_id: int, staff_id: int) -> None:
    """Карточка не дошла (личка сотрудника закрыта): место в его часовом пределе освобождается."""
    await db.execute("DELETE FROM dm_ticket_cards WHERE ticket_id = ? AND staff_id = ?", (int(ticket_id), int(staff_id)))


async def staff_ids(db, min_rank: int) -> list[int]:
    async with db.execute("SELECT user_tg_id FROM users WHERE COALESCE(bot_rank, 0) >= ? ORDER BY user_tg_id", (int(min_rank),)) as c:
        return [int(r[0]) for r in await c.fetchall()]
