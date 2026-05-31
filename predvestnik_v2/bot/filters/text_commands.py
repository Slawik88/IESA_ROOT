import re

from aiogram.filters import BaseFilter
from aiogram.types import Message

# Алиасы команд с аргументами → подсказка правильного синтаксиса
WRONG_SYNTAX_HINTS: dict[str, str] = {
    "снять варн": "бот снять варн, @юзер [кол-во]",
    "снять пред": "бот снять варн, @юзер [кол-во]",
    "снять защиту": "бот снять защиту, @юзер",
    "убрать щит": "бот снять защиту, @юзер",
    "снять мут": "бот размут, @юзер",
    "ранг глобал": "бот ранг глобал, @юзер [0-3]",
    "глобал ранг": "бот ранг глобал, @юзер [0-3]",
    "дать ранг": "бот ранг, @юзер [0-6]",
    "выдать ранг": "бот ранг, @юзер [0-6]",
    "сет ранг": "бот ранг, @юзер [0-6]",
    "настройка щита": "бот настройка щита, [дни]",
    "щит новичка": "бот настройка щита, [дни]",
    "лимит варнов": "бот лимит варнов, [число]",
    "макс варнов": "бот лимит варнов, [число]",
    "настройка чистки": "бот настройка чистки, [ранг]",
    "ранг чистки": "бот настройка чистки, [ранг]",
    "принять связь": "бот принять связь, [код]",
    "семейный баланс": "бот общак",
    "варн": "бот варн, @юзер [причина]",
    "пред": "бот варн, @юзер [причина]",
    "предупреждение": "бот варн, @юзер [причина]",
    "заглушить": "бот мут, @юзер [10м/2ч/1д]",
    "мут": "бот мут, @юзер [10м/2ч/1д]",
    "размут": "бот размут, @юзер",
    "кик": "бот кик, @юзер",
    "выгнать": "бот кик, @юзер",
    "бан": "бот бан, @юзер [причина]",
    "заблокировать": "бот бан, @юзер [причина]",
    "разбан": "бот разбан, @юзер",
    "разблокировать": "бот разбан, @юзер",
    "иммунитет": "бот иммунитет, @юзер",
    "абсолют": "бот иммунитет, @юзер",
    "защита": "бот защита, @юзер [5д/1ч]",
    "защитить": "бот защита, @юзер [5д/1ч]",
    "ранг": "бот ранг, @юзер [0-6]",
    "брак": "бот брак, @юзер",
    "свадьба": "бот брак, @юзер",
    "роспись": "бот брак, @юзер",
    "перевод": "бот перевод, @юзер [сумма]",
    "перевести": "бот перевод, @юзер [сумма]",
    "дать": "бот перевод, @юзер [сумма]",
    "скинуть": "бот перевод, @юзер [сумма]",
    "вложить": "бот вложить, [сумма]",
    "в общак": "бот вложить, [сумма]",
    "снять": "бот снять, [сумма]",
    "из общака": "бот снять, [сумма]",
    "инфо": "бот инфо, @юзер",
    "кто": "бот инфо, @юзер",
    "досье": "бот инфо, @юзер",
    "поход": "бот поход, [2/4/6/8]",
    "экспедиция": "бот поход, [2/4/6/8]",
    "открыть": "бот открыть, [egg_id] [количество]",
}

_SORTED_WRONG_ALIASES = sorted(WRONG_SYNTAX_HINTS.keys(), key=len, reverse=True)


class WrongSyntaxCmd(BaseFilter):
    """
    Ловит «бот [известный_алиас] [что-то]» без запятой.
    Возвращает correct_usage — подсказку правильного синтаксиса.

    Пример: «бот варн @user» → correct_usage = "бот варн, @юзер [причина]"
    """
    async def __call__(self, message: Message) -> dict | bool:
        if not message.text:
            return False
        text = message.text.lower().strip()
        if not text.startswith("бот"):
            return False
        clean_text = text[3:].lstrip(" ,.").strip()
        clean_text = re.sub(r'\s*,\s*', ', ', clean_text)

        for alias in _SORTED_WRONG_ALIASES:
            # Есть пробел после алиаса, нет запятой сразу после него
            if clean_text.startswith(alias + " ") and not clean_text.startswith(alias + " ,"):
                return {"correct_usage": WRONG_SYNTAX_HINTS[alias]}
        return False


class UnknownBotCmd(BaseFilter):
    """Matches 'бот X' messages that start with 'бот' but have content after it.
    Used as a catch-all in the last router to suggest similar commands.
    Injects: bot_cmd_text (str) — the part after 'бот ', before any comma."""

    async def __call__(self, message: Message) -> dict | bool:
        if not message.text:
            return False
        text = message.text.lower().strip()
        if not text.startswith("бот"):
            return False
        rest = text[3:].lstrip(" ,.").strip()
        rest = re.sub(r'\s*,\s*', ', ', rest)
        if len(rest) < 2:
            return False
        # Take only the "command" portion (before first comma or newline)
        cmd_part = rest.split(",")[0].split("\n")[0].strip()
        return {"bot_cmd_text": cmd_part}


class TextCmd(BaseFilter):
    """
    Фильтр текстовых команд с разделителем-запятой.

    Синтаксис:
      «бот [алиас]»            — команда без аргументов (точное совпадение)
      «бот [алиас], [арги]»    — команда с аргументами (запятая = разделитель)

    Примеры:
      «бот баланс»             → text_args = ""
      «бот варн, @user спам»   → text_args = "@user спам"
      «бот чистка, 01.05-07.05 30» → text_args = "01.05-07.05 30"
      «бот чистка открыть»    → не совпадает (нет запятой) → игнорируется
    """
    def __init__(self, aliases: list[str]):
        # Сортируем от длинных к коротким — "снять варн" раньше чем "снять"
        self.aliases = sorted(aliases, key=len, reverse=True)

    async def __call__(self, message: Message) -> dict | bool:
        if not message.text:
            return False

        text = message.text.lower().strip()

        if not text.startswith("бот"):
            return False

        # Отрезаем "бот" и лишние символы перед командой
        clean_text = text[3:].lstrip(" ,.").strip()
        # Нормализуем пробелы вокруг запятой: "ранг , @юзер" → "ранг, @юзер"
        clean_text = re.sub(r'\s*,\s*', ', ', clean_text)

        for alias in self.aliases:
            # Точное совпадение — команда без аргументов
            if clean_text == alias:
                return {"text_args": ""}
            # Запятая — разделитель между командой и аргументами
            if clean_text.startswith(alias + ","):
                args = clean_text[len(alias) + 1:].strip()
                return {"text_args": args}

        return False
