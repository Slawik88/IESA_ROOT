"""Terminal adapter for the retired CP duel system.

The product now uses the clicker combat loop. Legacy Mora wagers must not be
created or resolved into new rewards; a still-pending challenge may only be
closed so its challenger's reserve becomes spendable again.
"""
from infrastructure.repositories.duel import set_duel_status


LEGACY_DUEL_CLOSED_MESSAGE = (
    "Старые дуэли со ставками закрыты. Боевая система теперь находится "
    "во вкладке «Игра»; незавершённую старую ставку можно только освободить."
)


async def create_challenge(
    db,
    challenger_id: int,
    challenged_id: int,
    chat_id: int,
    stake: float,
) -> tuple[bool, dict | str]:
    """Reject every new legacy wager without reading or mutating balances."""
    return False, LEGACY_DUEL_CLOSED_MESSAGE


async def accept_duel(db, duel_id: int) -> tuple[bool, dict | str]:
    """Retire a pending legacy challenge instead of producing a battle result."""
    await decline_duel(db, duel_id)
    return False, LEGACY_DUEL_CLOSED_MESSAGE


async def decline_duel(db, duel_id: int) -> bool:
    """Atomically release the challenger hold and terminalize a pending duel."""
    async with db.connection.transaction():
        async with db.execute(
            "SELECT id, status, stake, challenger_id FROM duels "
            "WHERE id = ? FOR UPDATE",
            (duel_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row or row[1] != "pending":
            return False
        await db.execute(
            "UPDATE user_reserve SET reserved_mora = "
            "GREATEST(0, reserved_mora - ?) WHERE user_id = ?",
            (row[2], row[3]),
        )
        await set_duel_status(db, duel_id, "declined")
    return True
