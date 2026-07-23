"""FastAPI/routers/battle.py — Боёвка 3.0 «Руны отряда» (BATTLE_REWORK_CONCEPT.md).

Тонкий адаптер: логика — services/battle3.py, состояние — repositories/battles.py.
Бои идут ОТРЯДОМ юнитов из Казармы (services/barracks.py); мирные питомцы в боях
не участвуют. У юнитов нет персистентного HP — каждый бой с полными силами.
"""
import random
import time

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.constants import (
    GATES2_FLOORS, GATES2_CP_GATE, GATES2_ENTRIES_PER_DAY,
    GATES2_DARK_MORA_BASE, GATES2_DARK_MORA_PER_FLOOR, GATES2_DARK_MORA_MULT,
    GATES2_SHARD_CHANCE,
    GATES2_SHARD_RANGE,
    UNIT_SHARD_DROP_ABYSS_BOSS,
    WAR_NODE_SHIELD_HOURS,
    B4_TUTORIAL_SEED,
)
from core.units import UNITS
from infrastructure.repositories import battles as bt_repo
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories import units as u_repo
from infrastructure.repositories import users as users_repo
from services import battle3 as b3
from services import barracks
from services.battle import rate_limited

router = APIRouter(prefix="/combat2", tags=["battle3"])


class GatesEnterRequest(BaseModel):
    floor: int


class ActionRequest(BaseModel):
    battle_id: int
    type: str
    unit_i: int | None = None
    cell: dict | None = None
    target_i: int | None = None


class QteRequest(BaseModel):
    battle_id: int
    tap_offset_ms: int


class UltRequest(BaseModel):
    battle_id: int
    unit_i: int


class BattleIdRequest(BaseModel):
    battle_id: int


async def get_active_b3(db, uid: int, mode: str | None = None) -> dict | None:
    """Активный бой в формате 3.0; старые бои (движок стоек) закрываются молча."""
    row = await bt_repo.get_active(db, uid, mode)
    if not row:
        return None
    st = row["state"]
    if "ally" not in st or "grid" not in st:
        # бой доклеточного движка (3.0) — закрываем как отмену, без штрафа поражения
        await bt_repo.finish(db, row["id"], "cancelled")
        await db.commit()
        return None
    return row


# ── Врата ─────────────────────────────────────────────────────────────────────

@router.get("/gates")
async def gates_overview(db=Depends(get_db), user=Depends(require_tg_user)):
    """Врата: этажи с CP-гейтом, входы, отряд из Казармы, активный бой."""
    uid = user["id"]
    cp = await barracks.squad_cp(db, uid)
    used = await bt_repo.count_today(db, uid, "gates")
    squad = await barracks.squad_units(db, uid)
    active = await get_active_b3(db, uid)
    return {
        "cp": cp,
        "entries_left": max(0, GATES2_ENTRIES_PER_DAY - used),
        "floors": [{"floor": f, "cp_gate": GATES2_CP_GATE[f], "open": cp >= GATES2_CP_GATE[f],
                    "enemies": 2 if f <= 2 else 3,
                    "reward_dark": round((GATES2_DARK_MORA_BASE + GATES2_DARK_MORA_PER_FLOOR * f) * GATES2_DARK_MORA_MULT),
                    "unit_shards": True}
                   for f in range(1, GATES2_FLOORS + 1)],
        # Честные шансы дропа (легенда UI раньше говорила «шанс 🔷» без цифр)
        # БЛ2: осколки юнита гарантированы с ЛЮБОГО этажа (растут с этажом) — см. _gates_reward.
        "loot": {"shard_chance_pct": round(GATES2_SHARD_CHANCE * 100),
                 "shard_range": list(GATES2_SHARD_RANGE),
                 "unit_shard_chance_pct": 100,
                 "unit_shard_range": [1, 4]},
        "squad": [{"unit_id": s["unit_id"], "level": s["level"], "slot": s["slot"],
                   "name": UNITS[s["unit_id"]]["name"],
                   "emoji": UNITS[s["unit_id"]]["emoji"]} for s in squad],
        "squad_cp": await barracks.squad_cp(db, uid),
        "active_battle": b3.public_state(active["state"], active["id"]) if active else None,
        # Онбординг боя: пройден ли «Первый бой» (клиент решает автопредложение обучения).
        "tutorial_done": await users_repo.get_combat_tutorial_done(db, uid),
    }


