"""Pet level-ups paid with Pet Cards, Mora and Essence (ECO-04, P7). Dark until ``pets_level_up_v1`` is on."""
from __future__ import annotations

from uuid import uuid4

from core.economy_contract import InsufficientBalance
from core.pet_levels_v1 import FLAG, POLICY_VERSION, REASON_CODE, level_up_cost
from core.pets_v1 import MAX_LEVEL, PetPolicyError
from infrastructure.repositories import economy_ledger, system_flags
from infrastructure.repositories import pets_v1 as repo
from infrastructure.repositories import skins_v3 as essence_repo
from services.pets_v1 import PetConflict


def _cost_dict(cost) -> dict:
    return {"cards": cost.cards, "mora": cost.mora, "essence": cost.essence}


async def enabled(db) -> bool:
    return await system_flags.is_enabled(db, FLAG)


async def level_up_pet(db, *, user_id: int, pet_id: int, action_id: str) -> dict:
    """One step L -> L+1: cards of the pet's species, Mora and (L5/L10/L15) Essence, all or nothing."""
    action_id = str(action_id or "").strip()
    if not action_id or len(action_id) > 96:
        raise PetPolicyError("action_id обязателен.")
    if not await enabled(db):
        raise PetPolicyError("Улучшение питомцев пока недоступно.")
    await essence_repo.ensure_tables(db)
    request = {"type": "level_up", "pet_id": int(pet_id)}
    async with db.connection.transaction():
        await repo.lock_user(db, int(user_id))
        replay = await repo.cached_action(db, int(user_id), action_id)
        if replay:
            if replay["request"] != request:
                raise PetConflict("action_id уже использован для другого действия.")
            return {**replay["response"], "idempotent_replay": True}
        pet = await repo.get_owned_pet_full(db, int(user_id), int(pet_id))
        if not pet:
            raise PetPolicyError("Питомец не найден или принадлежит другому игроку.")
        state = await repo.get_state(db, int(user_id), int(pet_id))
        level = int(state["level"])
        if level >= MAX_LEVEL:
            raise PetPolicyError("Питомец уже на максимальном уровне.")
        cost = level_up_cost(level, str(pet["rarity"]))
        species = str(pet["species_id"])
        try:
            cards_left = await repo.spend_cards(db, user_id=int(user_id), species_id=species, quantity=cost.cards)
        except ValueError as exc:
            raise PetPolicyError(f"Не хватает карт: нужно {cost.cards}.") from exc
        try:
            mutation = await economy_ledger.apply_balance_change(
                db, int(user_id), {"mora": -cost.mora}, reason_code=REASON_CODE,
                idempotency_key=f"pet-level:{int(user_id)}:{action_id}", source_type="pets_v1",
                reference_type="pet_level_up", reference_id=f"{int(pet_id)}:{cost.level_after}",
                metadata={"policy_version": POLICY_VERSION, "pet_id": int(pet_id), "species_id": species,
                          "level_before": cost.level_before, "level_after": cost.level_after, **_cost_dict(cost)},
                note="Улучшение питомца",
            )
        except InsufficientBalance as exc:
            raise PetPolicyError(f"Не хватает Моры: нужно {cost.mora}.") from exc
        if cost.essence:
            try:
                await essence_repo.essence_apply(
                    db, int(user_id), -cost.essence, reason=REASON_CODE, reference=f"{int(pet_id)}:{cost.level_after}",
                    idempotency_key=f"pet-level:{action_id}",
                )
            except ValueError as exc:
                raise PetPolicyError(f"Не хватает Эссенции: нужно {cost.essence}.") from exc
        await repo.set_level(db, int(user_id), int(pet_id), cost.level_after)
        await repo.save_level_up(
            db, level_up_id=uuid4().hex, user_id=int(user_id), pet_id=int(pet_id), action_id=action_id,
            species_id=species, rarity=str(pet["rarity"]), level_before=cost.level_before,
            level_after=cost.level_after, cards=cost.cards, mora=cost.mora, essence=cost.essence,
            economy_operation_id=str(mutation.operation_id), policy_version=POLICY_VERSION,
        )
        response = {"ok": True, "pet_id": int(pet_id), "level_before": cost.level_before,
                    "level_after": cost.level_after, "cost": _cost_dict(cost), "cards_left": cards_left,
                    "idempotent_replay": False}
        await repo.save_action(db, int(user_id), action_id, request, response)
    return response


async def next_step(db, user_id: int, pets: list[dict]) -> dict:
    """Read-only data for the pet screen: price of the next step and the cards in stock."""
    cards = await repo.card_balances(db, int(user_id))
    items = {}
    for pet in pets:
        level = int(pet["level"])
        if level >= MAX_LEVEL:
            items[int(pet["id"])] = None
            continue
        cost = level_up_cost(level, str(pet["rarity"]))
        have = cards.get(str(pet["species_id"]), 0)
        items[int(pet["id"])] = {**_cost_dict(cost), "cards_have": have, "level_after": cost.level_after}
    return {"enabled": await enabled(db), "max_level": MAX_LEVEL, "policy_version": POLICY_VERSION, "steps": items}
