"""Idempotent active-pet writer for the approved pet foundation."""
from __future__ import annotations

import secrets

from infrastructure.repositories import pets_v1 as repo
from infrastructure.repositories import chests_v1 as chest_repo, economy_ledger, system_flags
from core.pets_v1 import MAX_LEVEL, POLICY_VERSION, PetPolicyError, apply_active_slot_swap, endurance_after_elapsed, level_effects, spend_activity_endurance, validate_activity, validate_expedition_decision
from core.chests_v1 import FOODS, KEY_SOURCE_COUNTS, PET_SPECIES, POLICY_VERSION as CHEST_POLICY_VERSION, KeyGrant, canonical_snapshot_fingerprint, validate_key_grant
from core.pet_info_v1 import level_milestones, species_info
from core.echo_shards_v1 import MaxDuplicateCompensation
from services.echo_shards_v1 import EchoShardReceipt, compensate_max_duplicate_in_transaction
from uuid import uuid4


class PetConflict(PetPolicyError): pass


async def _settle_activity_keys(db, user_id: int) -> list[dict]:
    if not await system_flags.is_enabled(db, "content_chests_v1"):
        return []
    await chest_repo.assert_delivery_ready(db)
    receipts = []
    for run in await repo.unrewarded_completed_runs(db, int(user_id)):
        kind = str(run["kind"])
        grant = validate_key_grant(KeyGrant(
            source_kind=f"pet_{kind}_complete", source_event_id=str(run["id"]), amount=1,
            source_snapshot={"run_id": str(run["id"]), "activity_kind": kind,
                             "duration_hours": int(run["duration_hours"]), "pet_id": int(run["pet_id"])},
        ))
        snapshot_hash = canonical_snapshot_fingerprint(grant.source_snapshot)
        existing = await chest_repo.find_grant(
            db, user_id=int(user_id), source_kind=grant.source_kind, source_event_id=grant.source_event_id,
        )
        if existing:
            grant_id = str(existing["id"])
            after = int(existing["balance_before"]) + await chest_repo.grant_total(
                db, user_id=int(user_id), source_kind=grant.source_kind,
                source_event_id=grant.source_event_id)
        else:
            account = await chest_repo.lock_account(db, int(user_id))
            grant_id = uuid4().hex
            after = await chest_repo.apply_grant(
                db, grant_id=grant_id, user_id=int(user_id), source_kind=grant.source_kind,
                source_event_id=grant.source_event_id, amount=1, policy_version=CHEST_POLICY_VERSION,
                source_snapshot=dict(grant.source_snapshot), source_snapshot_hash=snapshot_hash,
                balance_before=int(account["balance"]), account_epoch=int(account["account_epoch"]),
            )
            after = await chest_repo.apply_bonus_grants(
                db, user_id=int(user_id), source_kind=grant.source_kind,
                source_event_id=grant.source_event_id, policy_version=CHEST_POLICY_VERSION,
                source_snapshot=dict(grant.source_snapshot), source_snapshot_hash=snapshot_hash,
                balance_before=after, account_epoch=int(account["account_epoch"]),
            )
        await repo.save_activity_reward(
            db, run_id=str(run["id"]), user_id=int(user_id), activity_kind=kind, key_grant_id=grant_id,
        )
        from services import quests_v1 as quests
        from services.vip import is_vip_active
        await quests.record_metric(
            db, user_id=int(user_id), metric="pet_activity_completed", event_id=str(run["id"]),
            vip_active=await is_vip_active(db, int(user_id)),
            sources=await quests.available_sources(db, user_id=int(user_id)),
        )
        from services import achievements_v1 as achievements
        await achievements.record_terminal(
            db, user_id=int(user_id), metric="pet_activity_completed", source_event_id=str(run["id"]),
            source_snapshot={"run_id": str(run["id"]), "activity_kind": kind,
                             "duration_hours": int(run["duration_hours"]), "pet_id": int(run["pet_id"])},
        )
        receipts.append({"run_id": str(run["id"]), "activity_kind": kind,
                         "amount_keys": await chest_repo.grant_total(
                             db, user_id=int(user_id), source_kind=grant.source_kind,
                             source_event_id=grant.source_event_id),
                         "key_balance": after})
    return receipts


