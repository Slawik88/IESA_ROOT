"""Design lint of the Mini App screens (S13): regressions of the house style that a reader of a diff easily misses.

- Currency emoji 🪙 💎 ✨ 💧 are drawn (v3Cur, app.50.js). The shared renderers (sheet OM, toast, spend confirm, reward card, flying sparks)
  pass ready markup through v3CurIn, so no screen shows them as text; the browser check is ui_smoke.py (CURRENCY), this file guards the plumbing.
- Loading is a skeleton (v3Skel / .sk), not the text «Загрузка…» in a `.loader`.
- Screen headers are v3Head, not the hand-made `.v3-screen-head`.
- No inline `color:#…` in screen markup and no font under 10 px in the v3 stylesheets.
Online Mafia (S14–S15) and the admin panel (S10–S11) have their own sessions and are not linted here.

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_design_lint_v3.py
"""
from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "FastAPI" / "static"
APP = {p.name: p.read_text(encoding="utf-8") for p in sorted(STATIC.glob("app.*.js"))}
CSS = {p.name: p.read_text(encoding="utf-8") for p in sorted(STATIC.glob("*-v3*.css"))}
CSS_EXEMPT = {"mafia-online-v3.css"}     # S14–S15 rebuild it

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    if not ok:
        failures.append(message)


# 1. Shared renderers draw the currencies
helper = APP["app.50.js"]
check("function v3CurIn(" in helper and "_V3_CUR_EMOJI" in helper, "app.50.js: v3CurIn is missing")
check("el('mb').innerHTML=v3CurIn(body)" in APP["app.01.js"], "OM(): the sheet body must go through v3CurIn")
check("${v3CurIn(b.l)}" in APP["app.01.js"], "OM(): button labels must go through v3CurIn")
toast = APP["app.28.js"]
for needle, what in [("v3CurIn(_profileEsc(text))", "toast text"), ("v3CurIn(_profileEsc(v))", "confirm rows"),
                     ("v3CurIn(_profileEsc(s.cta", "confirm button"), ("v3CurIn(_profileEsc(glyph))", "toast/reward glyph")]:
    check(needle in toast, f"app.28.js: {what} must go through v3CurIn")
check("spark.innerHTML = v3Cur(currency)" in APP["app.31.js"], "v3Fly: sparks must be the drawn currency")

# v3CurIn semantics: attributes and <option> keep the text, the rest is drawn (the JS is mirrored to keep the test without a browser)
SPLIT = re.compile(r"""(<(?:[^>"']|"[^"]*"|'[^']*')*>)""")


def cur_in(html: str) -> str:
    raw, out = 0, []
    for part in SPLIT.split(html):
        if part.startswith("<"):
            m = re.match(r"^<(/?)(option|textarea|title)\b", part, re.I)
            if m:
                raw += -1 if m.group(1) else 1
            out.append(part)
        else:
            out.append(part if raw > 0 else re.sub("🪙|💎|✨|💧", "<svg/>", part))
    return "".join(out)


check(cur_in('<b aria-label="5 ✨">5 ✨</b><option>✨ Зарники</option>') == '<b aria-label="5 ✨">5 <svg/></b><option>✨ Зарники</option>',
      "v3CurIn mirror: attribute and option text must stay text")
check("(<(?:[^>\"']|\"[^\"]*\"|'[^']*')*>)" in helper, "v3CurIn: tag split must skip quoted attributes (keep in sync with this test)")

# 2. Skeletons, headers, inline colours
for name, js in APP.items():
    if name in ("app.55.js", "app.56.js", "app.07.js"):
        continue                                  # Mafia online and the old admin entry: their own sessions
    check('class="loader"' not in js, f"{name}: text loader «Загрузка…» — use v3Skel(label)")
    check("v3-screen-head" not in js, f"{name}: hand-made header — use v3Head(title, {{sub, back, end}})")
    hit = re.search(r'style="[^"]*\bcolor:\s*#[0-9a-fA-F]{3,8}', js)
    check(not hit, f"{name}: inline hex colour {hit.group(0)[:60] if hit else ''} — use the --v3-* tokens")
check("function v3Skel(" in APP["app.20.js"], "app.20.js: v3Skel is missing")

# 3. Smallest font in the v3 stylesheets
for name, css in CSS.items():
    if name in CSS_EXEMPT:
        continue
    for m in re.finditer(r"font-size:\s*([0-9.]+)px", css):
        check(float(m.group(1)) >= 10, f"{name}: font-size {m.group(1)}px under the 10 px floor (line {css.count(chr(10), 0, m.start()) + 1})")

# 4. Settings rows: one neutral icon colour (MINIAPP_DESIGN_RULES §1), red only for deleting the account
settings = APP["app.26.js"]
check(not re.search(r"_ST_ICO = \{[^}]*'#[0-9a-f]{6}'", settings, re.S), "app.26.js: settings icons carry their own colours again")

if failures:
    print("\n".join("FAIL " + f for f in failures))
    raise SystemExit(1)
print(f"OK design lint: {len(APP)} scripts, {len(CSS) - len(CSS_EXEMPT)} stylesheets; currencies, skeletons, headers, inline colours, 10 px floor, settings icons")
