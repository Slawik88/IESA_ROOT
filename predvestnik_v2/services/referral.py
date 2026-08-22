"""Read-only compatibility boundary for the retired referral program.

Existing ``referred_by`` rows remain available for audit and abuse analysis.
New links do not bind accounts and never mint currency, VIP time, or premium
commission. Promo codes are a separate system and remain enabled.
"""


async def register_referral(db, new_user_id: int, referrer_id: int) -> bool:
    """Return ``False`` without touching the database or granting a reward."""
    return False
