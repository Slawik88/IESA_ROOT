"""Terminal settlement for retired wager mini-games.

Sapper, Safe and Alchemy no longer accept starts or actions. An existing active
session may only be refunded at face value and closed, atomically and once.
"""
from infrastructure.repositories.economy import add_balance


async def refund_active_sessions(db, user_id: int) -> dict:
    """Refund and close every active legacy session for one player."""
    refunded = 0.0
    count = 0
    async with db.connection.transaction():
        async with db.execute(
            "SELECT id, game, stake FROM minigame_sessions "
            "WHERE user_id = ? AND status = 'active' ORDER BY id FOR UPDATE",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        for row in rows:
            session_id = int(row["id"])
            stake = max(0.0, float(row["stake"] or 0))
            game = str(row["game"])
            if stake:
                await add_balance(
                    db,
                    user_id,
                    mora=stake,
                    commit=False,
                    source="legacy_minigame_refund",
                    idempotency_key=f"legacy-minigame-refund:{session_id}",
                    source_type="migration",
                    reference_type="minigame_session",
                    reference_id=session_id,
                    metadata={"game": game, "policy": "retire_at_face_value"},
                )
            await db.execute(
                "UPDATE minigame_sessions SET status = 'retired_refund', payout = ?, "
                "updated_at = NOW() WHERE id = ? AND status = 'active'",
                (stake, session_id),
            )
            refunded += stake
            count += 1

    return {"count": count, "refunded_mora": round(refunded, 2)}
