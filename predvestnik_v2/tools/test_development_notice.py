#!/usr/bin/env python3
"""The active-development notice must be present in both public entry points."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    index = (ROOT / "FastAPI/static/index.html").read_text(encoding="utf-8")
    start_handler = (ROOT / "bot/handlers/payments.py").read_text(encoding="utf-8")
    assert 'class="development-notice"' in index
    assert "Предвестник в активной разработке" in index
    assert "Предвестник находится в активной разработке" in start_handler
    print("OK: public Mini App and /start disclose active development")


if __name__ == "__main__":
    main()
