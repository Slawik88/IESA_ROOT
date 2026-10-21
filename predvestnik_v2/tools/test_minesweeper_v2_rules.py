#!/usr/bin/env python3
"""Fast deterministic tests for Minesweeper board and state rules."""
from core import minesweeper_v2 as rules

# A real safe-halo board can win on its first open. Preserve the win while
# excluding it from a speed contest: no manual solving time was measured.
spec = rules.difficulty("easy")
layout = rules.board((536).to_bytes(32, "big"), spec, 14)
revealed, _, status, _ = rules.apply_action(spec=spec, layout=layout, revealed=set(), flags=set(), kind="open", cell=14)
assert status == "won" and len(revealed) == 30
assert not rules.speed_ranked(status=status, opened_actions=1, elapsed_ms=0)
assert not rules.speed_ranked(status=status, opened_actions=1, elapsed_ms=1200)
assert not rules.speed_ranked(status=status, opened_actions=2, elapsed_ms=0)
assert not rules.speed_ranked(status="active", opened_actions=2, elapsed_ms=250)
assert rules.speed_ranked(status=status, opened_actions=2, elapsed_ms=250)


for spec in rules.DIFFICULTIES.values():
    first = (spec.size * spec.size) // 2
    layout = rules.board(bytes(range(32)), spec, first)
    assert len(layout["mines"]) == spec.mines
    assert first not in layout["mines"]
    assert not set(rules.neighbours(spec.size, first)) & layout["mines"]
    for cell, value in layout["adjacent"].items():
        assert value == sum(next_cell in layout["mines"] for next_cell in rules.neighbours(spec.size, cell))

spec = rules.difficulty("easy")
layout = rules.board(b"x" * 32, spec, 0)
revealed, flags, status, changed = rules.apply_action(spec=spec, layout=layout, revealed=set(), flags=set(), kind="open", cell=0)
assert 0 in revealed and 0 in changed and status in ("active", "won")
closed = next(cell for cell in range(spec.size * spec.size) if cell not in revealed and cell not in layout["mines"])
revealed, flags, status, _ = rules.apply_action(spec=spec, layout=layout, revealed=revealed, flags=flags, kind="toggle_flag", cell=closed)
assert closed in flags
same_revealed, _, _, _ = rules.apply_action(spec=spec, layout=layout, revealed=revealed, flags=flags, kind="open", cell=closed)
assert same_revealed == revealed
mine = next(iter(layout["mines"]))
revealed, flags, status, changed = rules.apply_action(spec=spec, layout=layout, revealed=revealed, flags=flags, kind="open", cell=mine)
assert status == "lost" and changed == (mine,)
print("minesweeper_v2_rules: safe start, counts, flags and terminal loss OK")

# Independent geometric oracle: never call neighbours to validate neighbours.
# Corners, edges and centres on every difficulty, many seeds and safe first cells.
for spec in rules.DIFFICULTIES.values():
    total = spec.size ** 2
    for seed_id in range(64):
        for first in (0, spec.size-1, total//2, total-1):
            layout = rules.board(seed_id.to_bytes(32, "big"), spec, first)
            coords = [divmod(mine, spec.size) for mine in layout["mines"]]
            for cell, value in layout["adjacent"].items():
                row,col = divmod(cell, spec.size)
                expected = sum(max(abs(row-y),abs(col-x)) == 1 for y,x in coords)
                assert value == expected, (spec.id,seed_id,first,cell,value,expected)
print("Mines numbers: independent 8-neighbour geometry oracle passes 768 boards")
