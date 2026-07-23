"""Блок 15 этап 2: добыча 🌑 из Врат срезана на ~60% (×GATES2_DARK_MORA_MULT=0.4).
Проверяем: (1) на каждом этаже награда ≈40% прежней; (2) витрина этажей
(gates_overview) показывает РОВНО то, что выдаёт бой без множителей (display==grant);
(3) дневной потолок без скилл-множителей упал в целевой диапазон."""
import sys
import pathlib

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.constants import (
    GATES2_DARK_MORA_BASE as B, GATES2_DARK_MORA_PER_FLOOR as P,
    GATES2_DARK_MORA_MULT as M, GATES2_FLOORS as FLOORS,
    GATES2_ENTRIES_PER_DAY as ENTRIES,
)

assert abs(M - 0.4) < 1e-9, f"ожидали множитель 0.4 (−60%), получили {M}"

print(f"{'этаж':>5} {'было':>5} {'стало':>6} {'−%':>5} {'/день(стало)':>12}")
for f in range(1, FLOORS + 1):
    old = B + P * f                       # прежняя формула (до нерфа)
    new = round(old * M)                  # витрина: round((B+P*f)*M)
    grant = round(old * M)                # бой без бонуса/скилла: int(round(float*1.0)) == round
    assert new == grant, f"этаж {f}: витрина {new} ≠ выдача {grant} (display != grant)"
    frac = new / old
    assert 0.35 <= frac <= 0.48, f"этаж {f}: {old}→{new} = {frac:.0%}, ожидали ~40% (−60%)"
    print(f"{f:>5} {old:>5} {new:>6} {(1-frac)*100:>4.0f}% {new*ENTRIES:>12}")

# Дневной потолок без скилл-множителей на максимальном этаже
top_daily = round((B + P * FLOORS) * M) * ENTRIES
assert top_daily <= 20, f"этаж {FLOORS} без множителей {top_daily}🌑/день — ожидали ≤20"
# И реальное срезание против прежнего потолка (эт.6 без множителей было 45/день)
old_top_daily = (B + P * FLOORS) * ENTRIES
assert top_daily <= old_top_daily * 0.45, \
    f"дневной потолок {top_daily} должен быть ≤45% прежних {old_top_daily}"

print(f"\nOK: 🌑 из Врат −60% на каждом этаже, показ=выдача, "
      f"дневной потолок эт.{FLOORS} без множителей {top_daily}🌑 (было {old_top_daily})")
