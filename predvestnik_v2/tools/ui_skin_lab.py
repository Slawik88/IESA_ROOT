#!/usr/bin/env python3
"""Skin lab: look at cosmetics one by one, the way a player sees them (avatar, frame, halo, signature detail, nickname, title, stage background, scene and particles).

    python tools/ui_skin_lab.py --out /tmp/lab                                  # every skin at SSS, 390 px wide, a flagship phone (full mode)
    python tools/ui_skin_lab.py --only void,aurora --tiers D,B,SSS --out /tmp/lab
    python tools/ui_skin_lab.py --only frost --ladder --out /tmp/lab            # one picture per skin with every tier D..SSS: judge how the look grows
    python tools/ui_skin_lab.py --only frost --device mid --out /tmp/lab        # what a mid-range phone gets (.ap-lite)
    python tools/ui_skin_lab.py --only void --frames 4 --out /tmp/lab           # four frames of the same skin: judge the motion, not only one pose
    python tools/ui_skin_lab.py --only void --view profile --out /tmp/lab       # the player's own profile (avatar on the left) instead of the Looks hero

One PNG per skin and tier (name-tier.png) plus contact sheets (sheet-N.png, four shots side by side) when PIL is installed.
Needs the same stand as tools/ui_smoke.py (PostgreSQL on 127.0.0.1:5433 and Chromium; the port must be 8403). It only reads: it never buys or equips anything,
the preview of a skin that is not owned is exactly what the shop shows (the profile view is the exception: it reseeds the preprod persona to wear each look).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from ui_smoke import DEVICES, PROFILE_READY, chromium_path, go, reseed, run_js  # noqa: E402
from ui_stand import DEFAULT_DSN, Stand, set_game_flags  # noqa: E402

INIT = ("localStorage.setItem('pv_tour','1');localStorage.setItem('lk_tour','1');localStorage.setItem('v3_lite','0');"
        "localStorage.setItem('pv_marks_seen','[\"developer\",\"founder\",\"tester\",\"streak30\",\"veteran\"]');")
PICK = "(a) => { const [id, tier] = a; _lkPick(id); lkTier(tier); }"
# Where in its cycle each scene motion is shown with --phase: the moment an event is on screen (peek, flash and cross are rare by design)
SEEK = """(on) => { const at = { peek: .89, flash: .915, cross: .5, sweep: .14, rise: .35, ripple: .3, twinkle: .5 };
  document.querySelectorAll('.ap-scene .sc').forEach(el => { const key = Object.keys(at).find(k => el.classList.contains(k)); if (!key) return;
    el.getAnimations().forEach(a => { if (on) { a.pause(); const t = a.effect.getComputedTiming(); a.currentTime = (t.delay || 0) + t.duration * at[key]; } else a.play(); }); }); }"""
HERO = """() => { const r = document.querySelector('.lk-hero'); if (!r) return null; const b = r.getBoundingClientRect(); return [b.left, b.top + scrollY, b.width, b.height]; }"""
TIERS = ["D", "C", "B", "A", "S", "SS", "SSS"]


def sheets(shots: list[tuple[str, Path]], out: Path, per: int, prefix: str = "sheet") -> int:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return 0
    count = 0
    for n in range(0, len(shots), per):
        group = shots[n:n + per]
        images = [Image.open(p).convert("RGB") for _, p in group]
        height = max(i.height for i in images)
        sheet = Image.new("RGB", (sum(i.width for i in images), height), (8, 8, 12))
        left = 0
        for (label, _), img in zip(group, images):
            sheet.paste(img, (left, 0)); ImageDraw.Draw(sheet).text((left + 8, 6), label, fill=(255, 255, 255)); left += img.width
        sheet.save(out / f"{prefix}-{n // per + 1}.png"); count += 1
    return count


def ladder(sid: str, out: Path, tiers: list[str]) -> None:
    from PIL import Image, ImageDraw
    images = [Image.open(out / f"{sid}-{t}.png").convert("RGB") for t in tiers]
    w, h = images[0].size
    cols = 4
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, h * rows), (8, 8, 12))
    for i, (t, img) in enumerate(zip(tiers, images)):
        sheet.paste(img, ((i % cols) * w, (i // cols) * h)); ImageDraw.Draw(sheet).text(((i % cols) * w + 8, (i // cols) * h + 6), f"{sid} {t}", fill=(255, 255, 255))
    sheet.save(out / f"ladder-{sid}.png")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", type=lambda s: s.split(","), default=None, help="skin ids (default: every skin, personal ones included)")
    parser.add_argument("--tiers", type=lambda s: s.split(","), default=["SSS"])
    parser.add_argument("--ladder", action="store_true", help="every tier D..SSS, plus one ladder-<skin>.png per skin")
    parser.add_argument("--view", choices=("looks", "profile"), default="looks")
    parser.add_argument("--device", choices=sorted(DEVICES), default="high")
    parser.add_argument("--width", type=int, default=390)
    parser.add_argument("--scale", type=float, default=1.0, help="device scale factor (2 for a sharp look at details)")
    parser.add_argument("--wait", type=int, default=1800, help="ms to let the animations run before the shot")
    parser.add_argument("--frames", type=int, default=1, help="shots per skin, 700 ms apart")
    parser.add_argument("--phase", action="store_true", help="freeze rare events (peek, flash, cross, sweep...) at the moment they are on screen")
    parser.add_argument("--full", action="store_true", help="shoot the whole Looks page top (hero + title + steps) instead of the hero only")
    parser.add_argument("--out", required=True)
    parser.add_argument("--port", type=int, default=8403)
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL", DEFAULT_DSN))
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    tiers = TIERS if args.ladder else args.tiers

    from core.skins_v3_catalog import SKINS
    ids = args.only or list(SKINS)
    asyncio.run(set_game_flags(args.dsn, True))
    from playwright.sync_api import sync_playwright
    shots: list[tuple[str, Path]] = []
    errors: list[str] = []
    with Stand(args.port, args.dsn, skin="void", tier="SSS", rich=True) as stand, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_path())

        def new_page():
            ctx = browser.new_context(viewport={"width": args.width, "height": 900}, device_scale_factor=args.scale, has_touch=True, is_mobile=True)
            page = ctx.new_page()
            page.add_init_script(INIT + DEVICES[args.device])
            page.on("pageerror", lambda e: errors.append(str(e)[:160]))
            go(page, stand.url)
            page.wait_for_function(PROFILE_READY, timeout=30000)
            return ctx, page

        def snap(page, sid, tier, clip, frames):
            for frame in range(frames):
                suffix = f"-f{frame + 1}" if frames > 1 else ""
                path = out / f"{sid}-{tier}{suffix}.png"
                page.screenshot(path=str(path), clip=clip)
                shots.append((f"{sid} {tier}{suffix}", path))
                if frame + 1 < frames:
                    page.wait_for_timeout(700)

        if args.view == "looks":
            reseed(args.dsn, skin="void", tier="SSS", owned=tuple(s for s, v in SKINS.items() if v.get("exclusive")))   # after the stand started: it seeds the persona itself
            ctx, page = new_page()
            page.wait_for_timeout(800)
            run_js(page, "openLooksModal()")
            page.wait_for_function("() => typeof _lk !== 'undefined' && _lk.st", timeout=20000)
            page.wait_for_timeout(600)
            for sid in ids:
                for tier in tiers:
                    page.evaluate(PICK, [sid, tier])
                    page.wait_for_timeout(args.wait)
                    if args.phase:
                        page.evaluate(SEEK, True)
                    box = page.evaluate(HERO)
                    if not box:
                        print(f"{sid}: no hero"); continue
                    x, y, w, h = box
                    if args.full:
                        h = min(h + 330, 1000)
                    page.evaluate("() => window.scrollTo(0, 0)")
                    snap(page, sid, tier, {"x": 0, "y": max(0, y - 6), "width": args.width, "height": h + 10}, args.frames)
            ctx.close()
        else:
            for sid in ids:
                for tier in tiers:
                    reseed(args.dsn, skin=sid, tier=tier)
                    ctx, page = new_page()
                    page.wait_for_timeout(args.wait)
                    if args.phase:
                        page.evaluate(SEEK, True)
                    snap(page, sid, tier, {"x": 0, "y": 0, "width": args.width, "height": 330}, args.frames)
                    ctx.close()
        browser.close()
    if errors:
        print("JS errors:", *sorted(set(errors)), sep="\n  ")
    if args.ladder and args.frames == 1:
        try:
            for sid in ids:
                ladder(sid, out, tiers)
        except ImportError:
            pass
    per = 4 if args.frames == 1 else args.frames
    made = 0 if args.ladder else sheets(shots, out, per)
    print(f"{len(shots)} shots{f' and {made} sheets' if made else ''} in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
