"""Idempotent writer for pets v2 «Тропа»: старт и возврат занятий, Следы, находки, ступени.

Все числа — из core/pets_v2.py. Время и дни считает база (UTC), броски делает сервер.
"""
from __future__ import annotations

import json
import random
from math import floor
from uuid import uuid4

from core import pets_v2 as rules
from core.pets_v2 import PetV2PolicyError
from infrastructure.repositories import pets_v2 as repo


class PetV2Conflict(PetV2PolicyError):
    pass


_FOOD_BY_LEVEL = ((20, "food_stew"), (10, "food_fried"), (1, "food_basic"))
_FIND_AMOUNT = {"mora": (3, 9), "essence": (2, 4)}
_HINT_PATHS = tuple(rules.PATHS)


def _action(action_id: str) -> str:
    action_id = str(action_id or "").strip()
    if not action_id or len(action_id) > 96:
        raise PetV2PolicyError("action_id обязателен.")
    return action_id


def _species_row(pet: dict) -> tuple:
    species = str(pet.get("species_id") or "")
    if species not in rules.SPECIES:
        raise PetV2PolicyError("Этот питомец пока не участвует в Тропе.")
    return rules.SPECIES[species]


def _json_list(value) -> list:
    if isinstance(value, str):
        value = json.loads(value)
    return list(value or [])


def _build(state: dict, talismans: list[dict]) -> dict:
    return {"calling": state.get("calling"), "traits": tuple(_json_list(state.get("traits"))),
            "talismans": tuple((t["kind"], int(t["tier"])) for t in talismans)}


def _fx(build: dict, hours: int = 3, route: str | None = None) -> dict:
    return rules.build_effects(build["calling"], build["traits"], build["talismans"], hours=hours, route=route)


def _rest(state: dict, pet: dict, now, build: dict) -> float:
    hours = max(0.0, (now - state["energy_at"]).total_seconds() / 3600)
    fx = _fx(build)
    return rules.energy_after_rest(float(state["energy"]), hours=hours, level=int(state["level"]), species_id=pet["species_id"],
                                   bonus=fx["energy_bonus"], delta=fx["regen_delta"])


def _terrain(pet: dict, route: str | None) -> bool:
    favorite = _species_row(pet)[1]
    return bool(route) and favorite in (route, "any")


def _chances(pet: dict, state: dict, run: dict, energy: float, build: dict) -> dict[str, float]:
    fx = _fx(build, int(run["hours"]), run["route"])
    resilience = rules.resilience(
        int(state["level"]), min(energy, rules.energy_max(int(state["level"]), pet["species_id"], fx["energy_bonus"])), pet["species_id"],
        terrain_match=_terrain(pet, run["route"]), guardian=fx["guardian"], energy_bonus=fx["energy_bonus"], extra=fx["resilience_extra"],
    )
    difficulty = rules.event_difficulty(int(run["hours"]))
    return {path: rules.path_chance(resilience, difficulty, path, pity=int(state["pity"]), bonus=fx["chance_bonus"][path]) for path in _HINT_PATHS}


def _hints(level: int, species_id: str, chances: dict[str, float]) -> dict:
    detail = rules.hint_detail(level, species_id)
    out = {}
    for path, chance in chances.items():
        item = {"sign": rules.chance_sign(chance)}
        if detail == "range":
            item["range"] = list(rules.chance_range(chance))
        elif detail == "exact":
            item["chance"] = round(chance, 1)
        out[path] = item
    return {"detail": detail, "paths": out}


def _roll_count(base: int, mult: float, rng) -> int:
    value = base * mult
    whole = floor(value)
    return whole + (1 if rng.random() < value - whole else 0)


