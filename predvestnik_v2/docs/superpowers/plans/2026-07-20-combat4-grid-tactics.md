# Боёвка 4.0 «Клеточная тактика» — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переписать движок боя с «руны-рука» на клеточную пошаговую тактику (поле 7×5,
AP на юнита, укрытия/LoS, EV-ИИ врага), сохранив казарму/юнитов/стихии/Ярость+ульты/QTE,
и встроить баланс БЛ1–БЛ4 из COMBAT_AUDIT.md. Все режимы (Врата/Бездна/Войны/Рейды/Дуэли)
переезжают одним релизом. Без параллельного мёртвого движка — рефактор `services/battle3.py`,
`FastAPI/routers/battle.py`, `FastAPI/static/app.11.js`.

**Architecture:** Server-authoritative, состояние в `battles.state_json`. Движок — чистые
функции в `services/battle3.py` (переписывается), тонкий адаптер — `FastAPI/routers/battle.py`.
Клиент шлёт действия (move/attack/skill/defend/ult/end_turn) + сырой `tap_offset_ms` для QTE;
сервер валидирует AP/дальность/LoS и грейдит тайминг сам.

**Tech Stack:** Python 3.11 (прод!), FastAPI, asyncpg (PGAdapter, `?`→`$N`), классический JS
в `app.11.js` (не ES-модуль, склейка через `main.py`), CSS-grid (без WebGL).

**Спека:** `docs/superpowers/specs/2026-07-20-combat4-grid-tactics-design.md` — читать ПЕРЕД
любой задачей.

## Global Constraints

- **Прод — Python 3.11**, не 3.12 (`project_prod_python_311_not_312`): не использовать синтаксис 3.12+; проверять `python -m py_compile` локально, но помнить про f-string/PEP 701 отличия.
- **PGAdapter**: SQL с `?`-плейсхолдерами (транслируются в `$1,$2`), `ON CONFLICT table.column`.
- **Иерархия слоёв**: `services/` не импортирует `bot.*`/`FastAPI.*`; SQL только в `infrastructure/repositories/`.
- **app.11.js** — classic script, править ЭТУ часть (не отдельные `<script>`); после правок `node --check` на собранном файле (или на самой части, если синтаксически самодостаточна).
- **Поле 7×5** (ширина W=7, высота H=5), координаты `{x:0..6, y:0..4}`, 4-соседство (без диагоналей).
- **Сохранить дословно** (не переписывать логику, только вызовы): `_apply_damage`, `_kill`, `_heal`, `_gain_rage`, `_escalation`, `_team_hp_frac`, `_tick_statuses`, `_mk_ally`, `_squad_synergy`, элементы/синергии, все 16 эффектов скиллов в `_exec_skill`, все 16 ультов в `_exec_ult`, QTE (`qte_window`/`grade_tap`/`resume_qte` flow), генераторы врагов (`gates_enemy_squad`/`abyss_enemy_squad`/`abyss_boss`/`war_wall`), `dumps`/`loads`.
- **Удалить**: колода/рука/сброс (`_rebuild_deck`/`_draw`/`_purge_dead_runes`/`_rune_steps`/`play_round`/`_process_queue`), Фокус (`reroll_rune`/`mark_forced_crit`/`B3_FOCUS_*`), виртуальные позиции и перехваты (`_pick_target` intercept, `B3_INTERCEPT_*`), рунный `_roll_intents`. Соответствующие роуты `/battle/round|reroll|focus-crit|triad` — убрать/заменить.
- **AP по ролям**: танк 4 / дд 5 / саппорт 5 / порождение (legendary) 6. Ход = 1 AP/клетка, атака = 2 AP, навык = 3 AP (КД 2 раунда), защита = 1 AP, ульта = 0 AP (нужна Ярость 100). Дальность атаки: танк 1 (melee), остальные 2 (ranged).
- **Нет автотестов в репо** (нет pytest/tests): верификация — `python -m py_compile` + прогонные скрипты (кладём в `predvestnik_v2/tools/`, запускаем, потом можно удалить) + ручной смоук на проде. Скрипты пишем как самостоятельные `.py`, импортящие движок и печатающие ASSERT-результаты.
- **Балансовые цифры БЛ1–БЛ4** — из COMBAT_AUDIT.md (владелец одобрил): гейт по Σ CP отряда, осколки с любого этажа, награда ×1.5 без потерь / ×1.25 за ≤6 раундов, «павший» юнит недоступен 3ч, «вскрытая оборона» +25%.

---

## ФАЗА A — Ядро: клеточная модель состояния и чистые алгоритмы

> Фундамент. Всё — чистые функции без БД, тестируются скриптом. Ничего из старого
> раунда-руны ещё не удаляем в этой фазе (движок пока не собирается целиком) — только
> ДОБАВЛЯЕМ новый модуль-хелпер, который Фаза B подключит. Это позволяет ревьюить
> алгоритмы изолированно.

### Task A1: Константы клеточной модели

