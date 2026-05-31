from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject

from core.constants import WOLF_BONUSES, WOLF_REDUCTION_CAP

_KNOWN_SPECIES = frozenset({
    "owl", "falcon", "turtle", "dog", "wolf", "fox",
    "hamster", "dragon", "unicorn", "cat",
})


def _empty_bonuses() -> dict:
    return {s: 0 for s in _KNOWN_SPECIES} | {"wolf_reduction": 0.0}


async def _compute_bonuses(db, user_id: int) -> dict:
    """Snapshot every non-exhausted nursery pet's level for the user, plus the
    pre-computed wolf fatigue reduction (slot-aware)."""
    bonuses = _empty_bonuses()
    async with db.execute(
        "SELECT species_id, COALESCE(pet_level, 1), placement "
        "FROM pets WHERE owner_id = ? AND placement IN ('active', 'passive') AND fatigue < 100",
        (user_id,),
    ) as cursor:
        pets = await cursor.fetchall()

    wolf_reduction = 0.0
    for species_id, level, placement in pets:
        if species_id in bonuses:
            bonuses[species_id] = level
        if species_id == "wolf":
            w = WOLF_BONUSES.get(max(1, min(10, level)), {})
            wolf_reduction = min(
                w.get("active_reduction" if placement == "active" else "passive_reduction", 0.0),
                WOLF_REDUCTION_CAP,
            )

    bonuses["wolf_reduction"] = wolf_reduction
    return bonuses


async def pet_bonuses_middleware(
    handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
    event: TelegramObject,
    data: Dict[str, Any],
) -> Any:
    db = data.get("db")
    user = data.get("event_from_user")

    if db and user and getattr(event, "message", None):
        data["pet_bonuses"] = await _compute_bonuses(db, user.id)
    else:
        data["pet_bonuses"] = _empty_bonuses()

    return await handler(event, data)