async def overview(db, user_id: int) -> dict:
    """Только чтение: ничего не создаёт и не меняет."""
    clock = await repo.clock(db)
    daily = await repo.get_daily(db, user_id, clock["day"])
    runs = await repo.open_runs(db, user_id)
    by_pet = {int(run["pet_id"]): run for run in runs}
    pets = []
    owned = await repo.list_owned_pets(db, user_id)
    all_talismans = await repo.list_talismans(db, user_id)
    builds: dict[int, dict] = {}
    for pet in owned:
        if pet.get("species_id") not in rules.SPECIES:
            continue
        level = int(pet["level"] or 1)
        mine = [t for t in all_talismans if t["pet_id"] is not None and int(t["pet_id"]) == int(pet["id"])]
        build = builds[int(pet["id"])] = _build(pet, mine)
        fx = _fx(build)
        energy_cap = rules.energy_max(level, pet["species_id"], fx["energy_bonus"])
        energy = float(pet["energy"]) if pet["energy"] is not None else float(rules.energy_max(1, pet["species_id"]))
        if pet["energy_at"] is not None:
            energy = _rest({"energy": energy, "energy_at": pet["energy_at"], "level": level}, pet, clock["now"], build)
        bond = await repo.bond_days(db, user_id, int(pet["id"]))
        item = {
            "id": int(pet["id"]), "name": pet.get("name"), "species_id": pet["species_id"], "rarity": pet["rarity"],
            "level": level, "xp": round(float(pet["xp"] or 0), 1),
            "next_cost": rules.level_cost(level, pet["rarity"]) if level < rules.MAX_LEVEL else None,
            "ceiling": rules.ceiling(bond), "bond_days": bond,
            "energy": round(energy, 1), "energy_max": energy_cap,
            "resilience": round(rules.resilience(level, min(energy, energy_cap), pet["species_id"], guardian=fx["guardian"],
                                                 energy_bonus=fx["energy_bonus"], extra=fx["resilience_extra"]), 1),
            "favorite_route": _species_row(pet)[1], "run_id": None,
            "calling": build["calling"], "traits": list(build["traits"]), "trait_slots": rules.trait_slots(level),
            "talismans": [t["id"] for t in mine],
        }
        run = by_pet.get(int(pet["id"]))
        if run:
            item["run_id"] = run["id"]
        pets.append(item)
    activities = []
    for run in runs:
        entry = {"id": run["id"], "pet_id": int(run["pet_id"]), "kind": run["kind"], "hours": int(run["hours"]),
                 "route": run["route"], "ends_at": str(run["ends_at"]), "ready": bool(run["ready"])}
        if run["kind"] == "expedition" and run["ready"]:
            pet = next((p for p in owned if int(p["id"]) == int(run["pet_id"])), None)
            if pet and pet["level"] is not None:
                build = builds[int(pet["id"])]
                state = {"level": pet["level"], "energy": pet["energy"], "energy_at": pet["energy_at"], "pity": pet["pity"]}
                energy = _rest(state, pet, clock["now"], build)
                entry["decision"] = _hints(int(pet["level"]), pet["species_id"], _chances(pet, state, run, energy, build))
        activities.append(entry)
    return {
        "policy_version": rules.POLICY_VERSION, "slots": rules.SLOTS, "pets": pets, "activities": activities,
        "daily": {"raw": round(daily["raw"], 1), "credited": round(daily["credited"], 1), "max": rules.DAILY_MAX},
        "durations": {"run": list(rules.RUN_HOURS), "watch": list(rules.WATCH_HOURS)}, "routes": list(rules.ROUTES),
        "talismans": [{"id": t["id"], "kind": t["kind"], "tier": int(t["tier"]), "pet_id": t["pet_id"]} for t in all_talismans],
        "callings": list(rules.AVAILABLE_CALLINGS), "traits": list(rules.AVAILABLE_TRAITS),
    }


async def start_run(db, *, user_id: int, pet_id: int, kind: str, hours: int, route: str | None, action_id: str) -> dict:
    action_id = _action(action_id)
    hours = int(hours)
    if kind in ("trek", "expedition"):
        if hours not in rules.RUN_HOURS or route not in rules.ROUTES:
            raise PetV2PolicyError("Поход и экспедиция: 3, 6 или 9 часов и один из маршрутов.")
        energy_kind = "run"
    elif kind == "watch":
        if hours not in rules.WATCH_HOURS:
            raise PetV2PolicyError("Дозор: 12 или 24 часа.")
        route, energy_kind = None, "watch"
    else:
        raise PetV2PolicyError("Неизвестное занятие.")
    request = {"type": "start", "pet_id": int(pet_id), "kind": kind, "hours": hours, "route": route}
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        replay = await repo.cached_action(db, user_id, action_id)
        if replay:
            if replay["request"] != request:
                raise PetV2Conflict("action_id уже использован для другого действия.")
            return {**replay["response"], "idempotent_replay": True}
        pet = await repo.get_owned_pet(db, user_id, pet_id)
        if not pet:
            raise PetV2PolicyError("Питомец не найден или принадлежит другому игроку.")
        _species_row(pet)
        runs = await repo.open_runs(db, user_id)
        if any(int(run["pet_id"]) == int(pet_id) for run in runs):
            raise PetV2Conflict("Этот питомец уже занят.")
        if len(runs) >= rules.SLOTS:
            raise PetV2Conflict("Все слоты заняты.")
        clock = await repo.clock(db)
        state = await repo.ensure_state(db, user_id, pet_id, rules.energy_max(1, pet["species_id"]))
        build = _build(state, await repo.equipped_talismans(db, user_id, pet_id))
        energy = rules.spend_energy(_rest(state, pet, clock["now"], build), energy_kind, hours)
        await repo.save_state(db, user_id, pet_id, level=int(state["level"]), xp=float(state["xp"]), energy=energy, pity=int(state["pity"]))
        run = await repo.create_run(db, run_id=uuid4().hex, user_id=user_id, pet_id=pet_id, kind=kind, hours=hours, route=route)
        response = {"ok": True, "run_id": run["id"], "ends_at": str(run["ends_at"]), "energy": round(energy, 1), "idempotent_replay": False}
        await repo.save_action(db, user_id, action_id, request, response)
    return response