def _duplicate_event_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 160 or any(ord(char) < 32 for char in normalized):
        raise PetPolicyError("source_event_id обязателен и должен быть безопасным идентификатором.")
    return normalized


def _duplicate_response(row: dict, *, replay: bool) -> dict:
    return {
        "ok": True, "pet_id": int(row["pet_id"]), "outcome": str(row["outcome"]),
        "level_before": int(row["level_before"]), "level_after": int(row["level_after"]),
        "echo_amount": int(row["echo_amount"]), "idempotent_replay": replay,
    }


async def apply_duplicate_progression(db, *, user_id: int, pet_id: int, source_event_id: str) -> dict:
    """Internal-only terminal writer for a pet duplicate.

    No HTTP/chat route calls this.  A future verified loot writer supplies its
    immutable source event id while this function owns level 1→16 and the
    level-16 Echo Shard boundary in one database transaction.
    """
    source_event_id = _duplicate_event_id(source_event_id)
    async with db.connection.transaction():
        await repo.lock_user(db, int(user_id))
        replay = await repo.find_duplicate_progression(db, int(user_id), source_event_id)
        if replay:
            if int(replay["pet_id"]) != int(pet_id) or str(replay["policy_version"]) != POLICY_VERSION:
                raise PetConflict("source_event_id уже привязан к другому дубликату питомца.")
            return _duplicate_response(replay, replay=True)
        source = await repo.find_terminal_duplicate_source(db, int(user_id), source_event_id)
        if not source or int(source["pet_id"]) != int(pet_id):
            raise PetPolicyError("Нет подтверждённого терминального события дубликата питомца.")
        if not await repo.get_owned_pet(db, int(user_id), int(pet_id)):
            raise PetPolicyError("Питомец не найден или принадлежит другому игроку.")
        state = await repo.get_state(db, int(user_id), int(pet_id))
        before = int(state["level"])
        outcome = "level_up" if before < MAX_LEVEL else "max_compensated"
        after = before + 1 if outcome == "level_up" else MAX_LEVEL
        echo_amount = 0 if outcome == "level_up" else 1
        snapshot = {
            "user_id": int(user_id), "pet_id": int(pet_id), "source_event_id": source_event_id,
            "level_before": before, "level_after": after, "level_cap": MAX_LEVEL,
            "outcome": outcome, "echo_amount": echo_amount, "pet_policy_version": POLICY_VERSION,
            "source_kind": str(source["source_kind"]), "source_snapshot": source["source_snapshot"],
        }
        await repo.set_level(db, int(user_id), int(pet_id), after)
        await repo.save_duplicate_progression(
            db, progression_id=uuid4().hex, user_id=int(user_id), source_event_id=source_event_id,
            pet_id=int(pet_id), level_before=before, level_after=after, outcome=outcome,
            echo_amount=echo_amount, policy_version=POLICY_VERSION, source_snapshot=snapshot,
        )
        if outcome == "max_compensated":
            receipt: EchoShardReceipt = await compensate_max_duplicate_in_transaction(
                db, user_id=int(user_id), event=MaxDuplicateCompensation(
                    source_kind="pet_v1_max_duplicate", source_event_id=source_event_id, source_line_id=0,
                    collectible_kind="pet", collectible_id=f"pet:{int(pet_id)}", observed_level=MAX_LEVEL,
                    observed_cap=MAX_LEVEL, amount=1, source_snapshot=snapshot,
                ),
            )
            if receipt.amount != 1:
                raise RuntimeError("Echo Shard policy returned an invalid pet duplicate amount.")
        return {"ok": True, "pet_id": int(pet_id), "outcome": outcome, "level_before": before,
                "level_after": after, "echo_amount": echo_amount, "idempotent_replay": False}

