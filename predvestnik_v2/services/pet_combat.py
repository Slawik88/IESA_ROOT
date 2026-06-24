"""services/pet_combat.py — БЛОК19 Ч.4: движок боевых питомцев (HP/Stamina).

Боевые статы выводятся из редкости×уровня. HP/Stamina — time-based (без планировщика):
Stamina пассивно копится, HP регенится ИЗ Stamina (пустая Stamina → HP стоит → нужен
медикамент = сток валюты). Реконсиляция считается на лету по combat_regen_at.
Чистая логика; запись/атомарность — в infrastructure/repositories/pet_combat.py.
"""
import time

from core.constants import (
    COMBAT_BASE_HP, COMBAT_BASE_STAMINA, COMBAT_BASE_ATK, COMBAT_BASE_DEF,
    COMBAT_LEVEL_SCALE, COMBAT_STAMINA_REGEN_PER_HOUR, COMBAT_HP_REGEN_PER_HOUR,
    COMBAT_STAMINA_PER_HP,
)

_RARITIES = ("common", "rare", "epic", "legendary", "mythic")


def combat_stats(rarity: str, level: int) -> dict:
    """Максимумы и atk/def боевого питомца по редкости и уровню."""
    r = rarity if rarity in _RARITIES else "common"
    scale = 1.0 + COMBAT_LEVEL_SCALE * max(0, (level or 1) - 1)
    return {
        "hp_max":      int(COMBAT_BASE_HP[r] * scale),
        "stamina_max": int(COMBAT_BASE_STAMINA[r] * scale),
        "attack":      int(COMBAT_BASE_ATK[r] * scale),
        "defense":     int(COMBAT_BASE_DEF[r] * scale),
    }


def reconcile(hp: float, hp_max: float, stamina: float, stamina_max: float,
              last_ts: float, now: float | None = None) -> tuple[float, float]:
    """Текущие (hp, stamina) с учётом прошедшего времени. Чистая функция.
    1) пассивно копим Stamina; 2) регеним HP, тратя Stamina."""
    now = now if now is not None else time.time()
    if last_ts is None:
        last_ts = now
    elapsed_h = (now - last_ts) / 3600.0
    if elapsed_h <= 0:
        return max(0.0, min(hp, hp_max)), max(0.0, min(stamina, stamina_max))
    stamina = min(stamina_max, stamina + COMBAT_STAMINA_REGEN_PER_HOUR * stamina_max * elapsed_h)
    if hp < hp_max and stamina > 0:
        want = COMBAT_HP_REGEN_PER_HOUR * hp_max * elapsed_h
        want = min(want, hp_max - hp, stamina / COMBAT_STAMINA_PER_HP)
        hp += want
        stamina -= want * COMBAT_STAMINA_PER_HP
    return max(0.0, min(hp, hp_max)), max(0.0, min(stamina, stamina_max))


def now_ts() -> float:
    return time.time()
