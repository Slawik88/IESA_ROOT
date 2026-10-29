"""Game leaderboards (Rhythm, Minesweeper) are the Mini App top itself: the same podium and rows, not a copy of them.

top-board.js = the game-page shim (top-board-v3.js) + the app parts that draw «Топ» (FastAPI/main.py, _TOP_BOARD_PARTS); the styles of the top live
in one file (top-board-v3.css) that the Mini App and the game pages both load.
"""
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
static = root / "FastAPI/static"
main = (root / "FastAPI/main.py").read_text(encoding="utf-8")
shim = (static / "top-board-v3.js").read_text(encoding="utf-8")

parts = re.search(r"_TOP_BOARD_PARTS = \(\"top-board-v3.js\", \*\(f\"app\.\{i:02d\}\.js\" for i in \(([^)]*)\)\)\)", main)
assert parts, "top-board.js = the shim + app parts"
numbers = [int(n) for n in parts.group(1).split(",")]
assert numbers == sorted(numbers), "app parts keep the order of app.js"
# every file that registers look scenes or ornaments must be in, or a look draws poorer in the games than in the Mini App
registries = {int(p.name[4:6]) for p in static.glob("app.*.js") if re.search(r"_scAdd\(|Object\.assign\((_ORN|_AP_DECOR|_ORN_FRAME)", p.read_text(encoding="utf-8"))}
assert registries <= set(numbers) and {17, 20, 22, 29, 50} <= set(numbers), (registries - set(numbers))
assert '"top-board.js": "".join(_read_static(p) for p in _TOP_BOARD_PARTS)' in main
assert "function gameTopBoardV3(" in shim and "v3Podium(" in shim and "_v3RowButton(" in shim, "the games draw with the Mini App podium and row"
assert not re.search(r"function (v3Podium|_v3PodId|_v3RowButton|apWho|apFromLook|apName)\b", shim), "the shim must not carry its own copy of the top"
assert "gameWhoV3" not in (static / "game-board-v3.js").read_text(encoding="utf-8"), "the old compact copy of the nick renderer is gone"

index = (static / "index.html").read_text(encoding="utf-8")
assert index.index("top-board-v3.css") < index.index("art-v3.css"), "the Mini App keeps the top styles at their old place in the cascade"
for page, script in (("rhythm-v2", "rhythm-v2.js"), ("minesweeper-v2", "minesweeper-v2.js")):
    html = (static / f"{page}.html").read_text(encoding="utf-8")
    js = (static / script).read_text(encoding="utf-8")
    for asset in ("/static/top-board.js", "/static/top-board-v3.css", "/static/appearance-v3.css", "/static/appearance-stage-v3.css", "/static/marks-v3.css", "{{SCENE_ART}}"):
        assert asset in html, (page, asset)
    assert html.index("top-board.js") < html.index(script), "the top loads before the game script"
    assert 'class="v3-top-list"' in html and "gameTopBoardV3(" in js and "gameTopRowV3" in js, page
    assert "lgl-pod" not in js and "lgl-medal-ico" not in js, f"{script}: its own podium is back"
print("OK: Rhythm and Minesweeper show the Mini App top itself (same podium, rows and styles), the profile stays one tap away")