**Files:**
- Modify: `core/constants.py` (секция «Боёвка 3.0», рядом с `B3_*`)

**Interfaces:**
- Produces: `GRID_W=7`, `GRID_H=5`, `B4_AP_BY_ROLE`, `B4_RANGE_BY_ROLE`, `B4_MOVE_AP`, `B4_ATK_AP`, `B4_SKILL_AP`, `B4_DEF_AP`, `B4_SKILL_CD`, `B4_COVER_RANGED_MULT`, `B4_DANGER_HP_FRAC`, `B4_EXPOSED_DEF_MULT`, `B4_DEFEND_MULT` — используются во всех фазах A–D.

- [ ] **Step 1: Добавить константы**

В `core/constants.py` после блока `B3_*` (после `B3_TRIAD_MULT`/перед разделом R3) добавить:

```python
# ── Боёвка 4.0 «Клеточная тактика» (services/battle3.py) ──────────────────────
GRID_W: int = 7                 # ширина поля (колонки x=0..6)
GRID_H: int = 5                 # высота поля (ряды y=0..4)
# AP-пул и дальность атаки по роли юнита
B4_AP_BY_ROLE: dict = {"tank": 4, "dd": 5, "support": 5, "legendary": 6}
B4_RANGE_BY_ROLE: dict = {"tank": 1, "dd": 2, "support": 2, "legendary": 2}
B4_MOVE_AP: int = 1             # AP за 1 клетку хода
B4_ATK_AP: int = 2             # AP за атаку
B4_SKILL_AP: int = 3           # AP за навык
B4_DEF_AP: int = 1             # AP за защиту
B4_SKILL_CD: int = 2           # кулдаун навыка (раундов)
B4_COVER_RANGED_MULT: float = 0.70   # урон по цели В укрытии от ranged (−30%)
B4_DANGER_HP_FRAC: float = 0.05      # опасная клетка: −5% hp_max за вход/старт хода
B4_EXPOSED_DEF_MULT: float = 1.25    # «вскрытая оборона»: не защищался и не в укрытии → +25%
B4_DEFEND_MULT: float = 0.60         # активная защита: входящий урон ×0.60 (−40%)
# Награда за скилл (БЛ3): множители исхода Врат/Бездны
B4_REWARD_NO_LOSS_MULT: float = 1.5  # ни один юнит не пал
B4_REWARD_FAST_MULT: float = 1.25    # победа за ≤ N раундов
B4_REWARD_FAST_ROUNDS: int = 6
B4_WOUND_HOURS: int = 3              # «павший» юнит недоступен N часов
```

- [ ] **Step 2: Роль legendary-юнита**

`B4_AP_BY_ROLE`/`B4_RANGE_BY_ROLE` используют ключ `"legendary"`, но у юнитов роль —
`dd`/`tank`/`support` (см. `core/units.py`). Порождение Бездны (`u_porozhdenie`) —
legendary по редкости, но роль у него одна из трёх. Решение: AP/дальность берём по
РОЛИ, а legendary-бонус (+1 AP) даём отдельным правилом в Фазе B по редкости. Убрать
ключ `"legendary"` из обоих словарей (оставить 3 роли), добавить:

```python
B4_AP_LEGENDARY_BONUS: int = 1   # +1 AP юнитам легендарной редкости (поверх роли)
```

- [ ] **Step 3: Проверить**

Run: `cd predvestnik_v2 && python -c "import core.constants as c; print(c.GRID_W, c.B4_AP_BY_ROLE, c.B4_AP_LEGENDARY_BONUS)"`
Expected: `7 {'tank': 4, 'dd': 5, 'support': 5} 1`

- [ ] **Step 4: Commit**

```bash
git add predvestnik_v2/core/constants.py
git commit -m "feat(combat4): константы клеточной модели (поле/AP/дальность/укрытия)"
```

---

### Task A2: Модуль сетки `services/battle_grid.py` — генерация, BFS, LoS

**Files:**
- Create: `services/battle_grid.py`
- Create (temp): `tools/test_battle_grid.py`

**Interfaces:**
- Produces:
  - `CELL_EMPTY=0, CELL_OBSTACLE=1, CELL_COVER=2, CELL_DANGER=3` (константы клеток)
  - `gen_grid(seed:int, spawns:list[tuple[int,int]]) -> list[list[int]]` — сетка H×W (grid[y][x]), детерминированная по seed, гарантированно связная между всеми spawns, спавн-клетки всегда пустые.
  - `passable(grid, x, y) -> bool` — в пределах поля и не препятствие.
  - `neighbors(x, y) -> list[tuple[int,int]]` — 4-соседи в пределах поля.
  - `reachable(grid, start, ap, blocked:set) -> dict[tuple,int]` — BFS: клетка→стоимость AP (≤ap), не входя в blocked (занятые юнитами) и препятствия.
  - `line_of_sight(grid, a, b) -> bool` — Брезенхэм; препятствие между a и b (исключая концы) рвёт LoS.
  - `chebyshev(a, b) -> int` и `manhattan(a, b) -> int`.