# Display-only flavour for the bestiary sheet.  It states no mechanics: level effects come from core.pets_v1.level_effects.
PET_LORE = {
    "moss_cat": "Спокойный кот, который спит на тёплых камнях у троп. Говорят, он находит дорогу даже в тумане.",
    "stone_beetle": "Жук с панцирем как булыжник. Его редко замечают, пока он не выползет из-под камня.",
    "ash_moth": "Мотылёк летит на остывающие угли и оставляет за собой серую пыльцу.",
    "dusk_hare": "Заяц, которого видно только в сумерках. Быстро исчезает, когда на него смотрят в упор.",
    "rain_finch": "Птичка поёт перед дождём. Путники ждут её голоса, чтобы вовремя найти укрытие.",
    "salt_fox": "Лисица с белёсым мехом идёт по соляным пустошам и выбирает самый безопасный путь.",
    "reed_guardian": "Хозяин камышовых заводей. Не любит шума, но спутников не бросает.",
    "lantern_gecko": "На спине у геккона тёплый огонёк, который светит ночью и не гаснет на ветру.",
    "mirror_owl": "Сова с перьями как зеркала. В её глазах можно увидеть тропу, которую ещё не прошёл.",
    "frost_stag": "Олень с ледяными рогами. Где он ступает, на земле остаётся иней.",
    "void_lynx": "Рысь, пришедшая из тьмы между звёздами. Появляется там, где не ждут.",
    "star_dragon": "Редчайший спутник. Дракон, в чешуе которого застряли осколки упавших звёзд.",
}


async def overview(db, user_id: int) -> dict:
    """Read-only view.  It never creates state or changes endurance on read."""
    profile = await repo.get_profile(db, user_id)
    active = int(profile["active_pet_id"]) if profile and profile.get("active_pet_id") else None
    pets = []
    for pet in await repo.list_owned_pets(db, user_id):
        stored = int(pet["endurance"] if pet["endurance"] is not None else 100)
        current = stored
        if pet["endurance_updated_at"]:
            current, _ = endurance_after_elapsed(stored, last_updated_at=pet["endurance_updated_at"], now=pet["server_now"])
        level = int(pet["level"] if pet["level"] is not None else 1)
        pets.append({"id":int(pet["id"]),"name":pet.get("name") or "Питомец","species_id":pet.get("species_id"),"rarity":pet.get("rarity"),"level":level,"endurance":current,"active":int(pet["id"])==active,"effects":level_effects(level)})
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        await repo.advance_due_runs(db, user_id)
        activity_rewards = await _settle_activity_keys(db, user_id)
        run = await repo.active_run(db, user_id)
    activity = None
    if run:
        activity = {key: (str(value) if key.endswith('_at') and value is not None else value) for key, value in run.items() if key != 'server_now'}
    route_options = await _route_options(db, user_id, activity, pets) if activity else None
    chest_inventory = await chest_repo.inventory_summary(db, user_id=int(user_id))
    food = [{"id": food_id, **FOODS[food_id], "quantity": int(quantity)}
            for food_id, quantity in chest_inventory["foods"].items() if food_id in FOODS and int(quantity) > 0]
    from core.pets_v1 import ACTIVITY_ENDURANCE_COST
    owned_species = {str(pet.get("species_id") or "") for pet in pets}
    bestiary = [
        {"id": species_id, "name": row["name"], "rarity": row["rarity"],
         "icon": row["icon"], "owned": species_id in owned_species,
         "lore": PET_LORE.get(species_id, ""), "info": species_info(species_id)}
        for species_id, row in PET_SPECIES.items()
    ]
    from services.pet_levels_v1 import next_step   # lazy: that module imports PetConflict from here
    level_up = await next_step(db, int(user_id), pets)
    return {"policy_version":POLICY_VERSION,"active_pet_id":active,"pets":pets,
            "level_up": level_up,
            "bestiary": bestiary,
            "bestiary_owned": sum(1 for item in bestiary if item["owned"]),
            "bestiary_total": len(bestiary),
            "route_options": route_options,
            "features": {
                "route_rewards": await route_rewards_enabled(db),
                "level_up": await system_flags.is_enabled(db, "pets_level_up_v1"),
                "trail": await system_flags.is_enabled(db, "pets_v2"),
            },
            "level_milestones": level_milestones(),
            "durations":[3,6,9],"activity":activity,"economy_enabled":True,
            "food": food, "activity_rewards": activity_rewards,
            "activity_costs": ACTIVITY_ENDURANCE_COST,
            "activity_reward_label": "За завершённый поход: 1 ключ, за экспедицию: 2 ключа",
            "activity_key_counts": {"trek": KEY_SOURCE_COUNTS["pet_trek_complete"], "expedition": KEY_SOURCE_COUNTS["pet_expedition_complete"]}}


