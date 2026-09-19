#!/usr/bin/env python3
"""Fast deterministic tests for Minesweeper board and state rules."""
from core import minesweeper_v2 as rules


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
