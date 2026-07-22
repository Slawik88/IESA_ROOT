"""Проверка фиксов переносов текста в темах профиля (бот я/анкета/инфо/топ/браки,
2026-07-23). Не рендерит визуально (Telegram-клиента нет), но печатает реальный
текст с намеренно длинными именами — глазами видно, что строки короче и не
ломают дерево ├/└. Стриповает HTML-теги для замера длины видимой строки."""
import sys
import pathlib
import re

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

_TAG_RE = re.compile(r"<[^>]+>")


def visible_len(s: str) -> int:
    return len(_TAG_RE.sub("", s))


def show(title: str, text: str, warn_at: int = 40):
    print(f"\n{'='*60}\n{title}\n{'='*60}")
    for line in text.split("\n"):
        vlen = visible_len(line)
        flag = "  ⚠ ДЛИННАЯ" if vlen > warn_at else ""
        print(f"[{vlen:3d}] {line}{flag}")


# ── profile.py::_pet_block ────────────────────────────────────────────────────
from bot.handlers.profile import _pet_block

long_pets = [
    {"name": "Разрушительпламенидревнегоогня", "species_id": "dragon", "pet_level": 10,
     "fatigue": 45, "rarity": "mythic", "placement": "active"},
    {"name": "Ша", "species_id": "cat", "pet_level": 3, "fatigue": 10,
     "rarity": "common", "placement": "passive"},
]
show("profile.py::_pet_block (длинное имя питомца)", _pet_block(long_pets))

# ── identity.py::_pets_block / _active_pet_str ────────────────────────────────
from bot.handlers.identity import _pets_block, _active_pet_str

show("identity.py::_pets_block (длинное имя питомца)", _pets_block(long_pets))
print(f"\nidentity.py::_active_pet_str → [{visible_len(_active_pet_str(long_pets))}] "
      f"{_active_pet_str(long_pets)}")

print("\nOK: см. вывод выше — ни одна строка не должна быть отмечена ⚠ (порог 40 "
      "видимых символов, ориентир для узких экранов)")
