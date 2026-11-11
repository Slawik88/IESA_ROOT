#!/usr/bin/env python3
"""Full start of both bots of the production container (Predvestnik + Domovoy, like scripts/run_bots.sh) against a FAKE Telegram.

Why it exists: on 2026-11-03 an aiogram bump passed every unit test and the Telegram simulator, then the container on
DigitalOcean (512 MB) went into a restart loop.  Tests that feed updates into a ready Dispatcher never start `python -m bot`
the way production does, so they cannot see a start-up that is too heavy or hangs.  This check does: it starts the fake
Telegram Bot API on loopback, runs both bots as separate processes, and watches them like the platform does.

    python tools/check_full_start.py --dsn postgresql://predvestnik_preprod@127.0.0.1:55432/pv_boot_check
    ... --backlog 3000 --seconds 120      # a queue of waiting updates, as after a restart
    ... --max-rss-mib 420                 # fail when both bots together hold more

Use the Python of the environment under test (venv with the library version being checked) and run it once per version:
the JSON line at the end is comparable between runs.  Memory is measured with psutil when it is installed.

Checked: the web part answers /api/health, both bots keep polling, neither process exits, the waiting updates are taken.
Loopback database only, throw-away DSN advised (the bot creates its whole schema there); Domovoy uses its own sqlite file
unless --domovoy-dsn is given.  Nothing here reaches the real Telegram: the library is pointed at the fake server in-process.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]          # predvestnik_v2/
DOMOVOY = ROOT.parent / "domovoy"
PV_TOKEN, DOM_TOKEN = "123456:fake-predvestnik", "123456:fake-domovoy"
CHAT = -1001234567890

# Runs `python -m bot` of the current directory with the library pointed at the fake server.
RUNNER = """
import os, runpy
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
port = os.environ["FAKE_TG_PORT"]
fake = TelegramAPIServer(base=f"http://127.0.0.1:{port}/bot{{token}}/{{method}}", file=f"http://127.0.0.1:{port}/file/bot{{token}}/{{path}}")
_orig = AiohttpSession.__init__
def _init(self, *a, **kw):
    kw.setdefault("api", fake)
    _orig(self, *a, **kw)
