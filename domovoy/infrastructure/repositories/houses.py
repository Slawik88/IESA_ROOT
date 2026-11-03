"""
infrastructure/repositories/houses.py — дома, участники, права.
"""
import secrets

from infrastructure.db import db, now_utc


def _new_invite_token() -> str:
    return secrets.token_urlsafe(16)


# ── Дома ─────────────────────────────────────────────────────────────────────

async def _insert_house(conn, name: str, owner_tg_id: int, owner_display_name: str) -> int:
    house_id = await conn.insert(
        "INSERT INTO houses (name, invite_token, created_by, created_at) VALUES (?, ?, ?, ?)",
        name, _new_invite_token(), owner_tg_id, now_utc(),
    )
    await conn.execute(
        "INSERT INTO memberships (house_id, tg_id, display_name, role, status, joined_at) "
        "VALUES (?, ?, ?, 'owner', 'active', ?)",
        house_id, owner_tg_id, owner_display_name, now_utc(),
    )
    return house_id


async def create_house(name: str, owner_tg_id: int, owner_display_name: str) -> int:
    """Дом + владелец — одна транзакция: дом без владельца не существует."""
    async with db.transaction() as conn:
        return await _insert_house(conn, name, owner_tg_id, owner_display_name)


async def create_house_once(name: str, owner_tg_id: int, owner_display_name: str) -> tuple[int, bool]:
    """Повтор создания того же дома сериализуется по строке владельца."""
    async with db.transaction() as conn:
        suffix = " FOR UPDATE" if db.is_postgres else ""
        await conn.fetchrow("SELECT tg_id FROM users WHERE tg_id = ?" + suffix, owner_tg_id)
        existing = await conn.fetch(
            "SELECT h.id, h.name FROM houses h JOIN memberships m ON m.house_id = h.id "
            "WHERE m.tg_id = ? AND m.role = 'owner' AND m.status = 'active' ORDER BY h.id",
            owner_tg_id,
        )
        match = next((house for house in existing if house["name"].casefold() == name.casefold()), None)
        if match:
            return match["id"], False
        return await _insert_house(conn, name, owner_tg_id, owner_display_name), True


async def list_all() -> list:
    """Все дома (для планировщика напоминаний)."""
    async with db.acquire() as conn:
        return await conn.fetch("SELECT id, name, invite_token, chat_id, created_by FROM houses")


async def get_house(house_id: int):
    async with db.acquire() as conn:
        return await conn.fetchrow(
            "SELECT id, name, invite_token, chat_id, created_by, created_at FROM houses WHERE id = ?",
            house_id,
        )


async def get_house_by_invite(token: str):
    async with db.acquire() as conn:
        return await conn.fetchrow(
            "SELECT id, name, invite_token, chat_id, created_by, created_at FROM houses WHERE invite_token = ?",
            token,
        )


async def set_chat(house_id: int, chat_id: int | None) -> None:
    """Привязка дома к чату (None — отвязать): сюда летят уведомления «в чат»."""
    async with db.acquire() as conn:
        await conn.execute("UPDATE houses SET chat_id = ? WHERE id = ?", chat_id, house_id)


async def rename_house(house_id: int, name: str) -> None:
    async with db.acquire() as conn:
        await conn.execute("UPDATE houses SET name = ? WHERE id = ?", name, house_id)


async def refresh_invite_token(house_id: int) -> str:
    token = _new_invite_token()
    async with db.acquire() as conn:
        await conn.execute("UPDATE houses SET invite_token = ? WHERE id = ?", token, house_id)
    return token


# ── Участники ────────────────────────────────────────────────────────────────

async def add_member(house_id: int, tg_id: int, display_name: str) -> bool:
    """Добавить участника; повторное вступление ничего не меняет (идемпотентно)."""
    async with db.acquire() as conn:
        rowcount = await conn.execute(
            """
            INSERT INTO memberships (house_id, tg_id, display_name, role, status, joined_at)
            VALUES (?, ?, ?, 'member', 'active', ?)
            ON CONFLICT (house_id, tg_id) DO UPDATE
            SET status = 'active', display_name = EXCLUDED.display_name, joined_at = EXCLUDED.joined_at
            WHERE memberships.status = 'left'
            """,
            house_id, tg_id, display_name, now_utc(),
        )
        return rowcount > 0


