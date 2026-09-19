#!/usr/bin/env python3
"""Lock mobile navigation against duplicate/overlapping browser back controls."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL = (ROOT / "FastAPI/static/app.01.js").read_text(encoding="utf-8")
CSS = (ROOT / "FastAPI/static/app.css").read_text(encoding="utf-8")


SUPPRESSED_BROWSER_BACK_PAGES = (
    "profile",
    "arena",
    "more",
    "looks",
    "questlog",
    "chests",
    "achievements-v1",
    "pets",
    "public-profile",
    "chat-tracker",
)

for page in SUPPRESSED_BROWSER_BACK_PAGES:
    assert f"'{page}'" in SHELL, page

assert "const suppressBrowserBack=[" in SHELL
assert "!btn && has && !inTg && !suppressBrowserBack" in SHELL
assert "!has || inTg || suppressBrowserBack" in SHELL

entry_action = CSS.split(".recon-entry-action {", 1)[1].split("}", 1)[0]
assert "min-height: 44px" in entry_action

print("OK: top-level/local-header pages suppress fallback back; game CTAs are 44px")
