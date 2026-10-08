#!/usr/bin/env python3
"""Баланс прокачки питомцев v2: симуляция 30/90/180 дней для разных игроков.
Запуск: python3 balance_sim.py
Все числа ниже — те же, что в PETS_V2_DESIGN.md. Меняешь число — перезапускаешь."""
from __future__ import annotations
import random

# ── Параметры (единый источник правды для дизайна) ─────────────────────────
MAX_LEVEL = 30
POOL_FULL = 500          # Следов в сутки на аккаунт по полной ставке
SOFT_WIDTH = 500         # следующие 500 «сырых» Следов в сутки идут по 25 %; дальше 0
SOFT_RATE = 0.25
RUN_XP = {3: 40, 6: 95, 9: 160}        # базовые Следы за поход
EXPEDITION_MULT = 1.2                  # экспедиция чуть щедрее (решение маршрута)
REPEAT_DECAY = 0.75      # повтор того же маршрута в те же сутки: ×0.75 за каждый повтор
FEED_XP = 10             # накормить питомца (раз в сутки на питомца)
DAILY_TASKS_XP = 60      # три ежедневных задания
WEEKLY_XP = 300          # «Большая охота» раз в неделю
# Связь (дни, когда с питомцем что-то делали) открывает потолок уровня
BOND_GATES = [(5, 2), (10, 21), (15, 50), (20, 90), (25, 140), (30, 200)]  # (потолок, дней связи)
RARITY_COST = {"common": 1.0, "uncommon": 1.1, "rare": 1.25, "epic": 1.5, "legendary": 1.8}


def level_cost(level: int, rarity: str = "common") -> int:
    """Следов на переход level -> level+1."""
    return round(40 * level ** 1.7 * RARITY_COST[rarity])


def ceiling(bond_days: int) -> int:
    """Максимальный уровень при данной Связи: новый потолок открывается через (потолок, дни)."""
    out = 5
    for lv, days in BOND_GATES:
        if bond_days >= days:
            out = min(MAX_LEVEL, lv + 5)
    return out


class Pet:
    def __init__(self, rarity="common"):
        self.rarity, self.level, self.xp, self.bond = rarity, 1, 0, 0

    def add(self, amount: float):
        self.xp += amount
        while self.level < min(MAX_LEVEL, ceiling(self.bond)):
            need = level_cost(self.level, self.rarity)
            if self.xp < need:
                break
            self.xp -= need
            self.level += 1
        # потолок: излишек хранится, но не уходит выше (до открытия ступени)
        cap = min(MAX_LEVEL, ceiling(self.bond))
        if self.level >= cap:
            self.xp = min(self.xp, level_cost(self.level, self.rarity) - 1) if self.level < MAX_LEVEL else 0


def pool_apply(before: float, raw: float) -> float:
    """Сколько Следов реально зачтётся. before — «сырые» Следы, полученные за сутки до этого."""
    full = max(0.0, min(raw, POOL_FULL - before))
    soft_before = max(0.0, before - POOL_FULL)
    soft = max(0.0, min(raw - full, SOFT_WIDTH - soft_before))
    return full + soft * SOFT_RATE


PROFILES = {
    # name: (runs per day, [hours of run], pets used, does tasks, feeds, active days fraction)
    "казуал (1 вход/день, ночной поход 9ч)": dict(runs=[9], pets=1, tasks=False, feed=False, play=0.8),
    "обычный (2–3 входа, 9ч+3ч, задания)": dict(runs=[9, 3], pets=1, tasks=True, feed=True, play=0.9),
    "активный (все слоты, 3 питомца)": dict(runs=[9, 6, 6, 3], pets=3, tasks=True, feed=True, play=1.0),
    "фармер (макс. слоты, 5 питомцев, без пропусков)": dict(runs=[9, 9, 9, 9, 3, 3], pets=5, tasks=True, feed=True, play=1.0),
}


def simulate(profile: dict, days: int, seed=1, rarities=None):
    rnd = random.Random(seed)
    rarities = rarities or ["common"] * profile["pets"]
    pets = [Pet(r) for r in rarities[: profile["pets"]]]
    total_credited = 0.0
    keys_cap = 0
    for d in range(days):
        if rnd.random() > profile["play"]:
            continue
        gained_today = 0.0
        used_routes: dict[tuple, int] = {}
        fed = set()
        for i, h in enumerate(profile["runs"]):
            pet = pets[i % len(pets)]
            pet.bond += 1 if pet not in fed else 0
            fed.add(pet)
            route = (i % 4, h)  # 4 разных маршрута на длительность
            k = used_routes.get(route, 0)
            used_routes[route] = k + 1
            raw = RUN_XP[h] * (REPEAT_DECAY ** k) * (EXPEDITION_MULT if i % 3 == 2 else 1.0)
            c = pool_apply(gained_today, raw)
            gained_today += raw
            pet.add(c)
            total_credited += c
        if profile["feed"]:
            for p in pets:
                c = pool_apply(gained_today, FEED_XP); gained_today += FEED_XP; p.add(c); total_credited += c
        if profile["tasks"]:
            c = pool_apply(gained_today, DAILY_TASKS_XP); gained_today += DAILY_TASKS_XP
            pets[0].add(c); total_credited += c
            if d % 7 == 6:
                c = pool_apply(gained_today, WEEKLY_XP); gained_today += WEEKLY_XP
                pets[0].add(c); total_credited += c
    return pets, total_credited


def main():
    print("Цена уровней (common):")
    cum = 0
    for lv in range(1, MAX_LEVEL):
        cum += level_cost(lv)
        if lv in (1, 4, 5, 9, 10, 14, 15, 19, 20, 24, 25, 29):
            print(f"  {lv:>2}→{lv+1:<2}: {level_cost(lv):>6} Следов, всего до {lv+1}: {cum:>7}")
    print(f"\nСуточный предел: {POOL_FULL} по полной + до {SOFT_WIDTH*SOFT_RATE:.0f} в мягкой зоне = {POOL_FULL+SOFT_WIDTH*SOFT_RATE:.0f} Следов/сутки на аккаунт\n")
    for name, prof in PROFILES.items():
        print(name)
        for days in (30, 90, 180, 365):
            pets, tot = simulate(prof, days)
            lv = sorted((p.level for p in pets), reverse=True)
            print(f"   {days:>3} дн: уровни питомцев {lv}, зачислено Следов {tot:,.0f}")
        print()


if __name__ == "__main__":
    main()
