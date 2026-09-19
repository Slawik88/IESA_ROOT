"""Application service for the isolated companion-v3 vertical slice."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any
import hashlib
import secrets

from core.companions_v3 import (
    ARCHIVE_VERSION,
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
    EXPEDITION_DISCOVERY_TEXT,
    EXPEDITION_DISCOVERY_NAMES,
    archive_set_id_for_discovery,
    archive_view,
    COMPANION_SKINS,
    COMPANION_SKIN_VERSION,
    companion_skin_catalog,
)
from infrastructure.repositories import companions_v3 as repo
from core.reconstruction import GAME_VERSION
from core.reconstruction import BALANCE_VERSION
from infrastructure.repositories import gameplay_events as event_repo
from services import scar_map_v1 as scar_map


CARE_ACTIONS = {
    "feed": ("Покормить", "Спутник запомнил спокойный ритуал."),
    "play": ("Поиграть", "В следующей сцене спутник станет смелее."),
    "groom": ("Привести в порядок", "Спутник встретит следующую сцену собраннее."),
}

# Choice must change the next scene, not grant a hidden combat modifier. The
# deterministic pick keeps web/chat/preview parity while avoiding a random
# outcome that could feel like a penalty for choosing the "wrong" care action.
CARE_SCENES: dict[str, tuple[tuple[str, str], ...]] = {
    "feed": (("shared_meal", "Спутник запомнил тёплый запах трав."), ("quiet_bowl", "Спутник оставил тебе маленький знак благодарности.")),
    "play": (("ripple_chase", "Спутник увёл игру к воде и открыл короткую тропу."), ("bell_game", "Спутник повторил твой ритм и спрятал смешной жест в Хронике.")),
    "groom": (("rain_brush", "Спутник спокойно пережил дождь и доверился твоим рукам."), ("silver_fur", "На шерсти блеснул след старого серебра — безымянная находка.")),
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
        "last_care_scene": (bond or {}).get("last_care_scene"),
        "active_companion": int(pet["id"]) == active_pet_id,
    }


def _public_expedition_view(contract: dict[str, Any]) -> dict[str, Any]:
    """Never reveal a committed Archive outcome before an explicit claim."""
    view = dict(contract)
    discovery_id = str(view.pop("discovery_id", "") or "")
    if view.get("status") == "claimed" and discovery_id in EXPEDITION_DISCOVERY_NAMES:
        view.update({
            "discovery_id": discovery_id,
            "discovery_name": EXPEDITION_DISCOVERY_NAMES.get(discovery_id),
            "discovery_text": EXPEDITION_DISCOVERY_TEXT.get(discovery_id),
            "archive_set_id": archive_set_id_for_discovery(discovery_id),
        })
    elif view.get("status") == "claimed":
        view.update({
            "discovery_id": None,
            "discovery_name": "Запись старой версии",
            "discovery_text": "Результат будет восстановлен при получении без потери договора.",
            "archive_set_id": None,
        })
    return view


async def archive_overview(db, user_id: int) -> dict[str, Any]:
    return archive_view(await repo.list_archive_discovery_counts(db, user_id))


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
    archive = await archive_overview(db, user_id)
    skins = companion_skin_catalog(archive)
    unlocked_skin_ids = {item["id"] for item in skins if item["unlocked"]}
    selected_skin_id = str((profile or {}).get("selected_skin_id") or "natural")
    if selected_skin_id not in unlocked_skin_ids:
        selected_skin_id = "natural"
    open_expeditions = sum(item["status"] in ("active", "ready") for item in expeditions)
    reserved_mora = await repo.reserved_mora_last_7_days(db, user_id)
    return {
        "policy": public_companion_manifest(),
        "meaningful_days": meaningful_days,
        "role_slots": role_slots,
        "next_role_day": next((day for day in public_companion_manifest()["role_unlock_days"] if day > meaningful_days), None),
        "unlocked_roles": unlocked,
        "selected_role_id": (profile or {}).get("selected_role_id"),
        "selected_skin_id": selected_skin_id,
        "skins": skins,
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
            "contracts": [_public_expedition_view(item) for item in expeditions],
            "ready_count": sum(item["status"] == "ready" for item in expeditions),
            "legacy_active": legacy_expeditions,
            "legacy_contracts_preserved": True,
        },
        "archive": archive,
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
        committed_discoveries = await repo.list_committed_discovery_ids(db, user_id)
        discovery_id = expedition_discovery(
            seed_digest, duration_hours, committed_discoveries
        )
        row = await repo.create_expedition(
            db, user_id=user_id, pet_id=pet_id, duration_hours=duration_hours,
            route_id=quote.route, fixed_mora=quote.projected_mora,
            seed_digest=seed_digest, discovery_id=discovery_id,
            discovery_policy_version=ARCHIVE_VERSION,
        )
        response = {
            "ok": True, "contract_id": int(row["id"]), "pet_id": int(pet_id),
            "duration_hours": duration_hours, "route_id": quote.route,
            "projected_mora": quote.projected_mora,
            "archive_version": ARCHIVE_VERSION,
            "archive_set_id": archive_set_id_for_discovery(discovery_id),
            "ends_at": row["ends_at"].isoformat(), "settled": False,
            "economic_reward": None,
        }
        await repo.save_action(db, user_id, action_id, "expedition_start", request, response)
        await event_repo.record_event(
            db,
            user_id=user_id,
            event_name="expedition_started",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            source="mini_app",
            payload={
                "contract_id": int(row["id"]), "pet_id": int(pet_id),
                "duration_hours": int(duration_hours), "route_id": quote.route,
                "projected_mora": int(quote.projected_mora),
                "archive_version": ARCHIVE_VERSION,
                "archive_set_id": archive_set_id_for_discovery(discovery_id),
            },
            idempotency_key=f"expedition-start:{GAME_VERSION}:{user_id}:{action_id}",
        )
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
        archive_before = await archive_overview(db, user_id)
        claimed = await repo.mark_ready_and_claim(db, user_id)
        if not claimed:
            raise CompanionConflict("Готовых походов пока нет.")
        enriched_claims = []
        new_ids: list[str] = []
        duplicate_ids: list[str] = []
        committed_ids = set(await repo.list_committed_discovery_ids(db, user_id))
        for item in claimed:
            discovery_id = str(item["discovery_id"])
            if discovery_id not in EXPEDITION_DISCOVERY_NAMES:
                seed_digest = str(item.get("seed_digest") or "")
                if len(seed_digest) != 64 or any(char not in "0123456789abcdef" for char in seed_digest.lower()):
                    seed_digest = hashlib.sha256(
                        f"legacy:{user_id}:{item['id']}:{item['duration_hours']}".encode("ascii")
                    ).hexdigest()
                discovery_id = expedition_discovery(
                    seed_digest, int(item["duration_hours"]), committed_ids
                )
                await repo.repair_expedition_discovery(
                    db, user_id, int(item["id"]), discovery_id, ARCHIVE_VERSION
                )
                item["discovery_id"] = discovery_id
            committed_ids.add(discovery_id)
            is_new = await repo.claim_archive_discovery(
                db, user_id, discovery_id, int(item["id"])
            )
            (new_ids if is_new else duplicate_ids).append(discovery_id)
            enriched_claims.append({
                "contract_id": int(item["id"]), "pet_id": int(item["pet_id"]),
                "projected_mora": int(item["fixed_mora"]),
                "discovery_id": discovery_id,
                "discovery_name": EXPEDITION_DISCOVERY_NAMES[discovery_id],
                "discovery_text": EXPEDITION_DISCOVERY_TEXT[discovery_id],
                "archive_set_id": archive_set_id_for_discovery(discovery_id),
                "is_new": is_new,
            })
        archive_after = await archive_overview(db, user_id)
        completed_before = {
            item["id"] for item in archive_before["sets"] if item["completed"]
        }
        newly_completed_sets = [
            item["id"] for item in archive_after["sets"]
            if item["completed"] and item["id"] not in completed_before
        ]
        response = {
            "ok": True,
            "claimed": enriched_claims,
            "projected_mora_total": sum(int(item["fixed_mora"]) for item in claimed),
            "archive": archive_after,
            "new_discovery_ids": new_ids,
            "duplicate_discovery_ids": duplicate_ids,
            "newly_completed_set_ids": newly_completed_sets,
            "settled": False, "economic_reward": None,
        }
        await repo.save_action(db, user_id, action_id, "expedition_claim", request, response)
        await event_repo.record_event(
            db,
            user_id=user_id,
            event_name="expedition_claimed",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            source="mini_app",
            payload={
                "claimed_count": len(response["claimed"]),
                "projected_mora_total": int(response["projected_mora_total"]),
                "contract_ids": [item["contract_id"] for item in response["claimed"]],
                "discovery_ids": [item["discovery_id"] for item in response["claimed"]],
            },
            idempotency_key=f"expedition-claim:{GAME_VERSION}:{user_id}:{action_id}",
        )
        await event_repo.record_event(
            db,
            user_id=user_id,
            event_name="archive_progressed",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            source="mini_app",
            payload={
                "archive_version": ARCHIVE_VERSION,
                "contract_ids": [item["contract_id"] for item in enriched_claims],
                "new_discovery_ids": new_ids,
                "duplicate_discovery_ids": duplicate_ids,
                "completed_set_ids": newly_completed_sets,
                "found_total": int(archive_after["found"]),
            },
            idempotency_key=f"archive-claim:{ARCHIVE_VERSION}:{user_id}:{action_id}",
        )
        await scar_map.apply_archive_claim(
            db, user_id=user_id, action_id=action_id,
            new_discovery_count=len(new_ids), source="mini_app",
        )
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


async def select_skin(
    db, user_id: int, skin_id: str, *, source: str = "mini_app"
) -> dict[str, Any]:
    skin_id = str(skin_id or "").strip()
    if skin_id not in COMPANION_SKINS:
        raise CompanionError("Неизвестный облик спутника.")
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        pets = await repo.list_owned_pets(db, user_id)
        if not pets:
            raise CompanionError("Сначала нужен хотя бы один спутник.")
        default_pet = next(
            (int(pet["id"]) for pet in pets if pet.get("placement") == "active"),
            int(pets[0]["id"]),
        )
        profile = await repo.ensure_profile(db, user_id, default_pet)
        archive = await archive_overview(db, user_id)
        available = {item["id"] for item in companion_skin_catalog(archive) if item["unlocked"]}
        if skin_id not in available:
            raise CompanionConflict(str(COMPANION_SKINS[skin_id]["hint"]))
        changed = str(profile.get("selected_skin_id") or "natural") != skin_id
        if changed:
            await repo.save_selected_skin(db, user_id, skin_id)
            await event_repo.record_event(
                db,
                user_id=user_id,
                event_name="companion_skin_selected",
                game_version=GAME_VERSION,
                balance_version=BALANCE_VERSION,
                source=source,
                payload={"skin_id": skin_id, "skin_version": COMPANION_SKIN_VERSION},
                # State transition is the idempotency boundary: a network replay
                # sees the already-selected skin and never enters this branch.
                # A→B→A is a real second transition and therefore a new event.
                idempotency_key=None,
            )
    return await overview(db, user_id)


async def care(
    db, user_id: int, pet_id: int, action: str, action_id: str,
    *, source: str = "mini_app",
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
            scene_id=CARE_SCENES[action][(points + int(pet_id)) % len(CARE_SCENES[action])][0],
        )
        label, scene_hint = CARE_ACTIONS[action]
        scene_id, scene_text = CARE_SCENES[action][(points + int(pet_id)) % len(CARE_SCENES[action])]
        response = {
            "ok": True,
            "pet_id": int(pet_id),
            "action": action,
            "action_name": label,
            "scene_hint": scene_hint,
            "scene_id": scene_id,
            "scene_text": scene_text,
            "bond": bond_progress(points),
            "care_bank": bank - 1,
            "economic_reward": None,
        }
        await repo.save_action(db, user_id, action_id, "care", request, response)
        await event_repo.record_event(
            db,
            user_id=user_id,
            event_name="companion_care",
            game_version=GAME_VERSION,
            balance_version=BALANCE_VERSION,
            source=source,
            payload={
                "pet_id": int(pet_id), "action": action,
                "scene_id": scene_id, "bond_points": points,
                "care_bank": bank - 1,
            },
            idempotency_key=f"companion-care:{GAME_VERSION}:{user_id}:{action_id}",
        )
    return response
