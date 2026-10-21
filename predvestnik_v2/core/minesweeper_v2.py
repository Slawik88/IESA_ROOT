"""Pure, server-owned rules for the approved Mini App Minesweeper."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Final, Literal


LEGACY_RULESET_VERSION: Final = "minesweeper-v1"
RULESET_VERSION: Final = "minesweeper-v2"
SUPPORTED_RULESETS: Final = frozenset((LEGACY_RULESET_VERSION, RULESET_VERSION))
GENERATOR_ATTEMPTS: Final = 8
ActionKind = Literal["open", "toggle_flag"]


@dataclass(frozen=True)
class Difficulty:
    id: str
    size: int
    mines: int
    label: str


DIFFICULTIES: Final = {
    "easy": Difficulty("easy", 6, 6, "Лёгкий"),
    "normal": Difficulty("normal", 9, 10, "Обычный"),
    "hard": Difficulty("hard", 9, 18, "Сложный"),
}


class MinesweeperRuleError(ValueError):
    pass


def speed_ranked(*, status: str, opened_actions: int, elapsed_ms: int | None) -> bool:
    """A safe first-click flood is a win, but measures no solving time."""
    return status == "won" and opened_actions >= 2 and elapsed_ms is not None and elapsed_ms > 0


def difficulty(value: str) -> Difficulty:
    try:
        return DIFFICULTIES[value]
    except KeyError as exc:
        raise MinesweeperRuleError("unknown Minesweeper difficulty") from exc


def neighbours(size: int, cell: int) -> tuple[int, ...]:
    row, column, result = divmod(cell, size)[0], cell % size, []
    for y in range(row - 1, row + 2):
        for x in range(column - 1, column + 2):
            if 0 <= y < size and 0 <= x < size and (y != row or x != column):
                result.append(y * size + x)
    return tuple(result)


def _random_order(seed: bytes, values: list[int]) -> list[int]:
    # A deterministic hash-stream shuffle avoids a global PRNG and makes every
    # server-side board reproducible solely from its secret seed + first cell.
    ordered = list(values)
    for index in range(len(ordered) - 1, 0, -1):
        digest = hashlib.sha256(seed + index.to_bytes(4, "big")).digest()
        swap = int.from_bytes(digest[:8], "big") % (index + 1)
        ordered[index], ordered[swap] = ordered[swap], ordered[index]
    return ordered


def _board_v1(seed: bytes, spec: Difficulty, first_cell: int) -> dict:
    total = spec.size * spec.size
    if not 0 <= int(first_cell) < total:
        raise MinesweeperRuleError("cell is outside the Minesweeper board")
    protected = {int(first_cell), *neighbours(spec.size, int(first_cell))}
    candidates = [cell for cell in range(total) if cell not in protected]
    # All release configurations have space for the safe halo.  This explicit
    # guard prevents a future malformed difficulty from silently losing first
    # move safety.
    if len(candidates) < spec.mines:
        raise MinesweeperRuleError("difficulty leaves no safe first move")
    mines = frozenset(_random_order(bytes(seed), candidates)[:spec.mines])
    adjacent = {cell: sum(next_cell in mines for next_cell in neighbours(spec.size, cell)) for cell in range(total)}
    return {"mines": mines, "adjacent": adjacent}


def board(seed: bytes, spec: Difficulty, first_cell: int, *, ruleset_version: str = RULESET_VERSION) -> dict:
    """Versioned deterministic boards: new games cannot win on their first open.

    Old runs/packets keep exactly their original layout. Bounded rejection plus
    a verified safe fallback prevents either a trivial board or an endless loop.
    """
    if ruleset_version not in SUPPORTED_RULESETS:
        raise MinesweeperRuleError("unknown Minesweeper ruleset")
    for attempt in range(GENERATOR_ATTEMPTS):
        candidate_seed = bytes(seed) if attempt == 0 else hashlib.sha256(
            bytes(seed) + b":minesweeper-v2:" + attempt.to_bytes(4, "big")
        ).digest()
        layout = _board_v1(candidate_seed, spec, first_cell)
        if ruleset_version == LEGACY_RULESET_VERSION or not _first_open_wins(layout, spec, first_cell):
            return layout
    # This layout is nontrivial for all 198 first cells of the shipped specs.
    layout = _board_v1(bytes(32), spec, first_cell)
    if _first_open_wins(layout, spec, first_cell):
        raise MinesweeperRuleError("difficulty has no nontrivial fallback board")
    return layout


def _first_open_wins(layout: dict, spec: Difficulty, first_cell: int) -> bool:
    return apply_action(spec=spec, layout=layout, revealed=set(), flags=set(), kind="open", cell=first_cell)[2] == "won"


def apply_action(*, spec: Difficulty, layout: dict, revealed: set[int], flags: set[int],
                 kind: ActionKind, cell: int) -> tuple[set[int], set[int], str, tuple[int, ...]]:
    total = spec.size * spec.size
    if kind not in ("open", "toggle_flag") or not 0 <= int(cell) < total:
        raise MinesweeperRuleError("invalid Minesweeper action")
    revealed, flags = set(revealed), set(flags)
    mines: frozenset[int] = layout["mines"]
    if kind == "toggle_flag":
        if cell not in revealed:
            if cell in flags:
                flags.remove(cell)
            elif len(flags) < spec.mines:
                flags.add(cell)
        return revealed, flags, "active", ()
    if cell in revealed or cell in flags:
        return revealed, flags, "active", ()
    if cell in mines:
        revealed.add(cell)
        return revealed, flags, "lost", (cell,)
    queue, changed = [cell], []
    while queue:
        current = queue.pop()
        if current in revealed or current in flags or current in mines:
            continue
        revealed.add(current); changed.append(current)
        if layout["adjacent"][current] == 0:
            queue.extend(neighbours(spec.size, current))
    status = "won" if len(revealed - mines) == total - spec.mines else "active"
    return revealed, flags, status, tuple(changed)
