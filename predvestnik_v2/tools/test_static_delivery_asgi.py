#!/usr/bin/env python3
"""Exercise the production FastAPI static surface without starting its DB lifespan."""
from pathlib import Path
import os
import re
import subprocess
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import RedirectResponse


ALLOWED = {
    "/static/app.css": "text/css",
    "/static/app.js": "application/javascript",
    "/static/app.devmode.js": "application/javascript",
    "/static/minesweeper-v2.css": "text/css",
    "/static/minesweeper-v2.js": "application/javascript",
    "/static/global-skins-v1.css": "text/css",
    "/static/global-skins-v1.js": "application/javascript",
    "/static/skins/lunar-archive-v1.webp": "image/webp",
    "/static/skins/void-atlas-v1.webp": "image/webp",
}
BLOCKED = (
    "/static/app.01.js",
    "/static/reconstruction-lab.css",
    "/static/reconstruction-lab.js",
    "/static/reconstruction-lab.html",
    "/static/concept-gallery.html",
    "/static/concept-gallery-production.html",
    "/static/concept-gallery-profile-card.html",
    "/static/design-concepts/profile-card/01-open-central-stage.png",
    "/static/economy-masterplan-report.html",
)


def assert_surface(client: TestClient, prefix: str = "") -> None:
    for path, media_type in ALLOWED.items():
        response = client.get(f"{prefix}{path}?v=contract-test")
        assert response.status_code == 200, path
        assert media_type in response.headers.get("content-type", ""), path
        assert response.content, path
    for path in BLOCKED:
        response = client.get(f"{prefix}{path}")
        assert response.status_code == 404, path
    for path in ("/static/app.css/",):
        response = client.get(f"{prefix}{path}?v=one", follow_redirects=False)
        assert response.status_code == 307, path
        assert urlparse(response.headers.get("location", "")).path == f"{prefix}{path[:-1]}", path
        assert urlparse(response.headers.get("location", "")).query == "v=one", path
    for method, path in (("get", "/reconstruction/"), ("post", "/reconstruction/start/")):
        response = getattr(client, method)(f"{prefix}{path}?x=1", follow_redirects=False)
        assert response.status_code == 404, path
    for method, path in (("get", "/zoo/"), ("post", "/zoo/start-expedition")):
        response = getattr(client, method)(f"{prefix}{path}?x=1", follow_redirects=False)
        assert response.status_code == 404, path


def assert_prefix_redirect_scope() -> None:
    """Prefix middleware must not rewrite application-owned redirects."""
    from FastAPI.prefix import strip_prefix_middleware

    app = FastAPI()

    @app.get("/external")
    async def external_redirect():
        return RedirectResponse("https://example.invalid/account", status_code=302)

    @app.get("/relative")
    async def relative_redirect():
        return RedirectResponse("next", status_code=302)

    client = TestClient(strip_prefix_middleware(app, "/predvestnik"))
    external = client.get("/predvestnik/external", follow_redirects=False)
    assert external.status_code == 302
    assert external.headers["location"] == "https://example.invalid/account"
    relative = client.get("/predvestnik/relative", follow_redirects=False)
    assert relative.status_code == 302
    assert relative.headers["location"] == "next"
    boundary = client.get("/predvestnik2/external", follow_redirects=False)
    assert boundary.status_code == 404
    unprefixed = client.get("/external", follow_redirects=False)
    assert unprefixed.status_code == 404


