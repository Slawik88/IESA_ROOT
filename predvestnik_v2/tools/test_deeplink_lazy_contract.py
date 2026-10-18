#!/usr/bin/env python3
"""Диплинки (?startapp=…) не должны ссылаться на экраны напрямую: они объявляются в более поздних частях скрипта,
и прямое обращение роняло весь скрипт ReferenceError'ом (профиль из лидерборда игр, «‹» из игры, ссылки из чата)."""
import re
from pathlib import Path

js = (Path(__file__).resolve().parents[1] / "FastAPI" / "static" / "app.02.js").read_text(encoding="utf-8")
block = js[js.index("const LINKS={"):js.index("};", js.index("const LINKS={"))]
bare = re.findall(r"\w+:(open[A-Za-z0-9]+)\s*[,}]", block)
assert not bare, f"LINKS ссылается на {bare} напрямую: оберните в ()=>…()"
print("OK: deep links resolve screens lazily")

for alias in ('bp', 'battlepass', 'pass', 'season'):
    assert f"{alias}:()=>openSeasonPass()" in block, f"{alias} should open the season pass"
