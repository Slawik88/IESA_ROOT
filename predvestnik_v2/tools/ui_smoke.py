#!/usr/bin/env python3
"""UI smoke suite: the whole player interface in a phone emulation, against the production-topology stand (tools/ui_stand.py).

    python tools/ui_smoke.py                          # every screen x widths 320/390/430, the persona wears Void at SSS
    python tools/ui_smoke.py --skins                  # every look at D and SSS x widths 320/430: profile, six dock tabs, Looks
    python tools/ui_smoke.py --only profile,top --widths 390 --shots /tmp/shots

A run FAILS on: a JS error, an unexpected HTTP error, a widened layout viewport, horizontal overflow, a dock that is not pinned inside the screen,
a screen opener that throws, a browser-default grey button. Reported as warnings (fail with --strict): controls under 32px, card-around-everything shells.
Needs PostgreSQL (see tools/ui_stand.py) and Chromium (PLAYWRIGHT_BROWSERS_PATH). Not part of the automatic test run. Admin screens are not covered.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from ui_smoke_checks import (BLOCKS, CANDIDATES, PAGES, PRESS, DOCK_SAMPLE, DOCK_TABS, EXPECTED_CONSOLE, EXPECTED_HTTP, GEOMETRY, KNOWN_OPEN, SCREENS, SKIP_CLICK, TAP)  # noqa: E402
from ui_stand import DEFAULT_DSN, PEER_ID, Stand, seed_persona, set_game_flags  # noqa: E402

FREEZE = "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}"
INIT = ("localStorage.setItem('pv_tour','1');"
        "localStorage.setItem('pv_marks_seen','[\"developer\",\"founder\",\"tester\",\"streak30\",\"veteran\"]')")
HEIGHT = 780
PROFILE_READY = "() => typeof _profileData !== 'undefined' && _profileData && _profileData.look"


def chromium_path() -> str | None:
    """The pre-installed Chromium may be a different build than the one this Playwright expects."""
    if os.getenv("CHROMIUM_PATH"):
        return os.environ["CHROMIUM_PATH"]
    found = sorted(Path(os.getenv("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")).glob("chromium-*/chrome-linux/chrome"))
    return str(found[-1]) if found else None


def reseed(dsn: str, **persona) -> None:
    """seed_persona is async and Playwright's sync API owns this thread's loop, so run it in a thread of its own."""
    params = {"skin": None, "tier": "D", "rich": True, "name": None, "vip": True, "owned": (), **persona}
    thread = threading.Thread(target=lambda: asyncio.run(seed_persona(dsn, **params)))
    thread.start(); thread.join()


class Probe:
    """Collects what a page does wrong while a scenario runs."""

    def __init__(self, page) -> None:
        self.problems: list[str] = []
        self.known: list[str] = []
        page.on("pageerror", lambda e: self.problems.append("js error: " + str(e)[:140]))
        page.on("console", lambda m: self._console(m))
        page.on("response", lambda r: self._response(r))

    def _console(self, msg) -> None:
        if msg.type == "error" and not any(x in msg.text for x in EXPECTED_CONSOLE):
            self.problems.append("console: " + msg.text[:140])

    def _response(self, resp) -> None:
        if resp.status < 400 or any(path in resp.url and resp.status == code for path, code in EXPECTED_HTTP):
            return
        known = any(path in resp.url and resp.status == code for path, code in KNOWN_OPEN)
        (self.known if known else self.problems).append(f"http {resp.status}: {resp.url[-80:]}")

    def take(self) -> list[str]:
        out, self.problems, self.known = self.problems, [], []
        return out

    def take_known(self) -> list[str]:
        out, self.known = sorted(set(self.known)), []
        return ["known open: " + x for x in out]


def open_app(stand: Stand, browser, width: int):
    ctx = browser.new_context(viewport={"width": width, "height": HEIGHT}, device_scale_factor=1, has_touch=True, is_mobile=True)
    page = ctx.new_page()
    page.add_init_script(INIT)
    probe = Probe(page)
    page.goto(stand.url)
    page.wait_for_function(PROFILE_READY, timeout=20000)
    page.wait_for_timeout(1200)
    probe.take()
    page.home = stand.base + "/"      # a tap may leave the app (a game page, an external link): every screen starts again from here
    return ctx, page, probe


def run_js(page, js: str) -> str | None:
    try:
        page.evaluate("() => { " + js.replace("PEER_ID", str(PEER_ID)) + "; return null; }")
        return None
    except Exception as exc:  # noqa: BLE001 - a throwing opener is a finding
        return "opener threw: " + str(exc).splitlines()[0][:140]


def settle(page) -> None:
    """Let the screen's own requests finish: a list that renders after the first second must still be judged."""
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:  # noqa: BLE001 - a long poll is not a finding
        pass
    page.wait_for_timeout(500)


