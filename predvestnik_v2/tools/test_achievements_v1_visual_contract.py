#!/usr/bin/env python3
"""Static delivery contract for the achievements screen: compact rows, one bar each, details and milestones in a sheet."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run() -> None:
    client = (ROOT / "FastAPI/static/app.12.js").read_text(encoding="utf-8")
    css = (ROOT / "FastAPI/static/achievements-v3.css").read_text(encoding="utf-8")

    for phrase in (
        "v3Head('Достижения'", "получено", "без скрытой косметики", "Как растут достижения",
        "'Завершения'", "'Активные недели'", "Вехи · Мора за сам уровень", "role=\"tablist\"",
        "aria-label=\"Категории достижений\"", "data-achievement-filter", "achievementsV1TabKey",
    ):
        assert phrase in client, phrase
    for family in ("rhythm", "minesweeper", "mafia", "chests", "pets"):
        assert f"{family}:" in client, family
    # Level needs both conditions: the single row bar follows the lagging one; finished paths fall back to the last milestone.
    assert "Math.min(achievementPct(events, t.events), achievementPct(weeks, t.weeks))" in client
    assert "final?.events_required" in client
    # Chat-bot achievements live in the same tab under their own filter, with their own load error.
    assert "'/achievements-v1/chat'" in client and "achievementChatItem" in client and "['chat', 'Чат']" in client
    assert "Достижения чата не загрузились" in client
    # One accent: bars are ink on track, no accent in the screen's own stylesheet.
    assert "--v3-acc" not in css and "background: var(--v3-ink)" in css
    assert "min-height: 60px" in css
    shell = (ROOT / "FastAPI/static/app.01.js").read_text(encoding="utf-8")
    assert "'achievements-v1'" in shell and "suppressBrowserBack" in shell
    main = (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")
    index = (ROOT / "FastAPI/static/index.html").read_text(encoding="utf-8")
    assert '"achievements-v3.css"' in main and "achievements-v3.css" in index
    print("OK: achievements rows, single lagging bar, sheet with both meters and milestones, chat filter")


if __name__ == "__main__":
    run()
