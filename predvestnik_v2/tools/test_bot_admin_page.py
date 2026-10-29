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
    index = ('<link href="{{BASE}}/bot-admin/admin.css?v={{VER}}"/><script src="{{BASE}}/bot-admin/admin.js?v={{VER}}"></script>'
             '<script src="{{BASE}}/bot-admin/admin-lists.js?v={{VER}}"></script><script src="{{BASE}}/bot-admin/admin-boot.js?v={{VER}}"></script>')
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, index_html=index, admin_js="console.log(1)", admin_css="body{}",
              **{**{name: "" for name in page._TYPES if name not in ("admin.js", "admin.css")},   # каждый файл страницы (их добавляют сессии)
                 "admin-lists.js": "console.log('lists')", "admin-boot.js": "console.log('boot')", "guide-admin.json": "{}"})
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
    for name, media in (("admin.js", "javascript"), ("admin-lists.js", "javascript"),
                        ("admin-boot.js", "javascript"), ("admin.css", "css")):
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

    # S11: единые исходники Mini App, тема образа и строгий вариант вместо собственной палитры.
    js = open(os.path.join(REAL_DIR, "admin-look.js"), encoding="utf-8").read()
    assert "PREFS.get('admin.look', 'own')" in js and 'adminThemeFallback' in js
    assert 'data-look="strict"' in js and 'data-look="own"' in js
    assert page._SHARED["appearance-core.js"] == "../app.20.js"
    assert page._SHARED["shell-v3.css"] == "../shell-v3.css"
    assert "shell-v3.css" in page._PAGE and "admin-look.js" in page._PAGE
    print("OK: admin assets ETag, shared appearance and theme switch")


if __name__ == "__main__":
    main()
