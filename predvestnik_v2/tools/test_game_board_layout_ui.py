"""Leaderboards of Rhythm and Minesweeper pages and of the Mini App Top on a phone: long nicks, look titles, VIP, marks, photos and the own row stay inside their column.

The owner saw on production (2026-10-29): nicks and titles cut on the podium, the title of #4 dropped onto a line of its own in the middle of the row.
The pages are the real ones of the stand (tools/ui_stand.py); only the leaderboard answer is replaced by a fixture of awkward rows.
Checked at 320/390/430: nothing leaves its podium column or row, the page never scrolls sideways, a list row stays 44–64 px,
the nick and the title of a row start at the same left edge and the title sits under the nick.

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. python tools/test_game_board_layout_ui.py [--shots DIR]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))

from playwright.sync_api import sync_playwright  # noqa: E402
from ui_smoke import chromium_path, go, open_app  # noqa: E402
from ui_stand import DEFAULT_DSN, Stand, set_game_flags  # noqa: E402
from services.skins_v3 import look_payload  # noqa: E402

NAMES = ["Kovic_the_longest_nickname_ever", "diegoyuuki", "Buy_a_very_long_name_too", "FrankensteinBoy", "Qwest226", "Я", "Очень_длинный_ник_на_кириллице"]


def flat(look: dict | None) -> dict:
    """The same rows in the shape of /leaderboards/* (messages, game wins): Top screen and profile Top-10 of the Mini App."""
    rows = [{"place": r["place"], "name": r["player"]["display_name"], "ref": r["player"]["profile_ref"], "count": 9000 - r["place"] * 700, "is_vip": r["player"]["is_vip"],
             "is_me": r["is_me"], "look": r["player"].get("look"), "mark": r["player"].get("mark"), "avatar_state": "absent", "level": 12} for r in fixture(look)["top"]]
    return {"top": rows, "items": rows, "page": 0, "pages": 1, "personal": {"place": 5, "count": 5500, "total": 812}}


def fixture(look: dict | None) -> dict:
    rows = []
    for i, name in enumerate(NAMES):
        player = {"display_name": "@" + name, "profile_ref": f"ref{i:02d}" + "x" * 14, "is_vip": i % 2 == 0, "avatar_state": "absent"}
        if look and i != 1:
            player["look"] = {**look, "title": "Хранитель Гавани, страж далёкого маяка" if i in (0, 3, 6) else look.get("title") or "Страж"}
        if i in (0, 4):
            player["mark"] = {"id": "streak30", "title": "Серия 30 дней", "glyph": "🔥", "tone": "orange"}
        rows.append({"place": i + 1, "player": player, "best_score": 96491 - i * 6000, "best_elapsed_ms": 41000 + i * 3100, "is_me": i == 4})
    return {"top": rows, "items": rows, "page": 0, "pages": 1, "personal": {"place": 5, "best_score": 72491, "total": 812}, "season": None}


GEOMETRY = """() => { const out = []; const W = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth > W + 1) out.push('page scrolls sideways: ' + document.documentElement.scrollWidth + ' > ' + W);
  const inside = (box, el, what) => { const a = box.getBoundingClientRect(), b = el.getBoundingClientRect(); if (!b.width) return;
    if (b.left < a.left - 1 || b.right > a.right + 1) out.push(what + ' leaves its box: ' + Math.round(b.left) + '..' + Math.round(b.right) + ' of ' + Math.round(a.left) + '..' + Math.round(a.right)); };
  const pods = [...document.querySelectorAll('#leaderboard-podium .lgl-pod')]; if (pods.length !== 3) out.push('podium has ' + pods.length + ' places');
  pods.forEach(p => p.querySelectorAll('.lb-avatar, .ap-name, .ap-plain, .ap-title, small').forEach(e => inside(p, e, 'podium ' + p.className.split(' ')[1] + ' ' + e.className.split(' ')[0])));
  const rows = [...document.querySelectorAll('#leaderboard-list > li')]; if (rows.length < 2) out.push('list has ' + rows.length + ' rows');
  rows.forEach((r, i) => { const h = r.getBoundingClientRect().height; if (h < 43 || h > 64) out.push('row ' + (i + 4) + ' is ' + Math.round(h) + ' px');
    r.querySelectorAll('a, .ap-name, .ap-plain, .ap-title, b').forEach(e => inside(r, e, 'row ' + (i + 4) + ' ' + (e.className || e.tagName).toString().split(' ')[0]));
    const nick = r.querySelector('.v3-who > span:first-child'), title = r.querySelector('.v3-who > .ap-title');
    if (nick && title) { const n = nick.getBoundingClientRect(), t = title.getBoundingClientRect();
      if (Math.abs(n.left - t.left) > 1.5) out.push('row ' + (i + 4) + ': title not under the nick (' + Math.round(n.left) + ' vs ' + Math.round(t.left) + ')');
      if (t.top < n.bottom - 1) out.push('row ' + (i + 4) + ': title beside the nick'); } });
  return out; }"""

# Mini App Top: podium cards and list rows (same rules, the row is a button of .v3-top-list)
APP_GEOMETRY = """() => { const out = []; const W = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth > W + 1) out.push('page scrolls sideways: ' + document.documentElement.scrollWidth + ' > ' + W);
  const inside = (box, el, what) => { const a = box.getBoundingClientRect(), b = el.getBoundingClientRect(); if (!b.width) return;
    if (b.left < a.left - 1 || b.right > a.right + 1) out.push(what + ' leaves its box: ' + Math.round(b.left) + '..' + Math.round(b.right) + ' of ' + Math.round(a.left) + '..' + Math.round(a.right)); };
  const root = document.getElementById('pg-top');
  const pods = [...root.querySelectorAll('.v3-podium:not(.is-ghost) .v3-pod')]; if (pods.length !== 3) out.push('podium has ' + pods.length + ' places');
  pods.forEach(p => p.querySelectorAll('.ap-name, .ap-plain, .ap-title, .v3-pod-name, small').forEach(e => inside(p, e, 'podium ' + p.className.split(' ')[1] + ' ' + String(e.className).split(' ')[0])));
  const rows = [...root.querySelectorAll('.v3-top-list > li')]; if (rows.length < 2) out.push('list has ' + rows.length + ' rows');
  rows.forEach((r, i) => { const h = r.getBoundingClientRect().height; if (h > 72) out.push('row ' + (i + 4) + ' is ' + Math.round(h) + ' px');
    r.querySelectorAll('.ap-name, .ap-plain, .ap-title, b').forEach(e => inside(r, e, 'row ' + (i + 4) + ' ' + String(e.className || e.tagName).split(' ')[0])); });
  return out; }"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shots")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--port", type=int, default=8403)
    args = parser.parse_args()
    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    t = threading.Thread(target=lambda: asyncio.run(set_game_flags(args.dsn, True))); t.start(); t.join()
    problems: list[str] = []
    with Stand(args.port, args.dsn, skin="void", tier="SSS") as stand, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_path())
        for width in (320, 390, 430):
            ctx, page, _probe = open_app(stand, browser, width)
            data = json.dumps(fixture(look_payload("void", "SSS", compact=True)))
            ctx.route("**/leaderboard/**", lambda route: route.fulfill(status=200, content_type="application/json", body=data))
            for path, game in (("/rhythm-v2", "rhythm"), ("/minesweeper", "minesweeper")):
                errors: list[str] = []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)[:120]))
                go(page, stand.base + path)
                page.wait_for_function("() => document.querySelectorAll('#leaderboard-podium .lgl-pod').length > 0", timeout=20000)
                page.wait_for_timeout(600)
                page.evaluate("() => document.getElementById('leaderboard-podium').scrollIntoView({block: 'start'})")
                found = page.evaluate(GEOMETRY) + ["js error: " + e for e in errors]
                problems += [f"{game} @{width}: {x}" for x in found]
                if shots:
                    page.locator("#leaderboard-podium").locator("xpath=..").screenshot(path=str(shots / f"{game}-board-{width}.png"))
            app_data = json.dumps(flat(look_payload("void", "SSS", compact=True)))
            ctx.route("**/leaderboards/**", lambda route: route.fulfill(status=200, content_type="application/json", body=app_data))
            for scope in ("Все игроки", "Ритм", "Сапёр"):
                go(page, page.home)
                page.wait_for_function("() => typeof openTopV3 === 'function' && typeof _profileData !== 'undefined' && !!_profileData", timeout=20000)
                page.evaluate("() => openTopV3()")
                page.wait_for_timeout(700)
                page.evaluate("s => { const b = [...document.querySelectorAll('#pg-top .v3-tab')].find(x => x.textContent.trim() === s); if (b) b.click(); }", scope)
                page.wait_for_function("() => document.querySelectorAll('#pg-top .v3-top-list > li').length > 1", timeout=15000)
                page.wait_for_timeout(500)
                problems += [f"app top «{scope}» @{width}: {x}" for x in page.evaluate(APP_GEOMETRY)]
                if shots and scope != "Сапёр":
                    page.locator("#pg-top .v3-top-body").screenshot(path=str(shots / f"app-top-{'rhythm' if scope == 'Ритм' else 'all'}-{width}.png"))
            ctx.close()
        browser.close()
    if problems:
        print("\n".join("FAIL " + p for p in problems))
        return 1
    print("OK: Rhythm, Minesweeper and the Mini App Top (all, Rhythm, Minesweeper) at 320/390/430 — long nicks, titles, VIP, marks and the own row stay in their columns, rows 44–64 px, no sideways scroll")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
