#!/usr/bin/env python3
"""Аудит экономики питомцев v2 по реальным правилам core/pets_v2.py и каталогу сундуков.
Считает месячный доход (Мора, Алмазы, Эссенция, ключи, ценность ключей) для профилей игроков и сборок.
Запуск: PYTHONPATH=. python3 tools/pets_v2_economy_audit.py"""
from __future__ import annotations
import random
from core import pets_v2 as p
from core import chests_v1 as ch

MONTHS = 300
PROFILES = {  # занятия в сутки (часы походов), дней игры в месяц
    "казуал": ([9], 24), "обычный": ([9, 3], 27), "активный (3 слота)": ([9, 6, 6, 3], 30),
    "максимум (3 слота + дозор)": ([9, 9, 9, 9, 3, 3], 30),
}
BUILDS = {  # (призвание, черты, любимая еда)
    "без сборки": (None, (), False),
    "Копилка": (None, ("piggybank",), False),
    "Искатель": ("seeker", ("meticulous",), False),
    "Следопыт+Нюх": ("tracker", ("nose",), False),
    "Привередливый (сыт)": (None, ("picky",), True),
}


def key_value() -> dict:
    """Ожидаемая ценность одного ключа: Мора, Алмазы, Зарники (карты и джокеры считаем отдельно)."""
    total = sum(ch.STAR_WEIGHTS.values())
    out = {"mora": 0.0, "diamonds": 0.0, "zarniki": 0.0}
    for star, w in ch.STAR_WEIGHTS.items():
        row = ch.REWARD_WEIGHTS[star]
        share = w / total
        for kind, pct in row.items():
            if kind == "mora":
                lo, hi = ch.MORA_RANGES[star]; out["mora"] += share * pct / 100 * (lo + hi) / 2
            elif kind == "diamonds":
                lo, hi = ch.DIAMOND_RANGES[star]; out["diamonds"] += share * pct / 100 * (lo + hi) / 2
            elif kind == "zarniki":
                lo, hi = ch.ZARNIKI_RANGES[star]; out["zarniki"] += share * pct / 100 * (lo + hi) / 2
    return out


def month(hours_list, days, build, rng, level=12):
    calling, traits, fed = build
    fx = p.build_effects(calling, traits, hours=9, fed_favorite=fed)
    res = {"mora": 0.0, "diamonds": 0.0, "essence": 0.0, "keys": 0.0, "xp": 0.0}
    week_diamond = {}
    week_extra = {}
    week_keys = {}
    for day in range(days):
        finds = {"mora": 0.0, "diamond": 0.0, "essence": 0.0}
        keys = 0
        raw_today = 0.0
        for i, h in enumerate(hours_list):
            shares = p.find_shares(fx["find_mods"], species_id="salt_fox", level=level)
            cats, w = list(shares), list(shares.values())
            for _ in range(p.ROLLS[("run", h)]):
                c = rng.choices(cats, w)[0]
                if c in ("treat", "talisman", "bonus_xp"):
                    continue
                amount = rng.randint(3, 9) if c == "mora" else rng.randint(2, 4) if c == "essence" else 1
                wk = week_diamond.get(day // 7, 0)
                allowed = p.cap_find(c, amount, today=finds[c], this_week=wk if c == "diamond" else 0.0)
                allowed = int(allowed)
                finds[c] += allowed
                if c == "diamond":
                    week_diamond[day // 7] = wk + allowed
            if i == 0 and keys < 1 and week_keys.get(day // 7, 0) < p.KEYS_PER_WEEK_MAX:
                keys += 1
                week_keys[day // 7] = week_keys.get(day // 7, 0) + 1
            if keys < p.KEYS_PER_DAY_MAX and week_keys.get(day // 7, 0) < p.KEYS_PER_WEEK_MAX and week_extra.get(day // 7, 0) < p.KEY_EXTRA_WEEKLY_MAX and rng.random() * 100 < fx["extra_key_chance"]:
                keys += 1
                week_keys[day // 7] = week_keys.get(day // 7, 0) + 1
                week_extra[day // 7] = week_extra.get(day // 7, 0) + 1
            raw = p.run_xp_raw(h, repeats_today=i) * fx["xp_mult"]
            res["xp"] += p.pool_credit(raw_today, raw); raw_today += raw
        res["mora"] += finds["mora"]; res["diamonds"] += finds["diamond"]; res["essence"] += finds["essence"]; res["keys"] += keys
    return res


def main() -> None:
    kv = key_value()
    print(f"Ценность ключа (без карт и джокеров): Мора {kv['mora']:.1f}, Алмазы {kv['diamonds']:.2f}, Зарники {kv['zarniki']:.2f}")
    rng = random.Random(11)
    print(f"\nДоход питомцев за месяц, среднее по {MONTHS} симуляциям (питомец 12 уровня, потолки включены):")
    print(f"{'профиль':28}{'сборка':22}{'Мора':>7}{'Алмаз':>7}{'Эссенц.':>9}{'ключей':>8}{'Мора с ключей':>15}{'Алмаз с ключей':>16}")
    for pname, (hours, days) in PROFILES.items():
        for bname, build in BUILDS.items():
            acc = {k: 0.0 for k in ("mora", "diamonds", "essence", "keys")}
            for _ in range(MONTHS):
                r = month(hours, days, build, rng)
                for k in acc: acc[k] += r[k] / MONTHS
            print(f"{pname:28}{bname:22}{acc['mora']:7.0f}{acc['diamonds']:7.1f}{acc['essence']:9.1f}{acc['keys']:8.1f}"
                  f"{acc['keys'] * kv['mora']:15.0f}{acc['keys'] * kv['diamonds']:16.1f}")
    print("\nПрочие источники Эссенции: ступени 80 на питомца за всю игру; испытание недели 5/12/20 (до ~80 в месяц при полной сборке).")


if __name__ == "__main__":
    main()
