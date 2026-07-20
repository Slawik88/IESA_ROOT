"""services/battle_grid.py — клеточное поле Боёвки 4.0: генерация с гарантией
связности, BFS-достижимость по AP, линия видимости (Брезенхэм). Чистые функции,
без БД и без состояния боя — тестируются изолированно (tools/test_battle_grid.py)."""
import random

from core.constants import GRID_W, GRID_H

CELL_EMPTY = 0
CELL_OBSTACLE = 1
CELL_COVER = 2
CELL_DANGER = 3


def neighbors(x: int, y: int):
    out = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < GRID_W and 0 <= ny < GRID_H:
            out.append((nx, ny))
    return out


def passable(grid, x: int, y: int) -> bool:
    if not (0 <= x < GRID_W and 0 <= y < GRID_H):
        return False
    return grid[y][x] != CELL_OBSTACLE


def _connected(grid, spawns) -> bool:
    """Все spawn-клетки во взаимно достижимой (по проходимым) компоненте."""
    if not spawns:
        return True
    seen = {spawns[0]}
    stack = [spawns[0]]
    while stack:
        x, y = stack.pop()
        for nx, ny in neighbors(x, y):
            if (nx, ny) not in seen and passable(grid, nx, ny):
                seen.add((nx, ny))
                stack.append((nx, ny))
    return all(s in seen for s in spawns)


def gen_grid(seed: int, spawns) -> list:
    """H×W сетка (grid[y][x]). Детерминирована по seed. Спавны — всегда пустые,
    и между ними гарантирована проходимость (иначе реролл с новым субсидом)."""
    rng = random.Random(seed)
    spawn_set = set(spawns)
    for attempt in range(50):
        grid = [[CELL_EMPTY] * GRID_W for _ in range(GRID_H)]
        # препятствия 3–5, укрытия 2–3, опасные 0–2 — только на не-спавн клетках
        cells = [(x, y) for y in range(GRID_H) for x in range(GRID_W)
                 if (x, y) not in spawn_set]
        rng.shuffle(cells)
        n_obs = rng.randint(3, 5)
        n_cov = rng.randint(2, 3)
        n_dng = rng.randint(0, 2)
        it = iter(cells)
        placed = []
        for _ in range(n_obs):
            try:
                x, y = next(it)
            except StopIteration:
                break
            grid[y][x] = CELL_OBSTACLE
            placed.append((x, y))
        if not _connected(grid, list(spawns)):
            # эта раскладка препятствий разорвала поле — новый субсид
            seed = (seed * 1103515245 + 12345) & 0x7fffffff
            rng = random.Random(seed)
            continue
        for _ in range(n_cov):
            try:
                x, y = next(it)
            except StopIteration:
                break
            grid[y][x] = CELL_COVER
        for _ in range(n_dng):
            try:
                x, y = next(it)
            except StopIteration:
                break
            grid[y][x] = CELL_DANGER
        return grid
    # Фолбэк: пустое поле (никогда не должно случиться при 50 попытках)
    return [[CELL_EMPTY] * GRID_W for _ in range(GRID_H)]


def reachable(grid, start, ap: int, blocked=None) -> dict:
    """BFS по стоимости AP (1/клетка). Возвращает {(x,y): cost} для cost<=ap.
    blocked — клетки, занятые живыми юнитами (сквозь них не ходят и не встают)."""
    blocked = blocked or set()
    sx, sy = start
    dist = {(sx, sy): 0}
    frontier = [(sx, sy)]
    while frontier:
        nxt = []
        for x, y in frontier:
            base = dist[(x, y)]
            if base >= ap:
                continue
            for nx, ny in neighbors(x, y):
                if (nx, ny) in dist or (nx, ny) in blocked:
                    continue
                if not passable(grid, nx, ny):
                    continue
                dist[(nx, ny)] = base + 1
                nxt.append((nx, ny))
        frontier = nxt
    dist.pop(start, None)
    return dist


def chebyshev(a, b) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def manhattan(a, b) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def line_of_sight(grid, a, b) -> bool:
    """Брезенхэм между центрами клеток; препятствие СТРОГО между a и b рвёт LoS.
    Концевые клетки не проверяются (сам стрелок/цель препятствием быть не могут)."""
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    cx, cy = x0, y0
    while (cx, cy) != (x1, y1):
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            cx += sx
        if e2 <= dx:
            err += dx
            cy += sy
        if (cx, cy) != (x1, y1) and grid[cy][cx] == CELL_OBSTACLE:
            return False
    return True
