#!/usr/bin/env python3
"""Crop of the scene pictures (FastAPI/static/app.35–38.js): a moving silhouette layer is drawn in a box that is mostly empty
(clock hands in a 380 px square, drones on an orbit, thin rays), and the compositor pays for the whole box every frame.
`cr: [x0, y0, x1, y1]` in the layer geometry (see _scCrop in app.35.js) shrinks the box to where the picture really has pixels;
the picture, its colour gradient and the centre of rotation stay where they were, so the look is the same.
A box given in px is cropped in whole px (the pixel grid of the layer stays put, the picture lands exactly); a box in % (a stretched picture) by fractions of the box.

    python tools/scene_crop.py             # table: which layers would gain, and the cr to give them
    python tools/scene_crop.py --apply     # writes cr into app.35–38.js (replaces the old ones, removes the ones that no longer pay)
    python tools/scene_crop.py --check     # every cr in the files must still hold all pixels of its picture (run after changing tools/scene_art_*.py)

Needs node (reads the scene data out of the real JS) and Playwright with Chromium (draws each picture into a canvas, 2x, and takes the alpha bounds).
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
STATIC = ROOT / "FastAPI/static"
PARTS = sorted(STATIC.glob("app.3[5-8].js"))

# Motions that move the layer as a whole around its own origin (rotation, scale, opacity, shifts in px): the crop keeps them exact.
# drift is in % of the layer width (the engine rescales it), wave/go and the shapes other than sil are not cropped.
CROPPABLE = {"spin", "sway", "pulse", "breathe", "beat", "blink", "twinkle", "float", "rise", "ripple", "peek", "flash", "flicker", "drift", "cross", "sweep"}
PAD = 2.0            # px of margin around the pixels (anti-aliasing of the rotated edge)
MIN_GAIN = 0.15      # a crop must save at least this share of the box
MIN_GAIN_PCT = 0.5   # a box in % cannot be cut on whole px (the picture shifts by a fraction of a px), so only a crop that saves half of it pays
MIN_AREA = 9000      # px², smaller boxes are not worth a field
REF_BOX = (434, 300)  # a % box has no size of its own; a stretched picture (st) is cropped by fractions, so any size will do

MEASURE = r"""async (items) => {
  const out = [];
  for (const it of items) {
    const img = new Image(); img.src = it.url;
    try { await img.decode(); } catch (e) { out.push(null); continue; }
    const K = 2, W = Math.ceil(it.w * K), H = Math.ceil(it.h * K);
    const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(img, it.dx * K, it.dy * K, it.dw * K, it.dh * K);
    const d = ctx.getImageData(0, 0, W, H).data;
    let x0 = W, y0 = H, x1 = -1, y1 = -1;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (d[(y * W + x) * 4 + 3] > 0) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
    out.push(x1 < 0 ? null : [x0 / K, y0 / K, (x1 + 1) / K, (y1 + 1) / K]);
  }
  return out;
}"""


def load_scenes() -> dict[str, list]:
    source = "\n".join(p.read_text(encoding="utf-8") for p in PARTS) + "\nprocess.stdout.write(JSON.stringify([..._AP_SCENES]));"
    done = subprocess.run(["node"], input=source, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr[:400]
    return dict(json.loads(done.stdout))


def load_pictures() -> dict[str, tuple[str, tuple[float, float, float, float]]]:
    import scene_art
    pics = {}
    for name, text in scene_art.render().items():
        for pic, value in re.findall(r'^\.i-([A-Za-z0-9_]+) \{ --img: (url\("data:image/svg\+xml,.*"\)); \}$', text, re.M):
            svg = urllib.parse.unquote(value[len('url("data:image/svg+xml,'):-2])
            vb = [float(v) for v in re.search(r"viewBox='([^']+)'", svg).group(1).split()]
            pics[pic] = (value[len('url("'):-2], tuple(vb))
    return pics


def px(value) -> float | None:
    m = re.fullmatch(r"(-?\d*\.?\d+)px", str(value))
    return float(m.group(1)) if m else None


def plan(scenes, pics) -> list[dict]:
    """Every sil layer that can be cropped (or already is): its box and what the picture paints in it."""
    items = []
    for sid, layers in scenes.items():
        for idx, (tier, classes, geo) in enumerate(layers):
            words = classes.split()
            if words[0] != "sil":
                continue
            pic = next((w[2:] for w in words if w.startswith("i-")), None)
            motions = [w for w in words[1:] if w in CROPPABLE]
            w, h = px(geo.get("w")), px(geo.get("h"))
            stretched = "st" in words and "m" not in words     # a masked layer always fits its mask with `contain`
            item = dict(look=sid, idx=idx, classes=classes, geo=geo, pic=pic, has=bool(geo.get("cr")), reason="")
            if not motions:
                item["reason"] = "still"
            elif pic not in pics:
                item["reason"] = "no picture"
            elif stretched:
                if (w is None) != (h is None):
                    item["reason"] = "box is half in px, half in %"      # the layer grid would not stay on whole px, the picture would shift by a fraction of a px
                else:
                    item["px"] = w is not None
                    w, h = (w or REF_BOX[0]), (h or REF_BOX[1])
                    item.update(w=w, h=h, dx=0, dy=0, dw=w, dh=h)
            elif w is None or h is None:
                item["reason"] = "box is not in px"
            else:
                vw, vh = pics[pic][1][2], pics[pic][1][3]
                if abs((vw / vh) / (w / h) - 1) > 0.03:
                    item["reason"] = "picture and box differ in shape"
                else:
                    item.update(w=w, h=h, dx=0, dy=0, dw=w, dh=h, px=True)
            org = geo.get("org", "50% 50%").split()
            if not item["reason"] and any(o.endswith("px") for o in org) and (px(geo.get("w")) is None or px(geo.get("h")) is None):
                item["reason"] = "origin in px of a box that is not in px"
            if not item["reason"] and "drift" in motions and not str(geo.get("dx", "7%")).endswith("%"):
                item["reason"] = "drift in px"
            if not item["reason"]:
                item["url"] = pics[pic][0]
            items.append(item)
    return items


def measure(items: list[dict]) -> None:
    from playwright.sync_api import sync_playwright
    todo = [it for it in items if not it["reason"]]
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception:      # noqa: BLE001 - the sandbox keeps Chromium outside the default path
            try:
                from ui_smoke import chromium_path
                browser = pw.chromium.launch(executable_path=chromium_path())
            except Exception as error:      # noqa: BLE001
                raise RuntimeError(f"Chromium is not available: {str(error)[:120]}")
        page = browser.new_page()
        boxes = page.evaluate(MEASURE, [{k: it[k] for k in ("url", "w", "h", "dx", "dy", "dw", "dh")} for it in todo])
        browser.close()
    for it, box in zip(todo, boxes):
        if box is None:
            it["reason"] = "empty picture"; continue
        w, h = it["w"], it["h"]
        if it.get("px"):      # whole px, outward
            cr = [max(0, math.floor(box[0] - PAD)), max(0, math.floor(box[1] - PAD)), min(math.ceil(w), math.ceil(box[2] + PAD)), min(math.ceil(h), math.ceil(box[3] + PAD))]
            it["need"] = list(box)
            it["share"] = (cr[2] - cr[0]) * (cr[3] - cr[1]) / (w * h)
        else:                 # fractions of the box, outward to 3 decimals
            x0, y0, x1, y1 = max(0, box[0] - PAD), max(0, box[1] - PAD), min(w, box[2] + PAD), min(h, box[3] + PAD)
            cr = [int(x0 / w * 1000) / 1000, int(y0 / h * 1000) / 1000, -int(-x1 / w * 1000) / 1000, -int(-y1 / h * 1000) / 1000]
            it["need"] = [box[0] / w, box[1] / h, box[2] / w, box[3] / h]
            it["share"] = (cr[2] - cr[0]) * (cr[3] - cr[1])
        it["cr"] = cr
        it["worth"] = it["share"] <= 1 - (MIN_GAIN if it.get("px") else MIN_GAIN_PCT) and w * h >= MIN_AREA


def fmt(cr: list[float]) -> str:
    return "[" + ", ".join(f"{v:g}" for v in cr) + "]"


def row_lines() -> dict[tuple[str, int], tuple[Path, int]]:
    """(look, layer index) -> (file, line number): every layer is one line starting with `  [<tier>, '`."""
    where = {}
    for part in PARTS:
        lines = part.read_text(encoding="utf-8").split("\n")
        look, idx = None, 0
        for n, line in enumerate(lines):
            m = re.match(r"_scAdd\('([a-z_0-9]+)', \[", line)
            if m:
                look, idx = m.group(1), 0
            elif line.startswith("]);"):
                look = None
            elif look and re.match(r"  \[\d, '", line):
                where[(look, idx)] = (part, n); idx += 1
    return where


def apply(items: list[dict]) -> int:
    where = row_lines()
    by_file: dict[Path, list[str]] = {}
    changed = 0
    for it in items:
        part, n = where[(it["look"], it["idx"])]
        lines = by_file.setdefault(part, part.read_text(encoding="utf-8").split("\n"))
        line = re.sub(r", cr: \[[^\]]*\]", "", lines[n])
        if it.get("worth"):
            assert line.endswith(" }],"), line
            line = line[: -len(" }],")] + f", cr: {fmt(it['cr'])}" + " }],"
        if line != lines[n]:
            lines[n] = line; changed += 1
    for part, lines in by_file.items():
        part.write_text("\n".join(lines), encoding="utf-8")
    return changed


def check(items: list[dict]) -> list[str]:
    bad = []
    for it in items:
        cr = it["geo"].get("cr")
        if not cr:
            continue
        name = f"{it['look']}[{it['idx']}] {it['classes']}"
        if it["reason"]:
            bad.append(f"{name}: has cr, but {it['reason']}"); continue
        need = it["need"]
        top_x, top_y = (it["w"], it["h"]) if it.get("px") else (1, 1)
        if not (0 <= cr[0] < cr[2] <= top_x and 0 <= cr[1] < cr[3] <= top_y):
            bad.append(f"{name}: cr {cr} is not a part of the box"); continue
        if it.get("px") and any(v != int(v) for v in cr):
            bad.append(f"{name}: cr of a box in px is whole px, got {cr}"); continue
        if need[0] < cr[0] - 1e-9 or need[1] < cr[1] - 1e-9 or need[2] > cr[2] + 1e-9 or need[3] > cr[3] + 1e-9:
            bad.append(f"{name}: the picture reaches {[round(v, 3) for v in need]}, outside cr {cr} (run tools/scene_crop.py --apply)")
    return bad


def main() -> int:
    if not shutil.which("node"):
        print("SKIP: node is not installed"); return 0
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("SKIP: playwright is not installed"); return 0
    scenes, pics = load_scenes(), load_pictures()
    items = plan(scenes, pics)
    try:
        measure(items)
    except RuntimeError as error:
        print(f"SKIP: {error}"); return 0
    if "--check" in sys.argv:
        bad = check(items)
        if bad:
            print("\n".join(bad)); return 1
        print(f"OK: {sum(1 for it in items if it['geo'].get('cr'))} cropped layers still hold all pixels of their pictures")
        return 0
    if "--apply" in sys.argv:
        print(f"{apply(items)} layers changed")
        return 0
    total = kept = 0
    for it in sorted((i for i in items if i.get("worth")), key=lambda i: -(i["w"] * i["h"] * (1 - i["share"]))):
        total += it["w"] * it["h"]; kept += it["w"] * it["h"] * it["share"]
        print(f"{it['look']:16} {it['idx']:2d} {it['classes'][:34]:34} {it['w']:4.0f}x{it['h']:<4.0f} keeps {100 * it['share']:3.0f}%  cr: {fmt(it['cr'])}{'' if it['has'] else '   (new)'}")
    print(f"-- {sum(1 for i in items if i.get('worth'))} layers, box area {total / (390 * 780):.2f} viewports -> {kept / (390 * 780):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
