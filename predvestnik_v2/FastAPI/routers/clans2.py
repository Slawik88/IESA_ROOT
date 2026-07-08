"""FastAPI/routers/clans2.py — R3 Кланы 2.0: Бездна, здания, роли, войны.
Тонкий адаптер: логика — services/clans2.py + services/battle3.py (Боёвка 3.0:
бои отрядом юнитов, открытие клеток — дневной лимит вместо стамины питомца)."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.constants import (
    CLAN_ROLES, CLAN_BUILDINGS2, CLAN_BUILD_MAX_LEVEL,
    WAR_DECLARE_COST_MORA, WAR_WINDOW_HOURS, WAR_ATTACKS_PER_DAY,
    WAR_WALL_MAX_DEFENDERS, ABYSS_OPENS_PER_DAY,
    ABYSS_CHEST_SHARDS, ABYSS_MONSTER_SHARDS, ABYSS_BOSS_SHARDS,
    UNIT_SHARD_DROP_ABYSS_BOSS,
)
from core.units import UNITS, unit_stats
from infrastructure.repositories import clans2 as repo
from infrastructure.repositories import battles as bt_repo
from services import clans2 as svc
from services import battle3 as b3
from services import barracks
from services.combat_power import calculate_cp

router = APIRouter(prefix="/clans2", tags=["clans2"])


class RoleRequest(BaseModel):
    user_id: int
    role: str


class OpenRequest(BaseModel):
    cell: int


class BuildRequest(BaseModel):
    key: str


class DeclareRequest(BaseModel):
    node_id: int


class WallRequest(BaseModel):
    node_id: int


class WarAttackRequest(BaseModel):
    war_id: int


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
    from FastAPI.routers.battle import get_active_b3
    m = await _member_or_403(db, user["id"])
    ab = await svc.get_or_create_abyss(db, m["clan_id"])
    radar = await repo.building_level(db, m["clan_id"], "radar")
    cp = (await calculate_cp(db, user["id"]))["total"]
    opens_used = await repo.abyss_opens_today(db, user["id"])
    opens_max = ABYSS_OPENS_PER_DAY + radar // 2
    squad = await barracks.squad_units(db, user["id"])
    active = await get_active_b3(db, user["id"])
    return {
        "week": ab["week_key"], "floor": ab["floor"], "key_found": ab["key_found"],
        "cp": cp, "cp_gate": svc.floor_cp_gate(ab["floor"]),
        "opens_left": max(0, opens_max - opens_used), "opens_max": opens_max,
        "grid": svc.public_grid(ab["grid"], ab["opened"], radar),
        # Честные диапазоны лута по типу клетки (легенда UI раньше показывала
        # только иконки без цифр — «не весь лут отображается»)
        "loot": {"chest": list(ABYSS_CHEST_SHARDS), "monster": list(ABYSS_MONSTER_SHARDS),
                 "boss": list(ABYSS_BOSS_SHARDS), "boss_unit_shards": list(UNIT_SHARD_DROP_ABYSS_BOSS)},
        "squad": [{"unit_id": s["unit_id"], "level": s["level"],
                   "name": UNITS[s["unit_id"]]["name"],
                   "emoji": UNITS[s["unit_id"]]["emoji"]} for s in squad],
        "squad_cp": await barracks.squad_cp(db, user["id"]),
        "active_battle": b3.public_state(active["state"], active["id"]) if active else None,
    }


@router.post("/abyss/open")
async def abyss_open(body: OpenRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    from FastAPI.routers.battle import get_active_b3
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
    if await get_active_b3(db, uid):
        raise HTTPException(400, "Сначала закончи текущий бой.")
    radar = await repo.building_level(db, m["clan_id"], "radar")
    opens_max = ABYSS_OPENS_PER_DAY + radar // 2
    if await repo.abyss_opens_today(db, uid) >= opens_max:
        raise HTTPException(400, f"Лимит открытий на сегодня: {opens_max}. Радар клана добавляет ещё.")

    cell_type = grid[body.cell]
    uname = user.get("username") or f"id{uid}"
    await repo.inc_abyss_opens(db, uid)

    if cell_type in (svc.CELL_MONSTER, svc.CELL_BOSS):
        # Боёвка 3.0: клетка откроется только при победе отряда
        squad = await barracks.squad_units(db, uid)
        if not squad:
            raise HTTPException(400, "Сначала собери отряд в Казарме (Арена → Казарма).")
        is_boss = cell_type == svc.CELL_BOSS
        enemies = (b3.abyss_boss(ab["floor"]) if is_boss
                   else b3.abyss_enemy_squad(ab["floor"]))
        state = b3.new_battle_state(squad, enemies, "abyss", {
            "floor": ab["floor"],
            "abyss": {"clan_id": m["clan_id"], "week": ab["week_key"],
                      "cell": body.cell, "boss": is_boss}})
        bid = await bt_repo.create(db, uid, 0, "abyss", body.cell, b3.dumps(state))
        await db.commit()
        return {"battle": b3.public_state(state, bid)}

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
    """Боёвка 3.0: стена строится АВТОМАТИЧЕСКИ из отрядов топ-участников клана
    (Σ hp_max + def×10 по юнитам отрядов, до 10 защитников) — без ручного выбора."""
    m = await _member_or_403(db, user["id"], roles=("owner", "warlord"))
    node = await repo.get_node(db, body.node_id)
    if not node or node["owner_clan_id"] != m["clan_id"]:
        raise HTTPException(403, "Узел не ваш.")
    async with db.execute(
        "SELECT user_id FROM clan_members WHERE clan_id = ?", (m["clan_id"],)) as c:
        member_ids = [int(r[0]) for r in await c.fetchall()]
    defenders = []
    for uid_ in member_ids:
        units = await barracks.squad_units(db, uid_)
        if not units:
            continue
        hp = 0.0
        for s in units:
            st = unit_stats(s["unit_id"], s["level"])
            hp += st["hp_max"] + st["def"] * 10
        defenders.append({"user_id": uid_, "hp": round(hp, 1),
                          "units": [s["unit_id"] for s in units]})
    defenders.sort(key=lambda d: -d["hp"])
    defenders = defenders[:WAR_WALL_MAX_DEFENDERS]
    total_hp = round(sum(d["hp"] for d in defenders), 1)
    if total_hp <= 0:
        raise HTTPException(400, "Ни у кого в клане нет отряда в Казарме — стену не из чего строить.")
    await repo.set_wall(db, body.node_id, json.dumps(defenders, ensure_ascii=False), total_hp)
    return {"ok": True, "wall_hp": total_hp, "defenders": len(defenders)}


@router.post("/war/attack")
async def war_attack(body: WarAttackRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    from FastAPI.routers.battle import get_active_b3
    uid = user["id"]
    m = await _member_or_403(db, uid)
    war = await repo.get_active_war(db, attacker_clan_id=m["clan_id"])
    if not war or war["id"] != body.war_id:
        raise HTTPException(404, "Активная война не найдена.")
    if await repo.war_attacks_today(db, war["id"], uid) >= WAR_ATTACKS_PER_DAY:
        raise HTTPException(400, f"Лимит: {WAR_ATTACKS_PER_DAY} атаки в день.")
    if await get_active_b3(db, uid):
        raise HTTPException(400, "Сначала закончи текущий бой.")
    node = await repo.get_node(db, war["node_id"])
    remaining = float(node["wall_hp_max"]) - float(war["damage_total"])
    if remaining <= 0:
        raise HTTPException(400, "Стена уже пробита.")
    squad = await barracks.squad_units(db, uid)
    if not squad:
        raise HTTPException(400, "Сначала собери отряд в Казарме (Арена → Казарма).")
    state = b3.new_battle_state(squad, b3.war_wall(remaining), "war", {
        "floor": 3, "war": {"war_id": war["id"], "node_id": war["node_id"]}})
    bid = await bt_repo.create(db, uid, 0, "war", war["id"], b3.dumps(state))
    await db.commit()
    return {"battle": b3.public_state(state, bid)}