async def _grant_find(db, user_id: int, run_id: str, category: str, amount: int, level: int, rng) -> None:
    if category == "talisman":
        for i in range(amount):
            await repo.add_talisman(db, user_id, f"{run_id}:{i}", rng.choice(sorted(rules.TALISMANS)), 1)
    elif category == "mora":
        await _ledger(db, user_id, {"mora": amount}, run_id, "mora")
    elif category == "diamond":
        await _ledger(db, user_id, {"diamonds": amount}, run_id, "diamond")
    elif category == "essence":
        from services.skins_v3 import grant_essence_in_transaction
        await grant_essence_in_transaction(db, user_id, amount, reason="pet_v2_find", reference=run_id)
    elif category == "treat":
        food = next(food_id for need, food_id in _FOOD_BY_LEVEL if level >= need)
        await repo.add_food(db, user_id, food, amount)


async def _ledger(db, user_id: int, deltas: dict, run_id: str, label: str) -> None:
    from infrastructure.repositories.economy_ledger import apply_balance_change
    await apply_balance_change(
        db, user_id, deltas, reason_code="pet_find", idempotency_key=f"pet_v2:{run_id}:{label}",
        source_type="pets", reference_type="pet_v2_run", reference_id=run_id,
    )


async def claim_run(db, *, user_id: int, run_id: str, action_id: str, path: str | None = None, rng=None) -> dict:
    action_id = _action(action_id)
    rng = rng or random.SystemRandom()
    request = {"type": "claim", "run_id": str(run_id), "path": path}
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        replay = await repo.cached_action(db, user_id, action_id)
        if replay:
            if replay["request"] != request:
                raise PetV2Conflict("action_id уже использован для другого действия.")
            return {**replay["response"], "idempotent_replay": True}
        run = await repo.get_run(db, user_id, run_id)
        if not run or run["status"] != "active":
            raise PetV2Conflict("Занятие не найдено или уже завершено.")
        if not run["ready"]:
            raise PetV2Conflict("Питомец ещё в пути.")
        expedition = run["kind"] == "expedition"
        if expedition and path not in rules.PATHS:
            raise PetV2PolicyError("Выбери осторожный, ровный или рискованный путь.")
        pet = await repo.get_owned_pet(db, user_id, int(run["pet_id"]))
        if not pet:
            raise PetV2PolicyError("Питомец не найден.")
        rarity, favorite, _, _, _ = _species_row(pet)
        clock = await repo.clock(db)
        day = clock["day"]
        state = await repo.ensure_state(db, user_id, int(pet["id"]), rules.energy_max(1, pet["species_id"]))
        build = _build(state, await repo.equipped_talismans(db, user_id, int(pet["id"])))
        fx = _fx(build, int(run["hours"]), run["route"])
        energy = _rest(state, pet, clock["now"], build)
        level, xp, pity = int(state["level"]), float(state["xp"]), int(state["pity"])

        outcome, mult, chance, energy_loss = "success", 1.0, None, 0
        if expedition:
            chance = _chances(pet, state, run, energy, build)[path]
            outcome = rules.decide_outcome(chance, rng.random() * 100)
            mult = rules.outcome_reward_mult(path, outcome, guardian=fx["guardian"]) * fx["reward_mult"][path]
            pity = min(3, rules.next_pity(pity, chance, outcome))
            if outcome == "fail":
                energy_loss = rules.PATHS[path][2]
            energy = max(0.0, energy - energy_loss)

        await repo.add_bond_day(db, user_id, int(pet["id"]), day)
        bond = await repo.bond_days(db, user_id, int(pet["id"]))
        stars = rules.seal_stars(await repo.species_bond_days(db, user_id, pet["species_id"]))
        match = _terrain(pet, run["route"])
        hours = int(run["hours"])
        if run["kind"] == "watch":
            base = rules.watch_xp_raw(hours) * fx["xp_mult"]
            rolls = rules.ROLLS[("watch", hours)]
        else:
            base = rules.run_xp_raw(
                hours, expedition=expedition, favorite_route=match, stars=stars, trait_mult=fx["xp_mult"],
                repeats_today=await repo.routes_claimed_today(db, user_id, day, run["route"]),
            )
            rolls = rules.ROLLS[("run", hours)]
        base *= mult

        daily = await repo.get_daily(db, user_id, day)
        finds = dict(daily["finds"])
        shares = rules.find_shares(fx["find_mods"], species_id=pet["species_id"], level=level)
        categories, weights = list(shares), list(shares.values())
        granted: dict[str, int] = {}
        bonus_raw = 0.0
        for _ in range(_roll_count(rolls, mult if expedition else 1.0, rng)):
            category = rng.choices(categories, weights)[0]
            if category == "bonus_xp":
                bonus_raw += base * 0.05
                continue
            lo, hi = _FIND_AMOUNT.get(category, (1, 1))
            amount = rng.randint(lo, hi)
            allowed = floor(rules.cap_find(
                category, amount, today=float(finds.get(category, 0)),
                this_week=await repo.week_find_total(db, user_id, day, category) if category in rules.FIND_WEEKLY_CAP else 0.0,
            ))
            if category in rules.FIND_DAILY_CAP and allowed <= 0:
                continue
            if category in ("mora", "diamond", "essence"):
                finds[category] = float(finds.get(category, 0)) + allowed
            granted[category] = granted.get(category, 0) + allowed
        for category, amount in granted.items():
            await _grant_find(db, user_id, run["id"], category, amount, level, rng)

        raw = base + bonus_raw
        credited = rules.pool_credit(daily["raw"], raw)
        await repo.save_daily(db, user_id, day, raw=daily["raw"] + raw, credited=daily["credited"] + credited, finds=finds)

        level_before = level
        xp += credited
        stage_essence = 0
        limit = rules.ceiling(bond)
        while level < min(limit, rules.MAX_LEVEL) and xp >= rules.level_cost(level, rarity):
            xp -= rules.level_cost(level, rarity)
            if level in rules.STAGE_ESSENCE and await repo.save_stage_reward(db, user_id, int(pet["id"]), level, rules.STAGE_ESSENCE[level]):
                from services.skins_v3 import grant_essence_in_transaction
                stage_essence += await grant_essence_in_transaction(
                    db, user_id, rules.STAGE_ESSENCE[level], reason="pet_v2_stage", reference=f"{pet['id']}:{level}",
                )
            level += 1
        if level >= rules.MAX_LEVEL:
            xp = 0.0
        elif level >= limit:
            xp = min(xp, float(rules.level_cost(level, rarity)))
        await repo.save_state(db, user_id, int(pet["id"]), level=level, xp=xp, energy=energy, pity=pity)

        result = {
            "ok": True, "run_id": run["id"], "kind": run["kind"], "outcome": outcome, "path": path,
            "chance": round(chance, 1) if chance is not None else None, "reward_mult": mult,
            "xp_raw": round(raw, 2), "xp_credited": round(credited, 2), "daily_credited": round(daily["credited"] + credited, 1),
            "level_before": level_before, "level_after": level, "ceiling": limit, "bond_days": bond,
            "energy": round(energy, 1), "energy_loss": energy_loss, "finds": granted, "stage_essence": stage_essence,
            "idempotent_replay": False,
        }
        await repo.finish_run(db, run["id"], result)
        await repo.save_action(db, user_id, action_id, request, result)
        await _record_progress(db, user_id, run)
    return result