async def add_member_by_invite(house_id: int, token: str, tg_id: int, display_name: str) -> bool | None:
    """Проверка текущего приглашения и вступление атомарны относительно ротации."""
    async with db.transaction() as conn:
        suffix = " FOR UPDATE" if db.is_postgres else ""
        house = await conn.fetchrow(
            "SELECT id FROM houses WHERE id = ? AND invite_token = ?" + suffix, house_id, token,
        )
        if house is None:
            return None
        rowcount = await conn.execute(
            "INSERT INTO memberships (house_id, tg_id, display_name, role, status, joined_at) "
            "VALUES (?, ?, ?, 'member', 'active', ?) "
            "ON CONFLICT (house_id, tg_id) DO UPDATE "
            "SET status = 'active', display_name = EXCLUDED.display_name, joined_at = EXCLUDED.joined_at "
            "WHERE memberships.status = 'left'",
            house_id, tg_id, display_name, now_utc(),
        )
        return rowcount > 0


async def get_membership(house_id: int, tg_id: int):
    async with db.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, house_id, tg_id, display_name, role, status, joined_at
            FROM memberships WHERE house_id = ? AND tg_id = ?
            """,
            house_id, tg_id,
        )


async def list_active_members(house_id: int) -> list:
    async with db.acquire() as conn:
        return await conn.fetch(
            """
            SELECT m.tg_id, m.display_name, m.role, u.username
            FROM memberships m
            LEFT JOIN users u ON u.tg_id = m.tg_id
            WHERE m.house_id = ? AND m.status = 'active'
            ORDER BY m.joined_at, m.id
            """,
            house_id,
        )


async def count_active_members(house_id: int) -> int:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM memberships WHERE house_id = ? AND status = 'active'",
            house_id,
        )
        return int(row["n"]) if row else 0


async def set_member_status(house_id: int, tg_id: int, status: str) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE memberships SET status = ? WHERE house_id = ? AND tg_id = ?",
            status, house_id, tg_id,
        )


async def leave_member(house_id: int, tg_id: int, today: str) -> bool:
    """Выход, отзыв прав и будущих планов — один переход, согласованный с графиком."""
    async with db.transaction() as conn:
        suffix = " FOR UPDATE" if db.is_postgres else ""
        await conn.fetchrow("SELECT id FROM houses WHERE id = ?" + suffix, house_id)
        changed = await conn.execute(
            "UPDATE memberships SET status = 'left' "
            "WHERE house_id = ? AND tg_id = ? AND status = 'active' AND role <> 'owner'",
            house_id, tg_id,
        )
        if not changed:
            return False
        await conn.execute("DELETE FROM member_permissions WHERE house_id = ? AND tg_id = ?", house_id, tg_id)
        await conn.execute(
            "DELETE FROM cleaning_days WHERE house_id = ? AND tg_id = ? AND status = 'open' AND planned_date > ?",
            house_id, tg_id, today,
        )
        return True


async def set_display_name(house_id: int, tg_id: int, display_name: str) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE memberships SET display_name = ? WHERE house_id = ? AND tg_id = ?",
            display_name, house_id, tg_id,
        )


async def list_houses_of_user(tg_id: int) -> list:
    async with db.acquire() as conn:
        return await conn.fetch(
            """
            SELECT h.id, h.name, m.role
            FROM memberships m JOIN houses h ON h.id = m.house_id
            WHERE m.tg_id = ? AND m.status = 'active'
            ORDER BY h.id
            """,
            tg_id,
        )


# ── Права ────────────────────────────────────────────────────────────────────

async def member_grants(house_id: int, tg_id: int) -> frozenset[str]:
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT permission FROM member_permissions WHERE house_id = ? AND tg_id = ?",
            house_id, tg_id,
        )
        return frozenset(row["permission"] for row in rows)


async def grant(house_id: int, tg_id: int, permission: str) -> bool:
    async with db.transaction() as conn:
        suffix = " FOR UPDATE" if db.is_postgres else ""
        await conn.fetchrow("SELECT id FROM houses WHERE id = ?" + suffix, house_id)
        member = await conn.fetchrow(
            "SELECT status FROM memberships WHERE house_id = ? AND tg_id = ?", house_id, tg_id,
        )
        if member is None or member["status"] != "active":
            return False
        await conn.execute(
            """
            INSERT INTO member_permissions (house_id, tg_id, permission)
            VALUES (?, ?, ?)
            ON CONFLICT (house_id, tg_id, permission) DO NOTHING
            """,
            house_id, tg_id, permission,
        )
        return True


async def revoke(house_id: int, tg_id: int, permission: str) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            "DELETE FROM member_permissions WHERE house_id = ? AND tg_id = ? AND permission = ?",
            house_id, tg_id, permission,
        )


async def clear_member_grants(house_id: int, tg_id: int) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            "DELETE FROM member_permissions WHERE house_id = ? AND tg_id = ?", house_id, tg_id
        )


class _Rollback(Exception):
    """Состав дома изменился между проверкой и передачей: транзакция откатывается."""


async def transfer_owner(house_id: int, old_owner: int, new_owner: int) -> bool:
    """Передача владения: ровно один владелец до и после, права нового владельца не нужны."""
    try:
        async with db.transaction() as conn:
            suffix = " FOR UPDATE" if db.is_postgres else ""
            await conn.fetchrow("SELECT id FROM houses WHERE id = ?" + suffix, house_id)
            demoted = await conn.execute(
                "UPDATE memberships SET role = 'member' WHERE house_id = ? AND tg_id = ? AND role = 'owner' "
                "AND status = 'active'", house_id, old_owner,
            )
            promoted = await conn.execute(
                "UPDATE memberships SET role = 'owner' WHERE house_id = ? AND tg_id = ? AND role = 'member' "
                "AND status = 'active'", house_id, new_owner,
            )
            if not (demoted and promoted):
                raise _Rollback
            await conn.execute("DELETE FROM member_permissions WHERE house_id = ? AND tg_id = ?", house_id, new_owner)
    except _Rollback:
        return False
    return True


async def delete_house(house_id: int) -> None:
    """Дом со всеми записями — одна транзакция; порядок удаления — от зависимых таблиц к houses."""
    async with db.transaction() as conn:
        suffix = " FOR UPDATE" if db.is_postgres else ""
        await conn.fetchrow("SELECT id FROM houses WHERE id = ?" + suffix, house_id)
        for statement in (
            "DELETE FROM web_receipt_uploads WHERE house_id = ?",
            "DELETE FROM expense_photos WHERE expense_id IN (SELECT id FROM expenses WHERE house_id = ?)",
            "DELETE FROM expense_edits WHERE house_id = ?",
            "DELETE FROM contribution_edits WHERE house_id = ?",
            "DELETE FROM money_import_items WHERE house_id = ?",
            "DELETE FROM expenses WHERE house_id = ?",
            "DELETE FROM contributions WHERE house_id = ?",
            "DELETE FROM categories WHERE house_id = ?",
            "DELETE FROM cleaning_days WHERE house_id = ?",
            "DELETE FROM schedule_versions WHERE house_id = ?",
            "DELETE FROM member_permissions WHERE house_id = ?",
            "DELETE FROM memberships WHERE house_id = ?",
            "DELETE FROM house_settings WHERE house_id = ?",
            "DELETE FROM user_notify_settings WHERE house_id = ?",
            "DELETE FROM scheduler_log WHERE house_id = ?",
        ):
            await conn.execute(statement, house_id)
        await conn.execute("UPDATE users SET active_house_id = NULL WHERE active_house_id = ?", house_id)
        await conn.execute("DELETE FROM houses WHERE id = ?", house_id)