def check_screen(page, probe: Probe, name: str, js: str, width: int, shots: Path | None) -> tuple[list[str], list[str]]:
    fails: list[str] = []; warns: list[str] = []
    page.goto(page.home)
    page.wait_for_function(PROFILE_READY, timeout=20000)
    page.wait_for_timeout(500)
    probe.take()
    err = run_js(page, js)
    if err:
        fails.append(err)
    settle(page)
    fails += page.evaluate(GEOMETRY, width)
    page.add_style_tag(content=FREEZE)
    for item in page.evaluate(BLOCKS):
        (fails if item.startswith("UA-DEFAULT") else warns).append(item)
    warns += ["small: " + x for x in page.evaluate(TAP)]
    warns += probe.take_known()
    fails += probe.take()
    if shots:
        page.screenshot(path=str(shots / f"{name}-{width}.png"), full_page=True)
    return fails, warns


def check_dock(page, width: int) -> list[str]:
    """Switch every dock tab, at the top and scrolled down, and watch the dock frame by frame."""
    out: list[str] = []
    base = page.evaluate("() => document.querySelector('.nav').getBoundingClientRect().bottom")
    for scroll in (0, 900):
        for tab in DOCK_TABS:
            page.evaluate(f"window.scrollTo(0,{scroll})")
            page.wait_for_timeout(150)
            page.evaluate(f"document.querySelector('.nb[data-page={tab}]').click()")
            frames = page.evaluate(DOCK_SAMPLE, 700)
            if any(abs(f[0] - base) > 2 or f[2] != width or f[3] != HEIGHT for f in frames):
                out.append(f"dock moved on tab {tab} (scroll {scroll}): bottom {min(f[0] for f in frames)}..{max(f[0] for f in frames)}, viewport {frames[-1][2]}x{frames[-1][3]}")
            out += [f"{tab}: {g}" for g in page.evaluate(GEOMETRY, width)]
    return out


def sweep_screens(stand, browser, args, results) -> None:
    reseed(args.dsn, skin="void", tier="SSS")
    shots = Path(args.shots) if args.shots else None
    for width in args.widths:
        ctx, page, probe = open_app(stand, browser, width)
        # What the profile underneath always shows is judged on the profile only, not repeated under every sheet.
        baseline = set(check_screen(page, probe, "profile", "switchPage('profile')", width, None)[1])
        for name, js in SCREENS:
            if args.only and name not in args.only:
                continue
            fails, warns = check_screen(page, probe, name, js, width, shots)
            results[f"{name} @{width}"] = (fails, warns if name.startswith("profile") else [w for w in warns if w not in baseline])
        for path in PAGES:
            if args.only and path not in args.only:
                continue
            page.goto(stand.base + path); settle(page); probe.take()
            page.goto(stand.base + path); settle(page)
            fails = [g for g in page.evaluate(GEOMETRY, width) if "dock" not in g] + [x for x in page.evaluate(BLOCKS) if x.startswith("UA-DEFAULT")] + probe.take()
            results[f"{path} @{width}"] = (fails, [])
            if shots:
                page.screenshot(path=str(shots / f"page{path.replace('/', '-')}-{width}.png"), full_page=True)
        ctx.close()