async def feed_pet(db, *, user_id: int, pet_id: int, food_id: str, action_id: str) -> dict:
    action_id = str(action_id or "").strip()
    if not action_id or len(action_id) > 96:
        raise PetPolicyError("action_id обязателен.")
    if food_id not in FOODS:
        raise PetPolicyError("Неизвестная еда.")
    request = {"type": "feed", "pet_id": int(pet_id), "food_id": str(food_id)}
    async with db.connection.transaction():
        await repo.lock_user(db, int(user_id))
        replay = await repo.cached_action(db, int(user_id), action_id)
        if replay:
            if replay["request"] != request:
                raise PetConflict("action_id уже использован для другого действия.")
            return {**replay["response"], "idempotent_replay": True}
        if not await repo.get_owned_pet(db, int(user_id), int(pet_id)):
            raise PetPolicyError("Питомец не найден или принадлежит другому игроку.")
        try:
            endurance, remaining = await repo.consume_food(
                db, user_id=int(user_id), pet_id=int(pet_id), food_id=food_id,
                restore=int(FOODS[food_id]["restore"]),
            )
        except ValueError as exc:
            raise PetPolicyError(str(exc)) from exc
        response = {"ok": True, "pet_id": int(pet_id), "food_id": food_id,
                    "endurance": endurance, "remaining": remaining, "idempotent_replay": False}
        await repo.save_action(db, int(user_id), action_id, request, response)
        from services import quests_v1 as quests
        from services.vip import is_vip_active
        await quests.record_metric(
            db, user_id=int(user_id), metric="pet_fed", event_id=action_id,
            vip_active=await is_vip_active(db, int(user_id)),
            sources=await quests.available_sources(db, user_id=int(user_id)),
        )
    return response


async def select_active_pet(db, user_id: int, pet_id: int, action_id: str) -> dict:
    action_id=str(action_id or "").strip()
    if not action_id or len(action_id)>96: raise PetPolicyError("action_id обязателен.")
    request={"pet_id":int(pet_id)}
    async with db.connection.transaction():
        await repo.lock_user(db,user_id)
        replay=await repo.cached_action(db,user_id,action_id)
        if replay:
            if replay["request"] != request: raise PetConflict("action_id уже использован для другого действия.")
            return {**replay["response"],"idempotent_replay":True}
        if not await repo.get_owned_pet(db,user_id,pet_id): raise PetPolicyError("Питомец не найден или принадлежит другому игроку.")
        profile=await repo.get_profile(db,user_id)
        current=profile.get("active_pet_id") if profile else None
        endurance=100
        if current is not None:
            state=await repo.get_state(db,user_id,int(current))
            endurance,_=endurance_after_elapsed(int(state["endurance"]),last_updated_at=state["endurance_updated_at"],now=state["server_now"])
            _,endurance=apply_active_slot_swap(current_pet_id=int(current),next_pet_id=int(pet_id),endurance=endurance)
            await repo.save_endurance(db,user_id,int(current),endurance)
        await repo.save_profile(db,user_id,int(pet_id))
        next_state=await repo.get_state(db,user_id,int(pet_id))
        response={"ok":True,"active_pet_id":int(pet_id),"previous_pet_id":current,"previous_pet_endurance":endurance,"level":level_effects(int(next_state["level"]))}
        await repo.save_action(db,user_id,action_id,request,response)
    return response


