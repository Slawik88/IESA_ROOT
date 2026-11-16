"""The Mini App reports its own errors: a real Chromium page against the real FastAPI app.

The Telegram SDK is blocked (as when telegram.org does not load), a script error is thrown in the
page and the profile request fails with 401 — all three must arrive at POST /telemetry.

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. \
        DATABASE_URL=postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod python tools/test_client_telemetry_browser.py
"""
from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from urllib.parse import urlparse


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _isolate_network(page) -> None:
    # Fonts, widgets and other external resources must not determine when the local page finishes loading.
    page.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
    page.route("**/telegram-web-app.js*", lambda route: route.abort())


def main() -> None:
    import uvicorn
    from playwright.sync_api import sync_playwright

    from core import ops_metrics
    from FastAPI.main import app
    from services import feature_switches, ops_health

    # The telemetry transport does not need a database. Keep the ordinary site-open
    # fixture in memory; switch persistence and denied entry are covered by the PG test.
    feature_switches._cache = {}
    feature_switches._loaded_at = time.monotonic()
    feature_switches.TTL = 3600

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    serving = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)   # Playwright needs the main loop
    serving.start()
    while not server.started:
        time.sleep(0.05)
    ops_metrics.registry.drain()
    ops_health._client_buffer.clear()
    posted: list[str] = []
    want = {"sdk_missing", "js_error", "fetch_fail"}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
            # Web login needs no Telegram SDK. A blocked SDK must not manufacture an error.
            for blocked_storage in (False, True):
                context = browser.new_context()
                if blocked_storage:
                    context.add_init_script("Storage.prototype.getItem = function () { throw new Error('storage blocked'); }")
                web = context.new_page()
                _isolate_network(web)
                web.goto(f"http://127.0.0.1:{port}/", wait_until="load")
                web.wait_for_timeout(3500)
                assert not any(e["type"] == "sdk_missing" for e in ops_health._client_buffer)
                context.close()
                ops_health._client_buffer.clear()

            # On Telegram reload, the SDK's saved init params can survive after the hash is cleared.
            context = browser.new_context()
            context.add_init_script("sessionStorage.setItem('__telegram__initParams', JSON.stringify({tgWebAppData:'probe'}))")
            reload_page = context.new_page()
            _isolate_network(reload_page)
            reload_page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
            reload_page.wait_for_timeout(3500)
            assert any(e["type"] == "sdk_missing" for e in ops_health._client_buffer)
            context.close()
            ops_health._client_buffer.clear()
            page = browser.new_page(viewport={"width": 390, "height": 800})
            _isolate_network(page)
            page.on("request", lambda r: posted.append(r.post_data or "") if r.url.endswith("/telemetry") else None)
            page.goto(f"http://127.0.0.1:{port}/#tgWebAppPlatform=tdesktop", wait_until="load")
            page.evaluate("setTimeout(() => { throw new TypeError('telemetry probe') }, 0)")
            # Without Telegram the app stops at the login overlay; an API call made anyway is refused with 401.
            page.evaluate("fetch(location.pathname.replace(/\\/$/, '') + '/profile/me').catch(() => {})")
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not want <= {e["type"] for e in list(ops_health._client_buffer)}:
                page.wait_for_timeout(250)
            browser.close()
    finally:
        server.should_exit = True
        serving.join(10)

    events = list(ops_health._client_buffer)
    types = {e["type"] for e in events}
    assert want <= types, (types, posted)
    probe = next(e for e in events if e["type"] == "js_error" and "telemetry probe" in e["message"])
    assert probe["message"].startswith("TypeError") and probe["device"].startswith("browser/phone"), probe
    assert next(e for e in events if e["type"] == "sdk_missing")["message"] == "opened in Telegram"
    failed = [e for e in events if e["type"] == "fetch_fail"]
    assert all(e["status"] in (401, 0) or e["status"] >= 500 for e in failed), failed
    assert all("x-init-data" not in body and "pv_sess" not in body for body in posted)
    assert ops_metrics.registry.window.counters.get(("client", "js_error"), 0) >= 1
    print(f"OK: page errors, missing SDK and failed requests reach /telemetry ({len(events)} events)")


if __name__ == "__main__":
    main()
