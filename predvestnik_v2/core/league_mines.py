"""League Minesweeper boards: deterministic, proven solvable without a guess, of the logic depth the level asks.

The server opens the start for the player (a zero region when one works), so no board ever depends
on a lucky first click, and the start alone never clears the board.  Every board is reproducible from its secret seed alone; the mines
never leave the server.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from core import mines_logic as logic
from core.league_v1 import MinesLevel, mines_par_seconds

ATTEMPTS = 400          # derived seeds tried for the requested depth
EXACT_ATTEMPTS = 120    # after this many, the closest no-guess depth seen is accepted
START_TRIES = 6         # start cells tried per layout


class BoardError(ValueError):
    pass


@dataclass(frozen=True)
class Board:
    mines: frozenset[int]
    start: int
    adjacent: dict[int, int]
    clicks: int          # 3BV: minimum clicks
    tier: int
    par_s: int


def _rand(seed: bytes, label: str, index: int) -> int:
    return int.from_bytes(hashlib.sha256(seed + f":{label}:{index}".encode()).digest()[:8], "big")


def _layout(seed: bytes, spec: MinesLevel) -> tuple[frozenset[int], list[int]]:
    """Mines and the candidate start cells, zero regions first, both in seed order."""
    total = spec.width * spec.height
    cells = list(range(total))
    for i in range(total - 1, 0, -1):
        j = _rand(seed, "shuffle", i) % (i + 1)
        cells[i], cells[j] = cells[j], cells[i]
    mines = frozenset(cells[:spec.mines])
    adjacent = logic.adjacency(spec.width, spec.height, mines)
    safe = sorted((c for c in range(total) if c not in mines), key=lambda c: _rand(seed, "start", c))
    return mines, [c for c in safe if adjacent[c] == 0] + [c for c in safe if adjacent[c] > 0]


def generate(seed: bytes, spec: MinesLevel) -> Board:
    """First derived board that logic alone clears from the start and that needs the level's depth.

    The start never wins by itself (depth 0 is refused).  When the exact depth does not turn up,
    the closest solvable depth seen so far is used.
    """
    if spec.mines >= spec.width * spec.height:
        raise BoardError("level leaves no safe cell")
    best = None
    for attempt in range(ATTEMPTS):
        derived = hashlib.sha256(seed + attempt.to_bytes(4, "big")).digest()
        mines, starts = _layout(derived, spec)
        for start in starts[:START_TRIES]:
            result = logic.analyse(spec.width, spec.height, mines, [start])
            if not result.solvable or result.tier < 1:
                continue
            if result.tier == spec.tier:
                return _board(spec, mines, start, result.tier)
            if best is None or abs(result.tier - spec.tier) < abs(best[2] - spec.tier):
                best = (mines, start, result.tier)
            break
        if attempt >= EXACT_ATTEMPTS and best:
            return _board(spec, *best)
    if best:
        return _board(spec, *best)
    raise BoardError("no solvable board for this level")


def _board(spec: MinesLevel, mines: frozenset[int], start: int, tier: int) -> Board:
    clicks = logic.three_bv(spec.width, spec.height, mines)
    return Board(mines, start, logic.adjacency(spec.width, spec.height, mines), clicks, tier,
                 mines_par_seconds(spec, clicks))
