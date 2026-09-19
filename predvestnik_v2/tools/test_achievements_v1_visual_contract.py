#!/usr/bin/env python3
"""Static delivery contract for the browseable mobile achievement collection."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run() -> None:
    client = (ROOT / "FastAPI/static/app.12.js").read_text(encoding="utf-8")
    css = (ROOT / "FastAPI/static/app.css").read_text(encoding="utf-8")

    for phrase in (
        "Общий путь", "Получено за уровни", "без скрытой косметики",
        "Завершения", "Активные недели", "До уровня", "Вехи", "за достижение самого уровня",
        "aria-label=\"Категории достижений\"", "role=\"progressbar\"", "role=\"status\"",
        "<h1 class=\"looks-htitle\">", "aria-label=\"Вехи:",
    ):
        assert phrase in client, phrase
    for family in ("rhythm", "minesweeper", "mafia", "chests", "pets"):
        assert f"{family}:" in client, family
    for selector in (
        ".achievement-filters", ".achievement-card", ".achievement-meter",
        ".achievement-milestone", "@media (max-width:350px)",
    ):
        assert selector in css, selector
    assert "min-height:44px" in css
    shell = (ROOT / "FastAPI/static/app.01.js").read_text(encoding="utf-8")
    assert "'achievements-v1'" in shell and "suppressBrowserBack" in shell
    assert "requestAnimationFrame" in client and "data-achievement-filter" in client
    assert "finalMilestone?.events_required" in client
    print("OK: achievements v1 filters, exact dual progress, milestones and mobile actions")


if __name__ == "__main__":
    run()
