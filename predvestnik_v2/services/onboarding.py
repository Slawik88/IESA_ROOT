"""Compatibility guard for the retired legacy starter kit.

The Reconstruction campaign creates its starter squad and tutorial state only
when the player opens the game. Registration itself must not mint currencies,
gacha tokens or a random pet.
"""


async def grant_starter_kit(db, user_id: int) -> dict | None:
    """Close a pending legacy flag without granting any economic value."""
    try:
        await db.execute(
            "UPDATE users SET onboarded = TRUE "
            "WHERE user_tg_id = ? AND onboarded = FALSE",
            (user_id,),
        )
        await db.commit()
        return None
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        return None