def main() -> None:
    from FastAPI.main import app
    from FastAPI.prefix import strip_prefix_middleware

    direct = TestClient(app)
    assert_surface(direct)
    assert_prefix_redirect_scope()
    css = direct.get("/static/app.css")
    assert "icons/x.svg" not in css.text
    assert re.search(
        r"\.profile-showcase-main\s*>\s*\.character-showcase-area\s*,\s*"
        r"\.profile-showcase-main\s*>\s*\.player-data-rail\s*\{"
        r"\s*height:\s*100%;\s*min-height:\s*0;\s*\}",
        css.text,
    )
    assert direct.get("/static/icons/x.svg").status_code == 404
    app_js = direct.get("/static/app.js").text
    assert "renderProfileShowcase(d,d.cosmetics,{caption:'Публичный профиль'})" in app_js
    assert "renderProfileShowcase(d,d.cosmetics,{caption:'Личный профиль',openLooks:true})" in app_js
    assert "renderPublicProfileHero" not in app_js
    assert "active_skin_id==='lunar_archive'" not in app_js
    assert "Атлас Бездны" in app_js
    assert "data-store-mode" in app_js and "/cosmetics/buy-lineup" in app_js
    assert "/global-skins-v1/buy" in app_js
    assert "function itemWord(value)" in app_js
    assert "store-detail-hero--${e(detail)}" in app_js
    assert "store-preview-sheet" in app_js and "syncSkinPreview" in app_js
    assert 'role="dialog" aria-modal="true"' in app_js
    assert "/payments/zarniki/packages" in app_js and "/payments/zarniki/invoice" in app_js
    assert "if(_activePage==='looks'&&selected){closeSelection();return;}" in app_js
    assert "catalogSkins" in app_js and "(item.owned||item.selected)&&item.id!=='default'" in app_js
    assert "document.activeElement===last" in app_js
    assert "globalThis.navBack=function()" in app_js
    assert 'aria-controls="store-panel"' in app_js
    assert 'data-page="looks" onclick="openLooksModal()"' in direct.get("/").text
    assert "api('/themes" not in app_js and "api(`/themes" not in app_js
    skin_css = direct.get("/static/global-skins-v1.css").text
    assert "background-attachment:scroll!important" in skin_css
    public_renderer = (ROOT / "FastAPI" / "static" / "app.12.js").read_text(encoding="utf-8")
    public_profile = public_renderer.split("window.openPublicProfile", 1)[1].split("window.openChatTracker", 1)[0]
    assert "duel_wins" not in public_profile
    # The former Reconstruction URL is a compatibility redirect, not a hidden
    # route into retired writers.  The current hub owns its destination.
    game = direct.get("/game", follow_redirects=False)
    assert game.status_code == 307
    expected_hub = f"{os.environ.get('ROOT_PATH', '').rstrip('/')}/?startapp=games"
    assert game.headers["location"] == expected_hub
    minesweeper = direct.get("/minesweeper")
    assert minesweeper.status_code == 200
    assert '/static/minesweeper-v2.js?v=' in minesweeper.text
    assert '/static/global-skins-v1.css?v=' in minesweeper.text
    assert '/static/global-skins-v1.js?v=' in minesweeper.text
    base = os.environ.get("ROOT_PATH", "").rstrip("/")
    assert f'href="{base}/"' in minesweeper.text
    rhythm = direct.get("/rhythm-v2")
    assert rhythm.status_code == 200
    assert f'href="{base}/"' in rhythm.text
    assert '/static/global-skins-v1.css?v=' in rhythm.text
    assert '/static/global-skins-v1.js?v=' in rhythm.text

    if os.environ.get("STATIC_DELIVERY_ROOTED") == "1":
        rooted = TestClient(strip_prefix_middleware(app, "/predvestnik"))
        assert_surface(rooted, "/predvestnik")
        rooted_game = rooted.get("/predvestnik/game", follow_redirects=False)
        assert rooted_game.status_code == 307
        assert rooted_game.headers["location"] == "/predvestnik/?startapp=games"
        rooted_minesweeper = rooted.get("/predvestnik/minesweeper")
        assert rooted_minesweeper.status_code == 200
        assert '/predvestnik/static/minesweeper-v2.js?v=' in rooted_minesweeper.text
        assert 'href="/predvestnik/"' in rooted_minesweeper.text
        rooted_rhythm = rooted.get("/predvestnik/rhythm-v2")
        assert rooted_rhythm.status_code == 200
        assert 'href="/predvestnik/"' in rooted_rhythm.text
    else:
        env = {**os.environ, "ROOT_PATH": "/predvestnik", "STATIC_DELIVERY_ROOTED": "1"}
        subprocess.run([sys.executable, __file__], cwd=ROOT, env=env, check=True)
    print("ASGI static delivery contract: OK")


if __name__ == "__main__":
    main()