- [ ] **Step 1: Написать модуль**

```python
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
```

- [ ] **Step 2: Написать тест-скрипт**

Create `tools/test_battle_grid.py`:

```python
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
```

- [ ] **Step 3: Прогнать тест**

Run: `cd predvestnik_v2 && python tools/test_battle_grid.py`
Expected: заканчивается строкой `ALL GRID TESTS PASSED`, без AssertionError.

- [ ] **Step 4: py_compile**

Run: `cd predvestnik_v2 && python -m py_compile services/battle_grid.py`
Expected: без вывода.

- [ ] **Step 5: Commit**

```bash
git add predvestnik_v2/services/battle_grid.py predvestnik_v2/tools/test_battle_grid.py
git commit -m "feat(combat4): сетка — генерация со связностью, BFS-AP, линия видимости"
```

---

### Task A3: Спавны и врезка сетки в `new_battle_state`

**Files:**
- Modify: `services/battle3.py` (`new_battle_state`, `_mk_ally`, импорты)
- Modify (temp): `tools/test_battle_grid.py` (добавить проверку стейта) — или новый `tools/test_battle_state.py`

**Interfaces:**
- Consumes: `battle_grid.gen_grid`, константы A1.
- Produces: state теперь содержит `grid` (H×W), у каждого юнита `pos:{x,y}`, `ap`, `ap_max`, `cd:{skill:0}`, `defending:False`; враги тоже с `pos`. Ally-юниты имеют `ap_max` по роли+редкости. Функция `spawn_positions(n_ally, n_enemy) -> (ally_pts, enemy_pts)` детерминирует стартовые клетки.

> ЭТА задача только ДОБАВЛЯЕТ поля в state (grid/pos/ap). Рунная логика ещё
> присутствует и не ломается — снимаем её в Фазе B, когда action-модель готова.
> Так ревьюер видит врезку сетки изолированно.

- [ ] **Step 1: Импорты и хелпер спавнов**

В начало `services/battle3.py` добавить (к существующим импортам `core.constants`):

```python
from core.constants import (
    GRID_W, GRID_H, B4_AP_BY_ROLE, B4_AP_LEGENDARY_BONUS, B4_RANGE_BY_ROLE,
)
from services import battle_grid as grid_mod
```

Добавить функцию (рядом с генераторами врагов):

```python
def spawn_positions(n_ally: int, n_enemy: int):
    """Отряд — колонки 0–1, враги — 5–6. Ряды по центру поля. Детерминировано."""
    rows = [2, 1, 3, 0, 4]  # порядок заполнения: центр наружу
    ally = [(0 if i % 2 == 0 else 1, rows[i]) for i in range(n_ally)]
    enemy = [(6 if i % 2 == 0 else 5, rows[i]) for i in range(n_enemy)]
    return ally[:n_ally], enemy[:n_enemy]


def _unit_ap_max(unit: dict) -> int:
    ap = B4_AP_BY_ROLE.get(unit.get("role"), 5)
    from core.units import UNITS
    if UNITS.get(unit.get("uid"), {}).get("rarity") == "legendary":
        ap += B4_AP_LEGENDARY_BONUS
    return ap
```

(Проверить в `core/units.py`, что у юнита есть поле `rarity`; если ключ иной —
адаптировать. Для врагов рарности нет — им AP не нужен, у них своя фаза.)

- [ ] **Step 2: Врезать сетку и позиции в new_battle_state**

В `new_battle_state`, ПОСЛЕ формирования `allies` и `enemies` (после цикла
`for e in enemies:` с setdefault), но ДО сборки `state = {...}`, вставить:

```python
    ally_pts, enemy_pts = spawn_positions(len(allies), len(enemies))
    for u, p in zip(allies, ally_pts):
        u["pos"] = {"x": p[0], "y": p[1]}
        u["ap_max"] = _unit_ap_max(u)
        u["ap"] = u["ap_max"]
        u["cd"] = {"skill": 0}
        u["defending"] = False
    for u, p in zip(enemies, enemy_pts):
        u["pos"] = {"x": p[0], "y": p[1]}
        u.setdefault("cd", {"skill": 0})
    seed = int((ctx or {}).get("seed") or random.randint(1, 2**31 - 1))
    battle_grid_data = grid_mod.gen_grid(seed, ally_pts + enemy_pts)
```

В словарь `state = {...}` добавить ключи: `"grid": battle_grid_data, "seed": seed,`
(рядом с `"mode"`).

- [ ] **Step 3: Тест — стейт содержит сетку и позиции**

Create `tools/test_battle_state.py`:

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from services import battle3 as b3
from core.constants import GRID_W, GRID_H

ally = [{"unit_id": uid, "level": 1, "slot": i}
        for i, uid in enumerate(list(__import__("core.units", fromlist=["UNITS"]).UNITS)[:3])]
