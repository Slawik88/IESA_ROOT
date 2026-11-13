"""Банк текстов «Шипперим» (S21), собранный на общем механизме bot/chat/text_banks.py.

Банк проверяет себя при импорте: уникальность после нормализации, безопасные
подстановки, длина 20–200, без ссылок и упоминаний, без стоп-слов. Повреждённый
банк падает с понятной ошибкой на старте теста, а не в чате у игрока.

Как добавить фразу: дописать в свою категорию (announce, compat_*, self_pair,
author_included, nobody, cooldown, opted_out) — проверка и тесты подхватят сами.
"""
from __future__ import annotations

from bot.chat.text_banks import TextBank, build
from bot.chat.ship_texts.announce import ANNOUNCE
from bot.chat.ship_texts.author_included import AUTHOR_INCLUDED
from bot.chat.ship_texts.compat import (
    COMPAT_0_10, COMPAT_11_25, COMPAT_26_40, COMPAT_41_55, COMPAT_56_70,
    COMPAT_71_85, COMPAT_86_95, COMPAT_96_100,
)
from bot.chat.ship_texts.cooldown import COOLDOWN
from bot.chat.ship_texts.nobody import NOBODY
from bot.chat.ship_texts.opted_out import OPTED_OUT
from bot.chat.ship_texts.self_pair import SELF_PAIR

# Пошлость и грубость (PG-13) плюс внутренние слова проекта (PLAYER_COPY, раздел 4).
# Проверка подстрочная, поэтому стоп-слова берём без коротких ложных попаданий.
STOP_WORDS = (
    "секс", "порно", "интим", "постель", "стриптиз", "оргазм", "обнаж", "голая", "голые", "голое",
    "насили", "труп", "убей", "убить", "умри", "сдохн", "дурак", "тупой", "идиот", "тварь", "мраз", "ненавиж",
    "кулдаун", "таймер", "чанк", "такт", "дроп", "лут", "баф", "дебаф", "нерф", "имба",
    "апгрейд", "прокачк", "ачивк", "кэш", "эндпоинт", "синхронизац", "сервер", "ресурс", "буст", "темп", "лимит", "лига",
)

_FIELDS = {
    "announce": ("a", "b"),
    "self_pair": ("a", "b"),
    "author_included": ("a", "b"),
    "opted_out": ("b",),
    "cooldown": ("sec",),
    "nobody": (),
    "compat_96_100": (), "compat_86_95": (), "compat_71_85": (), "compat_56_70": (),
    "compat_41_55": (), "compat_26_40": (), "compat_11_25": (), "compat_0_10": (),
}

BANK: TextBank = build(
    {
        "announce": ANNOUNCE,
        "self_pair": SELF_PAIR,
        "author_included": AUTHOR_INCLUDED,
        "opted_out": OPTED_OUT,
        "cooldown": COOLDOWN,
        "nobody": NOBODY,
        "compat_96_100": COMPAT_96_100,
        "compat_86_95": COMPAT_86_95,
        "compat_71_85": COMPAT_71_85,
        "compat_56_70": COMPAT_56_70,
        "compat_41_55": COMPAT_41_55,
        "compat_26_40": COMPAT_26_40,
        "compat_11_25": COMPAT_11_25,
        "compat_0_10": COMPAT_0_10,
    },
    _FIELDS,
    min_len=20,
    max_len=200,
    stop_words=STOP_WORDS,
)