async def start_activity(db, *, user_id: int, kind: str, hours: int, action_id: str) -> dict:
    kind, hours = validate_activity(kind, hours)
    action_id = str(action_id or "").strip()
    if not action_id or len(action_id) > 96:
        raise PetPolicyError("action_id обязателен.")
    request = {"type": "start_activity", "kind": kind, "hours": hours}
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        replay = await repo.cached_action(db, user_id, action_id)
        if replay:
            if replay["request"] != request:
                raise PetConflict("action_id уже использован для другого действия.")
            return {**replay["response"], "idempotent_replay": True}
        # Cached classic clients must not create a second reward path beside
        # the Trail. Old retries and settlement remain available after rollout.
        if await system_flags.is_enabled(db, "pets_v2"):
            raise PetConflict("Новые занятия доступны в Тропе. Обновите приложение и откройте Питомцев.")
        await repo.advance_due_runs(db, user_id)
        current = await repo.active_run(db, user_id)
        if current:
            raise PetConflict("Сначала заверши текущий поход или экспедицию.")
        profile = await repo.get_profile(db, user_id)
        pet_id = int(profile.get("active_pet_id") or 0) if profile else 0
        if not pet_id or not await repo.get_owned_pet(db, user_id, pet_id):
            raise PetPolicyError("Сначала выбери активного питомца.")
        state = await repo.get_state(db, int(user_id), pet_id)
        current_endurance, _ = endurance_after_elapsed(
            int(state["endurance"]), last_updated_at=state["endurance_updated_at"], now=state["server_now"],
        )
        remaining_endurance, endurance_cost = spend_activity_endurance(
            endurance=current_endurance, hours=hours,
        )
        await repo.save_endurance(db, int(user_id), pet_id, remaining_endurance)
        run = await repo.create_run(db, run_id=uuid4().hex, user_id=user_id, pet_id=pet_id, kind=kind, hours=hours)
        response = {
            "ok": True, "endurance_cost": endurance_cost, "endurance": remaining_endurance,
            "activity": {key: (str(value) if key.endswith('_at') and value is not None else value) for key, value in run.items() if key != 'server_now'},
        }
        await repo.save_action(db, user_id, action_id, request, response)
    return response


async def _route_options(db, user_id: int, activity: dict, pets: list[dict]) -> dict | None:
    """Routes of a ready expedition. Exact odds are shown only to pets with a hint charge (L4+)."""
    if activity.get("kind") != "expedition" or activity.get("status") != "ready" or activity.get("decision"):
        return None
    from core.pet_routes_v1 import ROUTES, WEEKLY_CAP_MORA, route_available, route_odds
    pet = next((item for item in pets if int(item["id"]) == int(activity["pet_id"])), None)
    if not pet or not await route_rewards_enabled(db):
        return {"rewards_enabled": False, "routes": []}
    effects, level = pet["effects"], int(pet["level"])
    hint = int(effects.get("expedition_hint_charges", 0)) > 0
    remaining = max(0, WEEKLY_CAP_MORA - await repo.route_paid_this_week(db, int(user_id)))
    routes = []
    for route in ROUTES:
        if not route_available(route, level):
            continue
        odds = route_odds(route, int(activity["duration_hours"]), effects)
        item = {"id": route}
        if hint:
            item.update(chance_percent=odds.chance_percent, reward_mora=min(odds.reward_mora, remaining))
        routes.append(item)
    return {"rewards_enabled": True, "hint": hint, "routes": routes,
            "weekly_remaining_mora": remaining, "weekly_cap_mora": WEEKLY_CAP_MORA}


