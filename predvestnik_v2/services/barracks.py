# services/barracks.py — Боёвка 3.0: Казарма (юниты игрока).
# Призыв за 💠 Осколки Бездны, прокачка осколками+морой, отряд из 3 позиций,
# стартовый выбор, одноразовая компенсация за старых «боевых» питомцев.
# Без импортов bot.* / FastAPI.* (иерархия services/).
import random

from core.constants import (
    UNIT_SUMMON_COST, UNIT_SUMMON_WEIGHTS, UNIT_DUP_SHARDS, UNIT_UNLOCK_SHARDS,
    UNIT_LEVEL_SHARDS, UNIT_LEVEL_MORA_BASE, SQUAD_SIZE,
    UNIT_COMPENSATION_CP_DIVISOR, UNIT_COMPENSATION_MIN,
)
from core.units import UNITS, unit_stats, unit_cp, STARTER_UNIT_CHOICES, ELEMENT_META, ROLE_META
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories import units as u_repo

SHARD_ITEM = "abyss_shard"   # 💠 в инвентаре


async def shard_balance(db, user_id: int) -> int:
    async with db.execute(
        "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
        (user_id, SHARD_ITEM),
    ) as c:
        row = await c.fetchone()
    return int(row[0] or 0) if row else 0


def _unit_view(unit_id: str, level: int, shards: int, in_squad_slot: int | None) -> dict:
    u = UNITS[unit_id]
    st = unit_stats(unit_id, max(1, level))
    el = ELEMENT_META.get(u["element"]) if u["element"] else {"emoji": "🌈", "name": "Все стихии"}
    need_next = UNIT_LEVEL_SHARDS.get(level + 1) if 1 <= level < 10 else None
    return {
        "unit_id": unit_id, "name": u["name"], "emoji": u["emoji"],
        "element": u["element"], "element_emoji": el["emoji"], "element_name": el["name"],
        "role": u["role"], "role_emoji": ROLE_META[u["role"]]["emoji"],
        "role_name": ROLE_META[u["role"]]["name"],
        "rarity": u["rarity"], "level": level, "shards": shards,
        "owned": level >= 1, "cp": unit_cp(unit_id, level) if level >= 1 else 0,
        "atk": st["atk"], "def": st["def"], "hp": st["hp_max"],
        "skill": u["skill"], "ult": u["ult"],
        "squad_slot": in_squad_slot,
        "next_level_shards": need_next,
        "next_level_mora": (UNIT_LEVEL_MORA_BASE * level) if need_next else None,
        "unlock_shards": UNIT_UNLOCK_SHARDS.get(u["rarity"]) if level == 0 else None,
    }


async def get_barracks(db, user_id: int) -> dict:
    """Полная сводка Казармы: юниты (владение+осколки), отряд, 💠, стартер-статус."""
    owned = {r["unit_id"]: r for r in await u_repo.get_units(db, user_id)}
    squad = await u_repo.get_squad(db, user_id)
    slot_by_unit = {uid: slot for slot, uid in squad.items()}
    units = []
    for unit_id in UNITS:
        row = owned.get(unit_id)
        units.append(_unit_view(
            unit_id, int(row["level"]) if row else 0,
            int(row["shards"]) if row else 0, slot_by_unit.get(unit_id)))
    n_owned = sum(1 for v in units if v["owned"])
    return {
        "units": units,
        "squad": {str(slot): squad.get(slot) for slot in range(SQUAD_SIZE)},
        "squad_cp": await squad_cp(db, user_id),
        "shards": await shard_balance(db, user_id),
        "summon_cost": UNIT_SUMMON_COST,
        "owned_count": n_owned,
        "starter_available": n_owned == 0,
        "starter_choices": list(STARTER_UNIT_CHOICES),
    }


async def squad_units(db, user_id: int) -> list[dict]:
    """Юниты отряда для боя: [{unit_id, level, slot, ...stats}] в порядке слотов."""
    squad = await u_repo.get_squad(db, user_id)
    owned = {r["unit_id"]: r for r in await u_repo.get_units(db, user_id)}
    out = []
    for slot in range(SQUAD_SIZE):
        uid = squad.get(slot)
        if not uid or uid not in UNITS:
            continue
        row = owned.get(uid)
        lvl = int(row["level"]) if row else 0
        if lvl < 1:
            continue
        out.append({"unit_id": uid, "level": lvl, "slot": slot})
    return out


async def squad_cp(db, user_id: int) -> int:
    return sum(unit_cp(u["unit_id"], u["level"]) for u in await squad_units(db, user_id))


async def pick_starter(db, user_id: int, unit_id: str) -> tuple[bool, str]:
    if unit_id not in STARTER_UNIT_CHOICES:
        return False, "Такого стартового юнита нет."
    if await u_repo.count_units(db, user_id) > 0:
        return False, "Стартовый юнит уже выбран."
    await u_repo.grant_unit(db, user_id, unit_id)
    await u_repo.unlock(db, user_id, unit_id)   # на случай строки level=0 от осколков
    await u_repo.set_squad_slot(db, user_id, 0, unit_id)
    await db.commit()
    u = UNITS[unit_id]
    return True, f"{u['emoji']} {u['name']} вступает в твою Казарму и встаёт во фронт отряда!"


