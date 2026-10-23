#!/usr/bin/env python3
"""The level preview of the League ladder (FastAPI/static/league-ladder.js: spec) must show what the server will build.

The preview repeats core.league_v1.mines_level / rhythm_level / rhythm_drafts in JavaScript (the API is not changed for a
preview).  Every level 1…1000 of both games is compared; Python round() halves to even, the JS copy must too.
Run: PYTHONPATH=. python3 tools/test_league_preview_parity.py   (needs node)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import league_v1 as rules  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = r"""
const fs = require('fs'), vm = require('vm');
const ctx = {window: {}, Math, Number};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
const spec = ctx.window.LeagueLadder.spec, out = [];
for (let n = 1; n <= 1000; n++) out.push([spec('minesweeper', n), spec('rhythm', n)]);
process.stdout.write(JSON.stringify(out));
"""


def main() -> None:
    script = os.path.join(ROOT, "FastAPI", "static", "league-ladder.js")
    got = json.loads(subprocess.run(["node", "-e", NODE, script], capture_output=True, text=True, check=True).stdout)
    for level, (mines, rhythm) in enumerate(got, start=1):
        m, r = rules.mines_level(level), rules.rhythm_level(level)
        assert mines == {"width": m.width, "height": m.height, "mines": m.mines, "tier": m.tier}, (level, mines, m)
        assert rhythm == {"signals": r.signals, "window": r.base_window_ms, "drafts": rules.rhythm_drafts(r)}, (level, rhythm, r)
    print("PASS league ladder preview == core.league_v1 for levels 1..1000 of both games")


if __name__ == "__main__":
    main()
