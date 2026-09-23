#!/usr/bin/env python3
"""Release Telegram profile stays compact and legacy renderers stay absent."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
release = (ROOT / "bot" / "handlers" / "release_profile.py").read_text(encoding="utf-8")

assert "safe_html" in release
assert "Центр активностей" in release
assert "Доступные активности: Ритм, Сапёр и Мафия" in release
for retired in ("combat_power", "_pet_block", "_pets_block", "_active_pet_str"):
    assert retired not in release
for path in (
    ROOT / "bot" / "handlers" / "profile.py",
    ROOT / "bot" / "handlers" / "identity.py",
):
    assert not path.exists(), path

print("OK: compact Telegram profile is canonical; legacy text renderers are absent")
