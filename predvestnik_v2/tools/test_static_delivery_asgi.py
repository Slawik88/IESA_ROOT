#!/usr/bin/env python3
"""Exercise the production FastAPI static surface without starting its DB lifespan."""
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import RedirectResponse


ALLOWED = {
    "/static/support-diagnostics.js": "application/javascript",
    "/static/support-feedback.js": "application/javascript",
    "/static/support-feedback.css": "text/css",
    "/local-games-sw.js": "application/javascript",
    "/static/local-games-v1.js": "application/javascript",
    "/static/nickname-v3.js": "application/javascript",
    "/static/nickname-v3.css": "text/css",
    "/static/skin-holidays-v3.css": "text/css",
    "/static/skin-scene-a-v3.css": "text/css",
    "/static/skin-scene-b-v3.css": "text/css",
    "/static/skin-scene-c-v3.css": "text/css",
    "/static/skin-scene-d-v3.css": "text/css",
    "/static/skin-scene-e-v3.css": "text/css",
    "/static/skin-scene-f-v3.css": "text/css",
    "/static/skin-scene-g-v3.css": "text/css",
    "/static/skin-scene-v3.css": "text/css",
    "/static/vendor/telegram-web-app.js": "application/javascript",
    "/static/coin-market-v2.js": "application/javascript",
    "/static/coin-market-chart.js": "application/javascript",
    "/static/coin-market-v2.css": "text/css",
    "/static/rhythm-v2.js": "application/javascript",
    "/static/app.css": "text/css",
    "/static/app.js": "application/javascript",
    "/static/page-transitions.js": "application/javascript",
    "/static/minesweeper-v2.js": "application/javascript",
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
    "/static/skin-sig-d-v3.css": "text/css",
    "/static/public-card-v3.css": "text/css",
    "/static/collect-v3.css": "text/css",
    "/static/toast-v3.css": "text/css",
    "/static/toast-gift-v3.css": "text/css",
    "/static/quests-v3.css": "text/css",
    "/static/marks-v3.css": "text/css",
    "/static/inventory-v3.css": "text/css",
    "/static/trail-v3.css": "text/css",
    "/static/guide-v3.css": "text/css",
    "/static/news-v3.css": "text/css",
    "/static/pass-v3.css": "text/css",
    "/static/store-v3.css": "text/css",
    "/static/motion-v3.css": "text/css",
    "/static/art-v3.css": "text/css",
    "/static/confirm-v3.css": "text/css",
    "/static/monolith-v3.css": "text/css",
    "/static/monolith-player-v3.css": "text/css",
    "/static/game-board-v3.js": "application/javascript",
}
BLOCKED = (
    "/static/app.01.js",
    "/static/admin-legacy.css",      # the old admin look: deleted, its last player rules (.btn) live at the end of app.css
    "/static/updates.json",          # the feed is /updates.json
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


GAME_SHELL_ASSETS = {"page-transitions.js", "support-feedback.css", "support-diagnostics.js", "support-feedback.js"}


def assert_surface(client: TestClient, prefix: str = "") -> None:
    guide = client.get(f"{prefix}/guide-v3.json")
    assert guide.status_code == 200 and len(guide.json()["topics"]) >= 25
    assert guide.headers["cache-control"] == "no-cache" and guide.headers.get("etag")
    unchanged = client.get(f"{prefix}/guide-v3.json", headers={"If-None-Match": guide.headers["etag"]})
    assert unchanged.status_code == 304 and not unchanged.content
    assert client.get(f"{prefix}/guide-v3.json", headers={"If-None-Match": '"old-guide"'}).status_code == 200
    for role in ("city", "citizen", "mafia", "don", "doctor", "detective"):
        for ext, mime in (("jpg", "image/jpeg"), ("webp", "image/webp")):
            ALLOWED[f"/static/mafia-art/{role}.{ext}"] = mime
    assert client.get(f"{prefix}/static/mafia-art/prompts.json").status_code == 404
    assert client.get(f"{prefix}/static/mafia-art/unknown.jpg").status_code == 404
    # Patch-note drafts and their screenshots are not public before the creator sends them (admin API only).
    for note in (ROOT / "FastAPI/static/patch-notes").glob("*.json"):
        assert client.get(f"{prefix}/static/patch-notes/{note.name}").status_code == 404, note.name
    for image in (ROOT / "FastAPI/static/patch-notes/img").glob("*"):
        assert client.get(f"{prefix}/static/patch-notes/img/{image.name}").status_code == 404, image.name
    assert client.get(f"{prefix}/static/announcements/family-tree.png").status_code == 404
    for path, media_type in ALLOWED.items():
        response = client.get(f"{prefix}{path}?v=contract-test")
        assert response.status_code == 200, path
        assert media_type in response.headers.get("content-type", ""), path
        assert response.content, path
        if path == "/local-games-sw.js":
            # SW — сам механизм обновления: всегда ревалидируется, даже с ?v=
            assert response.headers.get("cache-control") == "no-cache", path
            continue
        # Content-addressed URLs cache forever: HTML always references the
        # current release hash, so ?v= bytes are immutable by construction.
        assert response.headers.get("cache-control") == "public, max-age=31536000, immutable", path
    # Bare asset URLs (no ?v=) must still revalidate each load.
    bare = client.get(f"{prefix}/static/app.css")
    assert bare.headers.get("cache-control") == "no-cache", "bare asset revalidates"
    assert_prepared_delivery(client, prefix)
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


def assert_prepared_delivery(client: TestClient, prefix: str) -> None:
    """Text assets are gzipped once at start (not per request), carry an ETag and answer 304 while unchanged; the feed too."""
    import gzip
    from FastAPI.main import _STORE
    for path in ("/static/app.js", "/static/app.css", "/static/skin-scene-d-v3.css", "/updates.json", "/"):
        full = client.get(f"{prefix}{path}", headers={"Accept-Encoding": "gzip"})
        assert full.status_code == 200 and full.headers.get("content-encoding") == "gzip", path
        assert "accept-encoding" in full.headers.get("vary", "").lower() and full.headers.get("etag"), path
        raw = client.get(f"{prefix}{path}", headers={"Accept-Encoding": "identity"})
        assert raw.status_code == 200 and "content-encoding" not in raw.headers and raw.content == full.content, path
        assert len(raw.headers["content-length"]) and int(raw.headers["content-length"]) > len(gzip.compress(raw.content, 9)) * 2, path
        for validator in (full.headers["etag"], "W/" + full.headers["etag"]):
            again = client.get(f"{prefix}{path}", headers={"If-None-Match": validator, "Accept-Encoding": "gzip"})
            assert again.status_code == 304 and not again.content and again.headers.get("etag") == full.headers["etag"], (path, validator)
        assert client.get(f"{prefix}{path}", headers={"If-None-Match": '"older"'}).status_code == 200, path
    feed = client.get(f"{prefix}/updates.json")
    assert feed.headers.get("cache-control") == "no-cache" and feed.json()["updates"], "the feed revalidates and keeps its content"
    source = json.loads((ROOT / "FastAPI/static/updates.json").read_text(encoding="utf-8"))
    assert feed.json() == source and len(feed.content) < len((ROOT / "FastAPI/static/updates.json").read_bytes()), "the feed loses only spaces"
    app_js = client.get(f"{prefix}/static/app.js").text
    assert "\n// " not in app_js and len(app_js.encode()) < len(_STORE["app.js"].body) + 1, "app.js is served minified"
    sdk = client.get(f"{prefix}/static/vendor/telegram-web-app.js").text
    assert sdk == (ROOT / "FastAPI/static/vendor/telegram-web-app.js").read_text(encoding="utf-8"), "the official SDK copy is served byte for byte"


def page_versions(html: str) -> dict[str, str]:
    return dict(re.findall(r"/static/([\w./-]+)\?v=([0-9a-f]+)", html))


def assert_trial_deploy() -> None:
    """A deploy that changes one file changes only that file's address: the browser keeps every other file it has cached."""
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(ROOT / "FastAPI", Path(tmp) / "FastAPI", ignore=shutil.ignore_patterns("__pycache__"))
        marks = Path(tmp) / "FastAPI/static/marks-v3.css"
        marks.write_text(marks.read_text(encoding="utf-8") + "\n/* trial deploy */\n", encoding="utf-8")
        probe = ("import sys, json; sys.path[:0] = [sys.argv[1], sys.argv[2]]; from FastAPI import main;"
                 "print(json.dumps([main._INDEX.body.decode(), main.__file__]))")
        env = {**os.environ, "ROOT_PATH": ""}
        run = lambda first: json.loads(subprocess.run([sys.executable, "-c", probe, first, str(ROOT)], cwd=tmp, env=env,
                                                      capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
        before_html, before_file = run(str(ROOT))
        after_html, after_file = run(tmp)
    assert after_file.startswith(tmp) and before_file.startswith(str(ROOT)), "the trial build imports the copied package"
    before, after = page_versions(before_html), page_versions(after_html)
    assert before.keys() == after.keys() and len(before) > 40, sorted(set(before) ^ set(after))
    changed = sorted(name for name in before if before[name] != after[name])
    assert changed == ["marks-v3.css"], changed
    release = re.compile(r'<meta name="pv-release" content="([0-9a-f]{20})"')
    assert release.search(before_html)[1] != release.search(after_html)[1], "the release changes, so open apps offer the update"


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
    from FastAPI.routers.league_v1 import ASSET_VERSION as LEAGUE_VER

    from FastAPI.main import _STORE
    direct = TestClient(app)
    assert_surface(direct)
    for path in ("/", "/rhythm-v2", "/minesweeper"):
        response = direct.get(path)
        assert response.headers.get("cache-control") == "no-cache", path
        links = re.findall(r"/static/([^\"?]+)\?v=([^\"]+)", response.text)
        assert links, path
        for name, version in links:
            # every file has its own content hash; the casual game pages also take their look and the shared header (game-shell-v3.html, with the
            # support scripts it links) from the League assets, under the League hash
            league = name.startswith("league-demo/") or (path != "/" and name in GAME_SHELL_ASSETS)
            assert version == (LEAGUE_VER if league else _STORE[name].version), (path, name, version)
            if not name.startswith("league-demo/"):
                assert direct.get(f"/static/{name}?v={version}").status_code == 200, (path, name)
    assert re.fullmatch(r"[0-9a-f]{20}", _ASSET_VER), _ASSET_VER
    index = direct.get("/").text
    assert f'<meta name="pv-release" content="{_ASSET_VER}"/>' in index, "the release is in the page for the update banner and error reports"
    assert "{{" not in index, "every placeholder is filled"
    # The scene pictures are not linked: a scene asks for its file (apScene, app.35.js); the page only tells which picture is in which file.
    assert not re.search(r'<link[^>]+skin-scene-[a-g]-v3\.css', index), "scene picture files are loaded on demand"
    scene_art = json.loads(re.search(r"window\.__pvSceneArt=(\{.*?\});</script>", index)[1])
    assert sorted(scene_art) == list("abcdefg"), scene_art.keys()
    for letter, (href, names) in scene_art.items():
        assert href == f"{os.environ.get('ROOT_PATH', '').rstrip('/')}/static/skin-scene-{letter}-v3.css?v={_STORE[f'skin-scene-{letter}-v3.css'].version}", href
        art = (ROOT / f"FastAPI/static/skin-scene-{letter}-v3.css").read_text(encoding="utf-8")
        assert names and all(f".i-{name} {{ --img:" in art for name in names.split()), letter
    assert sum(len(names.split()) for _, names in scene_art.values()) > 150
    assert_prefix_redirect_scope()
    assert_trial_deploy()
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
    assert '/static/skin-runtime-v3.js?v=' in minesweeper.text
    for asset in ("league-demo.css", "league-games.css", "casual-games-v3.css", "league-art.js", "league-fx.js", "game-mode-v3.js", "game-shell-v3.js"):
        assert f'/static/league-demo/{asset}?v=' in minesweeper.text, f"the casual page takes {asset} from the League assets"
    base = os.environ.get("ROOT_PATH", "").rstrip("/")
    assert f'href="{base}/?startapp=games"' in minesweeper.text, "the back link keeps the mount of the app"
    rhythm = direct.get("/rhythm-v2")
    assert rhythm.status_code == 200
    assert f'href="{base}/?startapp=games"' in rhythm.text, "the back link keeps the mount of the app"
    assert '/static/skin-runtime-v3.js?v=' in rhythm.text
    assert '/static/league-demo/game-shell-v3.js?v=' in rhythm.text and '/static/league-demo/casual-games-v3.css?v=' in rhythm.text
    for page in (rhythm, minesweeper):
        assert '/static/game-board-v3.js?v=' in page.text and '/static/appearance-v3.css?v=' in page.text and '/static/marks-v3.css?v=' in page.text, 'game leaderboards load the skin renderer'

    if os.environ.get("STATIC_DELIVERY_ROOTED") == "1":
        rooted = TestClient(strip_prefix_middleware(app, "/predvestnik"))
        assert_surface(rooted, "/predvestnik")
        for path, name in (("/", "app.js"), ("/rhythm-v2", "game-board-v3.js"), ("/minesweeper", "game-board-v3.js")):
            response = rooted.get("/predvestnik" + path)
            assert response.headers.get("cache-control") == "no-cache", path
            assert f"/predvestnik/static/{name}?v={_STORE[name].version}" in response.text, path
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
