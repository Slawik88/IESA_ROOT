"""Прогон чистых функций battle_grid — запускать вручную, потом удалить."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from services import battle_grid as g
from core.constants import GRID_W, GRID_H

# Спавны: колонки 0–1 (отряд) и 5–6 (враги)
spawns = [(0, 1), (0, 3), (1, 2), (6, 1), (6, 3), (5, 2)]

# 1) Детерминизм + связность на 300 сидах
for seed in range(300):
    grid = g.gen_grid(seed, spawns)
    assert len(grid) == GRID_H and all(len(r) == GRID_W for r in grid), f"размер seed={seed}"
    for sx, sy in spawns:
        assert grid[sy][sx] == g.CELL_EMPTY, f"спавн занят seed={seed}"
    assert g._connected(grid, spawns), f"НЕСВЯЗНО seed={seed}"
    # детерминизм
    assert g.gen_grid(seed, spawns) == grid, f"недетерм. seed={seed}"
print("gen_grid: 300 сидов — связно, детерминировано, спавны пусты  OK")

# 2) reachable: пустое поле, ap=2 из угла → ромб
empty = [[0] * GRID_W for _ in range(GRID_H)]
r = g.reachable(empty, (0, 0), 2, set())
assert r.get((2, 0)) == 2 and r.get((1, 1)) == 2 and r.get((0, 2)) == 2, "BFS ромб"
assert (0, 0) not in r, "старт не в результате"
assert (3, 0) not in r, "за пределами AP"
# blocked стенка
r2 = g.reachable(empty, (0, 0), 3, {(1, 0), (0, 1)})
assert (2, 0) not in r2, "blocked не пройден"
print("reachable: ромб/AP/blocked  OK")

# 3) LoS: препятствие рвёт
grid = [[0] * GRID_W for _ in range(GRID_H)]
grid[2][3] = g.CELL_OBSTACLE
assert g.line_of_sight(grid, (3, 0), (3, 4)) is False, "препятствие на линии"
assert g.line_of_sight(grid, (0, 0), (6, 0)) is True, "чистая линия"
print("line_of_sight: препятствие/чистая  OK")
print("ALL GRID TESTS PASSED")
