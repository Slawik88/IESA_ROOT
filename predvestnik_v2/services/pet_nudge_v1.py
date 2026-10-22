"""Gentle pet reminder: counts app days without the pets screen and offers one soft card."""
from __future__ import annotations

from loguru import logger

from core import pet_nudge_v1 as rules
from core.chests_v1 import PET_SPECIES
from infrastructure.repositories import pet_nudge_v1 as repo
from infrastructure.repositories import system_flags


async def pets_opened(db, user_id: int) -> None:
    """Called by the pets screens. Never breaks them: the reminder is optional."""
    try:
        await repo.visit(db, user_id, True)
    except Exception:
        logger.exception("pet nudge: pets visit not recorded")


async def app_opened(db, user_id: int) -> dict:
    """One app visit; returns the card when it is due, otherwise {"show": False}."""
    await repo.visit(db, user_id, False)
    if not await repo.claim_show(db, user_id):
        return {"show": False}
    pet = await repo.oldest_pet(db, user_id)
    if pet:
        species = PET_SPECIES.get(pet["species_id"], {})
        pet = {"name": (pet["name"] or "").strip() or species.get("name", "Питомец"), "icon": species.get("icon", "🐾")}
    trail = await system_flags.is_enabled(db, "pets_v2")
    return {"show": True, **rules.card(pet, trail)}


async def answered(db, user_id: int, choice: str) -> None:
    await repo.answer(db, user_id, choice)
