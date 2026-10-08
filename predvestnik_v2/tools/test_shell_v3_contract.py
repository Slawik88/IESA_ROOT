#!/usr/bin/env python3
"""Static contract for the shell-v3 interface: flag wiring, tap targets, safe animation, honest copy."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "FastAPI/static"
css = (STATIC / "shell-v3.css").read_text(encoding="utf-8")
home = (STATIC / "app.15.js").read_text(encoding="utf-8")
hub = (STATIC / "app.04.js").read_text(encoding="utf-8")
index = (STATIC / "index.html").read_text(encoding="utf-8")
flags = (ROOT / "infrastructure/repositories/system_flags.py").read_text(encoding="utf-8")

# Every game shown in the hub is controlled by a real server flag.
hub_flags = re.findall(r"flag:'([a-z0-9_]+)'", hub)
assert len(hub_flags) == 3, hub_flags
for key in hub_flags:
    assert f'("{key}"' in flags, f"unknown flag {key}"

# Primary controls keep a 44px tap target.
for selector in (".v3-pill", ".v3-link", ".v3-row", ".nb", ".dn-close"):
    block = re.search(re.escape(selector) + r" \{[^}]*\}", css)
    assert block and re.search(r"(min-)?(height|width): 4[4-9]px|min-height: (5\d|7\d)px", block.group(0)), selector

# Motion budget: only transform/opacity are animated or transitioned in the new layer.
for line in css.splitlines():
    if "transition:" in line:
        assert not re.search(r"transition:[^;]*\b(width|height|margin|padding|top|left)\b", line), line
assert "@keyframes v3rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }" in css
assert "animation: v3rise .28s var(--v3-ease) backwards" in css
assert "backdrop-filter" not in css.split(".nav {", 1)[1].split("}", 1)[0]

# Quest reward claim: optimistic, but a failed balance refresh must not roll the reward back.
claim = home[home.index("function v3ClaimQuestReward"):home.index("// Баланс на профиле")]
assert "_v3RefreshBalance();" in claim and ".catch(e => { _v3Quests = before" in claim
assert "data-kind" in (STATIC / "app.16.js").read_text(encoding="utf-8") and "onclick=\"v3ClaimQuestReward('${" not in home

# TMA shell: version-gated chrome colours, haptics throttled, text selection restored for inputs.
assert "isVersionAtLeast(since)" in home and "'7.10'" in home and "_hapticAt" in home
assert "disableVerticalSwipes" in home
assert "overscroll-behavior: none" in css and "touch-action: manipulation" in css
assert "input, textarea" in css and "user-select: text" in css

# Navigation and honest copy.
assert index.count('type="button" class="nb') == 3
assert 'role="status"' in index and "dev-notice" in index
assert "/vip/" not in home and "Магазине" not in (STATIC / "app.02.js").read_text(encoding="utf-8").split("function showCurrModal", 1)[1][:2500]
# Skin tiers: server contract, cumulative fx classes, motion budget in the tier stylesheet.
skins_src = (ROOT / "core/skins_v3.py").read_text(encoding="utf-8")
assert 'TIERS: Final = ("D", "C", "B", "A", "S", "SS", "SSS")' in skins_src or 'TIERS = ("D", "C", "B", "A", "S", "SS", "SSS")' in skins_src
fx = (STATIC / "fx-tiers-v3.css").read_text(encoding="utf-8")
for level in range(1, 8):
    assert f"fx-{level}" in fx or level == 1, level
controller = (STATIC / "app.18.js").read_text(encoding="utf-8")
assert "fx-${i}" in controller and "v3_fx_cap" in controller and "visibilitychange" in controller
assert not re.search(r"classList\.add\([`'\"]skin-", controller), "tier classes must not use the skin- prefix"
def keyframe_props(css: str) -> dict[str, set[str]]:
    result, pos = {}, 0
    while (start := css.find("@keyframes", pos)) != -1:
        name = css[start:].split("{", 1)[0].split()[1]
        depth, i = 0, css.index("{", start)
        for j in range(i, len(css)):
            depth += css[j] == "{"
            depth -= css[j] == "}"
            if depth == 0:
                break
        result[name] = set(re.findall(r"([a-z-]+)\s*:", css[i + 1:j]))
        pos = j
    return result


appearance_files = ("appearance-v3.css", "appearance-ring-v3.css", "appearance-stage-v3.css", "skin-signatures-v3.css", "skin-signatures-2-v3.css", "looks-v3.css", "collect-v3.css", "toast-v3.css")
appearance = "".join((STATIC / name).read_text(encoding="utf-8") for name in appearance_files)
home_css = (STATIC / "shell-v3-home.css").read_text(encoding="utf-8")
for sheet in (fx, appearance, home_css, css):
    for name, props in keyframe_props(sheet).items():
        allowed = {"transform", "opacity"} | ({"background-position"} if name in {"apglint", "v3glint"} else set())   # блик по буквам лежит в фоне текста
        assert props <= allowed, (name, props)
assert len(keyframe_props(fx)) >= 4 and len(keyframe_props(appearance)) >= 12
for level in range(1, 8):
    assert f".ap-t{level}" in appearance, level
assert 'skins-v3.css' in index and 'fx-tiers-v3.css' in index
# Public card: skins scoped to the card, new card replaces the legacy opener, rows are clickable.
skins_css = (STATIC / "skins-v3.css").read_text(encoding="utf-8")
assert ".v3-scope.pp-neutral" in skins_css and "skin-deep-water" not in skins_css, "palettes now come from the server catalog"
card = (STATIC / "app.21.js").read_text(encoding="utf-8")
assert "window.openPublicProfile = openPublicCardV3" in card and "/public-profile-v3/" in card
assert "a.visible" in card and "pp-neutral" in card, "hidden look must fall back to the neutral palette"
top = (STATIC / "app.17.js").read_text(encoding="utf-8")
assert "_v3RowButton" in top and "openPublicProfile(" in top and "appearance-v3.css" in index
# Toasts: one implementation (app.28.js), shaped by the worn look; the old green blob and its CSS are gone.
assert sum(path.read_text(encoding="utf-8").count("function toast(") for path in STATIC.glob("app.*.js")) == 1
toast_js = (STATIC / "app.28.js").read_text(encoding="utf-8")
assert "apFromLook(_profileData?.look)" in toast_js and "tv-fr-" in toast_js and "role" in toast_js and "textContent" not in toast_js
assert "rgb(86,196,106)" not in (STATIC / "app.01.js").read_text(encoding="utf-8") and "@keyframes toastIn" not in (STATIC / "app.css").read_text(encoding="utf-8")
assert "toast-v3.css" in index
# Looks: native Telegram main button only inside Telegram, a first-visit tour, and the two display options live in settings.
looks_extra = (STATIC / "app.27.js").read_text(encoding="utf-8")
assert "tg && tg.initData && tg.MainButton" in looks_extra and "setParams(params)" in looks_extra and "hideProgress" in looks_extra and "is-native" in looks_extra
assert "lkTourOnce" in looks_extra and "pv_looks_tour" in looks_extra and "lkTourOnce(st)" in (STATIC / "app.23.js").read_text(encoding="utf-8")
settings_js, settings_css = (STATIC / "app.26.js").read_text(encoding="utf-8"), (STATIC / "settings-v3.css").read_text(encoding="utf-8")
assert "_toggleOled" in settings_js and "_toggleBig" in settings_js and "body.pv-oled" in settings_css and "!important" in settings_css.split("body.pv-oled", 1)[1].split("}", 1)[0]
assert "body.pv-big .page" in settings_css
print("OK: shell-v3 flags, tap targets, motion budget, claim safety and TMA shell are wired")
