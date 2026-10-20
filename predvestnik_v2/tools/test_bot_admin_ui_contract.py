"""Контракт админки 3.0: каркас страницы, адреса экранов и привязки, на которых держатся безопасность и разделы.

Поведение опасных действий проверяет tools/test_admin_safety.js (настоящие функции в vm), а путь в браузере —
tools/test_bot_admin_ui_flows.py. Здесь — то, что легко потерять при правке разметки:
1) каркас index.html (шапка, док, шторка, тост) и подключение всех файлов;
2) у каждого раздела с сервера есть экран (route) — иначе пункт меню ведёт в пустоту;
3) ключевые хуки безопасности в коде (request_id на окно, ввод ID, «Далее» у опасного, блок двойного нажатия);
4) правила интерфейса из docs/MINIAPP_DESIGN_RULES.md, которые проверяются текстом: зоны нажатия, без inline-обработчиков.

Запуск: python tools/test_bot_admin_ui_contract.py (ничего не нужно, ни база, ни браузер)
"""
from __future__ import annotations

import os
import re
import sys

STATIC = os.path.join(os.path.dirname(__file__), "..", "FastAPI", "static", "bot-admin")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")


def read(name: str) -> str:
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


def main() -> int:
    from FastAPI.routers.bot_admin.page import _TYPES
    from FastAPI.routers.bot_admin.auth import SECTIONS
    bad = []
    html = read("index.html")
    js = {n: read(n) for n in _TYPES if n.endswith(".js")}
    JS = "\n".join(js.values())
    css = read("admin.css")

    for hook in ('id="main"', 'id="tabs"', 'id="sheet"', 'id="toast"', 'id="ttl"', 'id="hback"', 'id="hsearch"'):
        if hook not in html:
            bad.append(f"в index.html пропал каркас {hook}")
    # Экран на каждый раздел сервера и на главную
    routes = set(re.findall(r"route\('([\w/:]+)'", JS))
    for key in [*SECTIONS, "home", "mychats", "player/:id", "chat/:id"]:
        if key not in routes:
            bad.append(f"нет экрана для раздела «{key}»")
    hooks = {
        "один request_id на открытое действие": "ctx = {...ctx, _rid: newRid()}",
        "сумма и VIP уходят с request_id": "request_id: ctx._rid",
        "ввод ID для самого опасного": "if (typedId !== String(ctx.id))",
        "опасное идёт через «Далее»": "label: danger ? 'Далее' : 'Выполнить'",
        "второй тап по кнопке шторки ничего не делает": "if (btn.disabled) return;",
        "рассылка: ключ на окно подтверждения": "const rid = newRid();",
        "рассылка: опрос только пока экран открыт": "if (!ctx.alive()) return;",
        "лимит выбора игроков": "PICK.ids.size < BULK_MAX",
        "жалоба: бан из жалобы с итогом": "openSheet({title: CONFIRM_TITLE.ban",
        "личный образ: лимит 1": "$v('#fmax').value = 1",
        "владельцу нет поиска по базе": "if (!ME || ME.owner) return;",
        "/me всегда при старте (кука разработчика)": "ME = await api('/me')",
        "назад Telegram — один обработчик": "TG.BackButton.onClick(goBack)",
        "выключение всего бота — красное подтверждение": "input.dataset.k === 'all' || input.dataset.k === 'site'",
    }
    for what, needle in hooks.items():
        if needle not in JS:
            bad.append(f"пропала проверка: {what} ({needle})")
    if re.search(r"""\son(click|change|input)=["']""", JS):
        bad.append("inline-обработчик onclick=\"…\" в разметке: используйте data-on и on(view, {...})")
    if re.search(r"(?<![\w.])confirm\(\s*[`'\"]", JS):
        bad.append("системный confirm(): используйте ask() — шторку в стиле админки")
    for rule, needle in ((".btn {", "min-height: 44px"), (".ib {", "height: 44px"), (".row {", "min-height: 60px")):
        m = re.search(re.escape(rule) + r"[^}]*", css)
        if not m or needle not in m.group(0):
            bad.append(f"в admin.css у {rule} нет {needle} (зона нажатия)")
    if ':root[data-theme="light"]' not in css or "prefers-reduced-motion" not in css:
        bad.append("в admin.css нет светлой темы или уважения к prefers-reduced-motion")
    for line in bad:
        print("✗", line)
    if not bad:
        print("OK: каркас, экраны разделов, хуки безопасности и правила интерфейса на месте")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
