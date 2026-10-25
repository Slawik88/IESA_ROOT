#!/usr/bin/env python3
"""Motion contract of the League page (docs/MOTION_V3.md): one-shot, transform/opacity only, everything off without motion.

CSS: no `infinite`, @keyframes and transitions touch only transform/opacity, no polygon clip-path or blend modes, and the
reduced-motion / no-fx / low switches are present.  JS: every Web Animation (`play(el, [...])`, `el.animate([...])`)
moves only transform/opacity; the one exception is the Rhythm window timer arc (stroke-dashoffset, as the profile ring).
The Rhythm rune must become readable within 120 ms.  Files stay within 300 lines.
Run: python3 tools/test_league_motion_contract.py
"""
from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "FastAPI" / "static"
CSS = ("league-demo.css", "league-games.css", "league-pass.css", "casual-games-v3.css")
JS = ("league-art.js", "league-fx.js", "league-demo.js", "league-ladder.js", "league-result.js", "league-mines.js",
      "league-rhythm-fx.js", "league-rhythm.js", "league-pass.js", "game-shell-v3.js", "game-mode-v3.js")
MOVING = {"transform", "opacity"}


def blocks(text: str, start: int) -> str:
    """Text of the brace block that opens at or after `start`."""
    i = text.index("{", start)
    depth = 0
    for j in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[j], 0)
        if depth == 0:
            return text[i + 1:j]
    raise AssertionError("unbalanced braces")


def css() -> None:
    for name in CSS:
        text = re.sub(r"/\*.*?\*/", "", (STATIC / name).read_text(encoding="utf-8"), flags=re.S)
        assert "infinite" not in text, f"{name}: бесконечная анимация"
        assert not re.search(r"clip-path:\s*(polygon|circle|ellipse|path)\(|mix-blend-mode:\s*(?!normal)", text), f"{name}: дорогой проход отрисовки"
        for match in re.finditer(r"@keyframes\s+([\w-]+)", text):
            props = set(re.findall(r"([\w-]+)\s*:", blocks(text, match.end())))
            assert props <= MOVING, f"{name}: @keyframes {match.group(1)} двигает {props - MOVING}"
        for value in re.findall(r"transition:\s*([^;}]+)", text):
            if value.strip().startswith("none"):
                continue
            for part in value.split(","):
                assert part.split()[0] in MOVING, f"{name}: transition {part.strip()}"
    demo = (STATIC / "league-demo.css").read_text(encoding="utf-8")
    for switch in ("prefers-reduced-motion: reduce", "body.no-fx", "body.lg-low"):
        assert switch in demo, f"нет выключателя движения: {switch}"


def js() -> None:
    seen = 0
    for name in JS:
        text = (STATIC / name).read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 300, f"{name}: длиннее 300 строк"
        # play(элемент, [кадры], …) из league-fx.js и el.animate([кадры], …)
        for match in re.finditer(r"\bplay\((?:[^,\[\]();]|\([^()]*\))+,\s*(?=\[)|\.animate\(\s*(?=\[)", text):
            body = text[match.end():]
            seen += 1
            depth, end = 0, 0
            for j, ch in enumerate(body):
                depth += {"[": 1, "]": -1}.get(ch, 0)
                if depth == 0:
                    end = j
                    break
            keys = set(re.findall(r"[{,]\s*(\w+)\s*:", body[:end])) - {"offset"}
            allowed = MOVING | ({"strokeDashoffset"} if name == "league-rhythm-fx.js" else set())
            assert keys <= allowed, f"{name}: анимируется {keys - allowed}"
    assert seen >= 25, f"проверено всего {seen} анимаций: выражение поиска сломалось"
    view = (STATIC / "league-rhythm-fx.js").read_text(encoding="utf-8")
    appear = re.search(r"function rune\(.*?\{duration: (\d+)", view, flags=re.S)
    assert appear and int(appear.group(1)) <= 120, "руна Ритма должна читаться не позже чем через 120 мс"
    css_rules = (STATIC / "league-fx.js").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css_rules and "no-fx" in css_rules and "'low'" in css_rules, "бюджет движения в league-fx.js"


if __name__ == "__main__":
    css()
    js()
    print("PASS league motion contract: one-shot, transform/opacity only, switches present, rune readable ≤120 ms, files ≤300 lines")
