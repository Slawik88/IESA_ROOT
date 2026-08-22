"""Application service for the isolated companion-v3 vertical slice."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any
import hashlib
import secrets

from core.companions_v3 import (
    COMPANION_ROLES,
    EXPEDITION_OPTIONS,
    bond_progress,
    public_companion_manifest,
    quote_expedition,
    recover_care_bank,
    role_unlock_count,
    expedition_discovery,
    expedition_slot_count,
    SECOND_EXPEDITION_SLOT_ENCOUNTER,
)
from infrastructure.repositories import companions_v3 as repo
from core.reconstruction import GAME_VERSION


CARE_ACTIONS = {
    "feed": ("Покормить", "Спутник запомнил спокойный ритуал."),
    "play": ("Поиграть", "В следующей сцене спутник станет смелее."),
    "groom": ("Привести в порядок", "Спутник встретит следующую сцену собраннее."),
}


class CompanionError(ValueError):
    pass


class CompanionConflict(CompanionError):
    pass


async def selected_role(db, user_id: int) -> str | None:
    profile = await repo.get_profile(db, user_id)
    role_id = (profile or {}).get("selected_role_id")
    role = COMPANION_ROLES.get(str(role_id)) if role_id else None
    return str(role_id) if role and role.get("implemented") else None


def _pet_view(pet: dict[str, Any], bond: dict[str, Any] | None, active_pet_id: int | None) -> dict[str, Any]:
    points = int((bond or {}).get("bond_points", 0))
    care_bank = int((bond or {}).get("care_bank", 1))
    if bond and bond.get("bank_updated_at") and bond.get("server_now"):
        care_bank, _ = recover_care_bank(
            care_bank, bond["bank_updated_at"], bond["server_now"]
        )
    return {
        "id": int(pet["id"]),
        "name": pet.get("name") or "Без имени",
        "species_id": pet.get("species_id"),
        "rarity": pet.get("rarity"),
        "legacy": {
            "level": int(pet.get("legacy_level") or 1),
            "duplicates": int(pet.get("legacy_duplicates") or 0),
            "copy_index": int(pet.get("copy_index") or 1),
            "placement": pet.get("placement"),
            "fatigue": int(pet.get("fatigue") or 0),
        },
        "bond": bond_progress(points),
        "care_bank": care_bank,
        "last_care_action": (bond or {}).get("last_care_action"),
        "active_companion": int(pet["id"]) == active_pet_id,
    }


async def overview(db, user_id: int) -> dict[str, Any]:
    pets = await repo.list_owned_pets(db, user_id)
    legacy_default = next((int(pet["id"]) for pet in pets if pet.get("placement") == "active"), None)
    profile = await repo.get_profile(db, user_id)
    active_pet_id = int(profile["active_pet_id"]) if profile and profile.get("active_pet_id") else legacy_default
    bonds = {int(item["pet_id"]): item for item in await repo.list_bond_states(db, user_id)}
    meaningful_days = await repo.count_meaningful_days(db, user_id)
    role_slots = role_unlock_count(meaningful_days)
    unlocked = list((profile or {}).get("unlocked_roles") or [])
    legacy_expeditions = await repo.list_legacy_expeditions(db, user_id)
    second_slot = await repo.has_second_expedition_slot(
        db, user_id, GAME_VERSION, SECOND_EXPEDITION_SLOT_ENCOUNTER
    )
    expedition_slots = expedition_slot_count(second_slot)
    expeditions = await repo.list_expeditions(db, user_id)
    open_expeditions = sum(item["status"] in ("active", "ready") for item in expeditions)
    reserved_mora = await repo.reserved_mora_last_7_days(db, user_id)
    return {
        "policy": public_companion_manifest(),
        "meaningful_days": meaningful_days,
        "role_slots": role_slots,
        "next_role_day": next((day for day in public_companion_manifest()["role_unlock_days"] if day > meaningful_days), None),
        "unlocked_roles": unlocked,
        "selected_role_id": (profile or {}).get("selected_role_id"),
        "active_pet_id": active_pet_id,
        "pets": [_pet_view(pet, bonds.get(int(pet["id"])), active_pet_id) for pet in pets],
        "care_actions": [
            {"id": action_id, "name": label, "scene_hint": hint}
            for action_id, (label, hint) in CARE_ACTIONS.items()
        ],
        "expeditions": {
            "mode": "shadow_only",
            "start_enabled": bool(pets) and not legacy_expeditions and open_expeditions < expedition_slots,
            "reason": (
                "Сначала заверши старый поход — его договор сохранён без изменений."
                if legacy_expeditions else
                "Результат фиксируется сервером, но Мора пока только считается и не начисляется."
            ),
            "slots": expedition_slots,
            "open_slots": max(0, expedition_slots - open_expeditions),
            "weekly_reserved_mora": reserved_mora,
            "options": [asdict(quote_expedition(hours, reserved_mora)) for hours in EXPEDITION_OPTIONS],
            "contracts": expeditions,
            "ready_count": sum(item["status"] == "ready" for item in expeditions),
            "legacy_active": legacy_expeditions,
            "legacy_contracts_preserved": True,
        },
    }


async def start_expedition(
    db, user_id: int, pet_id: int, duration_hours: int, action_id: str
) -> dict[str, Any]:
    action_id = str(action_id or "").strip()
    if not action_id or len(action_id) > 96:
        raise CompanionError("action_id обязателен и не должен превышать 96 символов.")
    if duration_hours not in EXPEDITION_OPTIONS:
        raise CompanionError("Доступны походы на 2, 6 или 12 часов.")
    request = {"pet_id": int(pet_id), "duration_hours": int(duration_hours)}
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        cached = await repo.get_cached_action(db, user_id, action_id)
        if cached:
            if cached["request"] != request:
                raise CompanionConflict("action_id уже использован для другого похода.")
            return {**cached["response"], "idempotent_replay": True}
        pet = await repo.get_owned_pet(db, user_id, pet_id)
        if not pet:
            raise CompanionError("Питомец не найден или принадлежит другому игроку.")
        if await repo.list_legacy_expeditions(db, user_id):
            raise CompanionConflict("Сначала заверши старый поход: его награда сохранена по старым правилам.")
        second_slot = await repo.has_second_expedition_slot(
            db, user_id, GAME_VERSION, SECOND_EXPEDITION_SLOT_ENCOUNTER
        )
        slots = expedition_slot_count(second_slot)
        if await repo.count_open_expeditions(db, user_id) >= slots:
            raise CompanionConflict("Все доступные слоты разведки заняты.")
        if await repo.pet_has_open_expedition(db, user_id, pet_id):
            raise CompanionConflict("Этот спутник уже находится в разведке.")
        reserved = await repo.reserved_mora_last_7_days(db, user_id)
        quote = quote_expedition(duration_hours, reserved)
        seed_digest = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
        discovery_id = expedition_discovery(seed_digest, duration_hours)
        row = await repo.create_expedition(
            db, user_id=user_id, pet_id=pet_id, duration_hours=duration_hours,
            route_id=quote.route, fixed_mora=quote.projected_mora,
            seed_digest=seed_digest, discovery_id=discovery_id,
        )
        response = {
            "ok": True, "contract_id": int(row["id"]), "pet_id": int(pet_id),
            "duration_hours": duration_hours, "route_id": quote.route,
            "projected_mora": quote.projected_mora, "discovery_id": discovery_id,
            "ends_at": row["ends_at"].isoformat(), "settled": False,
            "economic_reward": None,
        }
        await repo.save_action(db, user_id, action_id, "expedition_start", request, response)
    return response


async def claim_expeditions(db, user_id: int, action_id: str) -> dict[str, Any]:
    action_id = str(action_id or "").strip()
    if not action_id or len(action_id) > 96:
        raise CompanionError("action_id обязателен и не должен превышать 96 символов.")
    request = {"claim": "all_ready"}
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        cached = await repo.get_cached_action(db, user_id, action_id)
        if cached:
            if cached["request"] != request:
                raise CompanionConflict("action_id уже использован для другого действия.")
            return {**cached["response"], "idempotent_replay": True}
        claimed = await repo.mark_ready_and_claim(db, user_id)
        if not claimed:
            raise CompanionConflict("Готовых походов пока нет.")
        response = {
            "ok": True,
            "claimed": [{
                "contract_id": int(item["id"]), "pet_id": int(item["pet_id"]),
                "projected_mora": int(item["fixed_mora"]),
                "discovery_id": item["discovery_id"],
            } for item in claimed],
            "projected_mora_total": sum(int(item["fixed_mora"]) for item in claimed),
            "settled": False, "economic_reward": None,
        }
        await repo.save_action(db, user_id, action_id, "expedition_claim", request, response)
    return response


async def select_active_pet(db, user_id: int, pet_id: int) -> dict[str, Any]:
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        pet = await repo.get_owned_pet(db, user_id, pet_id)
        if not pet:
            raise CompanionError("Питомец не найден или принадлежит другому игроку.")
        await repo.ensure_profile(db, user_id, int(pet_id))
        await repo.save_active_pet(db, user_id, pet_id)
    return await overview(db, user_id)


async def select_role(db, user_id: int, role_id: str) -> dict[str, Any]:
    if role_id not in COMPANION_ROLES:
        raise CompanionError("Неизвестная роль спутника.")
    if not COMPANION_ROLES[role_id].get("implemented"):
        raise CompanionConflict("Эта роль ещё проходит боевую реализацию и пока недоступна для выбора.")
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        pets = await repo.list_owned_pets(db, user_id)
        if not pets:
            raise CompanionError("Сначала нужен хотя бы один питомец.")
        default_pet = next((int(pet["id"]) for pet in pets if pet.get("placement") == "active"), int(pets[0]["id"]))
        profile = await repo.ensure_profile(db, user_id, default_pet)
        unlocked = list(profile.get("unlocked_roles") or [])
        if role_id not in unlocked:
            slots = role_unlock_count(await repo.count_meaningful_days(db, user_id))
            if len(unlocked) >= slots:
                raise CompanionConflict("Следующий прямой выбор роли ещё не открыт.")
            unlocked.append(role_id)
        await repo.save_profile_roles(
            db, user_id, selected_role_id=role_id, unlocked_roles=unlocked
        )
    return await overview(db, user_id)


async def care(
    db, user_id: int, pet_id: int, action: str, action_id: str
) -> dict[str, Any]:
    action_id = str(action_id or "").strip()
    if not action_id or len(action_id) > 96:
        raise CompanionError("action_id обязателен и не должен превышать 96 символов.")
    if action not in CARE_ACTIONS:
        raise CompanionError("Доступно: покормить, поиграть или привести в порядок.")
    request = {"pet_id": int(pet_id), "action": action}
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        cached = await repo.get_cached_action(db, user_id, action_id)
        if cached:
            if cached["request"] != request:
                raise CompanionConflict("action_id уже использован для другого действия.")
            return {**cached["response"], "idempotent_replay": True}
        pet = await repo.get_owned_pet(db, user_id, pet_id)
        if not pet:
            raise CompanionError("Питомец не найден или принадлежит другому игроку.")
        state = await repo.get_bond_state(db, user_id, pet_id)
        bank, anchor = recover_care_bank(
            int(state["care_bank"]), state["bank_updated_at"], state["server_now"]
        )
        if bank <= 0:
            raise CompanionConflict("Запас заботы пуст. Одна возможность вернётся через 48 часов.")
        points = int(state["bond_points"]) + 1
        await repo.save_care(
            db, user_id, pet_id, bond_points=points, care_bank=bank - 1,
            bank_updated_at=anchor, action=action,
        )
        label, scene_hint = CARE_ACTIONS[action]
        response = {
            "ok": True,
            "pet_id": int(pet_id),
            "action": action,
            "action_name": label,
            "scene_hint": scene_hint,
            "bond": bond_progress(points),
            "care_bank": bank - 1,
            "economic_reward": None,
        }
        await repo.save_action(db, user_id, action_id, "care", request, response)
    return response


def preview_overview() -> dict[str, Any]:
    """Representative local-only state; never used as production player data."""
    policy = public_companion_manifest()
    pets = [
        {"id": 901, "name": "Мокко", "species_id": "fox", "rarity": "epic",
         "legacy": {"level": 7, "duplicates": 13, "copy_index": 1, "placement": "active", "fatigue": 22}},
        {"id": 902, "name": "Тихий Шорох", "species_id": "owl", "rarity": "rare",
         "legacy": {"level": 4, "duplicates": 5, "copy_index": 1, "placement": "passive", "fatigue": 0}},
        {"id": 903, "name": "Искра", "species_id": "dragon", "rarity": "legendary",
         "legacy": {"level": 10, "duplicates": 27, "copy_index": 1, "placement": "storage", "fatigue": 61}},
    ]
    for index, pet in enumerate(pets):
        pet.update({
            "bond": bond_progress(6 if index == 0 else 0),
            "care_bank": 3 if index == 0 else 1,
            "last_care_action": "play" if index == 0 else None,
            "active_companion": index == 0,
        })
    return {
        "policy": policy, "meaningful_days": 15, "role_slots": 4, "next_role_day": 20,
        "unlocked_roles": ["lantern", "guardian", "rhythm_keeper", "echo"], "selected_role_id": "lantern",
        "active_pet_id": 901, "pets": pets,
        "care_actions": [
            {"id": key, "name": value[0], "scene_hint": value[1]}
            for key, value in CARE_ACTIONS.items()
        ],
        "expeditions": {
            "mode": "shadow_only", "start_enabled": True,
            "reason": "Награды пока считаются в тени и не меняют кошелёк.",
            "options": [asdict(quote_expedition(hours)) for hours in EXPEDITION_OPTIONS],
            "slots": 2, "open_slots": 2, "weekly_reserved_mora": 0,
            "contracts": [], "ready_count": 0,
            "legacy_active": [], "legacy_contracts_preserved": True,
        },
    }
