"""Банк текстов «Моя статья» (S22) на общем механизме bot/chat/text_banks.py.

Две части банка:
- BANK — шаблонные категории (подводки, приговоры, повтор, пауза, выключение,
  служебные), проверяются text_banks.build при импорте;
- ARTICLES + DESCRIPTIONS — пары «номер статьи → пародийная расшифровка»,
  проверяются tools/test_article_texts.py (белый список, уникальность, граница).

Как добавить фразу: дописать в свою категорию — тесты подхватят сами.
Граница контента (см. файл сессии S22): sexual-темы и всё с несовершеннолетними
запрещены, списки корней живут в tools/test_article_texts.py.
"""
from __future__ import annotations

from bot.chat.article_texts.articles import ARTICLES, BY_NUMBER
from bot.chat.article_texts.cooldown import COOLDOWN
from bot.chat.article_texts.descriptions import DESCRIPTIONS
from bot.chat.article_texts.disabled import DISABLED
from bot.chat.article_texts.intro import INTRO
from bot.chat.article_texts.repeat import REPEAT
from bot.chat.article_texts.service import SERVICE
from bot.chat.article_texts.verdict import VERDICT
from bot.chat.text_banks import TextBank, build

# Пошлость и грубость (13+) плюс жаргон PLAYER_COPY и формулировки, выдающие
# текст за настоящий правовой документ. Проверка подстрочная, поэтому стоп-слова
# без коротких ложных попаданий.
STOP_WORDS = (
    "секс", "порно", "интим", "постель", "эротик", "стриптиз", "оргазм", "обнаж",
    "изнасил", "растлен", "педофил", "суицид", "самоубийств", "повесил", "геноцид",
    "бля", "хуй", "пизд", "еба", "ёб", "сука", "мраз", "ненавиж",
    "кулдаун", "таймер", "чанк", "такт", "дроп", "лут", "баф", "дебаф", "нерф", "имба",
    "апгрейд", "прокачк", "ачивк", "кэш", "эндпоинт", "синхронизац", "сервер", "ресурс", "буст", "темп", "лимит", "лига",
    "ук рф", "уголовный кодекс", "уголовного кодекса", "согласно ст", "вы обязаны",
    "лет тюрьмы", "лет лишения", "год тюрьмы", "смертная казнь",
)

_FIELDS = {
    "intro": (), "verdict": (), "repeat": (), "service": (),
    "cooldown": ("sec",), "disabled": (),
}

BANK: TextBank = build(
    {
        "intro": INTRO,
        "verdict": VERDICT,
        "repeat": REPEAT,
        "cooldown": COOLDOWN,
        "disabled": DISABLED,
        "service": SERVICE,
    },
    _FIELDS,
    min_len=20,
    max_len=200,
    stop_words=STOP_WORDS,
)
