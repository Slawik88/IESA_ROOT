"""Login survives a missing Telegram SDK, reads are retried, changes are not (roadmap S02).

A real Chromium page against the real FastAPI app, launched the way Telegram launches it (signed data in the
URL hash):
1. the app starts with its bundled SDK and makes no request to telegram.org;
2. no SDK copy loads at all -> requests still carry the signed launch data, the login window stays closed;
3. expired launch data -> the server answers 401 with the machine-readable reason ``stale_auth_date``, and inside
   Telegram the app shows "close and reopen" with a working close button instead of the login widget;
4. a dropped or "server busy" read is repeated, a dropped change (POST) is not, a timed-out read is not;
5. the live-updates socket carries the credential in its first message, not in its address.

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. \
        DATABASE_URL=postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod python tools/test_auth_recovery_browser.py
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import socket
import threading
import time
from urllib.parse import quote, urlencode

USER_ID = 990_000_777


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def signed_init_data(auth_date: int) -> str:
    fields = {"auth_date": str(auth_date), "user": json.dumps({"id": USER_ID, "first_name": "QA"}, separators=(",", ":"))}
    secret = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def launch_hash(init_data: str) -> str:
    return f"#tgWebAppData={quote(init_data, safe='')}&tgWebAppVersion=7.0&tgWebAppPlatform=android"


def main() -> None:
    import uvicorn
    from playwright.sync_api import sync_playwright

    from FastAPI.main import app
    from starlette.responses import StreamingResponse

    async def test_app(scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/profile/probe-slow-body":
            async def partial_json():
                yield b'{"ok":'
                await asyncio.sleep(5)
                yield b'true}'
            await StreamingResponse(partial_json(), media_type="application/json")(scope, receive, send)
            return
        await app(scope, receive, send)

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(test_app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    serving = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)   # Playwright needs the main loop
    serving.start()
    while not server.started:
        time.sleep(0.05)
    root = f"http://127.0.0.1:{port}/"
    fresh = signed_init_data(int(time.time()))
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()

            # 1. Startup does not depend on a request to telegram.org.
            page = browser.new_page(viewport={"width": 390, "height": 800})
            external_sdk = []
            def unavailable_sdk(route):
                external_sdk.append(route.request.url)
                route.abort()
            page.route("**/telegram.org/js/telegram-web-app.js*", unavailable_sdk)
            page.route("**/profile/me", lambda route: route.abort())
            page.goto(root + launch_hash(fresh), wait_until="domcontentloaded")
            page.wait_for_function("typeof api === 'function'")
            assert not external_sdk, external_sdk
            assert page.evaluate("window.Telegram.WebApp.initData") == fresh, "the SDK copy reads the launch data"
            page.close()

            # 2. No SDK at all: the signed launch data is read from the address hash.
            page = browser.new_page(viewport={"width": 390, "height": 800})
            page.route("**/telegram.org/**", lambda route: route.abort())
            page.route("**/vendor/telegram-web-app.js*", lambda route: route.abort())
            seen: list[str] = []

            def profile_route(route):
                seen.append(route.request.headers.get("x-init-data", ""))
                route.abort()

            page.route("**/profile/me", profile_route)
            page.goto(root + launch_hash(fresh), wait_until="domcontentloaded")
            page.wait_for_function("typeof api === 'function'")
            page.wait_for_timeout(500)
            assert page.evaluate("!window.Telegram || !window.Telegram.WebApp"), "bundled SDK was blocked"
            assert seen and seen[0] == fresh, ("profile request without launch data", seen[:1])
            assert page.evaluate("document.getElementById('login-ov').classList.contains('hidden')"), "login window opened"

            # 3. Expired launch data: the reason is machine-readable.
            stale = signed_init_data(int(time.time()) - 2 * 86400)
            answer = page.evaluate("""async stale => {
                const r = await fetch(BASE + '/profile/notification-prefs', {headers: {'x-init-data': stale}});
                return [r.status, r.headers.get('x-auth-reason')];
            }""", stale)
            assert answer == [401, "stale_auth_date"], answer
            page.close()

            # 3b. Inside Telegram an expired launch shows "close and reopen", never the login widget.
            page = browser.new_page(viewport={"width": 390, "height": 800})
            page.route("**/telegram.org/**", lambda route: route.abort())
            page.goto(root + launch_hash(stale), wait_until="domcontentloaded")
            page.wait_for_function("!document.getElementById('login-ov').classList.contains('hidden')")
            visible = page.evaluate("""() => [...document.querySelectorAll('#login-ov [data-login]')]
                .filter(n => n.offsetParent !== null).map(n => n.dataset.login)""")
            assert visible and set(visible) == {"telegram"}, visible
            assert "сутки" in page.inner_text("#login-reopen-why")
            page.evaluate("window.__closed = 0; Telegram.WebApp.close = () => { window.__closed++; }")
            page.click("#login-reopen-close")
            assert page.evaluate("window.__closed") >= 1, "the button closes the Mini App"

            # 4. Reads are repeated after a dropped connection or a busy server; changes and timeouts are not.
            calls = {"get": 0, "busy": 0, "post": 0, "slow": 0}

            def flaky_get(route):
                calls["get"] += 1
                route.abort() if calls["get"] == 1 else route.fulfill(json={"ok": True})

            def busy_get(route):
                calls["busy"] += 1
                route.fulfill(status=503, body="busy") if calls["busy"] == 1 else route.fulfill(json={"ok": True})

            def dropped_post(route):
                calls["post"] += 1
                route.abort()

            held: list = []

            def never(route):
                calls["slow"] += 1
                held.append(route)

            page.route("**/probe-get", flaky_get)
            page.route("**/probe-busy", busy_get)
            page.route("**/probe-post", dropped_post)
            page.route("**/probe-slow", never)
            assert page.evaluate("api('/probe-get')") == {"ok": True}
            assert page.evaluate("api('/probe-busy')") == {"ok": True}
            post = page.evaluate("api('/probe-post', {method: 'POST', body: '{}'}).then(() => 'sent', e => e)")
            assert post == "Нет связи с сервером. Проверь интернет и попробуй ещё раз.", post
            slow = page.evaluate("api('/probe-slow', {timeout: 300}).then(() => 'answered', e => e)")
            assert slow == "Сервер долго не отвечает. Попробуй ещё раз через минуту.", slow
            assert calls == {"get": 2, "busy": 2, "post": 1, "slow": 1}, calls
            held[0].abort()
            body_timeout = page.evaluate("api('/profile/probe-slow-body', {timeout: 300}).catch(e => e)")
            assert body_timeout == slow, body_timeout
            events = page.evaluate("PVDiagnostics.snapshot().then(x => x.events)")
            timeouts = [e["data"] for e in events if e["data"].get("error_kind") == "Timeout"]
            assert any(e["route"] == "/profile/:value" and e["duration_ms"] >= 250 for e in timeouts), timeouts

            # 5. The live-updates socket: credential in the first message, not in the address.
            sockets: list = []
            frames: list[str] = []

            def watch(ws) -> None:
                sockets.append(ws)
                ws.on("framesent", lambda payload: frames.append(payload if isinstance(payload, str) else payload.get("payload", "")))

            page.on("websocket", watch)
            page.evaluate("_uid = %d; connectWS()" % USER_ID)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not frames:
                page.wait_for_timeout(100)
            assert sockets, "no socket opened"
            assert "init=" not in sockets[0].url and "token=" not in sockets[0].url, sockets[0].url
            assert frames and json.loads(frames[0]) == {"type": "auth", "init": stale}, frames[:1]   # this page was launched with `stale`
            # 6. A failed app script leaves an actionable screen before the bundle can run.
            page.close()
            page = browser.new_page(viewport={"width": 320, "height": 690})
            page.route("**/static/app.js?*", lambda route: route.abort(), times=1)
            page.goto(root, wait_until="domcontentloaded")
            retry = page.get_by_role("button", name="Повторить загрузку")
            retry.wait_for()
            assert retry.bounding_box()["height"] >= 44
            retry.click()
            page.wait_for_function("typeof api === 'function' && !document.querySelector('#pv-boot-failure').open")
            page.close()

            # A stylesheet that never responds must not hide the recovery screen.
            page = browser.new_page(viewport={"width": 430, "height": 800})
            blocked_css = []
            page.route("**/static/app.css?*", lambda route: blocked_css.append(route))
            page.clock.install()
            page.goto(root, wait_until="commit")
            page.locator("#pv-boot-failure").wait_for(state="attached")
            page.clock.fast_forward(16_000)
            page.locator("#pv-boot-failure button").wait_for(state="visible")
            assert blocked_css
            blocked_css[0].continue_()
            page.wait_for_function("typeof api === 'function' && !document.querySelector('#pv-boot-failure').open")
            page.close()

            # A failed refresh keeps the last profile visible and the button can recover it.
            page = browser.new_page(viewport={"width": 390, "height": 800})
            cached = json.dumps({"user_id": USER_ID, "display_name": "Сохранённый профиль"})
            page.add_init_script(f"localStorage.setItem('pv_profile_v3', {json.dumps(cached)})")
            page.route("**/profile/me", lambda route: route.fulfill(
                json={"user_id": USER_ID, "display_name": "Свежий профиль"}))
            page.route("**/profile/me", lambda route: route.fulfill(
                status=500, json={"detail": "Не удалось обновить профиль."}), times=1)
            page.goto(root + launch_hash(fresh), wait_until="domcontentloaded")
            retry = page.locator("#pv-profile-retry button")
            retry.wait_for()
            assert "Сохранённый профиль" in page.locator("#pro-main").inner_text()
            retry.click()
            page.get_by_text("Свежий профиль", exact=True).wait_for()
            assert retry.count() == 0
            browser.close()
    finally:
        server.should_exit = True
        serving.join(10)
    print("OK: SDK copy, launch data without SDK, stale reason, GET-only retries, socket credential off the address")


if __name__ == "__main__":
    main()
