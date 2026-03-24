"""
Pet service — handles pet walk and related actions.

Usage:
    from services.pet_service import walk
    result = await walk(user_id, chat_id)
    # result = {
    #   "ok": True, "pet_type": "cat", "pet_name": "Мурка",
    #   "fatigue": 40, "walk_mins": 90, "reward": 20, "partner_rewarded": False
    # }
"""
from database.db import start_pet_walk_full
from .exceptions import PetAlreadyWalkingError, PetNotFoundError


async def walk(user_id: int, chat_id: int) -> dict:
    """Start a pet walk for *user_id* in *chat_id*.

    Returns a result dict on success.

    Raises
    ------
    PetAlreadyWalkingError  If the pet is already on a walk.
    PetNotFoundError        If the user has no pet or the pet can't walk for another reason.
    """
    result = await start_pet_walk_full(user_id, chat_id)
    if not result.get("ok"):
        mins_left = result.get("mins_left")
        if mins_left is not None:
            raise PetAlreadyWalkingError(mins_left)
        raise PetNotFoundError(result.get("error", ""))
    return result