async def summon(db, user_id: int) -> tuple[bool, dict | str]:
    """Призыв за 💠: новый юнит ИЛИ дубль → осколки этого юнита."""
    ok = await eco_repo.remove_item(db, user_id, SHARD_ITEM, UNIT_SUMMON_COST, commit=False)
    if not ok:
        have = await shard_balance(db, user_id)
        return False, f"Нужно {UNIT_SUMMON_COST} 💠 (у тебя {have}). Осколки капают в Бездне и Вратах."
    rarity = random.choices(
        list(UNIT_SUMMON_WEIGHTS), weights=list(UNIT_SUMMON_WEIGHTS.values()))[0]
    pool = [uid for uid, u in UNITS.items() if u["rarity"] == rarity]
    unit_id = random.choice(pool)
    existing = await u_repo.get_unit(db, user_id, unit_id)
    is_dup = bool(existing and int(existing["level"]) >= 1)
    if is_dup:
        shards = UNIT_DUP_SHARDS.get(rarity, 10)
        await u_repo.add_shards(db, user_id, unit_id, shards)
    else:
        await u_repo.grant_unit(db, user_id, unit_id)
        await u_repo.unlock(db, user_id, unit_id)
        shards = 0
    await db.commit()
    u = UNITS[unit_id]
    return True, {"unit_id": unit_id, "name": u["name"], "emoji": u["emoji"],
                  "rarity": rarity, "duplicate": is_dup, "shards": shards,
                  "element_emoji": (ELEMENT_META.get(u["element"]) or {}).get("emoji", "🌈"),
                  "role_name": ROLE_META[u["role"]]["name"]}


async def unlock_by_shards(db, user_id: int, unit_id: str) -> tuple[bool, str]:
    """Открыть юнита накопленными таргет-осколками (дроп боссов)."""
    u = UNITS.get(unit_id)
    if not u:
        return False, "Юнит не найден."
    row = await u_repo.get_unit(db, user_id, unit_id)
    if row and int(row["level"]) >= 1:
        return False, "Юнит уже открыт."
    need = UNIT_UNLOCK_SHARDS.get(u["rarity"], 20)
    have = int(row["shards"]) if row else 0
    if have < need:
        return False, f"Нужно {need} осколков юнита (есть {have})."
    await u_repo.spend_shards(db, user_id, unit_id, need)
    await u_repo.unlock(db, user_id, unit_id)
    await db.commit()
    return True, f"{u['emoji']} {u['name']} открыт за осколки!"


async def level_up(db, user_id: int, unit_id: str) -> tuple[bool, str]:
    row = await u_repo.get_unit(db, user_id, unit_id)
    if not row or int(row["level"]) < 1:
        return False, "У тебя нет этого юнита."
    lvl = int(row["level"])
    if lvl >= 10:
        return False, "Максимальный уровень."
    need_shards = UNIT_LEVEL_SHARDS[lvl + 1]
    need_mora = UNIT_LEVEL_MORA_BASE * lvl
    if int(row["shards"]) < need_shards:
        return False, f"Нужно {need_shards} осколков юнита (есть {int(row['shards'])})."
    bal = await eco_repo.get_balance(db, user_id)
    if float(bal["user_balance_mora"] or 0) < need_mora:
        return False, f"Нужно {need_mora:.0f} 🪙."
    await u_repo.spend_shards(db, user_id, unit_id, need_shards)
    await eco_repo.add_balance(db, user_id, mora=-need_mora, source="spend",
                               note=f"Прокачка юнита {UNITS[unit_id]['name']} → {lvl + 1}")
    await u_repo.set_level(db, user_id, unit_id, lvl + 1)
    await db.commit()
    u = UNITS[unit_id]
    return True, f"{u['emoji']} {u['name']} теперь уровня {lvl + 1}!"


async def set_squad(db, user_id: int, slots: dict) -> tuple[bool, str]:
    """slots: {"0": unit_id|None, "1": ..., "2": ...} — валидация владения."""
    owned = {r["unit_id"] for r in await u_repo.get_units(db, user_id) if int(r["level"]) >= 1}
    seen = set()
    for s in range(SQUAD_SIZE):
        uid = slots.get(str(s)) or slots.get(s)
        if uid:
            if uid not in owned:
                return False, "Нельзя поставить юнита, которого нет."
            if uid in seen:
                return False, "Один юнит — в одном слоте."
            seen.add(uid)
    for s in range(SQUAD_SIZE):
        uid = slots.get(str(s)) or slots.get(s)
        await u_repo.set_squad_slot(db, user_id, s, uid)
    await db.commit()
    return True, "Отряд сохранён."


async def compensate_pets_migration(db) -> int:
    """Одноразовая компенсация 💠 всем владельцам питомцев за выпиленный боевой
    слой (маркер schema_migrations.battle3_compensation). Возвращает число игроков."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            key TEXT PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    async with db.execute(
        "SELECT 1 FROM schema_migrations WHERE key = 'battle3_compensation'"
    ) as c:
        if await c.fetchone():
            return 0
    from services.combat_power import pet_cp
    async with db.execute(
        "SELECT owner_id, rarity, COALESCE(pet_level,1) AS pet_level FROM pets "
        "WHERE placement IN ('active','passive')"
    ) as c:
        rows = await c.fetchall()
    totals: dict[int, float] = {}
    for r in rows:
        totals[int(r["owner_id"])] = totals.get(int(r["owner_id"]), 0.0) \
            + pet_cp(r["rarity"], r["pet_level"])
    for uid, cp_sum in totals.items():
        shards = max(UNIT_COMPENSATION_MIN, int(round(cp_sum / UNIT_COMPENSATION_CP_DIVISOR)))
        await eco_repo.add_item(db, uid, SHARD_ITEM, shards)
    await db.execute("INSERT INTO schema_migrations (key) VALUES ('battle3_compensation') "
                     "ON CONFLICT (key) DO NOTHING")
    await db.commit()
    return len(totals)
