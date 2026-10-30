"""Actual PG -> production WS listener -> production client -> authorized HTTP room."""
import argparse
import asyncio
import os
import socket
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import AsyncMock, patch

import asyncpg
import uvicorn
from fastapi import WebSocket
from fastapi.responses import HTMLResponse
from playwright.sync_api import sync_playwright

from test_mafia_online_ui import build_app, function, html
from FastAPI import notifications


def check(dsn, out):
    app = build_app(dsn)
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            yield
            task = notifications._balance_listener_task
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            notifications._balance_listener_task = None

    app.router.lifespan_context = lifespan
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/"]

    @app.websocket("/ws/{user_id}")
    async def socket_session(websocket: WebSocket, user_id: int):
        await websocket.accept()
        await websocket.receive_json()  # test identity replaces production Telegram signature only
        await notifications.ws_session(websocket, user_id)

    @app.get("/")
    async def page():
        helpers = """let _ws=null,_wsTries=0,_wsTimer=0,_wsPageAway=false;
          const INIT_DATA='test';const sess=()=>'';function showAppUpdate(){}
          const _backHooks=[],_navStack=['profile'];let switched=false;
          function switchPage(){switched=true;}
        """
        helpers += function("app.01.js", "connectWS") + function("app.01.js", "navBack")
        return HTMLResponse(html().replace("</body>", "<script>" + helpers +
                            ";connectWS();openMafiaOnline();</script></body>"))

    async def connect():
        return await asyncpg.connect(dsn)

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    out.mkdir(parents=True, exist_ok=True)
    with patch("infrastructure.database.create_pool", AsyncMock()), \
         patch("infrastructure.database.connect_direct", connect), \
         patch("infrastructure.repositories.balance_events.ensure_schema", AsyncMock()):
        worker = threading.Thread(target=server.run, daemon=True)
        worker.start()
        try:
            for _ in range(150):
                if server.started or not worker.is_alive():
                    break
                time.sleep(.1)
            assert server.started
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
                contexts = [browser.new_context(viewport={"width": 390, "height": 844}) for _ in range(2)]
                a, b = [context.new_page() for context in contexts]
                errors = []
                for page in (a, b):
                    page.on("pageerror", lambda error: errors.append(str(error)))
                a.goto(f"http://127.0.0.1:{port}/?user=101")
                a.locator("#mo-quick").click()
                a.wait_for_function("MO.data?.me?.id===101")
                room = a.evaluate("MO.room")
                b.goto(f"http://127.0.0.1:{port}/?user=202")
                b.evaluate("id=>moJoin(id)", room)
                b.wait_for_function("MO.data?.players.length===2")
                a.wait_for_function("MO.data?.players.length===2", timeout=1000)
                b.locator("#mo-text").fill("Мой черновик")
                a.locator("#mo-text").fill("Быстрое сообщение")
                version = a.evaluate("MO.data.version")
                started = time.monotonic()
                a.evaluate("moSend()")
                b.wait_for_function("[...MO.messages.values()].some(m=>m.body==='Быстрое сообщение')", timeout=1000)
                latency = time.monotonic() - started
                assert b.evaluate("MO.data.version") == version
                assert b.locator("#mo-text").input_value() == "Мой черновик"
                assert b.locator("#mo-text").evaluate("e=>e===document.activeElement")
                b.screenshot(path=str(out / "mafia-live-390.png"))
                # The lost PG/WS interval is repaired by the ready signal on reconnect.
                b.evaluate("_ws.close(1000)")
                time.sleep(1.6)  # avoid the normal chat rate limit
                a.locator("#mo-text").fill("После обрыва")
                a.evaluate("moSend()")
                b.wait_for_function("[...MO.messages.values()].some(m=>m.body==='После обрыва')", timeout=5000)
                b.evaluate("moHelp()")
                b.locator("#mo-sheet").wait_for(state="visible")
                b.keyboard.press("Escape")
                assert b.locator("#modal").is_visible()
                assert not b.locator("#mo-sheet").is_visible()
                b.evaluate("navBack()")
                b.wait_for_function("!document.getElementById('modal').open")
                assert b.evaluate("!switched&&_navStack.length===1")
                assert not errors, errors
                for context in contexts:
                    context.close()
                browser.close()
                print(f"PASS real PG/WS/HTTP same-version message {latency:.3f}s; focused draft, reconnect, Escape and Telegram-Back callback")
        finally:
            server.should_exit = True
            worker.join(timeout=15)
            assert not worker.is_alive(), "live test server failed to stop"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", type=Path, default=Path(".local/mafia-live-ui"))
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("loopback PostgreSQL required")
    check(args.dsn, args.out)
