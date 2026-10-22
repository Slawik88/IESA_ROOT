"""Pure logic solver for ranked Minesweeper levels: can a board be cleared without a guess, and how deep is the logic?

Tiers of a single deduction step:
  1 — one number: all its closed neighbours are mines, or all are safe;
  2 — two numbers: the closed cells of one are a subset of the other (the 1-2 / 1-1 patterns);
  3 — exact reasoning over a whole frontier group (and the count of mines left on the board).
``analyse`` repeats the cheapest step that still makes progress and reports the deepest tier it needed.
Every search is bounded, so a pathological board is rejected instead of stalling a request.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

ENUMERATION_BUDGET = 60_000   # recursion nodes per tier-3 step; a board that needs more is rejected


@dataclass(frozen=True)
class Analysis:
    solvable: bool   # cleared from the start without a single guess
    tier: int        # deepest tier any step needed (0 when the start already wins)
    steps: int


def neighbours(width: int, height: int, cell: int) -> tuple[int, ...]:
    row, col = divmod(cell, width)
    return tuple(y * width + x for y in range(row - 1, row + 2) for x in range(col - 1, col + 2)
                 if 0 <= y < height and 0 <= x < width and (y, x) != (row, col))


def adjacency(width: int, height: int, mines: frozenset[int]) -> dict[int, int]:
    return {c: sum(n in mines for n in neighbours(width, height, c)) for c in range(width * height)}


def flood(width: int, height: int, mines: frozenset[int], adjacent: dict[int, int],
          revealed: set[int], cell: int) -> set[int]:
    """Cells revealed by opening ``cell`` (zeros spread); ``cell`` must be safe."""
    opened, queue = set(), [cell]
    while queue:
        current = queue.pop()
        if current in revealed or current in opened or current in mines:
            continue
        opened.add(current)
        if adjacent[current] == 0:
            queue.extend(neighbours(width, height, current))
    return opened


def _constraints(width, height, adjacent, revealed, flags) -> list[tuple[frozenset[int], int]]:
    out = set()
    for cell in revealed:
        closed = [n for n in neighbours(width, height, cell) if n not in revealed and n not in flags]
        if closed:
            need = adjacent[cell] - sum(n in flags for n in neighbours(width, height, cell))
            out.add((frozenset(closed), need))
    return list(out)


def _tier1(cons):
    safe, mines = set(), set()
    for cells, need in cons:
        if need == 0:
            safe |= cells
        elif need == len(cells):
            mines |= cells
    return safe, mines


def _tier2(cons):
    safe, mines = set(), set()
    for a_cells, a_need in cons:
        for b_cells, b_need in cons:
            if a_cells is b_cells or not a_cells < b_cells:
                continue
            rest, left = b_cells - a_cells, b_need - a_need
            if left == 0:
                safe |= rest
            elif left == len(rest):
                mines |= rest
    return safe, mines


class _Budget(Exception):
    pass


def _enumerate(cells: list[int], cons, budget: list[int]) -> tuple[dict[int, int], dict[int, dict[int, int]]]:
    """Solutions by mine count k: counts[k] and, per cell, how many of them mine it."""
    index = {c: i for i, c in enumerate(cells)}
    local = [([index[c] for c in cs], need) for cs, need in cons]
    by_cell = [[] for _ in cells]
    for ci, (cs, _) in enumerate(local):
        for i in cs:
            by_cell[i].append(ci)
    mined, unset = [0] * len(local), [len(cs) for cs, _ in local]
    assign, counts, per = [0] * len(cells), {}, {c: {} for c in cells}

    def rec(i: int, k: int) -> None:
        budget[0] -= 1
        if budget[0] < 0:
            raise _Budget
        if i == len(cells):
            counts[k] = counts.get(k, 0) + 1
            for j, value in enumerate(assign):
                if value:
                    per[cells[j]][k] = per[cells[j]].get(k, 0) + 1
            return
        for value in (0, 1):
            if any(mined[ci] + value > local[ci][1] or mined[ci] + value + unset[ci] - 1 < local[ci][1] for ci in by_cell[i]):
                continue
            assign[i] = value
            for ci in by_cell[i]:
                mined[ci] += value
                unset[ci] -= 1
            rec(i + 1, k + value)
            for ci in by_cell[i]:
                mined[ci] -= value
                unset[ci] += 1
        assign[i] = 0

    rec(0, 0)
    return counts, per


def _groups(cons) -> list[tuple[list[int], list]]:
    parent: dict[int, int] = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for cells, _ in cons:
        first = next(iter(cells))
        for c in cells:
            parent[find(c)] = find(first)
    groups: dict[int, list[int]] = {}
    for c in parent:
        groups.setdefault(find(c), []).append(c)
    return [(sorted(g), [(cs, n) for cs, n in cons if cs & set(g)]) for g in groups.values()]


def _tier3(cons, closed: Iterable[int], mines_left: int):
    """Certain cells from exact reasoning per frontier group plus the global mine count."""
    closed = set(closed)
    budget = [ENUMERATION_BUDGET]
    results = [(cells,) + _enumerate(cells, group, budget) for cells, group in _groups(cons)]
    frontier = {c for cells, _, _ in results for c in cells}
    interior = closed - frontier
    fits = lambda total: 0 <= mines_left - total <= len(interior)   # noqa: E731
    safe, mines = set(), set()
    for gi, (cells, counts, per) in enumerate(results):
        rest = _sizes(other[1] for gj, other in enumerate(results) if gj != gi)
        feasible = [k for k in counts if any(fits(k + r) for r in rest)]
        total = sum(counts[k] for k in feasible)
        for cell in cells:
            hits = sum(per[cell].get(k, 0) for k in feasible)
            if total and hits == 0:
                safe.add(cell)
            elif total and hits == total:
                mines.add(cell)
    if interior:
        left = {mines_left - k for k in _sizes(counts for _, counts, _ in results) if fits(k)}
        if left == {0}:
            safe |= interior
        elif left == {len(interior)}:
            mines |= interior
    return safe, mines


def _sizes(distributions) -> set[int]:
    """Every possible total of mines over several frontier groups."""
    totals = {0}
    for counts in distributions:
        totals = {a + b for a in totals for b in counts}
    return totals


def analyse(width: int, height: int, mines: frozenset[int], start: Iterable[int]) -> Analysis:
    """Clear the board from the already-open ``start`` cells by logic alone."""
    adjacent = adjacency(width, height, mines)
    revealed: set[int] = set()
    for cell in start:
        revealed |= flood(width, height, mines, adjacent, revealed, cell)
    flags: set[int] = set()
    goal = width * height - len(mines)
    tier = steps = 0
    try:
        while len(revealed) < goal:
            cons = _constraints(width, height, adjacent, revealed, flags)
            closed = [c for c in range(width * height) if c not in revealed and c not in flags]
            for level, step in ((1, _tier1), (2, _tier2), (3, None)):
                safe, found = step(cons) if step else _tier3(cons, closed, len(mines) - len(flags))
                safe -= revealed | flags
                found -= flags
                if safe or found:
                    tier = max(tier, level)
                    break
            else:
                return Analysis(False, tier, steps)
            steps += 1
            flags |= found
            for cell in safe:
                if cell in mines:   # a sound solver never gets here; refuse rather than mislead
                    return Analysis(False, tier, steps)
                revealed |= flood(width, height, mines, adjacent, revealed, cell)
    except _Budget:
        return Analysis(False, max(tier, 3), steps)
    return Analysis(True, tier, steps)


def three_bv(width: int, height: int, mines: frozenset[int]) -> int:
    """Minimum clicks to clear the board (each zero region counts once)."""
    adjacent = adjacency(width, height, mines)
    seen: set[int] = set()
    clicks = 0
    for cell in range(width * height):
        if cell not in mines and cell not in seen and adjacent[cell] == 0:
            clicks += 1
            seen |= flood(width, height, mines, adjacent, seen, cell)
    return clicks + sum(1 for c in range(width * height) if c not in mines and c not in seen)
