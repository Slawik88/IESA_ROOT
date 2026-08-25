#!/usr/bin/env python3
"""Exercise the production FastAPI static surface without starting its DB lifespan."""
from pathlib import Path
import os
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
    "/static/reconstruction-lab.css": "text/css",
    "/static/reconstruction-lab.js": "application/javascript",
    "/static/icons/x.svg": "image/svg+xml",
}
BLOCKED = (
    "/static/app.01.js",
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
    for path in ("/static/app.css/", "/static/icons/x.svg/"):
        response = client.get(f"{prefix}{path}?v=one", follow_redirects=False)
        assert response.status_code == 307, path
        assert urlparse(response.headers.get("location", "")).path == f"{prefix}{path[:-1]}", path
        assert urlparse(response.headers.get("location", "")).query == "v=one", path
    for method, path in (("get", "/reconstruction/"), ("post", "/reconstruction/start/")):
        response = getattr(client, method)(f"{prefix}{path}?x=1", follow_redirects=False)
        assert response.status_code == 307, path
        assert urlparse(response.headers.get("location", "")).path == f"{prefix}{path[:-1]}", path
        assert urlparse(response.headers.get("location", "")).query == "x=1", path


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


def allow_static_game_document(app: FastAPI) -> None:
    """Keep this static-surface test independent of the live feature-flag DB.

    The separate feature-gate contract proves that `/game` is fail-closed.  Here
    we exercise only its rendered production document and asset URLs.
    """
    route = next(route for route in app.routes if getattr(route, "path", None) == "/game")
    dependency = route.dependant.dependencies[0].call
    app.dependency_overrides[dependency] = lambda: None


def main() -> None:
    from FastAPI.main import app
    from FastAPI.prefix import strip_prefix_middleware

    allow_static_game_document(app)
    direct = TestClient(app)
    assert_surface(direct)
    assert_prefix_redirect_scope()
    css = direct.get("/static/app.css")
    assert "icons/x.svg" not in css.text
    legacy_icon = direct.get("/static/icons/x.svg?v=stale-telegram-webview")
    assert legacy_icon.status_code == 200
    assert "image/svg+xml" in legacy_icon.headers.get("content-type", "")
    game = direct.get("/game")
    assert game.status_code == 200
    assert 'data-runtime="production"' in game.text

    if os.environ.get("STATIC_DELIVERY_ROOTED") == "1":
        rooted = TestClient(strip_prefix_middleware(app, "/predvestnik"))
        assert_surface(rooted, "/predvestnik")
        rooted_game = rooted.get("/predvestnik/game")
        assert rooted_game.status_code == 200
        assert 'href="/predvestnik/static/reconstruction-lab.css?v=' in rooted_game.text
        assert 'src="/predvestnik/static/reconstruction-lab.js?v=' in rooted_game.text
    else:
        env = {**os.environ, "ROOT_PATH": "/predvestnik", "STATIC_DELIVERY_ROOTED": "1"}
        subprocess.run([sys.executable, __file__], cwd=ROOT, env=env, check=True)
    print("ASGI static delivery contract: OK")


if __name__ == "__main__":
    main()