async def route_rewards_enabled(db) -> bool:
    from core.pet_routes_v1 import FLAG
    return await system_flags.is_enabled(db, FLAG)


async def _settle_route(db, *, user_id: int, run: dict, decision: str) -> dict | None:
    """Server-side roll of the chosen route; Mora is paid once per run. None while the flag is off."""
    from core.pet_routes_v1 import (
        POLICY_VERSION as ROUTE_POLICY, REASON_CODE as ROUTE_REASON, SCOUT_MIN_LEVEL, payout_after_cap,
        roll_success, route_odds, WEEKLY_CAP_MORA,
    )
    state = await repo.get_state(db, int(user_id), int(run["pet_id"]))
    level = int(state["level"])
    effects = level_effects(level)
    enabled = await route_rewards_enabled(db)
    if decision == "scout" and not enabled:
        raise PetPolicyError("Этот маршрут пока недоступен.")   # raising rolls back the route choice
    if decision == "scout" and level < SCOUT_MIN_LEVEL:
        raise PetPolicyError(f"Разведка доступна с {SCOUT_MIN_LEVEL} уровня питомца.")
    if not enabled:
        return None
    hours = int(run["duration_hours"])
    odds = route_odds(decision, hours, effects)
    success = roll_success(odds, secrets.randbelow)
    paid = 0
    operation_id = None
    if success:
        paid = payout_after_cap(odds.reward_mora, await repo.route_paid_this_week(db, int(user_id)))
        if paid:
            mutation = await economy_ledger.apply_balance_change(
                db, int(user_id), {"mora": paid}, reason_code=ROUTE_REASON,
                idempotency_key=f"pet-route:{run['id']}", source_type="pets_v1",
                reference_type="pet_route", reference_id=str(run["id"]),
                metadata={"policy_version": ROUTE_POLICY, "route": decision, "hours": hours,
                          "chance_percent": odds.chance_percent, "reward_mora": odds.reward_mora},
                note="Маршрут экспедиции",
            )
            operation_id = str(mutation.operation_id)
    await repo.save_route_reward(
        db, run_id=str(run["id"]), user_id=int(user_id), route=decision, hours=hours,
        chance_percent=odds.chance_percent, success=success, reward_mora=odds.reward_mora,
        paid_mora=paid, economy_operation_id=operation_id, policy_version=ROUTE_POLICY,
    )
    return {"route": decision, "chance_percent": odds.chance_percent, "success": success,
            "reward_mora": odds.reward_mora, "paid_mora": paid,
            "capped": bool(success and paid < odds.reward_mora), "weekly_cap_mora": WEEKLY_CAP_MORA}


async def choose_expedition(db, *, user_id: int, decision: str, action_id: str) -> dict:
    decision = validate_expedition_decision(decision)
    action_id = str(action_id or "").strip()
    if not action_id or len(action_id) > 96:
        raise PetPolicyError("action_id обязателен.")
    request = {"type": "choose_expedition", "decision": decision}
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        replay = await repo.cached_action(db, user_id, action_id)
        if replay:
            if replay["request"] != request:
                raise PetConflict("action_id уже использован для другого действия.")
            return {**replay["response"], "idempotent_replay": True}
        await repo.advance_due_runs(db, user_id)
        run = await repo.choose_expedition(db, user_id=user_id, choice=decision)
        if not run:
            raise PetConflict("Нет готовой экспедиции для этого выбора.")
        route = await _settle_route(db, user_id=user_id, run=run, decision=decision)
        rewards = await _settle_activity_keys(db, user_id)
        response = {
            "ok": True,
            "completed_without_reward": False,
            "route": route,
            "amount_keys": sum(int(item["amount_keys"]) for item in rewards),
            "activity": {
                key: (str(value) if key.endswith('_at') and value is not None else value)
                for key, value in run.items() if key != 'server_now'
            },
        }
        await repo.save_action(db, user_id, action_id, request, response)
    return response