enemies = b3.gates_enemy_squad(1)
st = b3.new_battle_state(ally, enemies, "gates", {"floor": 1, "seed": 42})
assert len(st["grid"]) == GRID_H and len(st["grid"][0]) == GRID_W
for u in st["ally"]["units"]:
    assert "pos" in u and 0 <= u["pos"]["x"] < GRID_W and 0 <= u["pos"]["y"] < GRID_H
    assert u["ap"] == u["ap_max"] >= 4
for u in st["enemy"]["units"]:
    assert "pos" in u
# спавны не совпадают
poss = [(u["pos"]["x"], u["pos"]["y"]) for u in st["ally"]["units"] + st["enemy"]["units"]]
assert len(poss) == len(set(poss)), "коллизия спавнов"
# детерминизм по seed
st2 = b3.new_battle_state(ally, enemies, "gates", {"floor": 1, "seed": 42})
assert st["grid"] == st2["grid"], "grid недетерминирован по seed"
print("battle_state: сетка+позиции+AP+детерминизм  OK")
```

- [ ] **Step 4: Прогнать + py_compile**

Run: `cd predvestnik_v2 && python tools/test_battle_state.py && python -m py_compile services/battle3.py`
Expected: `battle_state: ... OK`, затем без вывода от py_compile.

- [ ] **Step 5: Commit**

```bash
git add predvestnik_v2/services/battle3.py predvestnik_v2/tools/test_battle_state.py
git commit -m "feat(combat4): сетка/позиции/AP врезаны в new_battle_state"
```

---

## ФАЗА B — Action-модель (заменяет раунд-руну)

> Здесь снимаем колоду/руку/Фокус/перехваты и вводим per-action движок с AP.
> Ярость+ульты+QTE (крит/ульта) сохраняются. Скиллы/ульты 16 юнитов — эффекты те же,
> добавляется дальность/зона и валидация LoS.

### Task B1: Ядро действий `apply_action` (move/attack/defend/end_turn)

**Files:**
- Modify: `services/battle3.py`

**Interfaces:**
- Consumes: `battle_grid` (reachable/LoS/range), `_apply_damage`, `_gain_rage`, константы A1.
- Produces:
  - `apply_action(state, action:dict) -> dict` где action = `{type, unit_i, cell?, target_i?, tap_offset_ms?}`; type ∈ move/attack/defend/end_turn. (skill/ult — B2.) Возвращает `{ok:bool, err?:str, phase?:'qte', ...}`.
  - `_unit_pos(u)->tuple`, `_occupied(state, side=None)->set`, `_in_range(state, atk_i, tgt_i)->bool`, `_atk_range(unit)->int`.
  - `begin_player_turn(state)` — сброс AP всем живым ally, `defending=False`, тик КД, danger-урон стартующим на опасной клетке.
  - `end_player_turn(state)` → вызывает `_enemy_phase` (Фаза C) → `_end_round` (тик статусов/эскалация/telegraph).

- [ ] **Step 1: Хелперы позиций/дальности**

Добавить в `battle3.py`:

```python
def _pos(u: dict) -> tuple:
    p = u["pos"]
    return (p["x"], p["y"])


def _occupied(state: dict, exclude=None) -> set:
    s = set()
    for side in ("ally", "enemy"):
        for u in state[side]["units"]:
            if u["alive"] and u is not exclude:
                s.add(_pos(u))
    return s


def _atk_range(unit: dict) -> int:
    from core.constants import B4_RANGE_BY_ROLE
    return B4_RANGE_BY_ROLE.get(unit.get("role"), 2)


def _in_cell_type(state, u, cell_type) -> bool:
    x, y = _pos(u)
    return state["grid"][y][x] == cell_type
```

- [ ] **Step 2: begin_player_turn / danger / КД**

```python
def begin_player_turn(state: dict) -> None:
    from services.battle_grid import CELL_DANGER
    from core.constants import B4_DANGER_HP_FRAC
    events = state.setdefault("events_round", [])
    for u in state["ally"]["units"]:
        if not u["alive"]:
            continue
        u["ap"] = u["ap_max"]
        u["defending"] = False
        if u["cd"].get("skill", 0) > 0:
            u["cd"]["skill"] -= 1
        if _in_cell_type(state, u, CELL_DANGER):
            dmg = max(1, int(u["hp_max"] * B4_DANGER_HP_FRAC))
            u["hp"] = max(0, u["hp"] - dmg)
            events.append(f"🔥 {u['name']} на опасной клетке: −{dmg}")
            if u["hp"] <= 0:
                _kill(state, "ally", state["ally"]["units"].index(u), events)
