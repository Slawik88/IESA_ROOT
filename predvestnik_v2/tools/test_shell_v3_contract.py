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
skins_src = (ROOT / "core/global_skins_v1.py").read_text(encoding="utf-8")
assert 'TIERS = ("D", "C", "B", "A", "S", "SS", "SSS")' in skins_src
declared = re.findall(r'"tier": "(D|C|B|A|S|SS|SSS)"', skins_src)
assert len(declared) == skins_src.count('"css_class":'), "every skin needs a tier"
fx = (STATIC / "fx-tiers-v3.css").read_text(encoding="utf-8")
for level in range(1, 8):
    assert f"fx-{level}" in fx or level == 1, level
controller = (STATIC / "app.18.js").read_text(encoding="utf-8")
assert "fx-${i}" in controller and "v3_fx_cap" in controller and "visibilitychange" in controller
assert not re.search(r"classList\.add\([`'\"]skin-", controller), "tier classes must not use the skin- prefix"
for frame in re.findall(r"@keyframes [a-z0-9]+ \{(.*?)\}\s*(?=\n|$)", fx, re.S):
    props = set(re.findall(r"([a-z-]+)\s*:", frame))
    assert props <= {"transform", "opacity"}, props
assert 'skins-v3.css' in index and 'fx-tiers-v3.css' in index
print("OK: shell-v3 flags, tap targets, motion budget, claim safety and TMA shell are wired")