async def _record_progress(db, user_id: int, run: dict) -> None:
    """Квесты и достижения не должны блокировать награду: сбой откатывается в savepoint и логируется."""
    try:
        async with db.connection.transaction():
            await _record_progress_inner(db, user_id, run)
    except Exception as exc:  # noqa: BLE001 — прогресс квестов вторичен
        from loguru import logger
        logger.warning("pets_v2: прогресс квестов пропущен для {}: {}", run["id"], exc)


async def _record_progress_inner(db, user_id: int, run: dict) -> None:
    from services import quests_v1 as quests
    from services import achievements_v1 as achievements
    from services.vip import is_vip_active
    await quests.record_metric(
        db, user_id=int(user_id), metric="pet_activity_completed", event_id=str(run["id"]),
        vip_active=await is_vip_active(db, int(user_id)),
        sources=await quests.available_sources(db, user_id=int(user_id)),
    )
    await achievements.record_terminal(
        db, user_id=int(user_id), metric="pet_activity_completed", source_event_id=str(run["id"]),
        source_snapshot={"run_id": str(run["id"]), "activity_kind": run["kind"],
                         "duration_hours": int(run["hours"]), "pet_id": int(run["pet_id"])},
    )


def _week_start(day):
    from datetime import timedelta
    return day - timedelta(days=day.weekday())


