# infrastructure/repositories/routing.py
import aiosqlite
import asyncpg
import secrets
from dataclasses import dataclass


class BindRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class BindRequest:
    nonce: str
    main_chat_id: int
    main_chat_title: str
    creator_id: int


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


async def create_bind_request(db, main_chat_id: int, main_chat_title: str, creator_id: int) -> str:
    """Create a creator-bound, short-lived handoff; nonce is not a bearer grant."""
    nonce = secrets.token_urlsafe(24)
    async with db.connection.transaction():
        await db.execute("DELETE FROM chat_bind_requests WHERE main_chat_id = ?", (main_chat_id,))
        await db.execute(
            "INSERT INTO chat_bind_requests (nonce, main_chat_id, main_chat_title, creator_id, expires_at) "
            "VALUES (?, ?, ?, ?, NOW() + INTERVAL '10 minutes')",
            (nonce, main_chat_id, main_chat_title or "Основной чат", creator_id),
        )
    return nonce


async def peek_bind_request(db, *, nonce: str, creator_id: int) -> BindRequest:
    """Read a still-live request before external Telegram rights checks."""
    async with db.execute(
        "SELECT main_chat_id, main_chat_title, creator_id FROM chat_bind_requests "
        "WHERE nonce = ? AND creator_id = ? AND expires_at > NOW()",
        (nonce, creator_id),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise BindRequestError("Запрос не найден, истёк или создан другим модератором.")
    return BindRequest(nonce, int(row[0]), str(row[1]), int(row[2]))


async def consume_bind_request(db, *, nonce: str, creator_id: int, admin_chat_id: int) -> BindRequest:
    """Atomically consume a request and write a one-to-one routing binding."""
    if not nonce or len(nonce) > 128:
        raise BindRequestError("Запрос привязки недействителен.")
    try:
        async with db.connection.transaction():
            async with db.execute(
                "DELETE FROM chat_bind_requests WHERE nonce = ? AND creator_id = ? "
                "AND expires_at > NOW() RETURNING main_chat_id, main_chat_title, creator_id",
                (nonce, creator_id),
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                raise BindRequestError("Запрос не найден, истёк или создан другим модератором.")
            request = BindRequest(nonce, int(row[0]), str(row[1]), int(row[2]))
            if request.main_chat_id == int(admin_chat_id):
                raise BindRequestError("Основной и админ-чат должны быть разными.")

            async with db.execute(
                "SELECT admin_chat_id FROM chat_links WHERE main_chat_id = ? FOR UPDATE",
                (request.main_chat_id,),
            ) as cursor:
                current_route = await cursor.fetchone()
            previous_admin_chat_id = int(current_route[0]) if current_route else None
            if current_route and int(current_route[0]) != int(admin_chat_id):
                async with db.execute(
                    "SELECT 1 FROM purge_sessions WHERE chat_id = ? AND status = 'active' "
                    "LIMIT 1 FOR UPDATE",
                    (request.main_chat_id,),
                ) as cursor:
                    if await cursor.fetchone():
                        raise BindRequestError(
                            "Нельзя менять админ-чат во время активной чистки. "
                            "Сначала завершите или отмените её."
                        )

            async with db.execute(
                "SELECT main_chat_id FROM chat_links WHERE admin_chat_id = ? "
                "AND main_chat_id <> ? FOR UPDATE",
                (admin_chat_id, request.main_chat_id),
            ) as cursor:
                if await cursor.fetchone():
                    raise BindRequestError("Этот админ-чат уже обслуживает другой основной чат.")
            async with db.execute(
                "SELECT main_chat_id FROM chat_links WHERE admin_chat_id = ? "
                "AND main_chat_id <> ? FOR UPDATE",
                (request.main_chat_id, request.main_chat_id),
            ) as cursor:
                if await cursor.fetchone():
                    raise BindRequestError("Основной чат уже является админ-чатом другой группы.")
            await db.execute(
                "INSERT INTO chat_links (main_chat_id, admin_chat_id) VALUES (?, ?) "
                "ON CONFLICT(main_chat_id) DO UPDATE SET admin_chat_id = EXCLUDED.admin_chat_id, added_at = NOW()",
                (request.main_chat_id, admin_chat_id),
            )
            await db.execute(
                "INSERT INTO chat_bind_audit "
                "(main_chat_id, previous_admin_chat_id, admin_chat_id, actor_id) "
                "VALUES (?, ?, ?, ?)",
                (request.main_chat_id, previous_admin_chat_id, admin_chat_id, creator_id),
            )
    except asyncpg.UniqueViolationError as exc:
        raise BindRequestError("Этот админ-чат уже обслуживает другой основной чат.") from exc
    return request


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


async def get_broadcast_targets(db: aiosqlite.Connection, audience: str = "all") -> list[int]:
    """Чаты-получатели рассылки по фильтру аудитории.
    audience: all | main | admin | main_admin | dm | dm_admin.
    main  = основные группы (chat_id<0, НЕ привязанные админки);
    admin = привязанные админ-чаты; dm = личные чаты (chat_id>0)."""
    async with db.execute("SELECT chat_id FROM chat_settings") as cur:
        all_ids = [r[0] for r in await cur.fetchall()]
    async with db.execute(
        "SELECT admin_chat_id FROM chat_links WHERE admin_chat_id IS NOT NULL"
    ) as cur:
        admin_ids = {r[0] for r in await cur.fetchall()}

    main_ids  = [c for c in all_ids if c < 0 and c not in admin_ids]
    admins    = [c for c in all_ids if c in admin_ids]
    dm_ids    = [c for c in all_ids if c > 0]

    sel = {
        "all":        all_ids,
        "main":       main_ids,
        "admin":      admins,
        "main_admin": [c for c in all_ids if c < 0],
        "dm":         dm_ids,
        "dm_admin":   dm_ids + admins,
    }.get(audience, all_ids)
    # дедуп с сохранением порядка
    seen, out = set(), []
    for c in sel:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


async def get_announce_chats(db: aiosqlite.Connection) -> list[int]:
    """Основные группы для публичных анонсов (новый лот аукциона и т.п.):
    реальные группы (chat_id < 0), исключая привязанные админ-чаты и ЛС."""
    async with db.execute(
        "SELECT cs.chat_id FROM chat_settings cs "
        "WHERE cs.chat_id < 0 "
        "AND cs.chat_id NOT IN "
        "(SELECT admin_chat_id FROM chat_links WHERE admin_chat_id IS NOT NULL)"
    ) as cursor:
        return [r[0] for r in await cursor.fetchall()]