def sweep_crawl(stand, browser, args, results) -> None:
    """Tap through each screen: every visible control (up to --taps) is pressed once on a fresh screen and the resulting state is judged like a screen.
    Controls that spend money or change the account are skipped by their label; a purchase confirm sheet opens but is never confirmed."""
    reseed(args.dsn, skin="void", tier="SSS")
    for width in args.widths:
        ctx, page, probe = open_app(stand, browser, width)
        for name, js in SCREENS:
            if args.only and name not in args.only:
                continue
            page.goto(page.home); page.wait_for_function(PROFILE_READY, timeout=20000)
            run_js(page, js); settle(page)
            labels = page.evaluate(CANDIDATES, SKIP_CLICK)[: args.taps]
            for index, label in labels:
                page.goto(page.home); page.wait_for_function(PROFILE_READY, timeout=20000)
                run_js(page, js); settle(page); probe.take()
                fails: list[str] = []
                try:
                    pressed = page.evaluate(PRESS, [index, label])
                    if not pressed:
                        continue          # the screen drew itself differently this time: the control is not there, nothing to judge
                except Exception as exc:  # noqa: BLE001
                    fails.append("click threw: " + str(exc).splitlines()[0][:100])
                settle(page)
                on_app = page.evaluate("() => !!document.querySelector('.nav')")        # a tap may open a game page or leave the app: those have no dock
                fails += [g for g in page.evaluate(GEOMETRY, width) if on_app or "dock" not in g] + [x for x in page.evaluate(BLOCKS) if x.startswith("UA-DEFAULT")] + probe.take()
                if fails:
                    results[f"{name} > {label[:40]} @{width}"] = (fails, [])
        ctx.close()
    results.setdefault("crawl", ([], []))


def sweep_skins(stand, browser, args, results) -> None:
    from core.skins_v3_catalog import SKINS
    for sid in SKINS:
        if args.only and sid not in args.only:
            continue
        for tier in ("D", "SSS"):
            reseed(args.dsn, skin=sid, tier=tier)
            for width in args.widths:
                ctx, page, probe = open_app(stand, browser, width)
                fails = page.evaluate(GEOMETRY, width) + check_dock(page, width)
                run_js(page, "openLooksModal()"); page.wait_for_timeout(900)
                fails += page.evaluate(GEOMETRY, width) + probe.take()
                results[f"{sid} {tier} @{width}"] = (fails, [])
                ctx.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skins", action="store_true", help="sweep every look instead of every screen")
    parser.add_argument("--crawl", action="store_true", help="press every control of every screen once and judge the state it opens")
    parser.add_argument("--taps", type=int, default=14, help="controls per screen in --crawl mode")
    parser.add_argument("--widths", type=lambda s: [int(x) for x in s.split(",")], default=None)
    parser.add_argument("--only", type=lambda s: set(s.split(",")), default=None, help="screen names (or skin ids with --skins)")
    parser.add_argument("--shots", help="directory for full-page screenshots (screens mode)")
    parser.add_argument("--flags", choices=("on", "off"), default="on", help="game/economy modules switched on (every screen shows its real content) or off (the closed state)")
    parser.add_argument("--strict", action="store_true", help="warnings fail the run too")
    parser.add_argument("--port", type=int, default=8403)
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL", DEFAULT_DSN))
    args = parser.parse_args()
    args.widths = args.widths or ([320, 430] if args.skins else [320, 390, 430])
    if args.shots:
        Path(args.shots).mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    results: dict[str, tuple[list[str], list[str]]] = {}
    asyncio.run(set_game_flags(args.dsn, args.flags == "on"))
    if args.flags == "off":
        EXPECTED_HTTP.append(("", 403))      # a closed module answers 403 "temporarily disabled"; the screen must show that, not break
    with Stand(args.port, args.dsn, skin="void", tier="SSS", rich=True) as stand, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_path())
        (sweep_skins if args.skins else sweep_crawl if args.crawl else sweep_screens)(stand, browser, args, results)
        browser.close()
    failed = warned = 0
    for key, (fails, warns) in results.items():
        if fails or warns:
            print(f"{'FAIL' if fails else 'warn'}  {key}")
            for line in fails[:6]: print("      !", line)
            for line in warns[:4]: print("      ~", line)
        failed += bool(fails); warned += bool(warns)
    print(f"{len(results)} scenarios: {failed} failed, {warned} with warnings")
    return 1 if failed or (args.strict and warned) else 0


if __name__ == "__main__":
    sys.exit(main())
