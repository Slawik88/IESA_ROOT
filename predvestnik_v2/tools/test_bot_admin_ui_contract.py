"""Контракт админки: перекладка вкладок не должна трогать логику опасных действий и привязки JS к разметке (ADM-01).

1) Функции, от которых зависят подтверждения, баны, баланс и рассылка, не меняются: сверяется хэш их текста.
   Правите такую функцию осознанно: обновите хэш здесь и скажите об этом в PR отдельной строкой.
2) Идентификаторы и хуки, на которые опирается JS, остаются в файлах.

Запуск: python tools/test_bot_admin_ui_contract.py (ничего не нужно, ни база, ни браузер)
"""
from __future__ import annotations

import hashlib
import os
import re
import sys

STATIC = os.path.join(os.path.dirname(__file__), "..", "FastAPI", "static", "bot-admin")
# Ядро и все вынесенные файлы: пинны хэшей ищутся только в admin.js, а хуки — в любом из них,
# чтобы дробление файла не выглядело пропажей привязки.
JS = open(os.path.join(STATIC, "admin.js"), encoding="utf-8").read()
JS_ALL = "\n".join(open(os.path.join(STATIC, name), encoding="utf-8").read()
                   for name in sorted(n for n in os.listdir(STATIC) if n.startswith("admin") and n.endswith(".js")))
CSS = open(os.path.join(STATIC, "admin.css"), encoding="utf-8").read()

# имя функции -> sha1 текста (с первой строки объявления до закрывающей скобки в нулевой колонке)
PINNED = {
    "actionForm": "4a21ef700980", "runAction": "a16cc5a2fe44", "needsTypedConfirm": "02d44637f82f", "confirmLines": "a0c36bee0b8d",
    "sheet": "219efbebaf00", "bulkRun": "7208d733c384", "api": "648a2f15c38d",
}

HOOKS_JS = [  # куски разметки/селекторов, на которые опирается код
    "$('#notescard h3')", "data-mact", "data-punish", "data-cid", "data-ctitle",
]
IDS = ["bcount", "bprev", "bgo", "btest", "bhist", "pback", "psearch", "sglobal", "dgon", "dghour", "repset", "secset", "revself", "revall"]
HOOKS_CSS = ["main > .bar:first-child", ".bulkbar", ".card.picked", ".mark-tile", ".sheet-back"]


def source(name: str) -> str:
    m = re.search(rf"^(?:async )?function {name}\(.*?^\}}\n", JS, re.S | re.M)
    assert m, f"функция {name} не найдена в admin.js"
    return m.group(0)


def digest(name: str) -> str:
    return hashlib.sha1(source(name).encode("utf-8")).hexdigest()[:12]


def main() -> int:
    bad = []
    for name, pinned in PINNED.items():
        got = digest(name)
        if got != pinned:
            bad.append(f"функция {name} изменилась (хэш {got}, ожидался {pinned})")
    for hook in HOOKS_JS:
        if hook not in JS_ALL:
            bad.append(f"в файлах админки пропала привязка {hook}")
    for i in IDS:
        if f'id="{i}"' not in JS_ALL:
            bad.append(f"в файлах админки пропал элемент id={i}")
    for hook in HOOKS_CSS:
        if hook not in CSS:
            bad.append(f"в admin.css пропало правило {hook}")
    # `.card` не должен менять роль «просто группа блоков»: у него остаётся прежнее определение без фона и рамки
    m = re.search(r"^\.card \{([^}]*)\}", CSS, re.M)
    if not m or "background" in m.group(1) or "box-shadow" in m.group(1):
        bad.append("правило .card получило фон или рамку: на нём держатся жалобы, панель выбора и рассылка, используйте .section")
    for line in bad:
        print("✗", line)
    if not bad:
        print("OK: логика опасных действий и хуки админки не тронуты")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--print" in sys.argv:
        for n in PINNED:
            print(n, digest(n))
        sys.exit(0)
    sys.exit(main())
