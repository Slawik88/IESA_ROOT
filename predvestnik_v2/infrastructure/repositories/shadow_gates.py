# infrastructure/repositories/shadow_gates.py — БЛОК19 Ч.7: Теневые Врата (24/7).
# Боевой питомец входит во Врата, теряет HP по времени и фармит Тёмную Мору.
# Вытащил до HP=0 → забрал лут. HP дошёл до 0 → лут сгорел. High Risk.
import time

from core.constants import (
    SHADOW_GATE_HP_DRAIN_PER_HOUR, SHADOW_GATE_DARK_MORA_PER_HOUR, SHADOW_GATE_MAX_HOURS,
)
from infrastructure.repositories import pet_combat as combat_repo

_HEAL_COST_PER_HP = 4.0   # 🪙 за 1 HP при лечении во Вратах (сток Моры)


def _tick(hp, hp_max, dark_mora, started_ts, last_tick_ts, rarity, now):
    """Чистый пересчёт: дрейн HP + начисление Тёмной Моры (пока питомец жив,
    не дольше SHADOW_GATE_MAX_HOURS суммарно). → (hp, dark_mora, alive)."""
    elapsed = (now - last_tick_ts) / 3600.0
    if elapsed <= 0 or hp <= 0:
        return max(0.0, hp), dark_mora, hp > 0
    drain_rate = SHADOW_GATE_HP_DRAIN_PER_HOUR * hp_max
    alive_h = hp / drain_rate if drain_rate > 0 else 0.0
    eff_h = min(elapsed, alive_h)                      # начисляем только пока жив
    # cap суммарного фарма SHADOW_GATE_MAX_HOURS от старта
    before = max(0.0, min((last_tick_ts - started_ts) / 3600.0, SHADOW_GATE_MAX_HOURS))
    after = max(0.0, min((now - started_ts) / 3600.0, SHADOW_GATE_MAX_HOURS))
    pay_h = max(0.0, min(eff_h, after - before))
    rate = SHADOW_GATE_DARK_MORA_PER_HOUR.get(rarity, 4)
    dark_mora += rate * pay_h
    new_hp = max(0.0, hp - drain_rate * elapsed)
    return new_hp, dark_mora, new_hp > 0


async def status(db, user_id: int) -> list[dict]:
    """Активные забеги игрока (реконсилированные, read-only)."""
    async with db.execute(
        "SELECT g.pet_id, g.started_at, EXTRACT(EPOCH FROM g.started_at) AS start_ts, "
        "EXTRACT(EPOCH FROM g.last_tick_at) AS tick_ts, g.dark_mora, g.hp, g.hp_max, "
        "g.rarity, p.name, p.species_id "
        "FROM shadow_gate_runs g LEFT JOIN pets p ON p.id = g.pet_id "
        "WHERE g.user_id = ? AND g.status = 'active'",
        (user_id,),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]
    now = time.time()
    out = []
    for r in rows:
        hp, dm, alive = _tick(r["hp"], r["hp_max"], r["dark_mora"],
                              r["start_ts"], r["tick_ts"], r["rarity"], now)
        out.append({
            "pet_id": r["pet_id"], "name": r["name"], "species_id": r["species_id"],
            "rarity": r["rarity"], "hp": round(hp, 1), "hp_max": r["hp_max"],
            "dark_mora": round(dm, 1), "alive": alive,
        })
    return out


async def enter(db, user_id: int, pet_id: int) -> tuple[bool, str]:
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT 1 FROM shadow_gate_runs WHERE pet_id = ?", (pet_id,)
            ) as c:
                if await c.fetchone():
                    return False, "Этот питомец уже во Вратах."
            async with db.execute(
                "SELECT 1 FROM active_expeditions WHERE pet_id = ?", (pet_id,)
            ) as c:
                if await c.fetchone():
                    return False, "Питомец сейчас в экспедиции."
            st = await combat_repo.lock_state(db, pet_id, owner_id=user_id)
            if not st:
                return False, "Питомец не найден."
            if st["hp"] <= 0:
                return False, "У питомца 0 HP — сначала вылечи его."
            # фиксируем актуальное HP в питомце и заводим забег
            await combat_repo.persist(db, pet_id, st["hp"], st["stamina"],
                                      st["hp_max"], st["stamina_max"], st["attack"], st["defense"])
            await db.execute("UPDATE pets SET placement = 'gates' WHERE id = ?", (pet_id,))
            await db.execute(
                "INSERT INTO shadow_gate_runs (pet_id, user_id, hp, hp_max, rarity) "
                "VALUES (?, ?, ?, ?, ?)",
                (pet_id, user_id, st["hp"], st["hp_max"], st["rarity"]),
            )
        return True, f"🌑 {st['name'] or 'Питомец'} вошёл во Врата Бездны."
    except Exception as e:
        return False, f"Ошибка: {e}"


