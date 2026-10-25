"""One header for the three game pages: Rhythm and Minesweeper (casual mode) and the League (ranked mode).

The header, the «Обычный | Рейтинг» switch and the season-pass strip come from ONE piece of markup
(static/game-shell-v3.html), so switching the mode changes only the content under it.
"""
from __future__ import annotations

import os

_PARTIAL = os.path.join(os.path.dirname(__file__), "static", "game-shell-v3.html")
_GAMES = ("rhythm", "minesweeper")


def _head(*, base: str, eyebrow: str, title: str, game: str | None, mode: str | None) -> str:
    with open(_PARTIAL, encoding="utf-8") as handle:
        text = handle.read()
    attrs = f' data-game-mode="{game}" data-gmode="{mode}"' if game in _GAMES and mode in ("casual", "ranked") else ""
    return (text.replace("{{BASE}}", base).replace("{{EYEBROW}}", eyebrow).replace("{{TITLE}}", title)
            .replace("{{MODE_ATTRS}}", attrs))


def render(html: str, *, base: str, version: str, eyebrow: str, title: str, game: str | None = None, mode: str | None = None) -> str:
    """Fill a game page: its own {{GAME_HEAD}} placeholder plus {{BASE}} and {{VER}} (the content hash of the League assets)."""
    head = _head(base=base, eyebrow=eyebrow, title=title, game=game, mode=mode)
    return html.replace("{{GAME_HEAD}}", head).replace("{{BASE}}", base).replace("{{VER}}", version)
