"""Contract for the season pass screen (app.43.js, pass-v3.css): wiring, the two calls to the server, the flag, the entry in «Что нового», calm styles, and a node run of the real script (tools/test_season_pass_ui_behavior.js). Read-only. Docs: docs/SEASON_PASS_UI.md."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "FastAPI/static"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from audit_release_whatsnew import validate_feed  # noqa: E402
from core import season_pass as rules  # noqa: E402
from ui_smoke_checks import SCREENS  # noqa: E402
from ui_stand import GAME_FLAGS, PASS_SCENARIOS  # noqa: E402

main_py = (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")
index = (STATIC / "index.html").read_text(encoding="utf-8")
delivery = (ROOT / "tools/test_static_delivery_asgi.py").read_text(encoding="utf-8")
shell = (STATIC / "app.01.js").read_text(encoding="utf-8")
core = (STATIC / "app.02.js").read_text(encoding="utf-8")
hub = (STATIC / "app.04.js").read_text(encoding="utf-8")
news = (STATIC / "app.42.js").read_text(encoding="utf-8")
script = (STATIC / "app.43.js").read_text(encoding="utf-8")
code = re.sub(r"^const _spWord = .*$", "", re.sub(r"//[^\n]*", "", script), flags=re.M)   # the comments name numbers and files that the code must not contain; the plural rule of Russian has its own 10 and 100
css = (STATIC / "pass-v3.css").read_text(encoding="utf-8")
plain_css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
router = (ROOT / "FastAPI/routers/season_pass.py").read_text(encoding="utf-8")
flags_repo = (ROOT / "infrastructure/repositories/system_flags.py").read_text(encoding="utf-8")
docs = (ROOT / "docs/SEASON_PASS_UI.md").read_text(encoding="utf-8")
news_docs = (ROOT / "docs/WHATS_NEW_V3.md").read_text(encoding="utf-8")
stand_docs = (ROOT / "docs/UI_STAND_AND_SMOKE.md").read_text(encoding="utf-8")

# Wiring: the page script comes after the one that holds the jump table and the profile (the part that reads the flag), the style sheet is served, linked and listed in the delivery test.
nums = [int(n) for n in re.findall(r"\d+", re.search(r"_APP_JS_PARTS = \[[^\]]*for i in \(([^)]*)\)", main_py).group(1))]
assert 43 in nums and 42 in nums and nums.index(42) < nums.index(43), nums
assert '"pass-v3.css"' in main_py and "pass-v3.css" in index and '"/static/pass-v3.css": "text/css"' in delivery
assert '<div id="pg-pass" class="page"></div>' in index
parts = {n: (STATIC / f"app.{n:02d}.js").read_text(encoding="utf-8") for n in nums}
for name in ("openSeasonPass", "loadSeasonPass", "spBack", "spClaim", "passCheck", "passHubRow"):
    owners = [n for n, text in parts.items() if re.search(rf"^function {name}\b", text, flags=re.M)]
    assert owners == [43], f"{name} is defined once, in app.43.js: {owners}"
assert "pass:loadSeasonPass" in shell, "the page loader of #pg-pass"
assert re.search(r"suppressBrowserBack=\[[^\]]*'pass'[^\]]*\]", shell), "the page has its own «‹ Назад», the floating one stays hidden"
assert "_gamesChildren=['pass']" in shell and "_gamesChildren.includes(name)" in shell, "the «Игры» tab stays lit on the pass page"
assert "typeof passHubRow==='function'" in hub and "passHubRow(host)" in hub, "the games hub asks the pass for its row"
assert re.search(r"try \{ checkWhatsNewBadge\(\); \} catch \(_\) \{\}\s*\n\s*try \{ passCheck\(\); \} catch \(_\) \{\}", core), "the profile load re-reads the pass for the dot on the «Игры» tab; a failure there never breaks the profile"
assert "pass:()=>openSeasonPass()" in core and "season:()=>openSeasonPass()" in core, "deep links"
assert re.search(r"^  pass: +\{ cta: 'Открыть Пропуск', tab: 'arena', run: \(\) => openSeasonPass\(\) \},?$", news, flags=re.M), "the jump of «Что нового»"
assert "`pass`" in news_docs, "docs/WHATS_NEW_V3.md names the jump key"

# The two calls to the server, and nothing else. The router answers exactly these.
assert script.count("api(") == 2, "the screen talks to the server twice: read and claim"
assert "api('/season-pass/me')" in script
assert "api('/season-pass/claim', { method: 'POST', body: JSON.stringify({ season }) })" in script
assert script.count("method: 'POST'") == 1
assert 'prefix="/season-pass"' in router and '@router.get("/me")' in router and '@router.post("/claim")' in router
assert re.search(r"class ClaimRequest\(BaseModel\):\s*\n\s*season: int", router)

# The flag: dark by default, read from the profile flags, never from guesses. The rules of the pass stay on the server.
assert rules.FLAG == "season_pass_v1" and "_sysFlags.season_pass_v1 !== true" in script
assert re.search(r'\("season_pass_v1",\s+"[^"]+",\s+False\)', flags_repo), "the flag is registered and off by default"
assert "season_pass_v1" in GAME_FLAGS, "the stand switches the flag together with the other modules"
assert re.search(rf"_SP_RHYTHM_TAPS = {rules.RHYTHM_MIN_CORRECT_TAPS};", script), "the hint «от N верных нажатий» repeats RHYTHM_MIN_CORRECT_TAPS of core/season_pass.py"
for number in (rules.LEVELS, rules.POINTS_PER_LEVEL, rules.MORA_PER_LEVEL, rules.ESSENCE_PER_LEVEL, rules.FULL_TRACK_MORA, rules.MINESWEEPER_POINTS, rules.RHYTHM_LEVEL_SCORE, 14):
    assert not re.search(rf"(?<![\w.#-]){number}(?![\w%.])", code), f"{number} comes from the server, the client does not recompute the rules"
assert "claimed_level" in script and "per_level" in script and "claimable_levels" in script, "the screen reads the numbers the server sends"

# Escaping: every text of the answer goes through the escaper, markup comes only from the script.
assert script.count("_profileEsc(") >= 15 and "innerHTML = String(" not in script and "eval(" not in script and "new Function" not in script and "location" not in code
assert "insertAdjacentHTML('beforeend', '<i class=\"sr-only sp-sr\">, есть награда пропуска</i>')" in script

# Styles: every sp-* class the script writes has a rule; motion is only opacity and transform and has the three off switches; no costly effects.
body = re.sub(r"\$\{[^}]*\}", " ", script)
used = set(re.findall(r"(?<![\w-])(sp-[a-z0-9]+(?:-[a-z0-9]+)*)", body))
styled = set(re.findall(r"\.(sp-[a-z0-9]+(?:-[a-z0-9]+)*)", plain_css))
hooks = {"sp-sr"} | {name for name in used if name.startswith("sp-h-")}   # the hidden note for screen readers (the global .sr-only styles it) and the ids that headings give to their sections (aria-labelledby)
assert {"sp-h-track", "sp-h-how", "sp-h-prev"} <= hooks
assert used - styled - hooks == set(), f"classes without a rule: {sorted(used - styled - hooks)}"
for name, frames in re.findall(r"@keyframes\s+([\w-]+)\s*\{((?:[^{}]|\{[^{}]*\})*)\}", plain_css):
    assert set(re.findall(r"([a-z-]+)\s*:", frames)) <= {"opacity", "transform"}, f"{name} animates more than transform and opacity"
assert "@keyframes spslide" in plain_css
assert "prefers-reduced-motion: reduce" in plain_css and ".no-fx " in plain_css and 'body[data-dev="low"]' in plain_css
assert not re.search(r"backdrop-filter|clip-path|mix-blend-mode|blur\(|filter\s*:|vmax", plain_css), "no costly effects on a page that is read and tapped"
assert not re.search(r"transition\s*:[^;]*\b(width|height|margin|padding|top|left|all)\b", plain_css)
assert not re.search(r"animation\s*:[^;]*\binfinite\b", plain_css), "nothing loops on a page that is read"
assert re.search(r"\.nb\[data-sp\]::before", plain_css), "the dot on the dock tab"
assert re.search(r"\.sp-hub\.is-hot \.v3-game-go::before", plain_css), "the dot on the hub row"
assert re.search(r"\.sp-track \{[^}]*grid-template-columns: repeat\(10, minmax\(0, 1fr\)\)", plain_css), "ten columns that shrink: the path never widens the page"
assert re.search(r"\.sp-meter > span > i \{[^}]*animation: spslide", plain_css) and not re.search(r"\.sp-meter[^{]*\{[^}]*transition", plain_css), "the fill slides in and is never animated by width"

# The entry in «Что нового»: behind the flag, with a jump to the screen.
updates = validate_feed(json.loads((STATIC / "updates.json").read_text(encoding="utf-8")), "updates.json")
entry = next(u for u in updates if u["id"] == "2026-10-13-season-pass")
assert entry["flag"] == rules.FLAG, "players see the note only when the pass is open"
assert entry["open"] == "pass" and entry["area"] == "games" and entry.get("kind") != "fix" and entry["tag"] == "Новое"
assert entry["where"].startswith("Игры") and len(entry["short"]) <= 150 and len(entry["details"]) >= 4

# The stand and the smoke suite show every state; the docs name every scenario and screen so that the next agent can find them.
assert {"default", "fresh", "new", "idle", "finish", "max"} <= set(PASS_SCENARIOS)
screens = {name for name, _ in SCREENS if name.startswith("pass")}
assert {"pass", "pass-new", "pass-idle", "pass-finish", "pass-max", "pass-prev", "pass-refused", "pass-closed", "pass-error"} <= screens, screens
for name in sorted(screens) + sorted(PASS_SCENARIOS) + ["season_pass_v1", "/season-pass/me", "/season-pass/claim", "RHYTHM_MIN_CORRECT_TAPS"]:
    assert name in docs, f"docs/SEASON_PASS_UI.md names {name}"
assert "season_pass_v1" in stand_docs and "--pass" in stand_docs, "docs/UI_STAND_AND_SMOKE.md tells how to see the pass"

# The part parses on its own (the shell contract parses the whole script), and the real script behaves in a vm with a stub page and a stub server.
if shutil.which("node"):
    done = subprocess.run(["node", "--check", str(STATIC / "app.43.js")], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:400]
    done = subprocess.run(["node", str(ROOT / "tools/test_season_pass_ui_behavior.js")], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, (done.stderr or done.stdout)[-1500:]

print("OK: the season pass screen is wired, talks to the server twice, keeps the rules on the server, stays behind the flag and the styles stay calm")
