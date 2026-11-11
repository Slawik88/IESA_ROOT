"""Настройки бота в переписках (S29a): что бот может делать у игрока. Чистые правила, без базы.

Каждая функция — переключатель. Значение для переписки берётся по цепочке: настройка этой переписки → общая настройка
игрока → значение по умолчанию. Всё здесь запускается только командой самого игрока (кнопкой пульта или «бот …»),
поэтому по умолчанию включено; то, что бот делал бы сам (автоответчик, S29c), по умолчанию выключено.
"""
from __future__ import annotations

from typing import Final

# ключ → (кнопка в настройках, пояснение, по умолчанию)
FEATURES: Final[dict[str, tuple[str, str, bool]]] = {
    "games": ("🎮 Игры вдвоём", "камень-ножницы-бумага, кубики, крестики-нолики", True),
    "bets": ("🎰 Игры на жетоны", "ставка жетонами казино; без неё играете просто так", True),
    "fun": ("🎲 Кубик, выбор, совместимость", "«бот кубик», «бот выбери», «бот совместимость»", True),
    "card": ("🪪 Визитка", "твоя карточка с образом, без кошелька", True),
    "invite": ("🔮 Позвать в игру", "ссылка на Предвестник для друга", True),
    "transfer": ("💸 Переводы", "заявка в личку, деньги уходят после твоего нажатия", True),
    "footer": ("🔖 Кнопка «Предвестник» на карточках", "друг может открыть игру из карточки", True),
}
ORDER: Final = tuple(FEATURES)

# Что игрок «предлагает» собеседнику: такие карточки не отправляются тому, кто нажал «🙅 Не предлагать мне».
OFFER_ACTIONS: Final = frozenset({"games", "invite", "compat"})

# Функции, которые администрация может выключить отдельно в «Функции» (кроме общего «Бизнес-режима»).
ADMIN_SWITCHES: Final[dict[str, str]] = {"games": "business:games", "bets": "business:bets"}

# Действия пульта → функция, которая их разрешает.
ACTION_FEATURE: Final[dict[str, str]] = {
    "games": "games", "dice": "fun", "choose": "fun", "compat": "fun", "card": "card", "invite": "invite", "transfer": "transfer",
}


def default(key: str) -> bool:
    return FEATURES[key][2]


def resolve(key: str, chat_value: bool | None, global_value: bool | None) -> bool:
    """Переписка → общие → по умолчанию."""
    if chat_value is not None:
        return chat_value
    if global_value is not None:
        return global_value
    return default(key)


def next_chat_value(current: bool | None) -> bool | None:
    """Кнопка в настройках одной переписки ходит по кругу: как в общих → включено → выключено → как в общих."""
    return True if current is None else False if current else None


def order_by_use(actions: list[str], uses: dict[str, int]) -> list[str]:
    """Частые действия пульта — первыми; при равенстве — исходный порядок."""
    return sorted(actions, key=lambda a: (-int(uses.get(a, 0)), actions.index(a)))
