"""Страница админки и её файлы: версия в адресах считается по содержимому, кеш не «вечный».

Раньше версия брала время изменения файлов, на хостинге оно не менялось от выкладки к выкладке, а файлы отдавались
с «immutable» на год: Telegram держал самую первую админку при свежей странице (экран «Загрузка…» без нижней панели).

Запуск: python tools/test_bot_admin_page.py (база не нужна)
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from FastAPI.routers.bot_admin import page  # noqa: E402

REAL_DIR = page._DIR


def write(directory, **files):
    for name, body in files.items():
        path = os.path.join(directory, name.replace("_", "."))
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        os.utime(path, (315532801, 315532801))   # время файлов одинаковое, как после сборки на хостинге


def asset(name, if_none_match=None):
    headers = {"if-none-match": if_none_match} if if_none_match else {}
    return asyncio.run(page.admin_asset(name, SimpleNamespace(headers=headers)))


def version_in_page():
    versions = set(re.findall(r"\?v=([0-9a-f]+)", page._PAGE))
    assert len(versions) == 1, versions
    return versions.pop()


def main():
    scripts = [n for n in page._TYPES if n.endswith(".js")]
    index = '<link href="{{BASE}}/bot-admin/admin.css?v={{VER}}"/>' + "".join(f'<script src="{{{{BASE}}}}/bot-admin/{n}?v={{{{VER}}}}"></script>' for n in scripts)
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, index_html=index, admin_css="body{}", **{n: f"console.log('{n}')" for n in scripts})
        page.load(tmp)
        first = version_in_page()
        assert "{{" not in page._PAGE

        # Новая выкладка с тем же временем файлов: версия обязана смениться, иначе Telegram возьмёт старое из кеша
        write(tmp, admin_js="console.log(2)")
        page.load(tmp)
        second = version_in_page()
        assert second != first, "версия не меняется при новом содержимом"
        write(tmp, admin_css="body{color:red}")
        page.load(tmp)
        assert version_in_page() not in (first, second), "правка стилей не меняет версию"
        third = version_in_page()
        write(tmp, **{"admin-lists.js": "console.log('lists2')"})
        page.load(tmp)
        assert version_in_page() not in (first, second, third), "правка вынесенного раздела не меняет версию"
        # то же содержимое — та же версия (кеш работает)
        page.load(tmp)
        again = version_in_page()
        page.load(tmp)
        assert version_in_page() == again

    page.load(REAL_DIR)
    ver = version_in_page()
    assert len(ver) >= 12

    # Страница не кешируется, файлы проверяются по ETag и не «вечные»
    response = asyncio.run(page.admin_page())
    assert response.headers["cache-control"] == "no-store"
    # Каждый файл из _TYPES подключён в index.html в том же порядке (ядро первым, старт последним)
    real_index = open(os.path.join(REAL_DIR, "index.html"), encoding="utf-8").read()
    order = re.findall(r'/bot-admin/(admin[\w-]*\.js)\?v=', real_index)
    assert order == [n for n in page._TYPES if n.endswith(".js")], order
    assert order[0] == "admin.js" and order[-1] == "admin-boot.js"
    for name in page._TYPES:
        media = "css" if name.endswith(".css") else "javascript"
        assert f"/bot-admin/{name}?v={ver}" in page._PAGE, name
        res = asset(name)
        assert res.status_code == 200 and media in res.media_type and res.body, name
        cache = res.headers["cache-control"]
        assert "immutable" not in cache and "max-age" not in cache and "no-cache" in cache, cache
        etag = res.headers["etag"]
        assert etag.startswith('"') and etag.endswith('"')
        # Файл не менялся: 304 без тела (и за «слабым» ETag прокси)
        for sent in (etag, "W/" + etag, f'"other", {etag}'):
            res = asset(name, sent)
            assert res.status_code == 304 and not res.body, (name, sent)
        # Файл изменился: полный ответ
        assert asset(name, '"stale"').status_code == 200
    assert asset("secret.py").status_code == 404 and asset("..").status_code == 404

    # В отданной странице нет несобранных меток и обязательный каркас на месте (нижняя панель скрыта до загрузки разделов)
    assert "{{" not in page._PAGE and 'id="tabs"' in page._PAGE and 'id="main"' in page._PAGE

    # Тема: по умолчанию как в Telegram, светлая и тёмная выбираются вручную, тема применяется до отрисовки без мигания
    js = open(os.path.join(REAL_DIR, "admin.js"), encoding="utf-8").read()   # тема — в ядре
    css = open(os.path.join(REAL_DIR, "admin.css"), encoding="utf-8").read()
    assert "PREFS.get('theme', 'auto')" in js and "TG.onEvent('themeChanged'" in js and "data-theme-pick" in js
    assert "TG.platform !== 'unknown'" in js, "вне Telegram SDK всегда говорит «светлая»: его схему нельзя брать вслепую"
    assert ':root[data-theme="light"]' in css and "color-scheme: light" in css
    assert "dataset.theme" in page._PAGE and page._PAGE.index("dataset.theme") < page._PAGE.index("admin.css"), "тема выбирается до загрузки стилей"
    print("OK: admin page versions follow content, assets revalidate by ETag, theme follows Telegram")


main()
