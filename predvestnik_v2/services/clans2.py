# services/clans2.py — R3 Кланы 2.0: Бездна (туман войны), здания, войны за узлы.
# Логика поверх infrastructure/repositories/clans2.py; бои — services/battle.py.
import json
import random
from datetime import datetime, timezone

from core.constants import (
    ABYSS_GRID, ABYSS_OPEN_STAMINA, ABYSS_SPLIT_TREASURY, ABYSS_TREASURY_WEEKLY_CAP,
    ABYSS_CHEST_SHARDS, ABYSS_MONSTER_SHARDS, ABYSS_BOSS_SHARDS, ABYSS_FLOOR_CP_BASE,
    CLAN_BUILD_BASE, CLAN_BUILD_GROWTH,
    CLAN_ACADEMY_PCT_PER_LEVEL, CLAN_RADAR_STAMINA_PCT_PER_LEVEL,
    CLAN_TREASURY_CAP_BASE, CLAN_TREASURY_CAP_PER_LEVEL,
    WAR_WALL_MAX_DEFENDERS, WAR_WALL_SEGMENT_HP,
)
from infrastructure.repositories import clans2 as repo
from infrastructure.repositories import economy as eco_repo
from services.battle import pet_battle_stats, gates_enemy


def week_key() -> str:
    iso = datetime.now(timezone.utc).isocalendar()
    return f"W{iso[0]}-{iso[1]:02d}"


# ── Здания ────────────────────────────────────────────────────────────────────

def build_cost(level_next: int) -> int:
    """Цена апгрейда здания НА уровень level_next (1..10), 💠 из казны."""
    return int(round(CLAN_BUILD_BASE * (CLAN_BUILD_GROWTH ** (level_next - 1))))


def treasury_cap(treasury_level: int) -> int:
    return CLAN_TREASURY_CAP_BASE + CLAN_TREASURY_CAP_PER_LEVEL * treasury_level


async def academy_pct(db, user_id: int) -> float:
    """+% к Море экспедиций от Академии клана игрока (0.0 если не в клане)."""
    m = await repo.get_member(db, user_id)
    if not m:
        return 0.0
    lvl = await repo.building_level(db, m["clan_id"], "academy")
    return lvl * CLAN_ACADEMY_PCT_PER_LEVEL


# ── Бездна: генерация и открытие ──────────────────────────────────────────────

CELL_EMPTY, CELL_CHEST, CELL_MONSTER, CELL_BOSS, CELL_EXIT = "empty", "chest", "monster", "boss", "exit"
_CENTER = (ABYSS_GRID * ABYSS_GRID) // 2   # 24 для 7×7 — стартовая открытая клетка


def generate_grid(clan_id: int, wk: str, floor: int) -> list[str]:
    """Детерминированная карта 7×7: seed = клан+неделя+этаж (оба процесса
    сгенерят одно и то же). Центр всегда пуст (стартовая клетка)."""
    rng = random.Random(f"{clan_id}:{wk}:{floor}")
    n = ABYSS_GRID * ABYSS_GRID
    cells = [CELL_EMPTY] * n
    idx = [i for i in range(n) if i != _CENTER]
    rng.shuffle(idx)
    boss_i, exit_i = idx[0], idx[1]
    cells[boss_i], cells[exit_i] = CELL_BOSS, CELL_EXIT
    rest = idx[2:]
    n_chest = round(len(rest) * 0.27)
    n_monster = round(len(rest) * 0.27)
    for i in rest[:n_chest]:
        cells[i] = CELL_CHEST
    for i in rest[n_chest:n_chest + n_monster]:
        cells[i] = CELL_MONSTER
    return cells


def _neighbors(i: int) -> list[int]:
    g = ABYSS_GRID
    r, c = divmod(i, g)
    out = []
    if r > 0: out.append(i - g)
    if r < g - 1: out.append(i + g)
    if c > 0: out.append(i - 1)
    if c < g - 1: out.append(i + 1)
    return out


def is_adjacent_open(opened: list[int], cell: int) -> bool:
    if cell == _CENTER:
        return True
    op = set(opened) | {_CENTER}
    return any(nb in op for nb in _neighbors(cell))


async def get_or_create_abyss(db, clan_id: int) -> dict:
    wk = week_key()
    ab = await repo.get_abyss(db, clan_id, wk)
    if not ab:
        await repo.create_abyss(db, clan_id, wk, 1, generate_grid(clan_id, wk, 1))
        ab = await repo.get_abyss(db, clan_id, wk)
    return ab


