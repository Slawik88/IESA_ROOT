#!/usr/bin/env python3
"""Cold start of the Mini App on a slow phone: a fresh browser (empty cache) opens the app through the production-topology stand (tools/ui_stand.py).

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. python tools/bench_cold_start.py [--device mid|low] [--runs 3] [--net slow4g|fast4g|none] [--cpu 4]

The network is throttled like the DevTools «Slow 4G» preset (562 ms round trip, 1.6 Mbit/s down) and the CPU 4× slower. telegram.org and Google Fonts are
blocked (the sandbox has no internet; in production they come from their own CDN either way), so the numbers compare only what this app serves.
Prints the median of the runs: first paint, DOMContentLoaded, profile ready (the app drew the player), bytes over the wire before the profile was ready
(all, CSS, JS) and how many stylesheets blocked the first paint. Needs PostgreSQL (see tools/ui_stand.py) and Chromium.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from ui_smoke import DEVICES, INIT, chromium_path  # noqa: E402
from ui_stand import DEFAULT_DSN, Stand  # noqa: E402

NETWORKS = {
    "slow4g": {"latency": 562.5, "downloadThroughput": 1.6 * 1024 * 1024 / 8 * .9, "uploadThroughput": 750 * 1024 / 8 * .9},
    "fast4g": {"latency": 150, "downloadThroughput": 9 * 1024 * 1024 / 8 * .9, "uploadThroughput": 1.5 * 1024 * 1024 / 8 * .9},
}
OUTSIDE = ("telegram.org", "fonts.googleapis.com", "fonts.gstatic.com")
# the player's profile is drawn: the identity block replaced the skeleton of index.html
READY = "() => typeof _profileData !== 'undefined' && !!_profileData && !!document.querySelector('#pro-main .v3-id')"


def one_run(stand: Stand, browser, args) -> dict[str, float]:
    ctx = browser.new_context(viewport={"width": 390, "height": 780}, device_scale_factor=1, has_touch=True, is_mobile=True)
    ctx.route("**/*", lambda route: route.abort() if any(host in route.request.url for host in OUTSIDE) else route.continue_())
    page = ctx.new_page()
    page.add_init_script(INIT + stand.browser_init + ";localStorage.setItem('v3_lite','0');" + DEVICES[args.device])
    cdp = ctx.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    if args.net != "none":
        cdp.send("Network.emulateNetworkConditions", {"offline": False, **NETWORKS[args.net]})
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": args.cpu})
    kinds: dict[str, str] = {}
    sizes: dict[str, float] = {}
    cdp.on("Network.responseReceived", lambda e: kinds.__setitem__(e["requestId"], e["type"]))
    cdp.on("Network.loadingFinished", lambda e: sizes.__setitem__(e["requestId"], e["encodedDataLength"]))
    page.goto(stand.url, wait_until="domcontentloaded", timeout=120000)
    page.wait_for_function(READY, timeout=120000, polling=50)
    ready = page.evaluate("() => performance.now()")
    by_kind = {"Stylesheet": 0.0, "Script": 0.0}
    for request_id, size in list(sizes.items()):
        kind = kinds.get(request_id, "")
        if kind in by_kind:
            by_kind[kind] += size
    timing = page.evaluate("""() => {
        const nav = performance.getEntriesByType('navigation')[0];
        const fcp = performance.getEntriesByName('first-contentful-paint')[0];
        const blocking = performance.getEntriesByType('resource').filter(r => r.initiatorType === 'link' && r.renderBlockingStatus === 'blocking').length;
        return {fcp: fcp ? fcp.startTime : -1, dcl: nav.domContentLoadedEventEnd, blocking};
    }""")
    ctx.close()
    return {"first paint, ms": timing["fcp"], "DOMContentLoaded, ms": timing["dcl"], "profile ready, ms": ready,
            "bytes before ready": sum(sizes.values()), "CSS bytes": by_kind["Stylesheet"], "JS bytes": by_kind["Script"],
            "render-blocking stylesheets": timing["blocking"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", choices=sorted(DEVICES), default="mid")
    parser.add_argument("--net", choices=(*NETWORKS, "none"), default="slow4g")
    parser.add_argument("--cpu", type=float, default=4)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--skin", default=None, help="the look the player wears (a skin id, e.g. void); default: the default look")
    parser.add_argument("--tier", default="SSS")
    parser.add_argument("--port", type=int, default=8403)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright
    with Stand(port=args.port, dsn=args.dsn, skin=args.skin, tier=args.tier) as stand, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_path())
        runs = [one_run(stand, browser, args) for _ in range(args.runs)]
        browser.close()
    print(f"cold start, look {args.skin or 'default'}, device {args.device}, network {args.net}, CPU x{args.cpu:g}, median of {args.runs}:")
    for key in runs[0]:
        value = statistics.median(run[key] for run in runs)
        print(f"  {key:28} {value / 1024:9.1f} KB" if "bytes" in key else f"  {key:28} {value:9.0f}")


if __name__ == "__main__":
    main()
