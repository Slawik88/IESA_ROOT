# infrastructure/repositories/routing.py
import aiosqlite
import secrets


async def create_bind_token(
    db: aiosqlite.Connection, main_chat_id: int, main_chat_title: str
) -> str:
    token = secrets.token_hex(6)
    await db.execute(
        "DELETE FROM chat_bind_tokens WHERE main_chat_id = ?", (main_chat_id,)
    )
    await db.execute(
        "INSERT INTO chat_bind_tokens (token, main_chat_id, main_chat_title) VALUES (?, ?, ?)",
        (token, main_chat_id, main_chat_title),
    )
    await db.commit()
    return token


async def get_and_delete_token(db: aiosqlite.Connection, token: str) -> dict | None:
    async with db.execute(
        "SELECT main_chat_id, main_chat_title FROM chat_bind_tokens WHERE token = ?",
        (token,),
    ) as cursor:
        row = await cursor.fetchone()

    if row:
        await db.execute("DELETE FROM chat_bind_tokens WHERE token = ?", (token,))
        await db.commit()
        return dict(row)
    return None


async def bind_admin_chat(
    db: aiosqlite.Connection, main_chat_id: int, admin_chat_id: int
):
    await db.execute(
        "INSERT INTO chat_links (main_chat_id, admin_chat_id) VALUES (?, ?) "
        "ON CONFLICT(main_chat_id) DO UPDATE SET admin_chat_id = ?",
        (main_chat_id, admin_chat_id, admin_chat_id),
    )
    await db.commit()


async def get_admin_chat(db: aiosqlite.Connection, main_chat_id: int) -> int | None:
    async with db.execute(
        "SELECT admin_chat_id FROM chat_links WHERE main_chat_id = ?", (main_chat_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else None
