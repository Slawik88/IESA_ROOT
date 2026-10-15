"""Stable release identity for the text assets served by the Mini App."""
from hashlib import sha256
from pathlib import Path
from collections.abc import Iterable


def asset_version(directory: str | Path, names: Iterable[str]) -> str:
    """Hash delivered contents in order, independent of buildpack file times."""
    digest = sha256()
    for name in dict.fromkeys(names):
        # Match _read_static's newline handling on Windows and Linux.
        content = (Path(directory) / name).read_text(encoding="utf-8").encode("utf-8")
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()[:20]