async def set_build(db, *, user_id: int, pet_id: int, calling: str | None, traits: list[str], talisman_ids: list[str], action_id: str) -> dict:
    """Собрать билд: призвание (с 10 ур.), черты (слоты с 5/15/25 ур.), до 2 талисманов.

    Пустой слот заполняется бесплатно. Замена призвания или черты бесплатна раз в неделю, дальше — Эссенция.
    """
    action_id = _action(action_id)
    traits, talisman_ids = [str(t) for t in traits], [str(t) for t in talisman_ids]
    request = {"type": "build", "pet_id": int(pet_id), "calling": calling, "traits": sorted(traits), "talismans": sorted(talisman_ids)}
    if len(set(traits)) != len(traits) or len(set(talisman_ids)) != len(talisman_ids):
        raise PetV2PolicyError("Повторы в сборке не допускаются.")
    if any(t not in rules.AVAILABLE_TRAITS for t in traits):
        raise PetV2PolicyError("Эта черта пока недоступна.")
    if calling is not None and calling not in rules.AVAILABLE_CALLINGS:
        raise PetV2PolicyError("Это призвание пока недоступно.")
    if len(talisman_ids) > rules.TALISMAN_SLOTS:
        raise PetV2PolicyError(f"Талисманов не больше {rules.TALISMAN_SLOTS}.")
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        replay = await repo.cached_action(db, user_id, action_id)
        if replay:
            if replay["request"] != request:
                raise PetV2Conflict("action_id уже использован для другого действия.")
            return {**replay["response"], "idempotent_replay": True}
        pet = await repo.get_owned_pet(db, user_id, pet_id)
        if not pet:
            raise PetV2PolicyError("Питомец не найден или принадлежит другому игроку.")
        _species_row(pet)
        if any(int(r["pet_id"]) == int(pet_id) for r in await repo.open_runs(db, user_id)):
            raise PetV2Conflict("Пока питомец в пути, сборку менять нельзя.")
        state = await repo.ensure_state(db, user_id, pet_id, rules.energy_max(1, pet["species_id"]))
        level = int(state["level"])
        if calling and level < rules.CALLING_MIN_LEVEL:
            raise PetV2PolicyError(f"Призвание открывается с {rules.CALLING_MIN_LEVEL} уровня.")
        if len(traits) > rules.trait_slots(level):
            raise PetV2PolicyError("Не хватает слотов черт.")
        owned = {t["id"]: t for t in await repo.list_talismans(db, user_id)}
        for talisman_id in talisman_ids:
            row = owned.get(talisman_id)
            if not row:
                raise PetV2PolicyError("Талисман не найден.")
        week = _week_start((await repo.clock(db))["day"])
        old_calling, old_traits = state["calling"], _json_list(state["traits"])
        calling_at, traits_at = state["calling_changed_at"], state["traits_changed_at"]
        cost = 0
        if old_calling and calling != old_calling:
            if calling_at == week:
                cost += rules.CALLING_SWAP_ESSENCE
            calling_at = week
        elif calling and not old_calling:
            calling_at = calling_at or None
        removed = [t for t in old_traits if t not in traits]
        if removed:
            if traits_at == week:
                cost += rules.TRAIT_SWAP_ESSENCE * len(removed)
            traits_at = week
        if cost:
            from infrastructure.repositories import skins_v3 as essence_repo
            try:
                await essence_repo.essence_apply(
                    db, user_id, -cost, reason="pet_v2_build", reference=f"{pet_id}", idempotency_key=f"pet_v2:build:{user_id}:{action_id}",
                )
            except ValueError as exc:
                raise PetV2PolicyError(f"Не хватает Эссенции: нужно {cost}.") from exc
        await repo.save_build(db, user_id, pet_id, calling=calling, traits=traits, calling_changed=calling_at, traits_changed=traits_at)
        await repo.set_talismans(db, user_id, pet_id, talisman_ids)
        response = {"ok": True, "pet_id": int(pet_id), "calling": calling, "traits": traits, "talismans": talisman_ids,
                    "essence_spent": cost, "idempotent_replay": False}
        await repo.save_action(db, user_id, action_id, request, response)
    return response
