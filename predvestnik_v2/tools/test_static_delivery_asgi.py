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
    "/local-games-sw.js": "application/javascript",
    "/static/local-games-v1.js": "application/javascript",
    "/static/nickname-v3.js": "application/javascript",
    "/static/nickname-v3.css": "text/css",
    "/static/skin-holidays-v3.css": "text/css",
    "/static/skin-scene-e-v3.css": "text/css",
    "/static/app.css": "text/css",
    "/static/app.js": "application/javascript",
    "/static/minesweeper-v2.css": "text/css",
    "/static/minesweeper-v2.js": "application/javascript",
    "/static/skin-runtime-v3.css": "text/css",
    "/static/skin-runtime-v3.js": "application/javascript",
    "/static/appearance-v3.css": "text/css",
    "/static/appearance-ring-v3.css": "text/css",
    "/static/appearance-stage-v3.css": "text/css",
    "/static/looks-v3.css": "text/css",
    "/static/skin-signatures-v3.css": "text/css",
    "/static/skin-signatures-2-v3.css": "text/css",
    "/static/skins-exclusive-v3.css": "text/css",
    "/static/skin-sig-a-v3.css": "text/css",
    "/static/skin-sig-b-v3.css": "text/css",
    "/static/skin-sig-c-v3.css": "text/css",
    "/static/public-card-v3.css": "text/css",
    "/static/collect-v3.css": "text/css",
    "/static/toast-v3.css": "text/css",
    "/static/toast-gift-v3.css": "text/css",
    "/static/quests-v3.css": "text/css",
    "/static/marks-v3.css": "text/css",
    "/static/inventory-v3.css": "text/css",
    "/static/trail-v3.css": "text/css",
    "/static/news-v3.css": "text/css",
    "/static/pass-v3.css": "text/css",
    "/static/store-v3.css": "text/css",
    "/static/motion-v3.css": "text/css",
    "/static/confirm-v3.css": "text/css",
    "/static/monolith-v3.css": "text/css",
    "/static/monolith-player-v3.css": "text/css",
    "/static/admin-legacy.css": "text/css",
    "/static/games-v3.css": "text/css",
    "/static/game-board-v3.js": "application/javascript",
}
BLOCKED = (
    "/static/app.01.js",
    "/static/global-skins-v1.js",
    "/static/skins/void-atlas-v1.webp",
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
    # The exact image preview must be readable before a creator can publish.
    for image in (ROOT / "FastAPI/static/announcements").glob("*.png"):
        response = client.get(f"{prefix}/static/announcements/{image.name}")
        assert response.status_code == 200 and response.content == image.read_bytes(), image.name
        assert response.headers.get("content-type") == "image/png", image.name
        assert response.headers.get("cache-control") == "no-cache", image.name
    assert client.get(f"{prefix}/static/announcements/no-such-image.png").status_code == 400
    for path, media_type in ALLOWED.items():
        response = client.get(f"{prefix}{path}?v=contract-test")
        assert response.status_code == 200, path
        assert media_type in response.headers.get("content-type", ""), path
        assert response.content, path
        assert response.headers.get("cache-control") == "no-cache", path
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
    from FastAPI.main import app, _ASSET_VER
    from FastAPI.prefix import strip_prefix_middleware

    direct = TestClient(app)
    assert_surface(direct)
    for path in ("/", "/rhythm-v2", "/minesweeper"):
        response = direct.get(path)
        assert response.headers.get("cache-control") == "no-cache", path
        versions = re.findall(r"/static/[^\"]+\?v=([^\"]+)", response.text)
        assert versions and set(versions) == {_ASSET_VER}, (path, versions)
    assert re.fullmatch(r"[0-9a-f]{20}", _ASSET_VER), _ASSET_VER
    assert_prefix_redirect_scope()
    css = direct.get("/static/app.css")
    assert "icons/x.svg" not in css.text
    assert "profile-showcase" not in css.text and "character-showcase" not in css.text, "the old profile showcase layout is gone"
    assert direct.get("/static/icons/x.svg").status_code == 404
    app_js = direct.get("/static/app.js").text
    assert "window.openPublicProfile = openPublicCardV3" in app_js and "renderPublicProfileHero" not in app_js
    assert "function openLooksModal()" in app_js and "/skins-v3/buy" in app_js and "/skins-v3/upgrade" in app_js and "/skins-v3/essence" in app_js
    assert "/global-skins-v1/" not in app_js and "/cosmetics/buy" not in app_js, "retired purchase endpoints must not be called"
    assert 'role="dialog" aria-modal="true"' in app_js and "document.activeElement === last" in app_js
    assert "/payments/zarniki/packages" in app_js and "/payments/zarniki/invoice" in app_js
    assert "function navBack()" in app_js and "function v3ApplyLook(" in app_js
    assert 'data-wn-page="looks"' in direct.get("/").text and 'id="pg-looks"' in direct.get("/").text, "looks is reachable from More and has its own page"
    assert "api('/themes" not in app_js and "api(`/themes" not in app_js
    skin_css = direct.get("/static/skin-runtime-v3.css").text
    assert "background-attachment: scroll !important" in skin_css
    assert "duel_wins" not in app_js.split("function renderPublicCardV3", 1)[1].split("\nfunction ", 1)[0]
    # The former Reconstruction URL is a compatibility redirect, not a hidden
    # route into retired writers.  The current hub owns its destination.
    game = direct.get("/game", follow_redirects=False)
    assert game.status_code == 307
    expected_hub = f"{os.environ.get('ROOT_PATH', '').rstrip('/')}/?startapp=games"
    assert game.headers["location"] == expected_hub
    minesweeper = direct.get("/minesweeper")
    assert minesweeper.status_code == 200
    assert '/static/minesweeper-v2.js?v=' in minesweeper.text
    assert '/static/skin-runtime-v3.css?v=' in minesweeper.text
    assert '/static/skin-runtime-v3.js?v=' in minesweeper.text
    assert '/static/games-v3.css?v=' in minesweeper.text
    base = os.environ.get("ROOT_PATH", "").rstrip("/")
    assert f'href="{base}/?startapp=games"' in minesweeper.text, "the back link keeps the mount of the app"
    rhythm = direct.get("/rhythm-v2")
    assert rhythm.status_code == 200
    assert f'href="{base}/?startapp=games"' in rhythm.text, "the back link keeps the mount of the app"
    assert '/static/skin-runtime-v3.css?v=' in rhythm.text
    assert '/static/skin-runtime-v3.js?v=' in rhythm.text
    assert '/static/games-v3.css?v=' in rhythm.text
    for page in (rhythm, minesweeper):
        assert '/static/game-board-v3.js?v=' in page.text and '/static/appearance-v3.css?v=' in page.text and '/static/marks-v3.css?v=' in page.text, 'game leaderboards load the skin renderer'

    if os.environ.get("STATIC_DELIVERY_ROOTED") == "1":
        rooted = TestClient(strip_prefix_middleware(app, "/predvestnik"))
        assert_surface(rooted, "/predvestnik")
        for path in ("/", "/rhythm-v2", "/minesweeper"):
            response = rooted.get("/predvestnik" + path)
            assert response.headers.get("cache-control") == "no-cache", path
            assert f"?v={_ASSET_VER}" in response.text, path
        rooted_game = rooted.get("/predvestnik/game", follow_redirects=False)
        assert rooted_game.status_code == 307
        assert rooted_game.headers["location"] == "/predvestnik/?startapp=games"
        rooted_minesweeper = rooted.get("/predvestnik/minesweeper")
        assert rooted_minesweeper.status_code == 200
        assert '/predvestnik/static/minesweeper-v2.js?v=' in rooted_minesweeper.text
        assert 'href="/predvestnik/?startapp=games"' in rooted_minesweeper.text, "the back link to the games hub keeps the mount"
        rooted_rhythm = rooted.get("/predvestnik/rhythm-v2")
        assert rooted_rhythm.status_code == 200
        assert 'href="/predvestnik/?startapp=games"' in rooted_rhythm.text, "the back link to the games hub keeps the mount"
    else:
        env = {**os.environ, "ROOT_PATH": "/predvestnik", "STATIC_DELIVERY_ROOTED": "1"}
        subprocess.run([sys.executable, __file__], cwd=ROOT, env=env, check=True)
    print("ASGI static delivery contract: OK")


if __name__ == "__main__":
    main()