AiohttpSession.__init__ = _init
runpy.run_module("bot", run_name="__main__", alter_sys=True)
"""


def serve(port: int, backlog: int, boot_fault: bool = False, widget_backlog: int = 0) -> None:
    """Minimal Telegram Bot API: enough for both bots to start, poll and answer; counts calls per bot."""
    from aiohttp import web

    calls: collections.Counter = collections.Counter()
    # Receipts survive a run: reusing IDs would only test deduplication on the next invocation.
    first_update = time.time_ns() // 1_000_000
    updates = [{"update_id": first_update + i, "message": {
        "message_id": 100 + i, "date": int(time.time()), "chat": {"id": CHAT, "type": "supergroup", "title": "Test chat"},
        "from": {"id": 7_000_000 + i % 500, "is_bot": False, "first_name": f"U{i % 500}", "username": f"user{i % 500}"},
        "text": ["привет", "баланс", "топ", "я", "бот помощь"][i % 5]}} for i in range(backlog)]
    updates.extend({"update_id": first_update + backlog + i, "widget_query": {
        "id": f"boot-widget-{i}", "from": {"id": 1, "is_bot": False, "first_name": "Creator"},
        "chat": {"id": 1, "type": "private"}, "message_id": 50 + i,
        "type": {"type": "data"}, "data": "ttt:m:0:---------"}} for i in range(widget_backlog))
    widget_answers: set[str] = set()
    widget_boards: set[str] = set()
    sent = [5000]

    def message(chat_id: int, text: str) -> dict:
        sent[0] += 1
        return {"message_id": sent[0], "date": int(time.time()), "chat": {"id": chat_id, "type": "supergroup", "title": "Test chat"},
                "from": {"id": 123456, "is_bot": True, "first_name": "Bot", "username": "pv_test_bot"}, "text": text}

    async def handler(request: web.Request) -> web.Response:
        method, token = request.match_info["method"], request.match_info["token"]
        calls[f"{'dom' if token.endswith('domovoy') else 'pv'}:{method}"] += 1
        form: Any
        try:
            form = await request.post() if request.content_type.startswith(("multipart", "application/x-www-form")) else (
                await request.json() if request.can_read_body else {})
        except Exception:
            form = {}
        if boot_fault and token == PV_TOKEN:
            if method == "deleteWebhook" and calls["pv:deleteWebhook"] == 1:
                return web.json_response({"ok": False, "error_code": 503, "description": "Test outage"}, status=503)
            if method == "setMyCommands" and calls["pv:setMyCommands"] == 1:
                await asyncio.sleep(60)
        if method == "getMe":
            result = {"id": 123456, "is_bot": True, "first_name": "Bot", "username": "pv_test_bot", "can_join_groups": True,
                      "can_read_all_group_messages": True, "supports_inline_queries": False}
        elif method == "getUpdates":
            offset = int(form.get("offset") or 0)
            if offset and token == PV_TOKEN:
                updates[:] = [u for u in updates if u["update_id"] >= offset]
            result = updates[:100] if token == PV_TOKEN else []
            if not result:
                await asyncio.sleep(min(int(form.get("timeout") or 0), 5))
        elif method in ("sendMessage", "editMessageText", "sendPhoto", "sendAnimation", "sendVideo", "sendDocument", "copyMessage"):
            result = message(int(form.get("chat_id") or CHAT), str(form.get("text") or "ok"))
        elif method == "getChatMember":
            result = {"status": "member", "user": {"id": int(form.get("user_id") or 1), "is_bot": False, "first_name": "U"}}
        elif method == "getChat":
            result = {"id": int(form.get("chat_id") or CHAT), "type": "supergroup", "title": "Test chat"}
        elif method == "getChatAdministrators":
            result = []
        elif method == "getChatMemberCount":
            result = 10
        elif method == "getStarTransactions":
            result = {"transactions": []}
        elif method == "answerWidgetQuery":
            query_id = str(form.get("widget_query_id") or "")
            widget_answers.add(query_id)
            data = json.loads(str(form.get("data") or "{}"))
            board = data.get("b") if isinstance(data, dict) else None
            if isinstance(board, str) and len(board) == 9 and board[0] == "x" and board.count("o") == 1:
                widget_boards.add(query_id)
            result = True
        else:
            result = True
        return web.json_response({"ok": True, "result": result})

    async def stats(_request: web.Request) -> web.Response:
        return web.json_response({"calls": dict(calls), "pending_updates": len(updates),
                                  "widget_answers": len(widget_answers), "widget_boards": len(widget_boards)})

    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.router.add_get("/_stats", stats)
    app.router.add_route("*", "/bot{token}/{method}", handler)
    web.run_app(app, host="127.0.0.1", port=port, print=None, access_log=None)


def _rss(proc: subprocess.Popen) -> int:
    try:
        import psutil
        root = psutil.Process(proc.pid)
        return sum(p.memory_info().rss for p in [root, *root.children(recursive=True)] if p.is_running())
    except Exception:
        return 0


def _get(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.read() if response.status == 200 else None
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dsn", help="loopback PostgreSQL for Predvestnik")
    parser.add_argument("--domovoy-dsn", default="", help="loopback PostgreSQL for Domovoy (default: sqlite file)")
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--backlog", type=int, default=0, help="updates waiting in the fake Telegram at start")
    parser.add_argument("--widget-backlog", type=int, default=0, help="creator widget requests added after ordinary updates")
    parser.add_argument("--max-rss-mib", type=int, default=0, help="fail when both bots together hold more (0: only report)")
    parser.add_argument("--health-timeout", type=int, default=60, help="seconds until /api/health must answer")
    parser.add_argument("--no-domovoy", action="store_true")
    parser.add_argument("--telegram-boot-fault", action="store_true",
                        help="first deleteWebhook returns 503 and the first optional menu request hangs")
    parser.add_argument("--serve", nargs=2, metavar=("PORT", "BACKLOG"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        serve(int(args.serve[0]), int(args.serve[1]), args.telegram_boot_fault, args.widget_backlog)
        return 0
    for dsn in (args.dsn, args.domovoy_dsn):
        if dsn and urlparse(dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise SystemExit("only a loopback PostgreSQL DSN is allowed")
    if not args.dsn:
        raise SystemExit("--dsn is required")
    if args.max_rss_mib:
        try:
            import psutil  # noqa: F401 — memory gate must never silently pass without measurement
        except ImportError as exc:
            raise SystemExit("--max-rss-mib requires psutil in the test environment") from exc

    tg_port, api_port = 18701, 18702
    base = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1", FAKE_TG_PORT=str(tg_port), PORT=str(api_port),
                BOT_TOKEN=PV_TOKEN, DOMOVOY_BOT_TOKEN=DOM_TOKEN, DATABASE_URL=args.dsn, DEVELOPER_ID="1",
                DOMOVOY_SUPERADMIN_TG_IDS="1", DOMOVOY_DATABASE_URL=args.domovoy_dsn)
    for key in ("PREDVESTNIK_ENV", "PREDVESTNIK_DATABASE_URL", "ROOT_PATH", "MINIAPP_URL"):
        base.pop(key, None)
    procs: dict[str, subprocess.Popen] = {}
    logs: dict[str, Path] = {}
    out_dir = Path(os.environ.get("TEMP") or "/tmp") / "check_full_start"
    out_dir.mkdir(exist_ok=True)

    def start(name: str, argv: list[str], cwd: Path, env: dict) -> None:
        logs[name] = out_dir / f"{name}.log"
        procs[name] = subprocess.Popen(argv, cwd=cwd, env=env, stdout=logs[name].open("wb"), stderr=subprocess.STDOUT)

    telegram_args = [sys.executable, __file__, "--serve", str(tg_port), str(args.backlog)]
    telegram_args.extend(["--widget-backlog", str(args.widget_backlog)])
    if args.telegram_boot_fault:
        telegram_args.append("--telegram-boot-fault")
    start("fake_telegram", telegram_args, ROOT, base)
    time.sleep(1.5)
    start("predvestnik", [sys.executable, "-c", RUNNER], ROOT, dict(base, PYTHONPATH=str(ROOT)))
    if not args.no_domovoy:
        start("domovoy", [sys.executable, "-c", RUNNER], DOMOVOY, dict(base, PYTHONPATH=str(DOMOVOY)))

    started = time.time()
    first_health = None
    after_ok = bad_after_ok = 0
    peak = {"predvestnik": 0, "domovoy": 0}
    exited: list[str] = []
    while time.time() - started < args.seconds:
        time.sleep(0.5)
        for name in ("predvestnik", "domovoy"):
            if name in procs:
                peak[name] = max(peak[name], _rss(procs[name]))
                if procs[name].poll() is not None and name not in exited:
                    exited.append(name)
        ok = _get(f"http://127.0.0.1:{api_port}/api/health") is not None
        if ok and first_health is None:
            first_health = round(time.time() - started, 1)
        if first_health is not None:
            after_ok += ok
            bad_after_ok += not ok

    raw = _get(f"http://127.0.0.1:{tg_port}/_stats")
    stats = json.loads(raw) if raw else {"calls": {}, "pending_updates": -1}
    for proc in procs.values():
        try:
            import psutil
            for child in psutil.Process(proc.pid).children(recursive=True):
                child.kill()
        except Exception:
            pass
        proc.kill()

    calls = stats["calls"]
    total_mib = sum(peak.values()) // 2**20
    problems = []
    if first_health is None or first_health > args.health_timeout:
        problems.append(f"/api/health did not answer within {args.health_timeout} s")
    if bad_after_ok > max(2, after_ok // 20):
        problems.append(f"/api/health failed {bad_after_ok} of {after_ok + bad_after_ok} times after the first answer")
    if exited:
        problems.append(f"process exited: {', '.join(exited)}")
    for key, label in (("pv", "predvestnik"), ("dom", "domovoy")):
        if label in procs and calls.get(f"{key}:getUpdates", 0) < 3:
            problems.append(f"{label} is not polling")
    if args.telegram_boot_fault and (calls.get("pv:deleteWebhook", 0) < 2 or not calls.get("pv:setMyCommands")):
        problems.append("the startup fault sequence was not exercised")
    if (args.backlog or args.widget_backlog) and stats["pending_updates"] != 0:
        problems.append(f"{stats['pending_updates']} waiting updates were not taken")
    if args.widget_backlog and stats.get("widget_answers", 0) != args.widget_backlog:
        problems.append(f"{stats.get('widget_answers', 0)} of {args.widget_backlog} widgets were answered")
    if args.widget_backlog and stats.get("widget_boards", 0) != args.widget_backlog:
        problems.append(f"{stats.get('widget_boards', 0)} of {args.widget_backlog} widgets returned a played board")
    if args.max_rss_mib and any(peak[label] == 0 for label in ("predvestnik", "domovoy") if label in procs):
        problems.append("memory measurement unavailable for a bot")
    if args.max_rss_mib and total_mib > args.max_rss_mib:
        problems.append(f"memory {total_mib} MiB is over the limit {args.max_rss_mib}")
    try:
        import aiogram
        version = aiogram.__version__
    except Exception:
        version = "?"
    print(json.dumps({"aiogram": version, "python": sys.version.split()[0], "first_health_s": first_health,
                      "peak_mib": {k: v // 2**20 for k, v in peak.items()}, "peak_total_mib": total_mib,
                      "calls": {k: v for k, v in sorted(calls.items()) if k.endswith(("getUpdates", "getMe", "deleteWebhook", "setMyCommands"))},
                      "pending_updates": stats["pending_updates"], "widget_answers": stats.get("widget_answers", 0),
                      "widget_boards": stats.get("widget_boards", 0),
                      "problems": problems, "logs": str(out_dir)}, ensure_ascii=False))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