```

- [ ] **Step 3: apply_action (move/attack/defend/end_turn)**

```python
def apply_action(state: dict, action: dict) -> dict:
    """Одно действие игрока. Валидация AP/дальности/LoS — здесь (server-authoritative)."""
    from services.battle_grid import reachable, line_of_sight, CELL_COVER
    from core.constants import (B4_MOVE_AP, B4_ATK_AP, B4_DEF_AP,
                                B4_COVER_RANGED_MULT, B4_DEFEND_MULT, B4_EXPOSED_DEF_MULT)
    if state.get("pending"):
        return {"ok": False, "err": "Сначала заверши QTE."}
    typ = action.get("type")
    if typ == "end_turn":
        return end_player_turn(state)
    ui = action.get("unit_i")
    units = state["ally"]["units"]
    if not isinstance(ui, int) or not (0 <= ui < len(units)) or not units[ui]["alive"]:
        return {"ok": False, "err": "Юнит недоступен."}
    u = units[ui]
    events = state.setdefault("events_round", [])

    if typ == "move":
        cell = action.get("cell") or {}
        dst = (cell.get("x"), cell.get("y"))
        reach = reachable(state["grid"], _pos(u), u["ap"], _occupied(state, exclude=u))
        cost = reach.get(dst)
        if cost is None:
            return {"ok": False, "err": "Клетка недостижима."}
        u["ap"] -= cost * B4_MOVE_AP
        u["pos"] = {"x": dst[0], "y": dst[1]}
        return {"ok": True, "hits": state.pop("hits_round", []), "ap": u["ap"]}

    if typ == "defend":
        if u["ap"] < B4_DEF_AP:
            return {"ok": False, "err": "Недостаточно AP."}
        u["ap"] -= B4_DEF_AP
        u["defending"] = True
        events.append(f"🛡 {u['name']} встаёт в защиту")
        return {"ok": True, "ap": u["ap"]}

    if typ == "attack":
        if u["ap"] < B4_ATK_AP:
            return {"ok": False, "err": "Недостаточно AP."}
        ti = action.get("target_i")
        enemies = state["enemy"]["units"]
        if not isinstance(ti, int) or not (0 <= ti < len(enemies)) or not enemies[ti]["alive"]:
            return {"ok": False, "err": "Цель недоступна."}
        tgt = enemies[ti]
        if grid_mod.chebyshev(_pos(u), _pos(tgt)) > _atk_range(u):
            return {"ok": False, "err": "Цель вне дальности."}
        if not line_of_sight(state["grid"], _pos(u), _pos(tgt)):
            return {"ok": False, "err": "Нет линии видимости."}
        u["ap"] -= B4_ATK_AP
        # крит-QTE как раньше: пауза
        syn_crit = state["ally"]["synergy"].get("crit", 0)
        if (not state.get("crit_qte_used") and random.random() < (u["crit"] + syn_crit)
                and not u["statuses"].get("no_crit")):
            state["crit_qte_used"] = True
            state["pending"] = {"type": "crit", "atk_i": ui, "tgt_i": ti}
            state["qte"] = qte_window(2)
            return {"ok": True, "phase": "qte", "qte_kind": "crit",
                    "hits": state.pop("hits_round", [])}
        _do_attack(state, ui, ti, events, crit_mult=1.0)
        if _battle_over(state):
            state["status"] = "won" if _alive_idx(enemies) == [] else "lost"
        return {"ok": True, "hits": state.pop("hits_round", []), "ap": u["ap"]}

    if typ == "skill":
        return _do_skill_action(state, ui, action.get("target_i"))
    return {"ok": False, "err": "Неизвестное действие."}
```

- [ ] **Step 4: `_do_attack` — урон с укрытием и «вскрытой обороной»**

Заменяет `_exec_attack`. Вызывает существующий `_apply_damage`, добавляя модификаторы
цели (укрытие/защита/вскрытая оборона):

```python
def _do_attack(state, atk_i, tgt_i, events, crit_mult=1.0, ranged=None):
    from services.battle_grid import CELL_COVER
    from core.constants import B4_COVER_RANGED_MULT, B4_DEFEND_MULT, B4_EXPOSED_DEF_MULT
    u = state["ally"]["units"][atk_i]
    tgt = state["enemy"]["units"][tgt_i]
    if ranged is None:
        ranged = _atk_range(u) >= 2
    raw = u["atk"] * crit_mult
    # укрытие: ranged −30%, melee игнорирует
    if ranged and _in_cell_type(state, tgt, CELL_COVER):
        raw *= B4_COVER_RANGED_MULT
        events.append(f"🪨 {tgt['name']} в укрытии: урон −30%")
    # вскрытая оборона: не защищался И не в укрытии → +25%
    if not tgt.get("defending") and not _in_cell_type(state, tgt, CELL_COVER):
        raw *= B4_EXPOSED_DEF_MULT
    dmg = _apply_damage(state, "ally", atk_i, "enemy", tgt_i, raw, events,
                        elem=u.get("element"))
    if crit_mult > 1.0:
        events.append(f"🎯 Крит! {u['name']} → {tgt['name']}: −{dmg}")
    else:
        events.append(f"⚔️ {u['name']} → {tgt['name']}: −{dmg}")
```

Примечание: входящая защита цели-юнита ИГРОКА (когда бьёт враг) обрабатывается в
Фазе C через тот же `defending`-флаг и `B4_DEFEND_MULT` — там при расчёте `raw`
врага умножать на `B4_DEFEND_MULT`, если цель `defending`.

- [ ] **Step 5: end_player_turn / _end_round**

```python
def end_player_turn(state: dict) -> dict:
    events = state.setdefault("events_round", [])
    _enemy_phase(state, events)            # Фаза C (EV-ИИ)
    if _battle_over(state):
        return _end_round(state, over=True)
    return _end_round(state, over=False)


