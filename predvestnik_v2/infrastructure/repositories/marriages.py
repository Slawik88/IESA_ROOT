# infrastructure/repositories/marriages.py
import aiosqlite
from infrastructure.repositories.economy import get_balance


async def get_user_marriage(
    db: aiosqlite.Connection, chat_id: int, user_id: int
) -> dict | None:
    async with db.execute(
        "SELECT id, chat_id, user1_id, user1_name, user2_id, user2_name, "
        "marriage_date, family_balance FROM marriages "
        "WHERE chat_id = ? AND (user1_id = ? OR user2_id = ?)",
        (chat_id, user_id, user_id),
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def family_bank_transaction(
    db: aiosqlite.Connection,
    marriage_id: int,
    user_id: int,
    amount: float,
    action: str,
) -> tuple[bool, str]:
    if amount <= 0:
        return False, "Сумма должна быть больше нуля."

    try:
        async with db.connection.transaction():
            # FOR UPDATE locks both rows to prevent race conditions on parallel operations
            async with db.execute(
                "SELECT family_balance FROM marriages WHERE id = ? FOR UPDATE", (marriage_id,)
            ) as cursor:
                m_row = await cursor.fetchone()
                if not m_row:
                    return False, "Брак не найден."
                family_balance = float(m_row[0])

            if action == "deposit":
                async with db.execute(
                    "SELECT user_balance_mora FROM users WHERE user_tg_id = ? FOR UPDATE",
                    (user_id,),
                ) as c:
                    u_row = await c.fetchone()
                user_mora = float(u_row[0]) if u_row else 0.0
                if user_mora < amount:
                    return False, "Недостаточно личной Моры."
                await db.execute(
                    "UPDATE users SET user_balance_mora = user_balance_mora - ? WHERE user_tg_id = ?",
                    (amount, user_id),
                )
                await db.execute(
                    "UPDATE marriages SET family_balance = family_balance + ? WHERE id = ?",
                    (amount, marriage_id),
                )
            elif action == "withdraw":
                if family_balance < amount:
                    return False, "Недостаточно Моры в семейном бюджете."
                await db.execute(
                    "UPDATE marriages SET family_balance = family_balance - ? WHERE id = ?",
                    (amount, marriage_id),
                )
                await db.execute(
                    "UPDATE users SET user_balance_mora = user_balance_mora + ? WHERE user_tg_id = ?",
                    (amount, user_id),
                )

        return True, "Успешно."
    except Exception as e:
        return False, f"Ошибка: {e}"


async def create_marriage(
    db: aiosqlite.Connection,
    chat_id: int,
    u1_id: int,
    u1_name: str,
    u2_id: int,
    u2_name: str,
):
    await db.execute(
        "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name) "
        "VALUES (?, ?, ?, ?, ?)",
        (chat_id, u1_id, u1_name, u2_id, u2_name),
    )
    await db.commit()


async def delete_marriage(db: aiosqlite.Connection, chat_id: int, user_id: int):
    await db.execute(
        "DELETE FROM marriages WHERE chat_id = ? AND (user1_id = ? OR user2_id = ?)",
        (chat_id, user_id, user_id),
    )
    await db.commit()


async def get_all_marriages(db: aiosqlite.Connection, chat_id: int) -> list[dict]:
    async with db.execute(
        "SELECT * FROM marriages WHERE chat_id = ? ORDER BY marriage_date DESC",
        (chat_id,),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


# ── Marriage proposals ─────────────────────────────────────────────────────────

async def create_proposal(db, chat_id: int, proposer_id: int, target_id: int) -> int:
    """Insert a pending proposal, expiring in 24 hours. Returns proposal id."""
    async with db.execute(
        "INSERT INTO marriage_proposals (chat_id, proposer_id, target_id, expires_at) "
        "VALUES (?, ?, ?, NOW() + INTERVAL '24 hours') RETURNING id",
        (chat_id, proposer_id, target_id),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0


async def update_proposal_status(
    db, chat_id: int, proposer_id: int, target_id: int, status: str
) -> None:
    """Update the most recent pending proposal between two users in a chat."""
    await db.execute(
        "UPDATE marriage_proposals SET status = ? "
        "WHERE chat_id = ? AND proposer_id = ? AND target_id = ? AND status = 'pending'",
        (status, chat_id, proposer_id, target_id),
    )
