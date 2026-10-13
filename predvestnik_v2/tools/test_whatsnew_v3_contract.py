"""Contract for the «Что нового» page (app.42.js, news-v3.css, FastAPI/static/updates.json): wiring, the format of the feed entries, the jumps «Открыть», the dots on the dock, calm styles, and a node run of the real script (tools/test_whatsnew_v3_behavior.js). Read-only. Format of the entries: docs/WHATS_NEW_V3.md."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "FastAPI/static"
sys.path.insert(0, str(ROOT / "tools"))
from audit_release_whatsnew import validate_feed  # noqa: E402

main_py = (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")
index = (STATIC / "index.html").read_text(encoding="utf-8")
delivery = (ROOT / "tools/test_static_delivery_asgi.py").read_text(encoding="utf-8")
shell = (STATIC / "app.01.js").read_text(encoding="utf-8")
core = (STATIC / "app.02.js").read_text(encoding="utf-8")
news = (STATIC / "app.42.js").read_text(encoding="utf-8")
app_css = (STATIC / "app.css").read_text(encoding="utf-8")
css = (STATIC / "news-v3.css").read_text(encoding="utf-8")
plain_css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
docs = (ROOT / "docs/WHATS_NEW_V3.md").read_text(encoding="utf-8")

# Wiring: the page script comes after the core part that keeps the data and the «seen» mark (app.02.js); the style sheet is served, linked and listed in the delivery test.
nums = [int(n) for n in re.findall(r"\d+", re.search(r"_APP_JS_PARTS = \[[^\]]*for i in \(([^)]*)\)", main_py).group(1))]
assert 2 in nums and 42 in nums and nums.index(2) < nums.index(42), nums
assert '"news-v3.css"' in main_py and "news-v3.css" in index and '"/static/news-v3.css": "text/css"' in delivery
assert '<div id="pg-news" class="page"></div>' in index
parts = {n: (STATIC / f"app.{n:02d}.js").read_text(encoding="utf-8") for n in nums}
for name in ("openWhatsNew", "loadWhatsNew", "wnBack"):
    owners = [n for n, text in parts.items() if re.search(rf"^function {name}\b", text, flags=re.M)]
    assert owners == [42], f"{name} is defined once, in app.42.js: {owners}"
assert "news:loadWhatsNew" in shell, "the page loader of #pg-news"
assert "news:()=>openWhatsNew()" in core, "the deep link to the page"
assert "openWhatsNew()" in index and "openWhatsNew()" in parts[39], "both entrances (the «Ещё» row and the bag menu) open the same page"

# The data and the «seen» mark stay in the core part; the old page code is gone from it and from app.css.
for name in ("_wnShown", "_wnFetch", "_wnSeenId", "_wnLatestId", "_wnNewCount", "_wnMarkSeen", "checkWhatsNewBadge", "_WN_ARCHIVE_BOUNDARY"):
    assert name in core, f"{name} stays in app.02.js"
assert "typeof _wnTabDots === 'function'" in core and "_wnTabDots(list)" in core, "the dots on the dock are recalculated whenever the feed is read"
assert not re.search(r"_wnCard|wnToggle|function _wnRender|function loadWhatsNew|function openWhatsNew", core), "the old page code is removed from app.02.js"
assert "wn-" not in re.sub(r"/\*.*?\*/", "", app_css, flags=re.S), "the old .wn-* rules are removed from app.css"
assert "_wnTabVisit(name)" in shell and "typeof _wnTabVisit === 'function'" in shell, "opening a dock tab puts its dot out"
assert re.search(r"suppressBrowserBack=\[[^\]]*'news'[^\]]*\]", shell), "the page has its own «‹ Назад», the floating one stays hidden"
assert "const _backHooks=[]" in shell and "navBack" in shell

# Tables: areas, groups and jumps. Every area belongs to a filter group; every jump has a short caption and points at something that exists.
area_block = news[news.index("const _WN_AREA = {"):news.index("// Чипы фильтра истории")]
areas = re.findall(r"^  (\w+): +\{ name: '([^']+)', group: '(\w+)', ic: '", area_block, flags=re.M)
area_keys = {key for key, _, _ in areas}
groups = dict(re.findall(r"\['(\w+)', '([^']+)'\]", news[news.index("const _WN_GROUPS = ["):news.index("// Раздел старых записей")]))
assert {"app", "games", "pets", "chests", "inventory", "looks", "quests", "top", "profile", "wallet", "chat"} <= area_keys, area_keys
assert all(group in groups for _, _, group in areas), "every area belongs to a filter group"
go_block = news[news.index("const _WN_GO = {"):news.index("const _wnOwn")]
jumps = re.findall(r"^  (\w+): +\{ cta: '([^']+)',(?: tab: '(\w+)',)? run: \(\) => ([^}]+) \},?$", go_block, flags=re.M)
go_keys = {key for key, _, _, _ in jumps}
assert len(jumps) == len(re.findall(r"cta: '", go_block)) >= 12, "every jump parses as key, caption, tab, call"
dock = set(re.findall(r'class="nb[^"]*" (?:id="[^"]*" )?data-page="(\w+)"', index))
for key, caption, tab, call in jumps:
    assert 3 <= len(caption) <= 24, f"{key}: the caption of the button is short ({caption!r})"
    assert not tab or tab in dock, f"{key}: dock tab {tab!r} exists in index.html"
    for page in re.findall(r"switchPage\('([\w-]+)'\)", call):
        assert f'id="pg-{page}"' in index, f"{key}: page {page} exists"
    for fn in re.findall(r"\b(open\w+)\(", call):
        assert any(re.search(rf"function\s+{fn}\b|window\.{fn}\s*=|\b{fn}\s*=\s*(?:async\s+)?(?:function|\()", text) for text in parts.values()), f"{key}: {fn} is defined"
assert "run:" in go_block and "eval(" not in news and "new Function" not in news and "location" not in news, "the page runs only the calls written in the table, never text from the feed"

# Escaping: every text of an entry goes through the escaper, markup comes only from the script.
assert news.count("_profileEsc(") >= 15 and "innerHTML = String(" not in news and "esc(" not in re.sub(r"_profileEsc\(", "", news)   # the hostile-text run of the behaviour test covers every field
assert "dangerouslySetInnerHTML" not in news and "insertAdjacentHTML('beforeend', '<i class=\"sr-only wn-sr\">, есть новое</i>')" in news

# The feed: format of the entries (docs/WHATS_NEW_V3.md). Fields besides the required ones are optional, but when present they must be valid.
feed = json.loads((STATIC / "updates.json").read_text(encoding="utf-8"))
updates = validate_feed(feed, "updates.json")
fix_tags = set(re.findall(r"'([^']+)'", re.search(r"_WN_FIX_TAGS = \[([^\]]*)\]", news).group(1)))
assert {"Исправления", "Исправлено", "Фикс", "Стабильность"} <= fix_tags
boundary = re.search(r"_WN_ARCHIVE_BOUNDARY = '([^']+)'", core).group(1)
ids = [u["id"] for u in updates]
assert boundary in ids, "the archive boundary is an entry of the feed"
shown = updates[:ids.index(boundary)]   # what the page can show; the archived entries below the boundary keep their old shape
assert len(shown) >= 40, len(shown)
marked = 0
for u in shown:
    where = f"{u['id']}"
    for field in ("area", "open", "where", "short", "flag", "kind"):
        assert field not in u or isinstance(u[field], str) and u[field].strip(), f"{where}.{field} is a non-empty string"
    if "area" in u:
        marked += 1
        assert u["area"] in area_keys, f"{where}.area {u['area']!r} is one of {sorted(area_keys)}"
    fix = u.get("kind") == "fix" or u["tag"] in fix_tags
    if "kind" in u:
        assert u["kind"] in ("fix", "new"), f"{where}.kind"
    if "open" in u:
        assert u["open"] in go_keys, f"{where}.open {u['open']!r} is one of {sorted(go_keys)}"
        assert not fix, f"{where}: a fix has no «Открыть» button, the field would be ignored"
    if "where" in u:
        assert len(u["where"]) <= 48, f"{where}.where is a path in words, up to 48 characters ({len(u['where'])})"
    if "short" in u:
        assert len(u["short"]) <= 150, f"{where}.short is one line, up to 150 characters ({len(u['short'])})"
        assert not u["short"].strip().lower().startswith(u["title"].strip().lower()), f"{where}.short complements the title, it does not repeat it"
    for term in u.get("terms", []):
        assert isinstance(term, dict) and term.get("term") and term.get("definition"), f"{where}.terms: term and definition"
    assert len(u["details"]) <= 14, f"{where}: details are bullets, not an essay"
assert marked >= 40, "the entries shown to players carry their area"
revision = next(u for u in shown if u["id"] == "2026-10-12-news-revision")
assert revision["area"] == "app" and revision.get("short") and len(revision["details"]) >= 3, "the patch note of this page is in the feed"
assert any("open" in u for u in shown) and any(u.get("where") for u in shown)

# The docs name every area and every jump, so a new key cannot appear in the code without a line for the next agent.
for key in sorted(area_keys | go_keys):
    assert f"`{key}`" in docs, f"docs/WHATS_NEW_V3.md names `{key}`"

# Styles: every wn-* class the script writes has a rule; motion is only opacity and transform and has the three off switches; no costly effects.
script = re.sub(r"\$\{[^}]*\}", " ", news)
used = set(re.findall(r"(?<![\w-])(wn-[a-z0-9]+(?:-[a-z0-9]+)*)", re.sub(r"'#?[\w-]*wn-h-(?:fresh|hist)'|id=\"wn-h-(?:fresh|hist)\"", "", script)))
styled = set(re.findall(r"\.(wn-[a-z0-9]+(?:-[a-z0-9]+)*)", plain_css))
hooks = {"wn-list", "wn-sr", "wn-h-fresh", "wn-h-hist"}   # ids and the hidden note for screen readers (the global .sr-only styles it)
assert used - styled - hooks == set(), f"classes without a rule: {sorted(used - styled - hooks)}"
for name, body in re.findall(r"@keyframes\s+([\w-]+)\s*\{((?:[^{}]|\{[^{}]*\})*)\}", plain_css):
    assert set(re.findall(r"([a-z-]+)\s*:", body)) <= {"opacity", "transform"}, f"{name} animates more than transform and opacity"
assert "@keyframes wnfade" in plain_css
assert "prefers-reduced-motion: reduce" in plain_css and ".no-fx " in plain_css and 'body[data-dev="low"]' in plain_css
assert not re.search(r"backdrop-filter|clip-path|mix-blend-mode|blur\(|filter\s*:|vmax", plain_css), "no costly effects on a page that is read and tapped"
assert not re.search(r"transition\s*:[^;]*\b(width|height|margin|padding|top|left|all)\b", plain_css)
assert not re.search(r"animation\s*:[^;]*\binfinite\b", plain_css), "nothing loops on a page that is read"
for selector, floor in ((".wn-chip", 40), (".wn-go", 36)):
    block = re.search(re.escape(selector) + r" \{[^}]*\}", plain_css)
    assert block and re.search(rf"min-height: ({floor}|[4-9]\d)px", block.group(0)), f"{selector} keeps a tap target of at least {floor}px"
assert re.search(r"\.wn-go::after \{[^}]*inset: -\d+px", plain_css), "a small link keeps a 44px tap zone"
assert re.search(r"\.nb\[data-wn\]::before", plain_css), "the dot on the dock tab"

# The parts parse on their own (the shell contract parses the whole script), and the real script behaves in a vm with a stub page.
if shutil.which("node"):
    done = subprocess.run(["node", "--check", str(STATIC / "app.42.js")], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[:400]
    done = subprocess.run(["node", str(ROOT / "tools/test_whatsnew_v3_behavior.js")], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, (done.stderr or done.stdout)[-1500:]

print("OK: «Что нового» is wired, the feed entries follow the format, «Открыть» ends on real screens and the styles stay calm")