def _end_round(state: dict, over: bool) -> dict:
    events = state.setdefault("events_round", [])
    _tick_statuses(state, events)          # сохранённая функция
    state["log"] = (state.get("log", []) + events)[-30:]
    state["events_round"] = []
    hits = state.pop("hits_round", [])
    if _battle_over(state) or over:
        state["status"] = ("won" if not _alive_idx(state["enemy"]["units"])
                           else "lost")
        return {"ok": True, "phase": "over", "hits": hits}
    begin_round(state)                     # эскалация/telegraph/round++ (переписан в C)
    begin_player_turn(state)               # AP reset нового хода
    return {"ok": True, "phase": "next", "hits": hits}
```

- [ ] **Step 6: py_compile (частичный — B2 достроит skill/ult)**

Run: `cd predvestnik_v2 && python -m py_compile services/battle3.py`
Expected: может ругнуться на неопределённые `_do_skill_action`/переписанный `begin_round` —
если так, ЗАГЛУШИТЬ временно `def _do_skill_action(state,ui,ti): return {"ok":False,"err":"tbd"}`
в конце файла, чтобы компилировалось; B2 заменит. Если чисто — идём дальше.

- [ ] **Step 7: Commit**

```bash
git add predvestnik_v2/services/battle3.py
git commit -m "feat(combat4): action-модель move/attack/defend/end_turn с AP/LoS/укрытиями"
```

---

### Task B2: Навыки и ульты на сетке (дальность/зона), снятие рун/Фокуса

**Files:**
- Modify: `services/battle3.py`

**Interfaces:**
- Consumes: B1.
- Produces: `_do_skill_action(state, ui, target_i)` (3 AP, КД 2, LoS+дальность 2 для целевых, 0 для само-бафов, зона для AoE) — переиспользует эффекты из старого `_exec_skill`; `request_ult`/`resume_qte` адаптированы под action-модель; удалены `_rebuild_deck/_draw/_purge_dead_runes/_rune_steps/play_round/_process_queue/reroll_rune/mark_forced_crit/_exec_attack/_exec_defense` и рунные поля state.

- [ ] **Step 1: Портировать эффекты скиллов в `_do_skill_action`**

Взять тело старого `_exec_skill` (switch по `u["uid"]`, строки 372–474 оригинала) —
эффекты СОХРАНИТЬ дословно, обернув в проверки AP/КД/дальности. Целевые скиллы требуют
цель в дальности 2 + LoS; само-бафы дальности не требуют; AoE бьёт врагов в радиусе 1
от выбранной цели. Каркас:

```python
def _do_skill_action(state, ui, target_i):
    from core.constants import B4_SKILL_AP, B4_SKILL_CD
    u = state["ally"]["units"][ui]
    if u["ap"] < B4_SKILL_AP:
        return {"ok": False, "err": "Недостаточно AP для навыка."}
    if u["cd"].get("skill", 0) > 0:
        return {"ok": False, "err": f"Навык на кулдауне ({u['cd']['skill']})."}
    events = state.setdefault("events_round", [])
    # (эффекты — из старого _exec_skill, целевым проверить дальность/LoS через
    #  _skill_target_ok(state, ui, target_i); AoE — _enemies_around(state, target_i, 1))
    u["ap"] -= B4_SKILL_AP
    u["cd"]["skill"] = B4_SKILL_CD
    _apply_skill_effect(state, ui, target_i, events)   # перенесённый switch
    if _battle_over(state):
        state["status"] = "won" if not _alive_idx(state["enemy"]["units"]) else "lost"
    return {"ok": True, "hits": state.pop("hits_round", []), "ap": u["ap"]}
```

Перенести switch как `_apply_skill_effect(state, u_i, tgt, events)` — заменить внутри
все `_exec_attack(...)` на `_do_attack(...)`, `enemy_t()`/`_pick_target(...,'enemy',...)`
на реальный выбор цели `target_i` с валидацией дальности; AoE-скиллы бьют
`_enemies_around(state, target_i, radius=1)`. Точная таблица дальностей 16 скиллов —
в спеке §«Юниты на поле»; при переносе для каждого скилла указать в комментарии его тип
(self/target/aoe) и радиус.

- [ ] **Step 2: Хелперы дальности скилла и зоны**

```python
def _skill_target_ok(state, ui, ti):
    from services.battle_grid import line_of_sight
    if ti is None:
        return False
    u = state["ally"]["units"][ui]
    tgt = state["enemy"]["units"][ti]
    return (tgt["alive"] and grid_mod.chebyshev(_pos(u), _pos(tgt)) <= 2
            and line_of_sight(state["grid"], _pos(u), _pos(tgt)))


