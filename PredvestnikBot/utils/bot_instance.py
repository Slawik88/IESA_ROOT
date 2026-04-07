# utils/bot_instance.py — глобальный хранитель экземпляра бота
# Позволяет слоям без прямого доступа к боту (database/, api/) отправлять уведомления.
from __future__ import annotations

_bot = None


def set_bot(b) -> None:
    """Вызывать один раз из main.py после создания Bot()."""
    global _bot
    _bot = b


def get_bot():
    """Вернуть текущий экземпляр Bot или None, если ещё не установлен."""
    return _bot
