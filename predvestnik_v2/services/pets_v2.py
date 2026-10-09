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


def _build(state: dict, talismans: list[dict], camp: dict | None = None) -> dict:
    return {"camp": camp or {}, "calling": state.get("calling"), "traits": tuple(_json_list(state.get("traits"))),
            "talismans": tuple((t["kind"], int(t["tier"])) for t in talismans)}


def _fx(build: dict, hours: int = 3, route: str | None = None) -> dict:
    return rules.build_effects(build["calling"], build["traits"], build["talismans"], hours=hours, route=route)


def _rest(state: dict, pet: dict, now, build: dict) -> float:
    hours = max(0.0, (now - state["energy_at"]).total_seconds() / 3600)
    fx = _fx(build)
    return rules.energy_after_rest(float(state["energy"]), hours=hours, level=int(state["level"]), species_id=pet["species_id"],
                                   camp_bonus=rules.camp_bonus("lounge", build["camp"].get("lounge", 0)), bonus=fx["energy_bonus"], delta=fx["regen_delta"])


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
    camp = await repo.camp_levels(db, user_id)
    builds: dict[int, dict] = {}
    for pet in owned:
        if pet.get("species_id") not in rules.SPECIES:
            continue
        level = int(pet["level"] or 1)
        mine = [t for t in all_talismans if t["pet_id"] is not None and int(t["pet_id"]) == int(pet["id"])]
        build = builds[int(pet["id"])] = _build(pet, mine, camp)
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
        run = by_pet.get(int(pet["id"])) or next((r for r in runs if r["companion_id"] is not None and int(r["companion_id"]) == int(pet["id"])), None)
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
        "camp": await _camp_view(db, user_id, camp),
        "trial": await trial_view(db, user_id),
        "callings": list(rules.AVAILABLE_CALLINGS), "traits": list(rules.AVAILABLE_TRAITS),
    }


async def start_run(db, *, user_id: int, pet_id: int, kind: str, hours: int, route: str | None, action_id: str,
                    companion_id: int | None = None) -> dict:
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
    request = {"type": "start", "pet_id": int(pet_id), "kind": kind, "hours": hours, "route": route, "companion_id": companion_id}
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
        busy = {int(r["pet_id"]) for r in runs} | {int(r["companion_id"]) for r in runs if r["companion_id"] is not None}
        if int(pet_id) in busy:
            raise PetV2Conflict("Этот питомец уже занят.")
        if len(runs) >= rules.SLOTS:
            raise PetV2Conflict("Все слоты заняты.")
        clock = await repo.clock(db)
        state = await repo.ensure_state(db, user_id, pet_id, rules.energy_max(1, pet["species_id"]))
        build = _build(state, await repo.equipped_talismans(db, user_id, pet_id), await repo.camp_levels(db, user_id))
        energy = rules.spend_energy(_rest(state, pet, clock["now"], build), energy_kind, hours)
        await repo.save_state(db, user_id, pet_id, level=int(state["level"]), xp=float(state["xp"]), energy=energy, pity=int(state["pity"]))
        if companion_id is not None:
            if kind == "watch":
                raise PetV2PolicyError("Спутник идёт только в поход или экспедицию.")
            if int(companion_id) == int(pet_id) or int(companion_id) in busy:
                raise PetV2Conflict("Спутник недоступен.")
            if await repo.species_count(db, user_id) < rules.PAIR_MIN_SPECIES:
                raise PetV2PolicyError(f"Пара открывается при {rules.PAIR_MIN_SPECIES} разных видах.")
            companion = await repo.get_owned_pet(db, user_id, companion_id)
            if not companion:
                raise PetV2PolicyError("Спутник не найден или принадлежит другому игроку.")
            _species_row(companion)
            c_state = await repo.ensure_state(db, user_id, companion_id, rules.energy_max(1, companion["species_id"]))
            c_build = _build(c_state, await repo.equipped_talismans(db, user_id, companion_id), await repo.camp_levels(db, user_id))
            c_energy = _rest(c_state, companion, clock["now"], c_build)
            if c_energy < rules.PAIR_ENERGY:
                raise PetV2PolicyError(f"Спутнику нужно {rules.PAIR_ENERGY} энергии.")
            await repo.save_state(db, user_id, companion_id, level=int(c_state["level"]), xp=float(c_state["xp"]),
                                  energy=c_energy - rules.PAIR_ENERGY, pity=int(c_state["pity"]))
        run = await repo.create_run(db, run_id=uuid4().hex, user_id=user_id, pet_id=pet_id, kind=kind, hours=hours, route=route,
                                    companion_id=int(companion_id) if companion_id is not None else None)
        response = {"ok": True, "run_id": run["id"], "ends_at": str(run["ends_at"]), "energy": round(energy, 1), "idempotent_replay": False}
        await repo.save_action(db, user_id, action_id, request, response)
    return response