def _enemies_around(state, ti, radius=1):
    if ti is None:
        return []
    c = _pos(state["enemy"]["units"][ti])
    return [i for i, e in enumerate(state["enemy"]["units"])
            if e["alive"] and grid_mod.chebyshev(_pos(e), c) <= radius]
```

- [ ] **Step 3: Адаптировать ульты (`request_ult`/`resume_qte`/`_exec_ult`)**

`request_ult(state, unit_i)` оставить как есть (ставит `pending`/`qte`). В `resume_qte`
ветку `crit` переписать под новые ключи pending (`atk_i`/`tgt_i` → `_do_attack`), ветку
`ult` оставить (вызывает `_exec_ult`, который сохраняем — ульты бьют по площади/цели без
изменений). После крита/ульты НЕ доигрывать фазу врага автоматически (ход не кончается —
AP-модель); вернуть `{"ok":True,"phase":"resolved","hits":...}`. `_exec_ult` (ult switch
476–596) — оставить, заменив внутри `_exec_attack`→`_do_attack` и таргетинг на реальные
позиции (ульта обычно AoE/по врагам — использовать `_alive_idx(enemy)`).

- [ ] **Step 4: Удалить мёртвый рунный код**

Удалить функции: `_rebuild_deck`, `_draw`, `_purge_dead_runes`, `_rune_steps`,
`play_round`, `_process_queue`, `reroll_rune`, `mark_forced_crit`, `_exec_attack`,
`_exec_defense`, `use_triad`. Из `new_battle_state` убрать `deck/discard/hand/hand_size_next/
focus/triad_available` и вызов `_rebuild_deck`. Убрать импорты `B3_HAND_SIZE/B3_FOCUS_*/
B3_INTERCEPT_*/B3_TRIAD_MULT/RUNE_KINDS/RUNE_EMOJI`. `_pick_target` — упростить до выбора
без перехвата (для врага-ИИ Фазы C вернём реальный выбор цели там).

- [ ] **Step 5: py_compile + расширить test_battle_state.py боем до победы**

Добавить в `tools/test_battle_state.py` прогон: собрать сильный отряд (level 10),
`gates_enemy_squad(1)`, и в цикле дёргать `apply_action` (move к врагу → attack) до
`status in (won/lost)`, проверяя, что AP не уходит в минус и бой завершается за <50 действий.

Run: `cd predvestnik_v2 && python -m py_compile services/battle3.py && python tools/test_battle_state.py`
Expected: OK, бой завершается.

- [ ] **Step 6: Commit**

```bash
git add predvestnik_v2/services/battle3.py predvestnik_v2/tools/test_battle_state.py
git commit -m "feat(combat4): навыки/ульты на сетке; удалён рунный движок и Фокус"
```

---

## ФАЗА C — EV-ИИ врага и телеграф

### Task C1: EV-скоринг вражеской фазы + telegraph

**Files:**
- Modify: `services/battle3.py` (`_enemy_phase`, `begin_round`→telegraph, `_roll_intents`→удалить/заменить)

**Interfaces:**
- Consumes: `battle_grid` (reachable/LoS), `_do_attack`-аналог для врага, `_apply_damage`.
- Produces: `_enemy_phase(state, events)` перебирает для каждого живого врага допустимые (клетка×действие) планы, считает `EV = ImmediateGain − Cost + Survivability + StrategicValue`, применяет лучший; детерминированный tie-breaker (роль dd>support>tank, затем меньший индекс). `_roll_telegraph(state)` — заранее роллит намерения (цель/зона угрозы) для UI; при hp<30% вес выживания ×2; боссы — 2 действия/фаза, AoE каждый 3-й раунд. Враг чтит `defending` цели (×B4_DEFEND_MULT) и укрытие.

- [ ] **Step 1–N:** (детализируется субагентом C1 по спеке §«ИИ врага»; полный EV-скоринг,
  детерминизм, телеграф). Тест: `tools/test_enemy_ai.py` — одинаковый state → одинаковый
  ход (детерминизм); враг с низким HP выбирает клетку вне досягаемости игрока, если есть;
  враг предпочитает бить незащищённую/раненую цель.

> NB для контроллера: эта задача самостоятельная и алгоритмически ёмкая — детализировать
> полный код при дистанции 1 задачи (после B2), на стандартной модели.

- [ ] **Commit:** `feat(combat4): EV-скоринг ИИ врага + телеграф угроз`

---

## ФАЗА D — Сериализация и роутер

### Task D1: `public_state` под сетку

**Files:** Modify `services/battle3.py` (`public_state`, `_pub_unit`).
Добавить в `_pub_unit`: `pos`, `ap`, `ap_max`, `defending`, `cd`, `range` (для ally).
В `public_state`: `grid`, убрать `hand/deck_left/focus/focus_costs`, добавить
`telegraph` (клетки под угрозой), `intents` в новом формате. Тест: сериализуемо в JSON
(`b3.dumps(public_state(...))` не падает). Commit.

### Task D2: Рефактор роутера `/combat2/battle/*`

**Files:** Modify `FastAPI/routers/battle.py`.
- Заменить `/battle/round|qte|ult|reroll|focus-crit|triad` на:
  - `POST /battle/action {battle_id, type, unit_i?, cell?, target_i?}` → `b3.apply_action`
  - `POST /battle/qte {battle_id, tap_offset_ms}` → `b3.resume_qte` (оставить)
  - `POST /battle/ult {battle_id, unit_i}` → `b3.request_ult` (оставить)
  - `/battle/flee`, `/battle/cancel` — оставить.
- Убрать `RoundRequest/HandRequest`, добавить `ActionRequest`. `_respond` — без изменений
  (сохраняет state, финализирует). Валидация AP/дальности — В ДВИЖКЕ (роутер только
  прокидывает и мапит err→HTTP 400). Тест: import-smoke (`python -c "import FastAPI.routers.battle"`),
  openapi не падает. Commit.

### Task D3: Миграция незавершённых боёв + БЛ1 (гейт по силе отряда)

**Files:** Modify `FastAPI/routers/battle.py` (`gates_enter`/`gates_overview`), `bot/__main__.py` или стартап (закрыть старые бои).
- `get_active_b3`: старый state без `grid` → `finish(..., "cancelled")` (не «lost»).
- БЛ1: в `gates_overview`/`gates_enter` гейт считать от `barracks.squad_cp` (Σ CP отряда),
  НЕ от `calculate_cp` (полный CP). Пороги `GATES2_CP_GATE` пересчитать в Фазе F после прогонов.
- Commit.

---

## ФАЗА E — Фронтенд арены (app.11.js)

### Task E1: Рендер поля 7×5 и состояние выбора
### Task E2: Тап-ввод (move/attack), панель действий, AP-счётчик
### Task E3: Threat-оверлей, телеграф, переиспользование QTE/лога/чисел урона

**Files:** Modify `FastAPI/static/app.11.js`.
> Детализируется при подходе (после D). Ключевое: CSS-grid 7×5 (клетки ~44–48px, помещается
> в 390px), тап по своему юниту → подсветка `reachable` (сервер отдаёт достижимые клетки в
> public_state ИЛИ фронт считает по grid+ap — решить в E1: отдавать с сервера, меньше дублей
> логики), тап клетка=move, тап враг=attack, панель (Навык/Защита/Ульта/Конец хода) + AP.
> QTE-кольцо/лог/всплывающие цифры — уже есть в app.11.js, переиспользовать. `node --check`
> на собранном скрипте. Каждая — свой commit.

---

## ФАЗА F — Баланс, режимы, эндшпиль-хвосты

### Task F1: Прогонный баланс-скрипт + пороги гейта (БЛ1)
`tools/balance_combat4.py`: симуляция «средний игрок» (жадный ИИ за игрока) на отрядах
L1/L5/L10 против этажей 1–6 → печатает winrate. Подобрать `GATES2_CP_GATE` так, чтобы
L1-отряд проходил эт.1–2 и НЕ эт.4+, L10 проходил эт.6 с усилием. Commit.

### Task F2: БЛ2 — краны осколков
`_gates_reward`: юнит-осколки гарантированно с любого этажа (1–2, растёт), убрать гейт `floor>=5`.
+2 дневных квеста с 💠/осколками (`core/registry.py::DAILY_QUESTS` + метрики). Commit.

### Task F3: БЛ3 — множители награды + ранение павших
`_gates_reward`/`_finalize_if_over`: множитель ×1.5 (без потерь юнитов) / ×1.25 (≤6 раундов).
«Павший» юнит → запись в таблицу кулдауна (недоступен 3ч, `barracks.squad_units` фильтрует
раненых). Новая колонка/таблица `unit_wounds`. Commit.

### Task F4: Абисс/Войны/Рейды/Дуэли на новом движке
Проверить `clans2.py` (Бездна создаёт бой через `b3.new_battle_state`) и war — они уже
идут через тот же движок, убедиться что spawn/grid работают; стена войны — статичный объект
без AP. Рейды/дуэли (без пошагового боя) — не трогаем. Commit.

---

## ФАЗА G — Документация

### Task G1: Переписать `ai_knowledge/combat.md` под 4.0 (сетка/AP/укрытия/LoS).
### Task G2: COMBAT_AUDIT.md — отметить БЛ1–БЛ4 сделанными; PLAYER_CHANGELOG.md — пост.
### Task G3: Финальный смоук на проде + деплой-заметка.

---

## Порядок и модели исполнения

A1→A2→A3 (фундамент) → B1→B2 (движок) → C1 (ИИ) → D1→D2→D3 (API) → E1→E2→E3 (фронт) →
F1→F4 (баланс/режимы) → G (доки). Фазы A/D/F — cheap/standard модель; B2/C1/E — standard;
финальный whole-branch review — самый мощный. Фаза A полностью детализирована кодом;
B детализирована; C/D/E/F/G — структура + интерфейсы, полный код детализируется субагентом
при дистанции ≤1 задачи (спека держит все цифры и правила).
