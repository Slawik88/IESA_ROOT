"""
Enhance service — handles item enhancement (заточка).

Usage:
    from services.enhance_service import enhance
    result = await enhance(user_id, chat_id, item_id)
    # result = {
    #   "success": True, "message": "✨ Заточка успешна! ...", "enhancement_level": 3
    # }
"""
from database.db import enhance_item as _db_enhance
from .exceptions import ItemNotFoundError, NotEnoughMoraError


async def enhance(user_id: int, chat_id: int, item_id: int) -> dict:
    """Attempt to enhance an RPG item (weapon / armor / artifact).

    Deducts the upgrade cost from the user's personal mora and returns the result.

    Returns
    -------
    dict with keys:
        ``success``           bool — whether the enhancement level went up.
        ``message``           str  — human-readable result (HTML-safe).
        ``enhancement_level`` int  — item's enhancement level after the attempt.

    Raises
    ------
    ItemNotFoundError   If the item doesn't exist, doesn't belong to the user,
                        or isn't an enhanceable slot.
    NotEnoughMoraError  If the user can't afford the enhancement cost.
    """
    ok, msg, new_level = await _db_enhance(user_id, chat_id, item_id)

    # db.enhance_item encodes error conditions in the returned message
    if not ok and new_level == 0 and "не найден" in msg:
        raise ItemNotFoundError(msg)

    # "Недостаточно Моры" is returned with new_level == current_level (unchanged).
    # Raise NotEnoughMoraError so callers can handle it uniformly.
    if not ok and "Недостаточно Моры" in msg:
        raise NotEnoughMoraError(have=0, need=0)  # exact amounts are in msg

    return {
        "success": ok,
        "message": msg,
        "enhancement_level": new_level,
    }
