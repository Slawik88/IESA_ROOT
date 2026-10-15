#!/usr/bin/env python3
"""Releases must change identity even with buildpack-normalized timestamps."""
from pathlib import Path
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from FastAPI.static_assets import asset_version


def main():
    names = ("index.html", "app.js", "theme.css")
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for name in names:
            (directory / name).write_text("release a\n", encoding="utf-8")
            os.utime(directory / name, (315532801, 315532801))
        original = asset_version(directory, names)
        # A markup-, JS- or CSS-only release of the same size/time must be new.
        for name in names:
            path = directory / name
            path.write_text("release b\n", encoding="utf-8")
            os.utime(path, (315532801, 315532801))
            assert asset_version(directory, names) != original, name
            path.write_text("release a\n", encoding="utf-8")
            os.utime(path, (1792050000, 1792050000))
            assert asset_version(directory, names) == original, name
        assert asset_version(directory, reversed(names)) != original
        # Newline normalization matches the actual text responses across hosts.
        (directory / "app.js").write_bytes(b"release a\r\n")
        assert asset_version(directory, names) == original
    print("Static release identity: OK")


if __name__ == "__main__":
    main()