def abyss_stamina_cost(radar_level: int) -> int:
    return max(5, int(round(ABYSS_OPEN_STAMINA *
                            (1.0 - CLAN_RADAR_STAMINA_PCT_PER_LEVEL * radar_level))))


async def split_loot(db, clan_id: int, user_id: int, shards: int) -> dict:
    """Сплит добычи 70/30 с недельным капом взноса в казну и капом самой казны:
    всё, что не влезло в казну — лично добытчику (💠 в инвентарь)."""
    wk = week_key()
    to_treasury = shards * ABYSS_SPLIT_TREASURY
    contributed = await repo.contrib_this_week(db, clan_id, user_id, wk)
    room_weekly = max(0.0, ABYSS_TREASURY_WEEKLY_CAP - contributed)
    to_treasury = min(to_treasury, room_weekly)
    # Кап самой казны (здание «Казна»)
    m = await repo.get_member(db, user_id)
    t_lvl = await repo.building_level(db, clan_id, "treasury")
    cap = treasury_cap(t_lvl)
    cur = float(m["treasury_shards"]) if m else 0.0
    to_treasury = min(to_treasury, max(0.0, cap - cur))
    personal = shards - to_treasury
    if to_treasury > 0:
        await repo.add_treasury(db, clan_id, shards=to_treasury)
        await repo.add_contrib(db, clan_id, user_id, wk, to_treasury)
    if personal > 0:
        await eco_repo.add_item(db, user_id, "abyss_shard", int(round(personal)))
    return {"treasury": round(to_treasury, 1), "personal": int(round(personal))}


def abyss_monster(floor: int) -> dict:
    """Монстр Бездны — та же кривая, что Врата (этаж Бездны ≈ этаж Врат)."""
    return gates_enemy(floor, 0)


def floor_cp_gate(floor: int) -> int:
    return ABYSS_FLOOR_CP_BASE * floor


def roll_chest() -> int:
    return random.randint(*ABYSS_CHEST_SHARDS)


def roll_monster_loot() -> int:
    return random.randint(*ABYSS_MONSTER_SHARDS)


def roll_boss_loot() -> int:
    return random.randint(*ABYSS_BOSS_SHARDS)


def radar_reveals(radar_level: int) -> bool:
    """L5/L10 Радара — подсветка типов соседних с открытыми клеток."""
    return radar_level >= 5


def public_grid(grid: list[str], opened: list[int], radar_level: int) -> list[dict]:
    """Карта для клиента: закрытые клетки скрыты («туман»), кроме случаев
    Радара L5+ (типы соседних с открытыми) — сервер решает, что видно."""
    op = set(opened) | {_CENTER}
    reveal_near = radar_reveals(radar_level)
    near: set[int] = set()
    if reveal_near:
        for i in op:
            near.update(_neighbors(i))
    out = []
    for i, cell in enumerate(grid):
        if i in op:
            out.append({"i": i, "state": "open", "type": cell})
        elif is_adjacent_open(opened, i):
            t = cell if (reveal_near and i in near) else None
            out.append({"i": i, "state": "reachable", "type": t})
        else:
            out.append({"i": i, "state": "fog", "type": None})
    return out


# ── Войны: стена ──────────────────────────────────────────────────────────────

def wall_hp_from_pets(pets: list[dict]) -> float:
    """Стена = Σ(hp_max + def×10) снапшота питомцев-защитников (до 10)."""
    total = 0.0
    for p in pets[:WAR_WALL_MAX_DEFENDERS]:
        st = pet_battle_stats(p["rarity"], p.get("pet_level", 1))
        total += st["hp_max"] + st["def"] * 10
    return round(total, 1)


def war_wall_enemy(remaining_hp: float) -> dict:
    """«Враг»-стена для Боя 2.0: не атакует; один ран бьёт сегмент ≤SEGMENT_HP."""
    seg = min(remaining_hp, WAR_WALL_SEGMENT_HP)
    return {"name": "Стена узла", "emoji": "🧱",
            "hp_max": int(seg), "atk": 0, "def": 8}


def default_wall_json(members_pets: list[dict]) -> str:
    return json.dumps(members_pets[:WAR_WALL_MAX_DEFENDERS], ensure_ascii=False)