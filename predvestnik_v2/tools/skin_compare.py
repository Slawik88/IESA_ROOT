"""Reproducible skin comparison from two checked-out revisions, without DB or Telegram.

python tools/skin_compare.py --before-root <baseline-worktree> --after-root <worktree> --out <empty-folder>
The output is a portable local HTML gallery; it is never a production route.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
UI = HERE / "skin_compare"
TIERS = ("D", "C", "B", "A", "S", "SS", "SSS")
PARTS = (15, 16, 17, 18, 19, 20, 22, 25, 29, 32, 33, 34, 35, 36, 37, 38, 48, 50, 53)
MODES = ("profile", "nick", "top", "telegram")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, encoding="utf-8").strip()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def css_files(project):
    tree = ast.parse((project / "FastAPI/main.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_SHELL_V3_CSS" for t in node.targets):
            return ["app.css", *ast.literal_eval(node.value)]
    raise RuntimeError("Current stylesheet order not found")


def make_preview(root, out, raw, cards, only=None):
    project = root / "predvestnik_v2"
    revision = git(root, "rev-parse", "HEAD")
    source = project / "FastAPI/static"
    css = css_files(project)
    files = [*css, *(f"skin-scene-{letter}-v3.css" for letter in "abcdefg"),
             *(f"app.{part:02d}.js" for part in PARTS), "app.01.js", "nickname-v3.js", "game-board-v3.js"]
    hashes = {f"FastAPI/static/{name}": digest((source / name).read_text(encoding="utf-8").encode("utf-8")) for name in files}
    for name in ("FastAPI/main.py", "core/skins_v3.py", "core/skins_v3_catalog.py", "services/skins_v3.py",
                 "core/skins_v3_chat.py", "bot/chat/skin_card.py", "bot/chat/skin_card_draw.py",
                 "bot/chat/skin_motion.py", "bot/chat/activity_graph.py"):
        hashes[name] = digest((project / name).read_text(encoding="utf-8").encode("utf-8"))
    # A dirty production asset must never be labelled as the committed baseline.
    for path, sha in hashes.items():
        committed = subprocess.check_output(["git", "-C", str(root), "show", f"{revision}:predvestnik_v2/{path}"])
        if digest(committed.replace(b"\r\n", b"\n")) != sha:
            raise RuntimeError(f"Commit the cosmetic sources before comparing: {path}")
    subprocess.run([sys.executable, str(HERE / "skin_compare_export.py"), "--root", str(root),
                    "--out", str(raw), *(["--cards"] if cards else []),
                    *(["--only", only] if only else [])], check=True)
    catalog = json.loads((raw / "catalog.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True)
    (out / "static").mkdir()
    for name in [*css, *(f"skin-scene-{letter}-v3.css" for letter in "abcdefg")]:
        shutil.copy2(source / name, out / "static" / name)
    fonts = project / "bot/chat/assets/fonts"
    (out / "fonts").mkdir()
    for font in fonts.glob("Onest-*.ttf"):
        path = str(font.relative_to(project)).replace("\\", "/")
        committed = subprocess.check_output(["git", "-C", str(root), "show", f"{revision}:predvestnik_v2/{path}"])
        if committed != font.read_bytes():
            raise RuntimeError(f"Commit the font source before comparing: {path}")
        shutil.copy2(font, out / "fonts" / font.name)
        hashes[path] = digest(font.read_bytes())
    art = {}
    for letter in "abcdefg":
        text = (source / f"skin-scene-{letter}-v3.css").read_text(encoding="utf-8")
        art[letter] = [f"static/skin-scene-{letter}-v3.css", " ".join(re.findall(r"\.i-([\w-]+)\s*\{", text))]
    prefix = """const BASE='.',tg=null;const el=id=>document.getElementById(id);
      const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      const _profileEsc=esc,fmt=n=>new Intl.NumberFormat('ru-RU').format(n);
      const _sysFlags={};let _profileData=null;const _uid=0;
      const api=()=>Promise.reject(new Error('Offline fixture'));
    """
    auth_source = (source / "app.01.js").read_text(encoding="utf-8")
    match = re.search(r"^function vipName\(.*?^\}", auth_source, re.M | re.S)
    if not match:
        raise RuntimeError("Production vipName helper missing")
    bundle = prefix + match.group() + "\n" + (source / "nickname-v3.js").read_text(encoding="utf-8")
    bundle += "\n" + (source / "game-board-v3.js").read_text(encoding="utf-8") + "\n"
    bundle += "\n".join((source / f"app.{part:02d}.js").read_text(encoding="utf-8") for part in PARTS)
    (out / "bundle.js").write_text(bundle, encoding="utf-8")
    (out / "data.js").write_text("const LAB_DATA=" + json.dumps(catalog, ensure_ascii=False) +
                                ";globalThis.__pvSceneArt=" + json.dumps(art) + ";", encoding="utf-8")
    links = "".join(f'<link rel="stylesheet" href="static/{name}">' for name in css)
    page = ('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            + links + '<link rel="stylesheet" href="preview.css"><body><div id="lab-root"></div>'
            '<script src="data.js"></script><script src="bundle.js"></script><script src="preview.js"></script></body></html>')
    (out / "preview.html").write_text(page, encoding="utf-8")
    for name in ("preview.js", "preview.css"):
        shutil.copy2(UI / name, out / name)
    return {"revision": revision, "source_hashes": hashes, "catalog_hash": digest((raw / "catalog.json").read_bytes()), "catalog": catalog}


def pixel_difference(before, after):
    if before.size != after.size:
        return {"changed_percent": 100.0, "changed_pixels": None, "size_changed": True}
    channels = ImageChops.difference(before.convert("RGB"), after.convert("RGB")).split()
    mask = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    changed = mask.point(lambda value: 255 if value else 0).histogram()[255]
    return {"changed_percent": changed * 100 / (before.width * before.height), "changed_pixels": changed, "size_changed": False}


def verify_sources(root, info):
    """A concurrent edit must not relabel a capture as a committed revision."""
    if git(root, "rev-parse", "HEAD") != info["revision"]:
        raise RuntimeError(f"Checkout moved during capture: {root}")
    for name, expected in info["source_hashes"].items():
        data = (root / "predvestnik_v2" / name).read_bytes()
        if name.endswith((".py", ".js", ".css")):
            data = data.replace(b"\r\n", b"\n")
        if digest(data) != expected:
            raise RuntimeError(f"Source changed during capture: {root}: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-root", type=Path, required=True)
    parser.add_argument("--after-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only", help="comma-separated ids; omitted means the entire catalog")
    parser.add_argument("--matrix", action="store_true", help="also compare mid/low/reduced and rare profile frames")
    parser.add_argument("--diff-dir", type=Path, help="optional external raw PNG evidence of non-zero differences")
    args = parser.parse_args()
    if args.only and (len(set(args.only.split(','))) != len(args.only.split(',')) or not all(args.only.split(','))):
        parser.error("Skin ids must be non-empty and unique")
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error("Output must be empty; stale images cannot become comparison evidence")
    out.mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir()
    renderer_files = [*UI.iterdir(), Path(__file__), HERE / "skin_compare_export.py", HERE / "skin_compare_merge.py"]
    renderer_hashes = {str(path.relative_to(HERE)).replace("\\", "/"): digest(path.read_bytes()) for path in renderer_files if path.is_file()}
    audit_path = args.after_root / "predvestnik_v2/docs/roadmap/findings/D2-cosmetics-plan.json"
    audit_bytes = audit_path.read_bytes()
    manifest = {"renderer": "skin-compare-v1", "width": 390, "scale": 1, "render_backend": "CPU raster, sRGB, no LCD subpixel text", "font": "local Onest 400/500/700; weights 300->400 and 600/650->700",
                "audit_hash":digest(audit_bytes), "coverage": [], "limitations": ["Profile stage only; not the full account page", "Telegram video is not measured by static cards",
                "Static fonts replace 300 with 400 and 600/650 with 700"], "renderer_hashes": renderer_hashes}
    with tempfile.TemporaryDirectory(prefix="predvestnik-skins-") as temporary:
        raw = Path(temporary)
        revisions = []
        for side, root in (("before", args.before_root), ("after", args.after_root)):
            info = make_preview(root.resolve(), raw / side / "package", raw / side, cards=True, only=args.only)
            manifest[side] = {key: value for key, value in info.items() if key != "catalog"}
            revisions.append(info)
        catalog = revisions[1]["catalog"]["catalog"]
        manifest["sets"] = revisions[1]["catalog"]["sets"]
        ids = args.only.split(",") if args.only else list(catalog)
        if set(ids) - set(catalog):
            parser.error("Unknown skin id")
        manifest["skins"] = {sid: catalog[sid] for sid in ids}
        for side in ("before", "after"):
            (raw / side / "package/cards").mkdir()
            for sid in ids:
                for tier in TIERS:
                    Image.open(raw / side / "cards" / f"{sid}-{tier}.png").resize((390, 296), Image.Resampling.LANCZOS).save(
                        raw / side / "package/cards" / f"{sid}-{tier}.webp", quality=76, method=6)
        errors = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None,
                                         args=["--disable-gpu", "--disable-lcd-text", "--force-color-profile=srgb"])
            manifest["chromium"] = browser.version
            pages = []
            for side in ("before", "after"):
                context = browser.new_context(viewport={"width": 390, "height": 430}, device_scale_factor=1,
                                              is_mobile=True, has_touch=True)
                context.add_init_script("localStorage.setItem('pv_no_fx','0');")
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                page.on("requestfailed", lambda request: errors.append(f"Resource failed: {request.url}: {request.failure}"))
                page.goto((raw / side / "package/preview.html").as_uri())
                page.wait_for_function("typeof labRender==='function'")
                pages.append(page)
            cases = [(mode, "high", "normal") for mode in MODES]
            if args.matrix:
                cases += [("profile", device, "normal") for device in ("mid", "low", "reduced", "calm")]
                cases += [("profile", "high", "rare")]
            manifest["cases"] = cases
            total = len(ids) * len(TIERS) * len(cases)
            for sid in ids:
                for tier in TIERS:
                    for mode, device, phase in cases:
                        key = f"{sid}-{tier}-{mode}-{device}-{phase}"
                        shots, states = [], []
                        for page in pages:
                            page.emulate_media(reduced_motion="reduce" if device == "reduced" else "no-preference")
                            page.evaluate("options=>labRender(options)", {"skin": sid, "tier": tier, "mode": mode, "device": device, "phase": phase})
                            page.wait_for_function("document.documentElement.dataset.ready==='yes'")
                            if errors:
                                raise RuntimeError("; ".join(sorted(set(errors))))
                            state = page.evaluate("LAB_STATE")
                            expected_cap = 3 if device == "low" else 6 if device == "mid" else 7
                            if not state["font"] or state["device_cap"] != expected_cap:
                                raise RuntimeError(f"Wrong font/device context: {key}: {state}")
                            if state["reduced_motion"] != (device == "reduced") or state["calm"] != (device == "calm"):
                                raise RuntimeError(f"Motion settings are not independent: {key}: {state}")
                            manifest.setdefault("scenes", {}).setdefault(sid, state.pop("scene"))
                            if not state["nodes"] or not state["scene_art_ready"]:
                                raise RuntimeError(f"Incomplete rendered scene: {key}: {state}")
                            states.append(state)
                            shots.append(Image.open(io.BytesIO(page.locator("#lab-root").screenshot())).convert("RGB"))
                        diff = pixel_difference(*shots)
                        if args.diff_dir and diff["changed_percent"]:
                            args.diff_dir.mkdir(parents=True, exist_ok=True)
                            for side, image in zip(("before", "after"), shots):
                                image.save(args.diff_dir / f"{key}-{side}.png")
                        if manifest["before"]["source_hashes"] == manifest["after"]["source_hashes"] and diff["changed_percent"]:
                            raise RuntimeError(f"Identical sources produced different pixels: {key}: {diff}")
                        record = {"key": key, "skin": sid, "tier": tier, "mode": mode, "device": device, "phase": phase,
                                  **diff, "pixel_hashes": [digest(image.tobytes()) for image in shots], "states": states}
                        if mode == "telegram":
                            originals = [Image.open(raw / side / "cards" / f"{sid}-{tier}.png").convert("RGB") for side in ("before", "after")]
                            record["telegram_original"] = {**pixel_difference(*originals), "pixel_hashes": [digest(image.tobytes()) for image in originals]}
                        record["has_changes"] = bool(diff["changed_pixels"] or diff["size_changed"] or
                                                     record.get("telegram_original", {}).get("changed_pixels") or
                                                     record.get("telegram_original", {}).get("size_changed"))
                        if manifest["before"]["source_hashes"] == manifest["after"]["source_hashes"] and record["has_changes"]:
                            raise RuntimeError(f"Identical sources produced different originals: {key}")
                        paths = []
                        for image in shots:
                            filename = f"images/{digest(image.tobytes())}.webp"
                            if not (out / filename).exists():
                                image.save(out / filename, quality=76, method=6)
                            paths.append(filename)
                        record["images"] = paths
                        manifest["coverage"].append(record)
                print(f"{sid}: {len(manifest['coverage'])}/{total} compared", flush=True)
            browser.close()
        if len(manifest["coverage"]) != total or len({row["key"] for row in manifest["coverage"]}) != total:
            raise RuntimeError("Incomplete or duplicated comparison matrix")
        for root, info in zip((args.before_root, args.after_root), revisions):
            verify_sources(root, info)
        shutil.copytree(raw / "before/package", out / "before")
        if manifest["before"]["source_hashes"] != manifest["after"]["source_hashes"]:
            shutil.copytree(raw / "after/package", out / "after")
    for path in renderer_files:
        if path.is_file() and digest(path.read_bytes()) != renderer_hashes[str(path.relative_to(HERE)).replace("\\", "/")]:
            raise RuntimeError(f"Renderer changed during capture: {path.name}; restart this run")
    for name in ("index.html", "gallery.js", "gallery.css"):
        shutil.copy2(UI / name, out / name)
    if audit_path.read_bytes() != audit_bytes:
        raise RuntimeError("Concepts changed during capture; restart this run")
    audit = json.loads(audit_bytes)
    (out / "audit.js").write_text("const AUDIT=" + json.dumps(audit, ensure_ascii=False) + ";", encoding="utf-8")
    # The source CSS and browser data remain in the package for interactive views.
    # Copy references are deduplicated only after both revisions have been rendered.
    if manifest["before"]["source_hashes"] == manifest["after"]["source_hashes"]:
        manifest["after_preview"] = "before/preview.html"
        manifest["duplicate_assets"] = True
    else:
        manifest["after_preview"] = "after/preview.html"
    payload = "const COMPARE=" + json.dumps(manifest, ensure_ascii=False) + ";"
    (out / "manifest.js").write_text(payload, encoding="utf-8")
    size = sum(path.stat().st_size for path in out.rglob("*") if path.is_file())
    if any(path.stat().st_size > 150 * 1024 for path in out.rglob("*.webp")):
        raise RuntimeError("A preview image exceeds 150 KiB")
    if size > 16 * 1024 * 1024:
        raise RuntimeError(f"Gallery exceeds 16 MiB: {size}; reduce the selected set or inspect asset duplication")
    print(f"READY: {len(ids)} skins, {len(manifest['coverage'])} comparisons, {size / 1024 / 1024:.2f} MiB; {out / 'index.html'}")


if __name__ == "__main__":
    main()