async def collect(db, user_id: int, pet_id: int) -> tuple[bool, str]:
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT EXTRACT(EPOCH FROM started_at) AS start_ts, "
                "EXTRACT(EPOCH FROM last_tick_at) AS tick_ts, dark_mora, hp, hp_max, rarity "
                "FROM shadow_gate_runs WHERE pet_id = ? AND user_id = ? FOR UPDATE",
                (pet_id, user_id),
            ) as c:
                r = await c.fetchone()
            if not r:
                return False, "Этот питомец не во Вратах."
            now = time.time()
            hp, dm, alive = _tick(r["hp"], r["hp_max"], r["dark_mora"],
                                  r["start_ts"], r["tick_ts"], r["rarity"], now)
            await db.execute("DELETE FROM shadow_gate_runs WHERE pet_id = ?", (pet_id,))
            await db.execute(
                "UPDATE pets SET placement = 'storage', hp = ?, combat_regen_at = to_timestamp(?) "
                "WHERE id = ?",
                (hp, now, pet_id),
            )
            if not alive:
                return False, "💀 Питомец еле выбрался — HP дошёл до 0, лут Бездны сгорел!"
            payout = round(dm, 0)
            if payout > 0:
                await db.execute(
                    "UPDATE users SET user_balance_dark_mora = COALESCE(user_balance_dark_mora, 0) + ? "
                    "WHERE user_tg_id = ?",
                    (payout, user_id),
                )
            return True, f"🌑 Возврат из Врат: +{payout:.0f} Тёмной Моры (HP осталось {hp:.0f})."
    except Exception as e:
        return False, f"Ошибка: {e}"


async def heal(db, user_id: int, pet_id: int) -> tuple[bool, str]:
    """Восстановить HP питомца во Вратах за Мору (сток). Полное лечение."""
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT EXTRACT(EPOCH FROM started_at) AS start_ts, "
                "EXTRACT(EPOCH FROM last_tick_at) AS tick_ts, dark_mora, hp, hp_max, rarity "
                "FROM shadow_gate_runs WHERE pet_id = ? AND user_id = ? FOR UPDATE",
                (pet_id, user_id),
            ) as c:
                r = await c.fetchone()
            if not r:
                return False, "Этот питомец не во Вратах."
            now = time.time()
            hp, dm, alive = _tick(r["hp"], r["hp_max"], r["dark_mora"],
                                  r["start_ts"], r["tick_ts"], r["rarity"], now)
            if not alive:
                await db.execute("DELETE FROM shadow_gate_runs WHERE pet_id = ?", (pet_id,))
                await db.execute(
                    "UPDATE pets SET placement = 'storage', hp = 0, combat_regen_at = to_timestamp(?) WHERE id = ?",
                    (now, pet_id),
                )
                return False, "💀 Поздно — питомец уже пал, лут сгорел."
            missing = r["hp_max"] - hp
            if missing <= 0:
                return False, "У питомца уже полное HP."
            cost = round(missing * _HEAL_COST_PER_HP, 0)
            async with db.execute(
                "SELECT COALESCE(user_balance_mora, 0) FROM users WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                bal = float((await c.fetchone())[0])
            if bal < cost:
                return False, f"Нужно {cost:.0f} 🪙 на лечение, не хватает."
            await db.execute(
                "UPDATE users SET user_balance_mora = user_balance_mora - ? WHERE user_tg_id = ?",
                (cost, user_id),
            )
            await db.execute(
                "UPDATE shadow_gate_runs SET hp = ?, dark_mora = ?, last_tick_at = to_timestamp(?) "
                "WHERE pet_id = ?",
                (r["hp_max"], dm, now, pet_id),
            )
        return True, f"💉 Питомец вылечен до полного HP за {cost:.0f} 🪙."
    except Exception as e:
        return False, f"Ошибка: {e}"
