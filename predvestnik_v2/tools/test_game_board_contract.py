"""Game leaderboards (Rhythm, Minesweeper) draw nicks like the Mini App tops and keep the profile link."""
from pathlib import Path

static = Path(__file__).resolve().parents[1] / "FastAPI/static"
board = (static / "game-board-v3.js").read_text(encoding="utf-8")
assert "window.gameWhoV3" in board and "skinNicknameV3" in board and "v3-markdot" in board and "v3-vipdot" in board
assert "innerHTML" not in board, "the renderer builds a string; every dynamic value goes through esc()"
for page, script in (("rhythm-v2", "rhythm-v2.js"), ("minesweeper-v2", "minesweeper-v2.js")):
    html = (static / f"{page}.html").read_text(encoding="utf-8")
    js = (static / script).read_text(encoding="utf-8")
    assert "/static/game-board-v3.js" in html and "/static/appearance-v3.css" in html and "/static/marks-v3.css" in html, page
    assert html.index("game-board-v3.js") < html.index(script), "renderer loads before the game script"
    assert "gameWhoV3(player)" in js and "?startapp=public&profile=" in js and "aria-label" in js, page
print("OK: game leaderboards use the shared skin renderer and stay tappable")
