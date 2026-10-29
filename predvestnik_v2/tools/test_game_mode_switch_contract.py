#!/usr/bin/env python3
"""«Обычный | Рейтинг» внутри игры (game-mode-v3.js): один переключатель и одна шапка на страницах Ритма, Сапёра и Лиги, плавный переход, без вкладки Лиги.

Run: PYTHONPATH=. python3 tools/test_game_mode_switch_contract.py
"""
import re
from pathlib import Path

from FastAPI import game_shell

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "FastAPI" / "static"
read = lambda name: (STATIC / name).read_text(encoding="utf-8")   # noqa: E731

switch, shell_js, shell_html = read("game-mode-v3.js"), read("game-shell-v3.js"), read("game-shell-v3.html")
assert "location.replace(" in switch, "смена режима заменяет страницу: «назад» ведёт в меню игр, а не по кругу режимов"
assert "data-gmode=" in switch and "data-mode=" not in switch, "страницы игр вешают обработчики на все [data-mode] (флаг, старт забега)"
assert "/league-demo/api/access" in switch and "pv_league_access" in switch, "переключатель виден только тем, кому Лига открыта"
assert "'/league?game=rhythm'" in switch and "'/league?game=minesweeper'" in switch and "'/rhythm-v2'" in switch and "'/minesweeper'" in switch

# Плавность: уход содержимого в сторону режима, приход с той же стороны, соседняя страница подгружена заранее, шапка не мигает
assert "gm-leaving" in switch and "gm-to-ranked" in switch and "pv_mode_dir" in switch and 'rel = \'prefetch\'' in switch.replace('"', "'"), "уход, направление и подгрузка"
assert "pv_mode_dir" in shell_html and "dataset.gm" in shell_html, "направление прихода читается до первой отрисовки"
demo_css = read("league-demo.css")
assert "@view-transition { navigation: auto; }" in demo_css, "шапка, переключатель и полоска держатся на месте между страницами"
for name in ("lg-hero", "lg-mode", "lg-strip"):
    assert f"view-transition-name: {name}" in demo_css, name
assert "gm-out-left" in demo_css and "gm-in-right" in demo_css and "html[data-gm=" in demo_css
assert "transition: color" not in demo_css, "движение Лиги — только transform и opacity"

# Одна шапка на три страницы
sample = {}
for page, game, mode, title in (("rhythm-v2.html", "rhythm", "casual", "Ритм"), ("minesweeper-v2.html", "minesweeper", "casual", "Сапёр"), ("league-demo.html", None, None, "Рейтинг")):
    html = read(page)
    assert html.count("{{GAME_HEAD}}") == 1, f"{page}: общая шапка"
    for old in ("lg-hero", "gmode-host", 'id="lg-strip"'):
        assert old not in html, f"{page}: {old} живёт только в game-shell-v3.html"
    done = game_shell.render(html, base="", version="v", eyebrow="Сезон", title=title, game=game, mode=mode)
    assert "{{" not in done, page
    if game:
        assert f'data-game-mode="{game}" data-gmode="casual" hidden' in done, f"{page}: место переключателя"
    end = '<button type="button" class="lgs" id="lg-strip" hidden></button>'
    head = done[done.index("<script>try{var d="):done.index(end) + len(end)]
    sample[page] = re.sub(r'(<h1 id="lg-title"[^>]*>)[^<]*|data-game-mode="\w+" data-gmode="\w+" ', r"\1", head)
assert len(set(sample.values())) == 1, "шапка, переключатель и полоска одинаковы на всех трёх страницах"
for page, script in (("rhythm-v2.html", "/static/rhythm-v2.js"), ("minesweeper-v2.html", "/static/minesweeper-v2.js")):
    html = read(page)
    order = [html.index(x) for x in ("league-demo/league-art.js", "league-demo/league-fx.js", "league-demo/game-mode-v3.js", "league-demo/game-shell-v3.js", script)]
    assert order == sorted(order), f"{page}: общие файлы грузятся до игры"
rhythm = read("rhythm-v2.html")
assert rhythm.index('id="intro"') < rhythm.index('id="run"'), "в Ритме переключатель над экранами; во время забега его прячет lg-playing"
assert ".lg-playing :is(.gmode-host, .lgs) { display: none; }" in demo_css, "во время забега и уровня переключатель и Пропуск скрыты"
assert "'lg-playing'" in read("rhythm-v2.js"), "обычный Ритм прячет их так же, как рейтинг"

main = (ROOT / "FastAPI" / "main.py").read_text(encoding="utf-8")
router = (ROOT / "FastAPI" / "routers" / "league_v1.py").read_text(encoding="utf-8")
for asset in ("game-mode-v3.js", "game-shell-v3.js", "casual-games-v3.css"):
    assert f'"{asset}": _' in router and asset in router[router.index("CASUAL_PAGE_ASSETS"):], f"{asset} раздаёт роутер Лиги и предзагружает офлайн-кэш"
assert "CASUAL_PAGE_ASSETS" in main and "game_shell.render(" in main and "league_v1_router.ASSET_VERSION" in main, "страницы обычного режима берут вид Лиги"
assert '@app.get("/static/game-mode-v3.js")' not in main, "переключатель раздаётся одним путём — вместе с Лигой"

league_js = read("league-demo.js")
assert "lg-tabs" not in read("league-demo.html") and "lg-tabs" not in league_js, "вкладок Сапёр/Ритм/Пропуск больше нет"
assert "GameMode.mount(mode, {game: state.view, mode: 'ranked', known: true})" in league_js
assert "GameMode.mount(mode, {game: state.view, mode: 'ranked'})" in league_js, "переключатель рисуется из памяти до ответа сервера"
assert "document.documentElement.dataset.theme = 'dark';" in league_js, "Лига тёмная, как меню и игры: без вспышки при переключении"
assert "window.GameShell" in league_js and "Shell().paintStrip" in league_js, "полоска и дни до конца — общий код"

hub = read("app.04.js")
assert "_gameMode('rhythm')==='ranked'?'/league?game=rhythm':'/rhythm-v2'" in hub
assert "_gameMode('minesweeper')==='ranked'?'/league?game=minesweeper':'/minesweeper'" in hub
assert "leaveForGame('/league#pass')" in hub and "<b>Пропуск сезона</b>" in hub, "в меню одна карточка — Пропуск, с возвратом в исходный экран"
assert "localStorage.setItem('pv_league_access'" in hub
print("OK: one «Обычный | Рейтинг» switch and one header in Rhythm, Minesweeper and the League; smooth hand-over; the menu opens the last mode")
