"""Заметки персонала об игроке (раздел «Игроки и чаты»): видны только персоналу, игрок их не видит.

Заметка не удаляется из базы: «удалённая» только скрывается (deleted_at), чтобы решения не пропадали бесследно.
Писать заметки может любой сотрудник, убирать — автор или роль не ниже REMOVE_RANK.
"""
from __future__ import annotations

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS bot_staff_notes (
        id          BIGSERIAL PRIMARY KEY,
        user_id     BIGINT NOT NULL,
        author_id   BIGINT NOT NULL,
        text        TEXT   NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        deleted_at  TIMESTAMPTZ,
        deleted_by  BIGINT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_bot_staff_notes_user ON bot_staff_notes (user_id, id DESC) WHERE deleted_at IS NULL",
)
MAX_LEN = 1000
MAX_PER_PLAYER = 200
REMOVE_RANK = 5   # разработчик и выше убирают чужие заметки
PAGE = 10


class NoteError(ValueError):
    pass


_ready = False


async def ensure_schema(db) -> None:
    global _ready
    for sql in STATEMENTS:
        await db.execute(sql)
    _ready = True


async def _ensure(db) -> None:
    if not _ready:
        await ensure_schema(db)


async def listing(db, user_id: int, viewer_id: int, viewer_rank: int, *, offset: int = 0, limit: int = PAGE) -> dict:
    await _ensure(db)
    async with db.execute("SELECT COUNT(*) FROM bot_staff_notes WHERE user_id = ? AND deleted_at IS NULL", (user_id,)) as cur:
        total = int((await cur.fetchone())[0])
    async with db.execute(
        "SELECT n.id, n.author_id, u.user_tg_username, n.text, n.created_at FROM bot_staff_notes n "
        "LEFT JOIN users u ON u.user_tg_id = n.author_id WHERE n.user_id = ? AND n.deleted_at IS NULL "
        "ORDER BY n.id DESC LIMIT ? OFFSET ?", (user_id, limit, max(0, offset))) as cur:
        rows = await cur.fetchall()
    items = [{"id": int(r[0]), "author": {"id": int(r[1]), "username": r[2]}, "text": r[3],
              "at": r[4].isoformat() if r[4] else None,
              "can_remove": int(r[1]) == viewer_id or viewer_rank >= REMOVE_RANK} for r in rows]
    return {"items": items, "total": total, "next": offset + len(items) if offset + len(items) < total else None}


async def add(db, user_id: int, author_id: int, text: str) -> int:
    text = (text or "").strip()
    if not text:
        raise NoteError("Напишите текст заметки.")
    if len(text) > MAX_LEN:
        raise NoteError(f"Заметка — до {MAX_LEN} символов.")
    await _ensure(db)
    async with db.execute("SELECT COUNT(*) FROM bot_staff_notes WHERE user_id = ? AND deleted_at IS NULL", (user_id,)) as cur:
        if int((await cur.fetchone())[0]) >= MAX_PER_PLAYER:
            raise NoteError("У игрока уже слишком много заметок: уберите ненужные.")
    async with db.execute(
        "INSERT INTO bot_staff_notes (user_id, author_id, text) VALUES (?, ?, ?) RETURNING id",
        (user_id, author_id, text)) as cur:
        return int((await cur.fetchone())[0])


async def remove(db, user_id: int, note_id: int, actor_id: int, actor_rank: int) -> bool:
    """Скрыть заметку: автор или роль не ниже REMOVE_RANK. False — такой заметки нет (или уже убрана)."""
    await _ensure(db)
    async with db.execute("SELECT author_id FROM bot_staff_notes WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                          (note_id, user_id)) as cur:
        row = await cur.fetchone()
    if not row:
        return False
    if int(row[0]) != actor_id and actor_rank < REMOVE_RANK:
        raise NoteError("Чужую заметку может убрать только разработчик.")
    await db.execute("UPDATE bot_staff_notes SET deleted_at = NOW(), deleted_by = ? WHERE id = ?", (actor_id, note_id))
    return True
