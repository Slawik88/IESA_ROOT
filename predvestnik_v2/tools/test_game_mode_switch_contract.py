#!/usr/bin/env python3
"""«Обычный | Рейтинг» внутри игры (game-mode-v3.js): один переключатель на страницах Ритма, Сапёра и Лиги, без вкладки Лиги.

Run: PYTHONPATH=. python3 tools/test_game_mode_switch_contract.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "FastAPI" / "static"
read = lambda name: (STATIC / name).read_text(encoding="utf-8")   # noqa: E731

switch = read("game-mode-v3.js")
assert "location.replace(" in switch, "смена режима заменяет страницу: «назад» ведёт в меню игр, а не по кругу режимов"
assert "data-gmode=" in switch and "data-mode=" not in switch, "страницы игр вешают обработчики на все [data-mode] (флаг, старт забега)"
assert "/league-demo/api/access" in switch and "pv_league_access" in switch, "переключатель виден только тем, кому Лига открыта"
assert "'/league?game=rhythm'" in switch and "'/league?game=minesweeper'" in switch and "'/rhythm-v2'" in switch and "'/minesweeper'" in switch

for page, game, script in (("rhythm-v2.html", "rhythm", "rhythm-v2.js"), ("minesweeper-v2.html", "minesweeper", "minesweeper-v2.js")):
    html = read(page)
    assert f'data-game-mode="{game}" data-gmode="casual" hidden' in html, f"{page}: место переключателя"
    assert html.index("/static/game-mode-v3.js") < html.index(f"/static/{script}"), f"{page}: переключатель грузится до игры"
rhythm = read("rhythm-v2.html")
assert rhythm.index('data-game-mode="rhythm"') > rhythm.index('id="intro"') and rhythm.index('data-game-mode="rhythm"') < rhythm.index('id="countdown"'), \
    "в Ритме переключатель на экране до забега: во время забега его не видно"

main = (ROOT / "FastAPI" / "main.py").read_text(encoding="utf-8")
assert '"game-mode-v3.js")' in main and '@app.get("/static/game-mode-v3.js")' in main, "файл раздаётся, версия и офлайн-кэш (_GAME_BOARD_ASSETS)"

league_html, league_js = read("league-demo.html"), read("league-demo.js")
router = (ROOT / "FastAPI" / "routers" / "league_v1.py").read_text(encoding="utf-8")
assert '"game-mode-v3.js": _JS' in router and "league-demo/game-mode-v3.js" in league_html
assert "lg-tabs" not in league_html and "lg-tabs" not in league_js, "вкладок Сапёр/Ритм/Пропуск больше нет"
assert 'id="lg-mode"' in league_html and 'id="lg-strip"' in league_html
assert "GameMode.mount(mode, {game: state.view, mode: 'ranked', known: true})" in league_js
assert "if (!state.me) return;" in league_js.split("function render(")[1].split("strip();")[0], "переключатель — только после ответа сервера"
assert ".lg-playing :is(.gmode-host, .lgs) { display: none; }" in read("league-demo.css"), "во время уровня переключатель и Пропуск скрыты"
assert "document.documentElement.dataset.theme = 'dark';" in league_js, "Лига тёмная, как меню и игры: без вспышки при переключении"

hub = read("app.04.js")
assert "_gameMode('rhythm')==='ranked'?'/league?game=rhythm':'/rhythm-v2'" in hub
assert "_gameMode('minesweeper')==='ranked'?'/league?game=minesweeper':'/minesweeper'" in hub
assert "location.href=BASE+'/league#pass'" in hub and "<b>Пропуск сезона</b>" in hub, "в меню одна карточка — Пропуск"
assert "localStorage.setItem('pv_league_access'" in hub
print("OK: one «Обычный | Рейтинг» switch in Rhythm, Minesweeper and the League; the menu opens the last mode; no League tabs")
