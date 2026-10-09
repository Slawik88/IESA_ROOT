#!/usr/bin/env python3
"""Билды питомцев v2 на реальных валютах игры: Мора, Алмазы, Эссенция, ключ, Лакомство, Талисман.
Находки делят таблицу весов (нулевая сумма): бонус одной категории делает остальные реже.
Суточные потолки не дают разогнать доход слотами и бросками.
Запуск: python3 tools/pets_v2_build_sim.py"""
from __future__ import annotations
import random

# вес категории при одном броске находки
BASE = {"Мора": 62, "Лакомство": 14, "Талисман": 6, "Алмаз": 2, "Эссенция": 3, "Бонус Следов": 13}
CAP = 2.5                      # множитель категории не выше x2.5
VALUE = {"Мора": 6, "Алмаз": 1, "Эссенция": 3}   # среднее значение одной находки
DAILY_CAP = {"Мора": 60, "Алмаз": 1, "Эссенция": 4}   # потолок дохода в сутки на аккаунт
WEEK_CAP = {"Алмаз": 2}                                # и в неделю
ROLLS = {3: 1, 6: 2, 9: 3, 12: 2, 24: 3}               # бросков за занятие

BUILDS = {
    "без сборки":                              {},
    "Копилка (кот + Нюх, Мора)":               {"Мора": 1.3, "Лакомство": 0.8},
    "Искатель (сова + Искатель + Скрупулёзный)": {"Алмаз": 2.5, "Эссенция": 2.5, "Мора": 0.75, "Бонус Следов": 0.7},
    "Мастер талисманов (жук + Старатель)":     {"Талисман": 2.5, "Мора": 0.85},
    "Кормилец (кот + Кормилец)":               {"Лакомство": 2.2, "Мора": 0.85},
    "Универсал (дракон)":                      {k: 1.12 for k in BASE},
}
PROFILES = {  # занятий в сутки (часы), дней игры в месяц
    "казуал": ([9], 24),
    "обычный": ([9, 3], 27),
    "активный (3 слота)": ([9, 6, 6, 3], 30),
    "максимум (слоты, без пропусков)": ([9, 9, 9, 9, 3, 3], 30),
}


def shares(mods: dict) -> dict:
    w = {k: BASE[k] * min(CAP, mods.get(k, 1.0)) for k in BASE}
    s = sum(w.values())
    return {k: v / s for k, v in w.items()}


def month(build: dict, runs: list[int], days: int, seed: int = 7) -> dict:
    rnd = random.Random(seed)
    sh = shares(build)
    cats, probs = list(sh), list(sh.values())
    out = {k: 0.0 for k in BASE}
    week = {k: 0.0 for k in WEEK_CAP}
    for d in range(days):
        if d % 7 == 0:
            week = {k: 0.0 for k in WEEK_CAP}
        today = {k: 0.0 for k in DAILY_CAP}
        for hours in runs:
            for _ in range(ROLLS[hours]):
                c = rnd.choices(cats, probs)[0]
                amount = VALUE.get(c, 1)
                if c in DAILY_CAP:
                    amount = min(amount, DAILY_CAP[c] - today[c])
                if c in WEEK_CAP:
                    amount = min(amount, WEEK_CAP[c] - week[c])
                    week[c] += max(amount, 0)
                if c in today:
                    today[c] += max(amount, 0)
                out[c] += max(amount, 0)
    return out


if __name__ == "__main__":
    print("Суммарный доход в месяц (Мора, Алмазы, Эссенция — штуки валюты; остальное — находки)")
    print(f"{'профиль / сборка':<60}" + "".join(f"{k:>13}" for k in BASE))
    for pname, (runs, days) in PROFILES.items():
        for bname, mods in BUILDS.items():
            if pname in ("казуал", "максимум (слоты, без пропусков)") or bname in ("без сборки", "Искатель (сова + Искатель + Скрупулёзный)"):
                r = month(mods, runs, days)
                print(f"{(pname + ' / ' + bname)[:59]:<60}" + "".join(f"{r[k]:>13.1f}" for k in BASE))
