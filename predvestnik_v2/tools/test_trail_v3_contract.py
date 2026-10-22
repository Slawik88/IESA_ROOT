"""Static contract for the player screens of the Trail (pets v2, flag pets_v2): wiring, the way back to the classic screen, one action id per action, escaped server text, calm tone, honest hints. Read-only."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "FastAPI/static"
main_py = (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")
index = (STATIC / "index.html").read_text(encoding="utf-8")
delivery = (ROOT / "tools/test_static_delivery_asgi.py").read_text(encoding="utf-8")
shell = (STATIC / "app.01.js").read_text(encoding="utf-8")
hub = (STATIC / "app.40.js").read_text(encoding="utf-8")
more = (STATIC / "app.41.js").read_text(encoding="utf-8")
css = (STATIC / "trail-v3.css").read_text(encoding="utf-8")
js = hub + more
plain_css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

# Wiring: both script parts come after the classic pets screen (app.12.js) and in this order; the style sheet is served, linked and listed in the delivery test.
parts = [int(n) for n in re.findall(r"\d+", re.search(r"_APP_JS_PARTS = \[[^\]]*for i in \(([^)]*)\)", main_py).group(1))]
assert 12 in parts and 40 in parts and 41 in parts and parts.index(12) < parts.index(40) < parts.index(41), parts
assert '"trail-v3.css"' in main_py and "trail-v3.css" in index and '"/static/trail-v3.css": "text/css"' in delivery
assert "const _TR_VIEWS = {}" in hub and "_TR_VIEWS.pet" in more and "_TR_VIEWS.camp" in more and "_TR_VIEWS.track" in more and "_TR_VIEWS.trial" in more

# Entry: the pets tab opens the Trail only while the flag is on; otherwise, and when the server says the Trail is closed, the classic screen stays.
assert "const _trClassic = window.openPetsV1;" in hub
assert re.search(r"window\.openPetsV1 = function \(\) \{\s*if \(_sysFlags\.pets_v2 !== true\) return _trClassic\.apply\(this, arguments\);\s*return openTrail\(\);", hub)
assert "Тропа пока закрыта" in hub and "_sysFlags.pets_v2 = false" in hub and "_trClassic()" in hub

# Every write goes through one function that attaches an action id (at most 96 characters); the id lives until the server answers: kept on every failed/uncertain response, dropped only on confirmed success.
forecast = hub[hub.index("function _trForecastSchedule"):hub.index("function _trSendHtml")]
assert "api('/pets-v2/preview'" in forecast and len(re.findall(r"method:\s*'POST'", forecast)) == 1
assert len(re.findall(r"method:\s*'POST'", js.replace(forecast, ""))) == 1 and "action_id: key.id" in hub
assert ".slice(0, 12)" in hub and "randomUUID" in hub, "id = short prefix + uuid, far below 96 characters"
assert "delete _tr.keys[key.k]; return data;" in hub and "if (typeof error === 'string') delete _tr.keys[key.k]" not in hub
assert "_tr.needsRefresh" in hub and "await trailRecover(); return;" in hub
for path in ("start", "claim", "build", "build-presets", "camp/upgrade", "talisman/reforge", "track/start", "track/open", "trial", "feed"):
    assert f"_trPost('{path}'" in js, path
assert "_tr.busy" in hub and "async function _trRun" in hub, "one action at a time: a second tap does not send a second request"

# The numbers of the rules come from the answer (me.rules), not from a copy in the client.
assert "rules.energy" in hub and "rules.xp" in hub and "rules.paths" in hub and "rules.swap" in more and "rules.reforge" in more and "rules.calling_texts" in more and "rules.traits" in more
assert not re.search(r"\b(625|45|30)\b[^\n]*(energy|энерг)", js), "no copy of energy costs"

# Honest hints and the calm tone: the chance is shown exactly as the server sent it; the daily cap is a quiet line, not a warning; failure keeps the part of the reward.
decision = hub[hub.index("function _trDecisionHtml"):hub.index("function trailPath(")]
odds = next(line for line in decision.splitlines() if "const odds =" in line)
assert "h.chance != null" in odds and "h.range" in odds and "h.sign" in decision and "Math.round" not in odds and "toFixed" not in odds, "the chance is printed as it came, never recomputed"
assert "На сегодня питомцы устали расти. Награды остаются." in hub
traces = hub[hub.index("function _trTraces"):hub.index("function _trSlot(")]
assert not re.search(r"tr-err|v3-err|danger|is-low|color:\s*red", traces), "the daily cap is a quiet line, not a warning"
assert "Часть награды сохранена" in hub and "Уровни, Связь и питомец остаются при вас" in hub
assert "Питомцев пока нет, их можно получить в сундуках." in hub
assert "Следы за сегодня" in hub and "const label = `Следы за сегодня: ${fmt(shown)} из ${fmt(max)}`" in hub

# Tone of the pet screens: no banners, no buy buttons, no store links.
assert not re.search(r"openStore|Купить|купить|Витрин|Магазин|openZarnikiTopup", js)

# Server text is escaped before it lands in the markup.
assert hub.count("_trE(") >= 20 and more.count("_trE(") >= 40 and "const _trE = _profileEsc;" in hub
assert "function _trKey(" in hub and "crypto" in hub and "Date.now()" in hub

# Phones: the way back of the system button closes the sheet or the sub-screen first; sheets trap focus and close on Esc.
assert "const _backHooks=[]" in shell and "_backHooks.some(" in shell and "_backHooks.push(" in hub
assert "'Escape'" in hub and "'Tab'" in hub and 'aria-modal="true"' in hub and 'role="alert"' in hub
assert "setInterval(() =>" in hub and "document.hidden" in hub, "the clock does not run while the app is hidden"

# Styles: every tr-* class the scripts write has a rule; motion is only transform and opacity and has the usual three off switches; no costly effects.
used = set(re.findall(r"\b(tr-[a-z0-9]+(?:-[a-z0-9]+)*)\b", re.sub(r"\$\{[^}]*\}", " ", js)))
styled = set(re.findall(r"\.(tr-[a-z0-9]+(?:-[a-z0-9]+)*)", plain_css))
hooks = {"tr-sheet-t", "tr-slots", "tr-pets", "tr-traces", "tr-slot", "tr-more", "tr-pet", "tr-job", "tr-who", "tr-facts-list", "tr-tal"}   # ids and hooks that only the scripts or the tests look for
hooks.update({"tr-preset-name", "tr-preset-slot", "tr-send-forecast", "tr-send-quote"})  # labelled inputs and live forecast regions
assert used - styled - hooks == set(), f"classes without a rule: {sorted(used - styled - hooks)}"
for name, props in re.findall(r"@keyframes\s+([\w-]+)\s*\{(.*?)\n(?=@|\.|/|\n|$)", plain_css, flags=re.S):
    assert set(re.findall(r"([a-z-]+)\s*:", props)) <= {"transform", "opacity"}, f"{name} animates more than transform and opacity"
assert "@keyframes trslide" in plain_css and "@keyframes trrise" in plain_css and "@keyframes trpop" in plain_css
assert "prefers-reduced-motion: reduce" in plain_css and ".no-fx " in plain_css and 'body[data-dev="low"]' in plain_css
assert not re.search(r"backdrop-filter|clip-path|mix-blend-mode|blur\(|vmax", plain_css), "no costly effects on a screen that is read and tapped"
assert not re.search(r"transition\s*:[^;]*\b(width|height|margin|padding|top|left)\b", plain_css)
for selector in (".tr-row", ".tr-chip", ".tr-seg-b", ".tr-opt"):
    block = re.search(re.escape(selector) + r" \{[^}]*\}", plain_css)
    assert block and re.search(r"min-height: (4[4-9]|[5-9]\d)px", block.group(0)), f"{selector} keeps a 44px tap target"

# The parts parse on their own (the shell contract parses the whole script).
if shutil.which("node"):
    for name in ("app.40.js", "app.41.js"):
        done = subprocess.run(["node", "--check", str(STATIC / name)], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr[:400]

print("OK: the Trail screens are wired, fall back to the classic screen, send one action id per action and keep the calm tone")