@router.post("/gates/enter")
async def gates_enter(body: GatesEnterRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    uid = user["id"]
    if not (1 <= body.floor <= GATES2_FLOORS):
        raise HTTPException(400, "Нет такого этажа.")
    if await get_active_b3(db, uid):
        raise HTTPException(400, "У тебя уже идёт бой — сначала закончи его.")
    if await bt_repo.count_today(db, uid, "gates") >= GATES2_ENTRIES_PER_DAY:
        raise HTTPException(400, f"Лимит Врат: {GATES2_ENTRIES_PER_DAY} входа в день.")
    cp = await barracks.squad_cp(db, uid)
    if cp < GATES2_CP_GATE[body.floor]:
        raise HTTPException(400, f"Этаж {body.floor} требует ⚡ {GATES2_CP_GATE[body.floor]} "
                                 f"Силы (у тебя {cp}).")
    squad = await barracks.squad_units(db, uid)
    if not squad:
        raise HTTPException(400, "Сначала собери отряд в Казарме (Арена → Казарма).")
    state = b3.new_battle_state(squad, b3.gates_enemy_squad(body.floor), "gates",
                                {"floor": body.floor})
    bid = await bt_repo.create(db, uid, 0, "gates", body.floor, b3.dumps(state))
    await db.commit()
    return b3.public_state(state, bid)


# ── Туториал: скриптованный «Первый бой» ──────────────────────────────────────

@router.post("/tutorial/start")
async def tutorial_start(db=Depends(get_db), user=Depends(require_tg_user)):
    """Онбординг боя: запустить/перезапустить «Первый бой». Реальный серверный бой на
    синтетическом отряде против слабых врагов; не тратит вход дня (mode='tutorial' не
    учитывается count_today), без награды, анти-фейл (hp≥1). Детерминирован (фикс-сид)."""
    uid = user["id"]
    if await get_active_b3(db, uid):
        raise HTTPException(400, "У тебя уже идёт бой — сначала закончи его.")
    state = b3.new_battle_state(b3.tutorial_squad(), b3.tutorial_enemy_squad(),
                                "tutorial", {"tutorial": True, "seed": B4_TUTORIAL_SEED})
    bid = await bt_repo.create(db, uid, 0, "tutorial", 0, b3.dumps(state))
    await db.commit()
    return b3.public_state(state, bid)


# ── Финализация исходов ───────────────────────────────────────────────────────

async def _gates_reward(db, uid: int, floor: int, state: dict | None = None) -> dict:
    from core.constants import (B4_REWARD_NO_LOSS_MULT, B4_REWARD_FAST_MULT,
                                B4_REWARD_FAST_ROUNDS)
    # БЛ3: множитель за скилл — без потерь юнитов ×1.5, победа ≤6 раундов ×1.25 (стакаются)
    mult = 1.0
    if state:
        allies = state.get("ally", {}).get("units", [])
        if allies and all(u.get("alive") for u in allies):
            mult *= B4_REWARD_NO_LOSS_MULT
        if state.get("round", 99) <= B4_REWARD_FAST_ROUNDS:
            mult *= B4_REWARD_FAST_MULT
    # Блок 15 эт.2: −60% добычи 🌑 из Врат (×GATES2_DARK_MORA_MULT), затем реликвия/скилл.
    dark = (GATES2_DARK_MORA_BASE + GATES2_DARK_MORA_PER_FLOOR * floor) * GATES2_DARK_MORA_MULT
    from infrastructure.repositories.shadow_merchant import get_gates_dark_bonus
    _sr_bonus = await get_gates_dark_bonus(db, uid)
    if _sr_bonus > 0:
        dark = int(dark * (1 + _sr_bonus))
    dark = int(round(dark * mult))
    await db.execute(
        "UPDATE users SET user_balance_dark_mora = COALESCE(user_balance_dark_mora,0) + ? "
        "WHERE user_tg_id = ?", (dark, uid))
    shards = 0
    if random.random() < GATES2_SHARD_CHANCE:
        shards = int(round(random.randint(*GATES2_SHARD_RANGE) * mult))
        await eco_repo.add_item(db, uid, "abyss_shard", shards)
    # БЛ2: осколки ЮНИТА гарантированно с ЛЮБОГО этажа (растут с этажом), а не 35% с эт.5+.
    # эт.1–2 → 1, эт.3–4 → 2, эт.5–6 → 2–3 (без множителя награды — это ресурс прокачки).
    n = (floor + 1) // 2 + (random.randint(0, 1) if floor >= 5 else 0)
    target = random.choice(list(UNITS))
    await u_repo.add_shards(db, uid, target, n)
    unit_shards = {"unit_id": target, "name": UNITS[target]["name"],
                   "emoji": UNITS[target]["emoji"], "n": n}
    return {"dark_mora": dark, "shards": shards, "unit_shards": unit_shards,
            "reward_mult": round(mult, 2)}


async def _abyss_finalize(db, uid: int, user: dict, state: dict, won: bool) -> dict | None:
    """Исход боя за клетку Бездны: победа открывает клетку, лут 70/30, босс —
    ключ этажа + таргет-осколки юнита."""
    ab_ctx = state.get("abyss") or {}
    clan_id, wk, cell = ab_ctx.get("clan_id"), ab_ctx.get("week"), ab_ctx.get("cell")
    if not clan_id:
        return None
    from infrastructure.repositories import clans2 as c2_repo
    from services import clans2 as c2
    uname = user.get("username") or f"id{uid}"
    if not won:
        await c2_repo.abyss_log(db, clan_id, uid, f"☠️ Отряд @{uname} пал в Бездне")
        return None
    ab = await c2_repo.get_abyss(db, clan_id, wk)
    if not ab or cell in ab["opened"]:
        return None
    ab["opened"].append(cell)
    is_boss = bool(ab_ctx.get("boss"))
    shards = c2.roll_boss_loot() if is_boss else c2.roll_monster_loot()
    split = await c2.split_loot(db, clan_id, uid, shards)
    await c2_repo.save_abyss(db, clan_id, wk, ab["opened"],
                             key_found=True if is_boss else None)
    unit_shards = None
    if is_boss:
        target = random.choice(list(UNITS))
        n = random.randint(*UNIT_SHARD_DROP_ABYSS_BOSS)
        await u_repo.add_shards(db, uid, target, n)
        unit_shards = {"unit_id": target, "name": UNITS[target]["name"],
                       "emoji": UNITS[target]["emoji"], "n": n}
    await c2_repo.abyss_log(
        db, clan_id, uid,
        (f"👑 @{uname} сразил БОССА: +{shards}🔷 и ключ этажа!" if is_boss
         else f"⚔️ @{uname} победил монстров: +{shards}🔷"))
    return {"shards": shards, "split": split, "boss_key": is_boss,
            "unit_shards": unit_shards}


async def _war_finalize(db, uid: int, state: dict) -> dict | None:
    """Урон рана засчитывается стене; пробитие → узел переходит атакующим."""
    war_ctx = state.get("war") or {}
    war_id = war_ctx.get("war_id")
    if not war_id:
        return None
    from infrastructure.repositories import clans2 as c2_repo
    dmg = float(state.get("dmg_total", 0))
    if dmg <= 0:
        return {"damage": 0}
    total = await c2_repo.add_war_damage(db, war_id, uid, dmg)
    async with db.execute("SELECT * FROM clan_wars2 WHERE id = ?", (war_id,)) as c:
        war = dict(await c.fetchone())
    node = await c2_repo.get_node(db, war["node_id"])
    breached = total >= float(node["wall_hp_max"] or 0)
    if breached and war["status"] == "active":
        await c2_repo.finish_war(db, war_id, "won")
        await c2_repo.transfer_node(db, war["node_id"], war["attacker_clan_id"],
                                    "[]", 1000.0, WAR_NODE_SHIELD_HOURS)
        await c2_repo.abyss_log(db, war["attacker_clan_id"], uid,
                                f"🏰 Узел «{node['name']}» ЗАХВАЧЕН! Щит 48ч.")
    return {"damage": int(dmg), "wall_total": int(total),
            "wall_hp_max": int(node["wall_hp_max"] or 0), "breached": breached}


async def _finalize_if_over(db, uid: int, user: dict, row: dict, state: dict) -> dict | None:
    """Если бой кончился — статус в БД + награды режима. Возвращает reward|None.

    БАГ 2026-07-23: bt_repo.finish() ниже выполняется через PGAdapter.execute(),
    который автокоммитится МГНОВЕННО (commit() — no-op без явного BEGIN, см.
    infrastructure/pg_adapter.py) — статус боя необратимо становится won/lost
    ДО того, как посчитаны награды режима. Раньше, если начисление наград кидало
    исключение (напр. set_combat_tutorial_done на ещё не задеплоенной колонке),
    оно улетало наверх необработанным: клиент получал голый 500, а бой на сервере
    уже навсегда завершён — любое следующее действие (атака/Сдаться/Выйти)
    отвечало 404 «бой не найден», хотя клиент ещё рисовал живого врага. Теперь
    начисление наград изолировано: сбой здесь не должен стоить игроку залипшего
    боя — победа/поражение долетают до клиента всегда, просто без «reward» в тот
    редкий раз, когда конкретная награда сама сломалась (это видно в логах)."""
    if state.get("status") not in ("won", "lost"):
        return None
    won = state["status"] == "won"
    await bt_repo.finish(db, row["id"], state["status"])
    reward = None
    try:
        if row["mode"] == "gates" and won:
            reward = await _gates_reward(db, uid, int(row["ref_id"]), state)
        elif row["mode"] == "abyss":
            reward = await _abyss_finalize(db, uid, user, state, won)
        elif row["mode"] == "war":
            reward = await _war_finalize(db, uid, state)
        elif row["mode"] == "tutorial" and won:
            # Онбординг боя: «Первый бой» — без награды (повтор через «?» = эксплойт),
            # только отмечаем прохождение. Экран победы покажет поздравление без лута.
            await users_repo.set_combat_tutorial_done(db, uid)
    except Exception:
        logger.exception(f"[battle] начисление награды упало (battle_id={row['id']}, "
                          f"mode={row['mode']}, uid={uid}) — бой всё равно завершается корректно")
        reward = None
    return reward


async def _load_battle(db, uid: int, battle_id: int) -> dict:
    row = await get_active_b3(db, uid)
    if not row or row["id"] != battle_id:
        raise HTTPException(404, "Бой не найден или уже завершён.")
    return row


async def _respond(db, uid: int, user: dict, row: dict, state: dict, extra: dict) -> dict:
    reward = await _finalize_if_over(db, uid, user, row, state)
    if state.get("status") in ("won", "lost"):
        await db.commit()
    else:
        await bt_repo.save_state(db, row["id"], b3.dumps(state), time.time())
        await db.commit()
    return {**b3.public_state(state, row["id"]), **extra, "reward": reward}


# ── Действия боя ──────────────────────────────────────────────────────────────

@router.post("/battle/action")
async def battle_action(body: ActionRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    uid = user["id"]
    row = await _load_battle(db, uid, body.battle_id)
    if rate_limited(row.get("last_action_at")):
        raise HTTPException(429, "Слишком быстро.")
    state = row["state"]
    if state.get("pending"):
        raise HTTPException(400, "Сначала заверши QTE.")
    action = {"type": body.type, "unit_i": body.unit_i,
              "cell": body.cell, "target_i": body.target_i}
    res = b3.apply_action(state, action)
    if not res.get("ok"):
        # действие отклонено движком (мало AP / вне дальности / нет LoS и т.п.)
        raise HTTPException(400, res.get("err") or "Недопустимое действие.")
    return await _respond(db, uid, user, row, state, {"turn": res})


@router.post("/battle/qte")
async def battle_qte(body: QteRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    uid = user["id"]
    row = await _load_battle(db, uid, body.battle_id)
    state = row["state"]
    if not state.get("pending"):
        raise HTTPException(400, "Нет ожидающего QTE.")
    res = b3.resume_qte(state, body.tap_offset_ms)
    return await _respond(db, uid, user, row, state, {"turn": res})


@router.post("/battle/ult")
async def battle_ult(body: UltRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    uid = user["id"]
    row = await _load_battle(db, uid, body.battle_id)
    state = row["state"]
    if state.get("pending"):
        raise HTTPException(400, "Сначала заверши QTE.")
    a = state["ally"]
    if a["rage"] < 100:
        raise HTTPException(400, "Ярость ещё не полна.")
    if not (0 <= body.unit_i < len(a["units"])) or not a["units"][body.unit_i]["alive"]:
        raise HTTPException(400, "Юнит недоступен.")
    res = b3.request_ult(state, body.unit_i)
    return await _respond(db, uid, user, row, state, {"turn": res})


@router.post("/battle/flee")
async def battle_flee(body: BattleIdRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Сдаться: бой закрывается поражением (награды не начисляются, вход потрачен)."""
    uid = user["id"]
    row = await _load_battle(db, uid, body.battle_id)
    state = row["state"]
    state["status"] = "lost"
    return await _respond(db, uid, user, row, state, {})


@router.post("/battle/cancel")
async def battle_cancel(body: BattleIdRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Выйти из боя без последствий: вход дня потрачен (создание боя уже засчитано
    в count_today), но это НЕ поражение — минуя _finalize_if_over напрямую, чтобы не
    сработали ни награды, ни лог-сообщения поражения (напр. abyss «Отряд пал»), ни
    урон стене войны. Юниты не персистентны (полные силы каждый бой) — сбрасывать
    отдельно нечего."""
    uid = user["id"]
    row = await _load_battle(db, uid, body.battle_id)
    await bt_repo.finish(db, row["id"], "cancelled")
    await db.commit()
    return {"ok": True}
