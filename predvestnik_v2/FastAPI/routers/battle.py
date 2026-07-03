"""FastAPI/routers/battle.py — R2: Бой 2.0 + Врата 2.0 (GDD_REBUILD_PLAN.md).

Тонкий адаптер: логика хода/грейдинга — services/battle.py, состояние —
infrastructure/repositories/battles.py. Бой ТРАТИТ реальные HP/стамину питомца
(pet_combat.persist после финала) — лечение после боя за 2🪙/HP."""
import random
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.constants import (
    GATES2_FLOORS, GATES2_CP_GATE, GATES2_ENTRIES_PER_DAY,
    GATES2_DARK_MORA_BASE, GATES2_DARK_MORA_PER_FLOOR, GATES2_SHARD_CHANCE,
    BATTLE_HEAL_MORA_PER_HP,
)
from infrastructure.repositories import battles as bt_repo
from infrastructure.repositories import pet_combat
from infrastructure.repositories import economy as eco_repo
from services import battle as bt
from services.combat_power import calculate_cp

router = APIRouter(prefix="/combat2", tags=["battle2"])


class GatesEnterRequest(BaseModel):
    floor: int
    pet_id: int


class ActionRequest(BaseModel):
    battle_id: int
    stance: str
    tap_offset_ms: int


class HealRequest(BaseModel):
    pet_id: int


@router.get("/gates")
async def gates_overview(db=Depends(get_db), user=Depends(require_tg_user)):
    """Врата 2.0: этажи с CP-гейтом, остаток входов, боевые питомцы, активный бой."""
    uid = user["id"]
    cp = (await calculate_cp(db, uid))["total"]
    used = await bt_repo.count_today(db, uid, "gates")
    async with db.execute(
        "SELECT id, name, species_id, rarity, COALESCE(pet_level,1) AS pet_level, placement "
        "FROM pets WHERE owner_id = ? AND COALESCE(placement,'') NOT IN ('auction')",
        (uid,),
    ) as c:
        pet_rows = [dict(r) for r in await c.fetchall()]
    pets = []
    for p in pet_rows:
        st = await pet_combat.get_state(db, p["id"], uid)
        if st:
            pets.append({**p, "hp": st["hp"], "hp_max": st["hp_max"],
                         "stamina": st["stamina"], "alive": st["alive"]})
    active = await bt_repo.get_active(db, uid)
    return {
        "cp": cp,
        "entries_left": max(0, GATES2_ENTRIES_PER_DAY - used),
        "floors": [{"floor": f, "cp_gate": GATES2_CP_GATE[f], "open": cp >= GATES2_CP_GATE[f],
                    "waves": bt.gates_waves(f),
                    "reward_dark": GATES2_DARK_MORA_BASE + GATES2_DARK_MORA_PER_FLOOR * f}
                   for f in range(1, GATES2_FLOORS + 1)],
        "pets": pets,
        "active_battle": bt.public_state(active["state"], active["id"]) if active else None,
        "heal_price_per_hp": BATTLE_HEAL_MORA_PER_HP,
    }