async def _roll_finds(db, user_id: int, day, source_id: str, count: int, *, pet: dict, level: int, mods: dict,
                      rng, finds: dict, base_xp: float = 0.0, with_bonus_xp: bool = True) -> tuple[dict, float]:
    """Броски находок с суточными и недельными потолками; `finds` обновляется на месте, награды выдаются здесь."""
    shares = rules.find_shares(mods, species_id=pet["species_id"], level=level)
    if not with_bonus_xp:
        shares = {k: v for k, v in shares.items() if k != "bonus_xp"}
    categories, weights = list(shares), list(shares.values())
    granted: dict[str, int] = {}
    bonus_raw = 0.0
    for _ in range(count):
        category = rng.choices(categories, weights)[0]
        if category == "bonus_xp":
            bonus_raw += base_xp * 0.05
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
        await _grant_find(db, user_id, source_id, category, amount, level, rng)
    return granted, bonus_raw


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


async def _ledger(db, user_id: int, deltas: dict, run_id: str, label: str, reason: str = "pet_find") -> None:
    from infrastructure.repositories.economy_ledger import apply_balance_change
    await apply_balance_change(
        db, user_id, deltas, reason_code=reason, idempotency_key=f"pet_v2:{run_id}:{label}",
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
        camp = await repo.camp_levels(db, user_id)
        build = _build(state, await repo.equipped_talismans(db, user_id, int(pet["id"])), camp)
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
                repeat_decay=rules.markers_decay(camp["markers"]),
                repeats_today=await repo.routes_claimed_today(db, user_id, day, run["route"]),
            )
            rolls = rules.ROLLS[("run", hours)]
        base *= mult

        daily = await repo.get_daily(db, user_id, day)
        finds = dict(daily["finds"])
        find_mods = dict(fx["find_mods"])
        companion = None
        if run["companion_id"] is not None:
            companion = await repo.get_owned_pet(db, user_id, int(run["companion_id"]))
            if companion and companion["species_id"] in rules.SPECIES:
                for key, value in rules.companion_find_mod(companion["species_id"]).items():
                    find_mods[key] = find_mods.get(key, 1.0) * value
            else:
                companion = None
        granted, bonus_raw = await _roll_finds(
            db, user_id, day, run["id"], _roll_count(rolls, mult if expedition else 1.0, rng),
            pet=pet, level=level, mods=find_mods, rng=rng, finds=finds, base_xp=base,
        )

        key_granted = 0
        if run["kind"] != "watch" and not finds.get("key"):
            try:
                async with db.connection.transaction():
                    key_granted = 1 if await _grant_key(db, user_id, run) else 0
            except Exception as exc:  # noqa: BLE001 — сундуки не должны блокировать награду
                from loguru import logger
                logger.warning("pets_v2: ключ не выдан для {}: {}", run["id"], exc)
            if key_granted:
                finds["key"] = 1.0

        raw = base + bonus_raw
        share = 1 + rules.PAIR_COMPANION_SHARE if companion else 1.0
        total_credit = rules.pool_credit(daily["raw"], raw * share)   # доля Спутника тоже идёт через суточную норму
        credited = total_credit / share
        raw *= share
        await repo.save_daily(db, user_id, day, raw=daily["raw"] + raw, credited=daily["credited"] + total_credit, finds=finds)

        level_before = level
        level, xp, stage_essence, limit = await _apply_xp(db, user_id, int(pet["id"]), rarity, level, xp + credited, bond)
        await repo.save_state(db, user_id, int(pet["id"]), level=level, xp=xp, energy=energy, pity=pity)
        if companion:
            c_state = await repo.ensure_state(db, user_id, int(companion["id"]), rules.energy_max(1, companion["species_id"]))
            c_bond = await repo.bond_days(db, user_id, int(companion["id"]))
            c_level, c_xp, _, _ = await _apply_xp(db, user_id, int(companion["id"]), _species_row(companion)[0],
                                                  int(c_state["level"]), float(c_state["xp"]) + credited * rules.PAIR_COMPANION_SHARE, c_bond)
            await repo.save_state(db, user_id, int(companion["id"]), level=c_level, xp=c_xp, energy=float(c_state["energy"]), pity=int(c_state["pity"]))

        result = {
            "ok": True, "run_id": run["id"], "kind": run["kind"], "outcome": outcome, "path": path,
            "chance": round(chance, 1) if chance is not None else None, "reward_mult": mult,
            "xp_raw": round(raw, 2), "xp_credited": round(credited, 2), "daily_credited": round(daily["credited"] + total_credit, 1),
            "level_before": level_before, "level_after": level, "ceiling": limit, "bond_days": bond,
            "energy": round(energy, 1), "energy_loss": energy_loss, "finds": granted, "key": key_granted, "stage_essence": stage_essence,
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


async def _grant_key(db, user_id: int, run: dict) -> bool:
    """Один ключ сундука в сутки за первый завершённый поход или экспедицию (пока сундуки включены)."""
    from infrastructure.repositories import chests_v1 as chest_repo, system_flags
    if not await system_flags.is_enabled(db, "content_chests_v1"):
        return False
    from core.chests_v1 import POLICY_VERSION as CHEST_POLICY_VERSION, KeyGrant, canonical_snapshot_fingerprint, validate_key_grant
    await chest_repo.assert_delivery_ready(db)
    grant = validate_key_grant(KeyGrant(
        source_kind=f"pet_{'expedition' if run['kind'] == 'expedition' else 'trek'}_complete", source_event_id=f"v2:{run['id']}", amount=1,
        source_snapshot={"run_id": str(run["id"]), "activity_kind": run["kind"], "duration_hours": int(run["hours"]), "pet_id": int(run["pet_id"])},
    ))
    account = await chest_repo.lock_account(db, int(user_id))
    await chest_repo.apply_grant(
        db, grant_id=uuid4().hex, user_id=int(user_id), source_kind=grant.source_kind, source_event_id=grant.source_event_id,
        amount=1, policy_version=CHEST_POLICY_VERSION, source_snapshot=dict(grant.source_snapshot),
        source_snapshot_hash=canonical_snapshot_fingerprint(grant.source_snapshot),
        balance_before=int(account["balance"]), account_epoch=int(account["account_epoch"]),
    )
    return True


async def _camp_view(db, user_id: int, levels: dict) -> dict:
    job = await repo.camp_job(db, user_id)
    return {
        "levels": levels,
        "job": {"building": job["building"], "to_level": int(job["to_level"]), "ends_at": str(job["ends_at"]), "done": bool(job["done"])} if job else None,
        "next_costs": {b: rules.camp_upgrade_cost(b, levels[b] + 1) if levels[b] < 5 else None for b in rules.CAMP_BUILDINGS},
    }


async def camp_upgrade(db, *, user_id: int, building: str, action_id: str) -> dict:
    """Начать стройку: Мора и Эссенция списываются сразу, постройка готова через указанное время. Одна стройка за раз."""
    action_id = _action(action_id)
    if building not in rules.CAMP_BUILDINGS:
        raise PetV2PolicyError("Неизвестная постройка.")
    request = {"type": "camp_upgrade", "building": building}
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        replay = await repo.cached_action(db, user_id, action_id)
        if replay:
            if replay["request"] != request:
                raise PetV2Conflict("action_id уже использован для другого действия.")
            return {**replay["response"], "idempotent_replay": True}
        await repo.settle_camp(db, user_id)
        if await repo.camp_job(db, user_id):
            raise PetV2Conflict("Сначала дождись окончания текущей стройки.")
        levels = await repo.camp_levels(db, user_id)
        if levels[building] >= 5:
            raise PetV2PolicyError("Постройка уже на максимальном уровне.")
        cost = rules.camp_upgrade_cost(building, levels[building] + 1)
        from core.economy_contract import InsufficientBalance
        try:
            await _ledger(db, user_id, {"mora": -cost["mora"]}, f"{building}:{levels[building] + 1}:{action_id}", "camp", reason="pet_camp")
        except InsufficientBalance as exc:
            raise PetV2PolicyError(f"Не хватает Моры: нужно {cost['mora']}.") from exc
        from infrastructure.repositories import skins_v3 as essence_repo
        try:
            await essence_repo.essence_apply(
                db, user_id, -cost["essence"], reason="pet_v2_camp", reference=f"{building}:{levels[building] + 1}",
                idempotency_key=f"pet_v2:camp:{user_id}:{action_id}",
            )
        except ValueError as exc:
            raise PetV2PolicyError(f"Не хватает Эссенции: нужно {cost['essence']}.") from exc
        await repo.start_camp_job(db, user_id, building, levels[building] + 1, cost["hours"])
        response = {"ok": True, "building": building, "to_level": levels[building] + 1, "cost": cost, "idempotent_replay": False}
        await repo.save_action(db, user_id, action_id, request, response)
    return response


async def reforge_talisman(db, *, user_id: int, talisman_id: str, action_id: str) -> dict:
    """Перековка: талисман на тир выше за Эссенцию, если позволяет Мастерская."""
    action_id = _action(action_id)
    request = {"type": "reforge", "talisman_id": str(talisman_id)}
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        replay = await repo.cached_action(db, user_id, action_id)
        if replay:
            if replay["request"] != request:
                raise PetV2Conflict("action_id уже использован для другого действия.")
            return {**replay["response"], "idempotent_replay": True}
        talisman = await repo.get_talisman(db, user_id, talisman_id)
        if not talisman:
            raise PetV2PolicyError("Талисман не найден.")
        tier = int(talisman["tier"])
        workshop = (await repo.camp_levels(db, user_id))["workshop"]
        if tier >= rules.workshop_max_tier(workshop):
            raise PetV2PolicyError("Мастерская пока не позволяет поднять тир.")
        cost = rules.reforge_cost(tier)
        from infrastructure.repositories import skins_v3 as essence_repo
        try:
            await essence_repo.essence_apply(
                db, user_id, -cost, reason="pet_v2_reforge", reference=str(talisman_id),
                idempotency_key=f"pet_v2:reforge:{user_id}:{action_id}",
            )
        except ValueError as exc:
            raise PetV2PolicyError(f"Не хватает Эссенции: нужно {cost}.") from exc
        await repo.set_talisman_tier(db, user_id, talisman_id, tier + 1)
        response = {"ok": True, "talisman_id": str(talisman_id), "tier": tier + 1, "essence_spent": cost, "idempotent_replay": False}
        await repo.save_action(db, user_id, action_id, request, response)
    return response


def _track_view(track: dict) -> dict:
    """Клиенту никогда не уходит `hidden` пока выслеживание открыто."""
    view = {"id": track["id"], "pet_id": int(track["pet_id"]), "status": track["status"], "points": int(track["points"]),
            "opened": track["opened"], "result": track.get("result")}
    if track["status"] != "open":
        view["hidden"] = int(track["hidden"])
    return view


async def start_track(db, *, user_id: int, pet_id: int, action_id: str, rng=None) -> dict:
    """Выслеживание: сервер прячет находку в сетке 3×3 и открывает три бесплатные подсказки. 2 попытки в сутки."""
    action_id = _action(action_id)
    rng = rng or random.SystemRandom()
    request = {"type": "track_start", "pet_id": int(pet_id)}
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
        day = (await repo.clock(db))["day"]
        today = await repo.tracks_today(db, user_id, day)
        if any(t["status"] == "open" for t in today):
            raise PetV2Conflict("Сначала закончи текущее выслеживание.")
        if len(today) >= rules.TRACK_DAILY:
            raise PetV2Conflict("На сегодня попытки закончились.")
        state = await repo.ensure_state(db, user_id, pet_id, rules.energy_max(1, pet["species_id"]))
        hidden = rng.randrange(9)
        clues = rng.sample([c for c in range(9) if c != hidden], rules.TRACK_FREE_CLUES)
        opened = [{"cell": c, "heat": rules.track_heat(hidden, c), "free": True} for c in sorted(clues)]
        track_id = uuid4().hex
        points = rules.track_points(int(state["level"]), pet["species_id"])
        await repo.create_track(db, track_id=track_id, user_id=user_id, pet_id=pet_id, day=day, hidden=hidden, opened=opened, points=points)
        response = {"ok": True, "track": _track_view({"id": track_id, "pet_id": pet_id, "status": "open", "points": points,
                                                        "opened": opened, "hidden": hidden}), "attempts_left": rules.TRACK_DAILY - len(today) - 1,
                    "idempotent_replay": False}
        await repo.save_action(db, user_id, action_id, request, response)
    return response


async def open_track_cell(db, *, user_id: int, track_id: str, cell: int, action_id: str, rng=None) -> dict:
    action_id = _action(action_id)
    rng = rng or random.SystemRandom()
    request = {"type": "track_open", "track_id": str(track_id), "cell": int(cell)}
    if not 0 <= int(cell) < 9:
        raise PetV2PolicyError("Клетка вне сетки 3×3.")
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        replay = await repo.cached_action(db, user_id, action_id)
        if replay:
            if replay["request"] != request:
                raise PetV2Conflict("action_id уже использован для другого действия.")
            return {**replay["response"], "idempotent_replay": True}
        clock = await repo.clock(db)
        track = next((t for t in await repo.tracks_today(db, user_id, clock["day"]) if t["id"] == str(track_id)), None)
        if not track or track["status"] != "open":
            raise PetV2Conflict("Выслеживание не найдено или уже закончено.")
        if any(o["cell"] == int(cell) for o in track["opened"]):
            raise PetV2PolicyError("Эта клетка уже открыта.")
        heat = rules.track_heat(int(track["hidden"]), int(cell))
        opened = [*track["opened"], {"cell": int(cell), "heat": heat, "free": False}]
        points = int(track["points"]) - 1
        status, result = "open", None
        if heat == "found" or points == 0:
            status = "won" if heat == "found" else "lost"
        if status == "won":
            pet = await repo.get_owned_pet(db, user_id, int(track["pet_id"]))
            state = await repo.ensure_state(db, user_id, int(track["pet_id"]), rules.energy_max(1, pet["species_id"]))
            build = _build(state, await repo.equipped_talismans(db, user_id, int(track["pet_id"])))
            daily = await repo.get_daily(db, user_id, clock["day"])
            finds = dict(daily["finds"])
            granted, _ = await _roll_finds(
                db, user_id, clock["day"], f"track:{track['id']}", rules.TRACK_ROLLS, pet=pet, level=int(state["level"]),
                mods=_fx(build)["find_mods"], rng=rng, finds=finds, with_bonus_xp=False,
            )
            await repo.save_daily(db, user_id, clock["day"], raw=daily["raw"], credited=daily["credited"], finds=finds)
            result = {"finds": granted}
        await repo.save_track(db, track["id"], opened=opened, points=max(points, 0), status=status, result=result)
        response = {"ok": True, "track": _track_view({**track, "opened": opened, "points": max(points, 0), "status": status, "result": result}),
                    "idempotent_replay": False}
        await repo.save_action(db, user_id, action_id, request, response)
    return response


async def _apply_xp(db, user_id: int, pet_id: int, rarity: str, level: int, xp: float, bond: int) -> tuple[int, float, int, int]:
    """Повышение уровней до потолка Связи; Эссенция за пройденные ступени. Возвращает (уровень, Следы, Эссенция, потолок)."""
    stage_essence = 0
    limit = rules.ceiling(bond)
    while level < min(limit, rules.MAX_LEVEL) and xp >= rules.level_cost(level, rarity):
        xp -= rules.level_cost(level, rarity)
        if level in rules.STAGE_ESSENCE and await repo.save_stage_reward(db, user_id, pet_id, level, rules.STAGE_ESSENCE[level]):
            from services.skins_v3 import grant_essence_in_transaction
            stage_essence += await grant_essence_in_transaction(
                db, user_id, rules.STAGE_ESSENCE[level], reason="pet_v2_stage", reference=f"{pet_id}:{level}",
            )
        level += 1
    if level >= rules.MAX_LEVEL:
        xp = 0.0
    elif level >= limit:
        xp = min(xp, float(rules.level_cost(level, rarity)))
    return level, xp, stage_essence, limit


async def submit_trial(db, *, user_id: int, pet_id: int, difficulty: int, action_id: str) -> dict:
    """Испытание недели: одна сдача в неделю на аккаунт. Награда зависит от совпадения сборки с тегами недели."""
    action_id = _action(action_id)
    if difficulty not in rules.TRIAL_ESSENCE:
        raise PetV2PolicyError("Сложность 1, 2 или 3.")
    request = {"type": "trial", "pet_id": int(pet_id), "difficulty": int(difficulty)}
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
        rarity, favorite, _, _, _ = _species_row(pet)
        clock = await repo.clock(db)
        week = _week_start(clock["day"])
        if await repo.trial_done(db, user_id, week):
            raise PetV2Conflict("Испытание этой недели уже сдано.")
        state = await repo.ensure_state(db, user_id, pet_id, rules.energy_max(1, pet["species_id"]))
        build = _build(state, await repo.equipped_talismans(db, user_id, pet_id), await repo.camp_levels(db, user_id))
        trial = rules.weekly_trial(week.toordinal())
        matches = rules.trial_matches(trial, favorite, build["traits"], build["talismans"])
        if matches < difficulty:
            raise PetV2PolicyError(f"Сборка совпадает с тегами недели на {matches} из 3, нужно {difficulty}.")
        essence = rules.TRIAL_ESSENCE[difficulty]
        daily = await repo.get_daily(db, user_id, clock["day"])
        credited = rules.pool_credit(daily["raw"], rules.TRIAL_XP)
        await repo.save_daily(db, user_id, clock["day"], raw=daily["raw"] + rules.TRIAL_XP, credited=daily["credited"] + credited, finds=daily["finds"])
        bond = await repo.bond_days(db, user_id, pet_id)
        level_before = int(state["level"])
        level, xp, stage_essence, _ = await _apply_xp(db, user_id, pet_id, rarity, level_before, float(state["xp"]) + credited, bond)
        await repo.save_state(db, user_id, pet_id, level=level, xp=xp, energy=float(state["energy"]), pity=int(state["pity"]))
        from services.skins_v3 import grant_essence_in_transaction
        await grant_essence_in_transaction(db, user_id, essence, reason="pet_v2_trial", reference=week.isoformat())
        await repo.save_trial(db, user_id, week, pet_id, difficulty, essence)
        response = {"ok": True, "week": week.isoformat(), "matches": matches, "difficulty": int(difficulty), "essence": essence,
                    "xp_credited": round(credited, 2), "level_before": level_before, "level_after": level,
                    "stage_essence": stage_essence, "idempotent_replay": False}
        await repo.save_action(db, user_id, action_id, request, response)
    return response


async def trial_view(db, user_id: int) -> dict:
    clock = await repo.clock(db)
    week = _week_start(clock["day"])
    trial = rules.weekly_trial(week.toordinal())
    return {"week": week.isoformat(), "tags": trial, "done": await repo.trial_done(db, user_id, week),
            "xp": rules.TRIAL_XP, "essence": rules.TRIAL_ESSENCE}
