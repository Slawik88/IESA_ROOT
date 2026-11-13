"""Combine independently rendered skin subsets, rejecting mixed revisions or duplicate cells."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def load(path):
    return json.loads(path.read_text(encoding="utf-8").removeprefix("const COMPARE=").removesuffix(";"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parts", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compact", action="store_true", help="publish matrix/reduced profile images; other measured views stay interactive")
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        parser.error("Output must be empty")
    manifests = [load(part / "manifest.js") for part in args.parts]
    combined = {**manifests[0], "skins": {}, "scenes": {}, "coverage": []}
    combined["publication"] = {"script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                               "compact":args.compact,
                               "images":"profile high/reduced normal; other views interactive" if args.compact else "all measured views"}
    keys = set()
    for manifest in manifests:
        for name in ("renderer", "before", "after", "chromium", "width", "scale", "renderer_hashes", "cases", "audit_hash"):
            if manifest[name] != combined[name]:
                raise ValueError(f"Cannot mix incompatible runs: {name}")
        expected = {(sid, tier, *case) for sid in manifest["skins"] for tier in ("D", "C", "B", "A", "S", "SS", "SSS") for case in manifest["cases"]}
        actual = {(row["skin"], row["tier"], row["mode"], row["device"], row["phase"]) for row in manifest["coverage"]}
        if actual != expected or len(manifest["coverage"]) != len(expected):
            raise ValueError("Incomplete or duplicated subset matrix")
        if set(combined["skins"]) & set(manifest["skins"]):
            raise ValueError("A skin appears in more than one subset")
        combined["skins"].update(manifest["skins"])
        combined["scenes"].update(manifest["scenes"])
        for row in manifest["coverage"]:
            if row["key"] in keys:
                raise ValueError("Duplicate comparison cell")
            keys.add(row["key"])
            published = dict(row)
            if args.compact and not (row["mode"] == "profile" and row["device"] in ("high", "reduced") and row["phase"] == "normal"):
                published.pop("images", None)
            combined["coverage"].append(published)
    shutil.copytree(args.parts[0], args.out, dirs_exist_ok=True, ignore=shutil.ignore_patterns("images") if args.compact else None)
    if args.compact:
        required = {name for row in combined["coverage"] for name in row.get("images", [])}
        (args.out/"images").mkdir(exist_ok=True)
        for name in required:
            source = next((part/name for part in args.parts if (part/name).is_file()), None)
            if source is None:
                raise ValueError(f"Missing comparison image: {name}")
            shutil.copy2(source,args.out/name)
    for part in args.parts[1:]:
        if not args.compact:
            shutil.copytree(part / "images", args.out / "images", dirs_exist_ok=True)
        for side in ("before", "after"):
            cards = part / side / "cards"
            if cards.exists():
                shutil.copytree(cards, args.out / side / "cards", dirs_exist_ok=True)
    (args.out / "manifest.js").write_text("const COMPARE=" + json.dumps(combined, ensure_ascii=False) + ";", encoding="utf-8")
    size = sum(path.stat().st_size for path in args.out.rglob("*") if path.is_file())
    if size > 16 * 1024 * 1024:
        raise ValueError(f"Package exceeds 16 MiB: {size}")
    if any(path.stat().st_size > 150 * 1024 for path in args.out.rglob("*.webp")):
        raise ValueError("A preview image exceeds 150 KiB")
    print(f"READY: {len(combined['skins'])} skins, {len(keys)} cells, {size / 1024 / 1024:.2f} MiB")


if __name__ == "__main__":
    main()