@router.post("/gates/enter")
async def gates_enter(body: GatesEnterRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    uid = user["id"]
    if not (1 <= body.floor <= GATES2_FLOORS):
        raise HTTPException(400, "Нет такого этажа.")
    if await bt_repo.get_active(db, uid):
        raise HTTPException(400, "У тебя уже идёт бой — сначала закончи его.")
    if await bt_repo.count_today(db, uid, "gates") >= GATES2_ENTRIES_PER_DAY:
        raise HTTPException(400, f"Лимит Врат: {GATES2_ENTRIES_PER_DAY} входа в день.")
    cp = (await calculate_cp(db, uid))["total"]
    if cp < GATES2_CP_GATE[body.floor]:
        raise HTTPException(400, f"Этаж {body.floor} требует ⚡ {GATES2_CP_GATE[body.floor]} "
                                 f"Силы (у тебя {cp}).")

    pst = await pet_combat.get_state(db, body.pet_id, uid)
    if not pst:
        raise HTTPException(404, "Питомец не найден.")
    if not pst["alive"]:
        raise HTTPException(400, "Питомец без сил — сначала вылечи его.")
    if pst["placement"] in ("auction",):
        raise HTTPException(400, "Питомец занят.")

    state = bt.new_gates_battle_state(
        {"rarity": pst["rarity"], "pet_level": pst["level"], "name": pst["name"],
         "species_id": pst["species_id"]}, body.floor)
    # Реальные текущие HP/стамина (не паспортный максимум) — бой продолжает их
    state["pet"]["hp"] = min(int(pst["hp"]), state["pet"]["hp_max"])
    state["pet"]["st"] = min(int(pst["stamina"]), state["pet"]["st_max"])

    bid = await bt_repo.create(db, uid, body.pet_id, "gates", body.floor, bt.dumps(state))
    await db.commit()
    return bt.public_state(state, bid)


async def _persist_pet_after_battle(db, battle_row: dict, state: dict) -> None:
    """Записать реальные HP/стамину питомца после финала боя."""
    pst = await pet_combat.get_state(db, battle_row["pet_id"])
    if not pst:
        return
    await pet_combat.persist(
        db, battle_row["pet_id"],
        hp=float(state["pet"]["hp"]), stamina=float(state["pet"]["st"]),
        hp_max=pst["hp_max"], stamina_max=pst["stamina_max"],
        attack=pst["attack"], defense=pst["defense"],
    )


async def _gates_reward(db, uid: int, floor: int) -> dict:
    dark = GATES2_DARK_MORA_BASE + GATES2_DARK_MORA_PER_FLOOR * floor
    await db.execute(
        "UPDATE users SET user_balance_dark_mora = COALESCE(user_balance_dark_mora,0) + ? "
        "WHERE user_tg_id = ?", (dark, uid))
    shards = 0
    if random.random() < GATES2_SHARD_CHANCE:
        shards = random.randint(1, 3)
        await eco_repo.add_item(db, uid, "abyss_shard", shards)
    return {"dark_mora": dark, "shards": shards}


@router.post("/battle/action")
async def battle_action(body: ActionRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    uid = user["id"]
    row = await bt_repo.get_active(db, uid)
    if not row or row["id"] != body.battle_id:
        raise HTTPException(404, "Бой не найден или уже завершён.")
    if bt.rate_limited(row.get("last_action_at")):
        raise HTTPException(429, "Слишком быстро — дождись следующего QTE.")
    if body.stance not in bt.STANCES:
        raise HTTPException(400, "Неизвестная стойка.")

    state = row["state"]
    grade, zs = bt.grade_tap(state.get("qte", {}), body.tap_offset_ms,
                             int(state.get("zero_streak", 0)))
    state["zero_streak"] = zs
    turn = bt.resolve_turn(state, body.stance, grade)
    state["qte"] = bt.qte_window(int(state.get("floor") or 1))

    reward = None
    if turn["battle_won"] or turn["battle_lost"]:
        status = "won" if turn["battle_won"] else "lost"
        await bt_repo.finish(db, row["id"], status)
        await _persist_pet_after_battle(db, row, state)
        if turn["battle_won"] and row["mode"] == "gates":
            reward = await _gates_reward(db, uid, int(row["ref_id"]))
        elif row["mode"] in ("abyss", "war"):
            # R3: результат забирает вызывающая система (Бездна/Война) по статусу
            pass
        await db.commit()
        return {**bt.public_state(state, row["id"], status), "turn": turn, "reward": reward}

    await bt_repo.save_state(db, row["id"], bt.dumps(state), time.time())
    await db.commit()
    return {**bt.public_state(state, row["id"]), "turn": turn, "reward": None}


@router.post("/heal")
async def heal_pet(body: HealRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Полное лечение питомца за Мору (BATTLE_HEAL_MORA_PER_HP за 1 HP)."""
    uid = user["id"]
    pst = await pet_combat.get_state(db, body.pet_id, uid)
    if not pst:
        raise HTTPException(404, "Питомец не найден.")
    missing = int(pst["hp_max"] - pst["hp"])
    if missing <= 0:
        raise HTTPException(400, "Питомец и так здоров.")
    price = round(missing * BATTLE_HEAL_MORA_PER_HP, 1)
    bal = await eco_repo.get_balance(db, uid)
    if float(bal["user_balance_mora"] or 0) < price:
        raise HTTPException(400, f"Нужно {price:.0f} 🪙 (лечение {missing} HP).")
    await eco_repo.add_balance(db, uid, mora=-price, source="spend",
                               note=f"Лечение питомца (+{missing} HP)")
    await pet_combat.persist(db, body.pet_id, hp=float(pst["hp_max"]),
                             stamina=float(pst["stamina"]), hp_max=pst["hp_max"],
                             stamina_max=pst["stamina_max"], attack=pst["attack"],
                             defense=pst["defense"])
    await db.commit()
    return {"ok": True, "healed": missing, "price": price}