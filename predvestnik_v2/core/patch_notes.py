"""Патч-ноуты в официальный канал: формат файлов, пределы и куда ведёт кнопка.

Правила для тех, кто пишет патч-ноуты (ИИ-агенты и люди): docs/PATCH_NOTES.md.
Здесь только числа и таблицы, которые читают и код, и тест формата (tools/test_patch_notes_contract.py).
"""
from __future__ import annotations

from pathlib import Path

from core.official_updates import CHAT_ID, THREAD_ID, UPDATES_URL  # noqa: F401  (одно место для адреса канала)

NOTES_DIR = Path(__file__).resolve().parents[1] / "FastAPI" / "static" / "patch-notes"
IMAGES_DIR = NOTES_DIR / "img"

# С этой даты каждая запись «Что нового» обязана попасть в патч-ноут (или в его skipped с причиной).
COVERAGE_SINCE = "2026-10-20"

KINDS = ("new", "better", "fix")
KIND_LABEL = {"new": "Новое", "better": "Улучшили", "fix": "Исправили"}

MAX_HEADLINE = 70
MAX_INTRO = 240
MAX_TITLE = 80
MAX_TEXT = 420          # видимых знаков в абзаце новинки
MAX_FIX = 170           # строка исправления
MAX_ITEMS = 8           # новинок и улучшений в одном посте
MAX_FIXES = 12
MAX_MESSAGE = 4000      # Telegram: 4096 видимых знаков в сообщении, держим запас под правки
MAX_CAPTION = 1024      # Telegram: подпись к одному фото
MAX_IMAGES = 10         # Telegram: альбом до 10 фото
FIXES_FOLD = 4          # больше исправлений — список сворачивается в раскрывающуюся цитату

IMAGE_EXT = (".png", ".jpg", ".jpeg")
IMAGE_MIN_BYTES, IMAGE_MAX_BYTES = 2_000, 9_000_000
UPLOAD_MAX_BYTES = 10_000_000
UPLOAD_MAX_SIDE = 2560
UPLOAD_MAX_PIXELS = 40_000_000

# Разметка, которую принимает Telegram (parse_mode=HTML). Всё прочее отклоняется до отправки.
ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre",
                "a", "blockquote", "tg-spoiler"}
ALLOWED_ATTRS = {"a": {"href"}, "blockquote": {"expandable"}}
LINK_SCHEMES = ("https://", "tg://")

# Кнопка под постом: ключ из патч-ноута -> (подпись, раздел Mini App для ?startapp=).
# Разделы совпадают с _handleStartParam (FastAPI/static/app.02.js).
BUTTONS = {
    "home": ("🔮 Открыть Предвестника", ""),
    "games": ("🎮 Открыть игры", "games"),
    "pass": ("🎟 Открыть пропуск", "pass"),
    "looks": ("🎨 Открыть образы", "looks"),
    "quests": ("📜 Открыть задания", "quests"),
    "pets": ("🐾 Открыть питомцев", "pets"),
    "top": ("🏆 Открыть топ", "top"),
    "family": ("🌳 Открыть мою семью", "family"),
    "inventory": ("🎒 Открыть инвентарь", "inventory"),
    "achievements": ("🏅 Открыть достижения", "achievements"),
    "zarniki": ("⚡ Открыть зарники", "zarniki"),
    "vip": ("👑 Открыть VIP", "vip"),
    "settings": ("⚙️ Открыть настройки", "settings"),
    "news": ("🗞 Что нового", "news"),
}
MAX_BUTTON_LABEL = 40

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря")
