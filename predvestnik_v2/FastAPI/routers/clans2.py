"""FastAPI/routers/clans2.py — R3 Кланы 2.0: Бездна, здания, роли, войны.
Тонкий адаптер: логика — services/clans2.py + services/battle.py."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.constants import (
    CLAN_ROLES, CLAN_BUILDINGS2, CLAN_BUILD_MAX_LEVEL,
    WAR_DECLARE_COST_MORA, WAR_WINDOW_HOURS, WAR_ATTACKS_PER_DAY,
    WAR_WALL_MAX_DEFENDERS,
)
from infrastructure.repositories import clans2 as repo
from infrastructure.repositories import battles as bt_repo
from infrastructure.repositories import pet_combat
from services import clans2 as svc
from services import battle as bt
from services.combat_power import calculate_cp
from services.pet_combat import stamina_recovery_info

router = APIRouter(prefix="/clans2", tags=["clans2"])


class RoleRequest(BaseModel):
    user_id: int
    role: str


class OpenRequest(BaseModel):
    cell: int
    pet_id: int


class BuildRequest(BaseModel):
    key: str


class DeclareRequest(BaseModel):
    node_id: int


class WallRequest(BaseModel):
    node_id: int
    pet_ids: list[int]


class WarAttackRequest(BaseModel):
    war_id: int
    pet_id: int


async def _member_or_403(db, uid: int, roles: tuple | None = None) -> dict:
    m = await repo.get_member(db, uid)
    if not m:
        raise HTTPException(403, "Ты не в клане.")
    if roles and m["role"] not in roles:
        raise HTTPException(403, f"Нужна роль: {'/'.join(roles)}.")
    return m


@router.get("/overview")
async def overview(db=Depends(get_db), user=Depends(require_tg_user)):
    m = await _member_or_403(db, user["id"])
    buildings = await repo.get_buildings(db, m["clan_id"])
    t_lvl = buildings.get("treasury", 0)
    return {
        "clan": {"id": m["clan_id"], "name": m["name"], "tag": m["tag"]},
        "role": m["role"],
        "treasury_shards": float(m["treasury_shards"]),
        "treasury_mora": float(m["treasury_mora"]),
        "treasury_cap": svc.treasury_cap(t_lvl),
        "buildings": [
            {"key": k, **CLAN_BUILDINGS2[k], "level": buildings.get(k, 0),
             "max": CLAN_BUILD_MAX_LEVEL,
             "next_cost": svc.build_cost(buildings.get(k, 0) + 1)
                          if buildings.get(k, 0) < CLAN_BUILD_MAX_LEVEL else None}
            for k in CLAN_BUILDINGS2
        ],
        "log": await repo.abyss_log_tail(db, m["clan_id"]),
    }


@router.post("/role")
async def set_role(body: RoleRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    m = await _member_or_403(db, user["id"], roles=("owner",))
    if body.role not in CLAN_ROLES or body.role == "owner":
        raise HTTPException(400, "Роль: warlord / treasurer / fighter.")
    target = await repo.get_member(db, body.user_id)
    if not target or target["clan_id"] != m["clan_id"]:
        raise HTTPException(404, "Игрок не в твоём клане.")
    if target["role"] == "owner":
        raise HTTPException(400, "Владыку не разжаловать.")
    await repo.set_role(db, m["clan_id"], body.user_id, body.role)
    return {"ok": True}


@router.post("/build")
async def build(body: BuildRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    m = await _member_or_403(db, user["id"], roles=("owner", "treasurer"))
    if body.key not in CLAN_BUILDINGS2:
        raise HTTPException(400, "Нет такого здания.")
    lvl = await repo.building_level(db, m["clan_id"], body.key)
    if lvl >= CLAN_BUILD_MAX_LEVEL:
        raise HTTPException(400, "Здание на максимуме.")
    cost = svc.build_cost(lvl + 1)
    if not await repo.upgrade_building(db, m["clan_id"], body.key, cost):
        raise HTTPException(400, f"В казне не хватает 💠 (нужно {cost}).")
    await repo.abyss_log(db, m["clan_id"], user["id"],
                         f"🏗 {CLAN_BUILDINGS2[body.key]['name']} → ур.{lvl + 1}")
    await db.commit()
    return {"ok": True, "key": body.key, "level": lvl + 1, "paid": cost}


# ── Бездна ────────────────────────────────────────────────────────────────────

@router.get("/abyss")
async def abyss(db=Depends(get_db), user=Depends(require_tg_user)):
    m = await _member_or_403(db, user["id"])
    ab = await svc.get_or_create_abyss(db, m["clan_id"])
    radar = await repo.building_level(db, m["clan_id"], "radar")
    cp = (await calculate_cp(db, user["id"]))["total"]
    async with db.execute(
        "SELECT id, name, species_id, rarity, COALESCE(pet_level,1) AS pet_level "
        "FROM pets WHERE owner_id = ? AND COALESCE(placement,'') != 'auction'",
        (user["id"],)) as c:
        pet_rows = [dict(r) for r in await c.fetchall()]
    pets = []
    for p in pet_rows:
        st = await pet_combat.get_state(db, p["id"], user["id"])
        if st and st["alive"]:
            pets.append({**p, "stamina": int(st["stamina"]), "hp": int(st["hp"]),
                         **stamina_recovery_info(st["stamina"], st["stamina_max"])})
    active = await bt_repo.get_active(db, user["id"])
    return {
        "week": ab["week_key"], "floor": ab["floor"], "key_found": ab["key_found"],
        "cp": cp, "cp_gate": svc.floor_cp_gate(ab["floor"]),
        "stamina_cost": svc.abyss_stamina_cost(radar),
        "grid": svc.public_grid(ab["grid"], ab["opened"], radar),
        "pets": pets,
        "active_battle": bt.public_state(active["state"], active["id"]) if active else None,
    }


@router.post("/abyss/open")
async def abyss_open(body: OpenRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    uid = user["id"]
    m = await _member_or_403(db, uid)
    ab = await svc.get_or_create_abyss(db, m["clan_id"])
    grid, opened = ab["grid"], ab["opened"]
    if not (0 <= body.cell < len(grid)):
        raise HTTPException(400, "Нет такой клетки.")
    if body.cell in opened or body.cell == svc._CENTER:
        raise HTTPException(400, "Клетка уже открыта.")
    if not svc.is_adjacent_open(opened, body.cell):
        raise HTTPException(400, "Открывать можно только смежные с открытыми («туман»).")
    cp = (await calculate_cp(db, uid))["total"]
    if cp < svc.floor_cp_gate(ab["floor"]):
        raise HTTPException(400, f"Этаж {ab['floor']} требует ⚡ {svc.floor_cp_gate(ab['floor'])}.")
    if await bt_repo.get_active(db, uid):
        raise HTTPException(400, "Сначала закончи текущий бой.")

    pst = await pet_combat.get_state(db, body.pet_id, uid)
    if not pst or not pst["alive"]:
        raise HTTPException(400, "Питомец не найден или без сил.")
    radar = await repo.building_level(db, m["clan_id"], "radar")
    st_cost = svc.abyss_stamina_cost(radar)
    if pst["stamina"] < st_cost:
        raise HTTPException(400, f"Питомцу нужно {st_cost} выносливости.")
    await pet_combat.persist(db, body.pet_id, hp=pst["hp"],
                             stamina=pst["stamina"] - st_cost,
                             hp_max=pst["hp_max"], stamina_max=pst["stamina_max"],
                             attack=pst["attack"], defense=pst["defense"])

    cell_type = grid[body.cell]
    uname = user.get("username") or f"id{uid}"

    if cell_type in (svc.CELL_MONSTER, svc.CELL_BOSS):
        # Бой 2.0: клетка откроется только при победе (в battle.action)
        is_boss = cell_type == svc.CELL_BOSS
        enemy_floor = ab["floor"] + (1 if is_boss else 0)
        state = bt.new_gates_battle_state(
            {"rarity": pst["rarity"], "pet_level": pst["level"], "name": pst["name"]},
            enemy_floor)
        state["waves"] = state["waves"][:1]
        state["enemy"] = dict(state["waves"][0]); state["enemy"]["hp"] = state["enemy"]["hp_max"]
        if is_boss:
            state["enemy"]["name"], state["enemy"]["emoji"] = "БОСС Бездны", "👑"
            state["enemy"]["hp_max"] = int(state["enemy"]["hp_max"] * 1.6)
            state["enemy"]["hp"] = state["enemy"]["hp_max"]
        state["pet"]["hp"] = min(int(pst["hp"]), state["pet"]["hp_max"])
        state["pet"]["st"] = min(int(pst["stamina"] - st_cost), state["pet"]["st_max"])
        state["abyss"] = {"clan_id": m["clan_id"], "week": ab["week_key"],
                          "cell": body.cell, "boss": is_boss}
        bid = await bt_repo.create(db, uid, body.pet_id, "abyss", body.cell, bt.dumps(state))
        await db.commit()
        return {"battle": bt.public_state(state, bid)}

    # Пустая клетка / сундук — мгновенный исход
    opened.append(body.cell)
    result = {"cell": body.cell, "type": cell_type, "battle": None}
    if cell_type == svc.CELL_CHEST:
        shards = svc.roll_chest()
        split = await svc.split_loot(db, m["clan_id"], uid, shards)
        await repo.abyss_log(db, m["clan_id"], uid,
                             f"📦 @{uname}: сундук +{shards}💠 ({split['treasury']} в казну)")
        result.update({"shards": shards, "split": split})
    elif cell_type == svc.CELL_EXIT:
        result["exit_found"] = True
        await repo.abyss_log(db, m["clan_id"], uid, f"🚪 @{uname} нашёл проход на след. этаж!")
    else:
        await repo.abyss_log(db, m["clan_id"], uid, f"▫️ @{uname} открыл пустую клетку")
    await repo.save_abyss(db, m["clan_id"], ab["week_key"], opened)
    await db.commit()
    return result


@router.post("/abyss/next-floor")
async def abyss_next_floor(db=Depends(get_db), user=Depends(require_tg_user)):
    m = await _member_or_403(db, user["id"], roles=("owner", "warlord"))
    ab = await svc.get_or_create_abyss(db, m["clan_id"])
    if not ab["key_found"]:
        raise HTTPException(400, "Сначала победите Босса этажа — он держит ключ.")
    exit_open = any(ab["grid"][i] == svc.CELL_EXIT for i in ab["opened"])
    if not exit_open:
        raise HTTPException(400, "Проход (🚪) ещё не найден на карте.")
    nf = ab["floor"] + 1
    await repo.replace_abyss_floor(db, m["clan_id"], ab["week_key"], nf,
                                   svc.generate_grid(m["clan_id"], ab["week_key"], nf))
    await repo.abyss_log(db, m["clan_id"], user["id"], f"⬇️ Клан спустился на этаж {nf}!")
    await db.commit()
    return {"ok": True, "floor": nf}


# ── Войны за узлы ─────────────────────────────────────────────────────────────

@router.get("/war/nodes")
async def war_nodes(db=Depends(get_db), user=Depends(require_tg_user)):
    m = await repo.get_member(db, user["id"])
    nodes = await repo.get_nodes(db)
    out = []
    for n in nodes:
        war = await repo.get_active_war(db, node_id=n["id"])
        out.append({
            "id": n["id"], "name": n["name"], "buff_key": n["buff_key"],
            "owner": ({"name": n["owner_name"], "tag": n["owner_tag"],
                       "clan_id": n["owner_clan_id"]} if n["owner_clan_id"] else None),
            "wall_hp_max": float(n["wall_hp_max"] or 0),
            "shield_left_sec": max(0, int(n["shield_left_sec"] or 0)) if n["shield_until"] else 0,
            "war": ({"id": war["id"], "attacker_clan_id": war["attacker_clan_id"],
                     "damage_total": float(war["damage_total"]),
                     "remaining_sec": max(0, int(war["remaining_sec"] or 0))} if war else None),
        })
    return {"nodes": out, "my_clan_id": m["clan_id"] if m else None,
            "my_role": m["role"] if m else None,
            "declare_cost": WAR_DECLARE_COST_MORA,
            "attacks_per_day": WAR_ATTACKS_PER_DAY}


@router.post("/war/declare")
async def war_declare(body: DeclareRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    m = await _member_or_403(db, user["id"], roles=("owner", "warlord"))
    node = await repo.get_node(db, body.node_id)
    if not node:
        raise HTTPException(404, "Узел не найден.")
    if node["owner_clan_id"] == m["clan_id"]:
        raise HTTPException(400, "Это уже ваш узел.")
    async with db.execute(
        "SELECT 1 FROM war_nodes WHERE id = ? AND shield_until > NOW()", (body.node_id,)
    ) as c:
        if await c.fetchone():
            raise HTTPException(400, "Узел под щитом после захвата.")
    if await repo.get_active_war(db, node_id=body.node_id):
        raise HTTPException(400, "За этот узел уже идёт война.")
    if await repo.get_active_war(db, attacker_clan_id=m["clan_id"]):
        raise HTTPException(400, "Клан уже ведёт войну.")
    # Незанятый узел — бесплатный захват «стеной по умолчанию» невозможен:
    # ставится война против пустой стены 1000 HP (символическая оборона Бездны)
    if node["owner_clan_id"] is None and float(node["wall_hp_max"] or 0) <= 0:
        await repo.set_wall(db, body.node_id, "[]", 1000.0)
    async with db.execute(
        "UPDATE clans SET treasury_mora = treasury_mora - ? "
        "WHERE clan_id = ? AND treasury_mora >= ? RETURNING clan_id",
        (WAR_DECLARE_COST_MORA, m["clan_id"], WAR_DECLARE_COST_MORA)) as c:
        if not await c.fetchone():
            raise HTTPException(400, f"В 🪙-казне клана нет взноса {WAR_DECLARE_COST_MORA:.0f} "
                                     f"(казну наполняет доход узлов).")
    wid = await repo.create_war(db, body.node_id, m["clan_id"],
                                node["owner_clan_id"], WAR_WINDOW_HOURS)
    await repo.abyss_log(db, m["clan_id"], user["id"],
                         f"⚔️ Объявлена война за «{node['name']}»!")
    await db.commit()
    return {"ok": True, "war_id": wid}


@router.post("/war/wall")
async def war_set_wall(body: WallRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    m = await _member_or_403(db, user["id"], roles=("owner", "warlord"))
    node = await repo.get_node(db, body.node_id)
    if not node or node["owner_clan_id"] != m["clan_id"]:
        raise HTTPException(403, "Узел не ваш.")
    if len(body.pet_ids) > WAR_WALL_MAX_DEFENDERS:
        raise HTTPException(400, f"Максимум {WAR_WALL_MAX_DEFENDERS} защитников.")
    pets = []
    for pid in body.pet_ids:
        async with db.execute(
            "SELECT p.id, p.name, p.rarity, COALESCE(p.pet_level,1) AS pet_level "
            "FROM pets p JOIN clan_members cm ON cm.user_id = p.owner_id "
            "WHERE p.id = ? AND cm.clan_id = ?", (pid, m["clan_id"])) as c:
            row = await c.fetchone()
        if row:
            pets.append(dict(row))
    hp = svc.wall_hp_from_pets(pets)
    await repo.set_wall(db, body.node_id, json.dumps(pets, ensure_ascii=False), hp)
    return {"ok": True, "wall_hp": hp, "defenders": len(pets)}


@router.post("/war/attack")
async def war_attack(body: WarAttackRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    uid = user["id"]
    m = await _member_or_403(db, uid)
    war = await repo.get_active_war(db, attacker_clan_id=m["clan_id"])
    if not war or war["id"] != body.war_id:
        raise HTTPException(404, "Активная война не найдена.")
    if await repo.war_attacks_today(db, war["id"], uid) >= WAR_ATTACKS_PER_DAY:
        raise HTTPException(400, f"Лимит: {WAR_ATTACKS_PER_DAY} атаки в день.")
    if await bt_repo.get_active(db, uid):
        raise HTTPException(400, "Сначала закончи текущий бой.")
    node = await repo.get_node(db, war["node_id"])
    remaining = float(node["wall_hp_max"]) - float(war["damage_total"])
    if remaining <= 0:
        raise HTTPException(400, "Стена уже пробита.")
    pst = await pet_combat.get_state(db, body.pet_id, uid)
    if not pst or not pst["alive"]:
        raise HTTPException(400, "Питомец не готов.")
    enemy = svc.war_wall_enemy(remaining)
    state = {
        "pet": {**bt.pet_battle_stats(pst["rarity"], pst["level"]),
                "name": pst["name"]},
        "waves": [enemy], "wave_idx": 0,
        "enemy": {**enemy, "hp": enemy["hp_max"]},
        "floor": 3, "qte": bt.qte_window(3), "zero_streak": 0, "log": [],
        "war": {"war_id": war["id"], "node_id": war["node_id"]},
    }
    state["pet"]["hp"] = min(int(pst["hp"]), state["pet"]["hp_max"])
    state["pet"]["st"] = min(int(pst["stamina"]), state["pet"]["st_max"])
    bid = await bt_repo.create(db, uid, body.pet_id, "war", war["id"], bt.dumps(state))
    await db.commit()
    return {"battle": bt.public_state(state, bid)}