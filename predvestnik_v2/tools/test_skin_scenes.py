#!/usr/bin/env python3
"""Skin scenes (app.35–38.js, skin-scene-*-v3.css): every look has its own world around the avatar, the world grows with the tier, and it stays cheap.

A scene is a list of layers [minimum tier 2..7, 'shape motion ...', {geometry and variables}]; here the data is read out of the real JS (node) and checked:
known shapes and motions, every picture it names is drawn, every tier C..SS adds something, the number of layers fits the budget of the phone classes."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
STATIC = ROOT / "FastAPI/static"

from core.skins_v3_catalog import SKINS  # noqa: E402
import scene_art  # noqa: E402

# Looks that do not have their own scene yet (the list only shrinks; when it is empty every look has a world).
PENDING = {"cobweb", "crimson_dark", "garland", "midnight_chimes",
           "pumpkin_lantern", "scarlet_star", "snow_globe", "witch_hour"}

SHAPES = {"glow", "ring", "sil", "dot", "band", "wave", "arc"}
MOTIONS = {"drift", "sway", "pulse", "breathe", "beat", "blink", "twinkle", "float", "rise", "spin", "ripple", "shimmer", "sweep", "cross", "peek", "flash"}
FLAGS = {"w2", "m", "fl", "st", "go", "rev", "dash"}
KEYS = {"l", "t", "r", "b", "w", "h", "c", "c2", "k", "o", "s", "s0", "s1", "bs", "bg", "bw", "bp", "gd", "dur", "del", "dx", "dy", "ang", "rot", "org", "fx", "fy", "tx", "ty", "tw"}
EVENTS = {"peek", "flash", "cross", "sweep", "rise", "ripple", "twinkle"}   # hidden while still (.ap-low and reduced motion): see skin-scene-v3.css
MAX_LAYERS = 24            # per look, everything at SSS
MAX_LITE_ANIMATED = 15     # animated layers a mid phone (no .w2) still runs at SSS

parts = sorted(STATIC.glob("app.3[5-8].js"))
assert parts and parts[0].name == "app.35.js"
main_py = (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")
index = (STATIC / "index.html").read_text(encoding="utf-8")
for part in parts:
    assert f'"{part.name}"' in main_py or re.search(rf"\b{int(part.name[4:6])}\b", re.search(r"_APP_JS_PARTS = \[.*?\]", main_py, re.S).group(0)), f"{part.name} is not in _APP_JS_PARTS"
art_css = {}
for letter in "abcd":
    name = f"skin-scene-{letter}-v3.css"
    assert name in main_py and name in index, f"{name} must be listed in _SHELL_V3_CSS and linked in index.html"
    art_css[letter] = (STATIC / name).read_text(encoding="utf-8")
assert "skin-scene-v3.css" in main_py and "skin-scene-v3.css" in index
drawn = re.findall(r"^\.i-([A-Za-z0-9_]+) \{ --img: url\(", "".join(art_css.values()), re.M)
assert len(drawn) == len(set(drawn)), "a picture is drawn twice"
for name, value in re.findall(r'^\.i-([A-Za-z0-9_]+) \{ --img: url\("data:image/svg\+xml,(.*)"\); \}$', "".join(art_css.values()), re.M):
    try:
        ET.fromstring(urllib.parse.unquote(value))
    except ET.ParseError as error:
        raise AssertionError(f"picture {name} is not valid SVG (a browser draws nothing): {error}")
for name, text in scene_art.render().items():
    assert (STATIC / name).read_text(encoding="utf-8") == text, f"{name} differs from tools/scene_art*.py: run tools/scene_art.py"

# The renderer puts the scene between the background and the particles and the CSS keeps it still where it must.
renderer = (STATIC / "app.20.js").read_text(encoding="utf-8")
assert re.search(r"</div>\$\{apScene\(ap\)\}<div class=\"ap-fx", renderer), "apStage: .ap-bg, then the scene, then .ap-fx"
scene_css = (STATIC / "skin-scene-v3.css").read_text(encoding="utf-8")
assert ".ap-lite .ap-scene .w2 { display: none; }" in scene_css and ".ap-low .ap-scene :is(" in scene_css and "prefers-reduced-motion" in scene_css
for keyframes in re.findall(r"@keyframes \w+ \{(.*?)\n", scene_css):
    assert not re.search(r"\b(left|top|width|height|filter|background|box-shadow)\s*:", keyframes), "scene motion is transform and opacity only"
assert "filter:" not in re.sub(r"/\*.*?\*/", "", scene_css, flags=re.S), "light is a gradient, never a filter"

if not shutil.which("node"):
    print("OK: scene files wired (node is not installed: scene data not evaluated)")
    sys.exit(0)

source = "\n".join(p.read_text(encoding="utf-8") for p in parts) + "\nprocess.stdout.write(JSON.stringify([..._AP_SCENES]));"
done = subprocess.run(["node", "-e", source], capture_output=True, text=True)
assert done.returncode == 0, done.stderr[:400]
scenes = dict(json.loads(done.stdout))
assert set(scenes) <= set(SKINS), f"scenes for unknown looks: {sorted(set(scenes) - set(SKINS))}"
missing = {sid for sid in SKINS if sid not in scenes}
assert missing == PENDING, f"looks without a scene: {sorted(missing - PENDING)}; looks with a scene still listed as pending: {sorted(PENDING - missing)}"
used: set[str] = set()
for sid, layers in scenes.items():
    assert 6 <= len(layers) <= MAX_LAYERS, f"{sid}: {len(layers)} layers"
    tiers = {layer[0] for layer in layers}
    assert {2, 3, 4, 5, 6} <= tiers, f"{sid}: every tier C..SS must add something (has {sorted(tiers)})"
    animated = 0
    for tier, classes, geo in layers:
        assert isinstance(tier, int) and 2 <= tier <= 7, (sid, tier)
        words = classes.split()
        assert words[0] in SHAPES, f"{sid}: unknown shape in '{classes}'"
        motions = [w for w in words[1:] if w in MOTIONS]
        assert len(motions) <= 1 or set(motions) == {"float", "blink"}, f"{sid}: one motion per layer (only float with blink may share): '{classes}'"
        pictures = [w[2:] for w in words if w.startswith("i-")]
        for w in words[1:]:
            assert w in MOTIONS or w in FLAGS or w.startswith("i-"), f"{sid}: unknown word '{w}' in '{classes}'"
        for picture in pictures:
            assert picture in drawn, f"{sid}: picture i-{picture} is not drawn (tools/scene_art_*.py)"
            used.add(picture)
        assert words[0] != "sil" or pictures, f"{sid}: a silhouette needs a picture: '{classes}'"
        assert words[0] != "wave" or ("go" in words and pictures), f"{sid}: a wave needs 'go' and a picture"
        assert set(geo) <= KEYS, f"{sid}: unknown variable {sorted(set(geo) - KEYS)}"
        animated += bool(motions or "go" in words) and "w2" not in words
    assert animated <= MAX_LITE_ANIMATED, f"{sid}: {animated} animated layers for a mid phone (budget {MAX_LITE_ANIMATED})"
unused = sorted(set(drawn) - used)
assert not unused, f"pictures nobody uses: {unused}"
print(f"OK: skin scenes: {len(scenes)} looks with their own world, {len(drawn)} pictures, every tier C..SS adds a layer")
