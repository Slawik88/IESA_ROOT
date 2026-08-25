#!/usr/bin/env python3
"""Static delivery contract: preview must expose exactly the production assets."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    main_py = read("FastAPI/main.py")
    preview = read("tools/preview_server.mjs")
    css = read("FastAPI/static/app.css")
    preview_test = read("tools/verify_preview_server.mjs")
    production_preview_test = read("tools/verify_reconstruction_preview_contract.mjs")
    reconstruction_tests = "\n".join(
        read(path) for path in (
            "tools/verify_reconstruction_lab.mjs",
            "tools/verify_archivist_companion.mjs",
            "tools/verify_clicker_accessibility.mjs",
        )
    )

    # The current stylesheet has no external close-icon dependency.  The route
    # below is deliberately a one-release compatibility shim for cached CSS.
    assert 'icons/x.svg' not in css
    assert '@app.get("/static/icons/x.svg")' in main_py
    assert '_LEGACY_CLOSE_ICON_SVG = _read_static("icons/x.svg")' in main_py
    assert '_APP_CSS = _read_static("app.css")' in main_py
    assert 'return Response(_LEGACY_CLOSE_ICON_SVG, media_type="image/svg+xml")' in main_py

    # Preview serves the same explicit assets, never a filesystem directory.
    for path in (
        "/static/app.css",
        "/static/app.js",
        "/static/app.devmode.js",
        "/static/reconstruction-lab.css",
        "/static/reconstruction-lab.js",
        "/static/icons/x.svg",
    ):
        assert f"p === '{path}'" in preview, path
    assert "staticContentType" not in preview
    assert "path.join(STATIC, p.slice('/static/'.length))" not in preview
    assert "if (p.startsWith('/static/')) return send(res, 404" in preview

    # Known internal paths must stay absent and browser checks must exercise that.
    for path in (
        "/static/app.01.js",
        "/static/reconstruction-lab.html",
        "/static/concept-gallery.html",
        "/static/concept-gallery-production.html",
        "/static/concept-gallery-profile-card.html",
        "/static/design-concepts/profile-card/01-open-central-stage.png",
        "/static/economy-masterplan-report.html",
    ):
        assert path in preview_test

    assert "${base}/__preview/reconstruction-lab" in reconstruction_tests
    assert "${base}/game" not in reconstruction_tests
    assert "data-preview-bridge" not in preview
    assert "if (p === '/reconstruction' || p.startsWith('/reconstruction/'))" in preview
    assert "productionContract: true" in preview
    assert "? `/production${suffix}`" in preview
    assert 'href="/static/reconstruction-lab.css?v=${assetVersion}"' in preview
    assert 'src="/static/reconstruction-lab.js?v=${assetVersion}"' in preview
    assert "reconstruction preview production contract: OK" in production_preview_test
    assert "'/reconstruction/start'" in production_preview_test

    print("static delivery contract: OK")


if __name__ == "__main__":
    main()
