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

# Пост короткий: каждый пункт — одна строка «эмодзи название — суть», весь пост влезает подписью под одно фото.
MAX_HEADLINE = 50
MAX_INTRO = 110         # необязательная строка под заголовком
MAX_TITLE = 45          # название пункта
MAX_TEXT = 120          # суть пункта: одно предложение, максимум два
MAX_FIX = 80            # строка исправления
MAX_SENTENCES = 2
MAX_ITEMS = 4           # новинок и улучшений в одном посте; больше — делите на два дня или объединяйте
MAX_FIXES = 5
MAX_MESSAGE = 990       # видимых знаков: подпись к фото в Telegram — 1024, запас под ссылку на приложение
MAX_CAPTION = 1024      # Telegram: подпись к фото или альбому
MAX_IMAGES = 10         # Telegram: альбом до 10 фото
FIXES_FOLD = 3          # больше исправлений — список сворачивается в раскрывающуюся цитату

# Слова разработчика, которых игрок не понимает. Нашлось в тексте поста — тест и админка не пропустят.
JARGON = (r"api", r"sql", r"json", r"бэкенд\w*", r"бекенд\w*", r"фронт\w*", r"эндпоинт\w*", r"рефактор\w*",
          r"кэш\w*", r"кеш\w*", r"деплой\w*", r"миграци\w*", r"сервер\w*", r"websocket\w*", r"баг\w*",
          r"хотфикс\w*", r"транзакци\w*", r"идемпотент\w*", r"база данных", r"базе данных", r"бд", r"логи",
          r"логов", r"запрос\w* к", r"оптимизаци\w*", r"асинхрон\w*", r"флаг модул\w*")

IMAGE_MIN_SIDE, IMAGE_MAX_RATIO = 320, 3.0     # скриншот читается в ленте; Telegram сам режет слишком вытянутые
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
    "exchange": ("📈 Открыть биржу", "exchange"),
}
MAX_BUTTON_LABEL = 40

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря")
