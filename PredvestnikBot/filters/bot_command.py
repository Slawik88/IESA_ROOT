from aiogram.filters import BaseFilter
from aiogram.types import Message


class BotCommand(BaseFilter):
    """
    Совпадает с текстовыми сообщениями вида 'бот <команда>' или 'бот <команда> <аргументы>'.
    Не зависит от регистра. Возвращает {'cmd_args': str} при совпадении.
    """

    def __init__(self, *commands: str):
        self.commands = [c.lower() for c in commands]

    async def __call__(self, message: Message) -> bool | dict:
        if not message.text:
            return False

        text = message.text.strip()
        text_lower = text.lower()

        for cmd in self.commands:
            prefix = f"бот {cmd}"
            if text_lower == prefix:
                return {"cmd_args": ""}
            if text_lower.startswith(prefix + " "):
                return {"cmd_args": text[len(prefix) + 1:].strip()}

        return False


class PlainCommand(BaseFilter):
    """
    Совпадает с текстовыми сообщениями БЕЗ префикса 'бот'.
    Используется для коротких команд-действий: пни, обними, лизни и т.д.
    Возвращает {'cmd_args': str} при совпадении.
    """

    def __init__(self, *commands: str):
        self.commands = [c.lower() for c in commands]

    async def __call__(self, message: Message) -> bool | dict:
        if not message.text:
            return False

        text = message.text.strip()
        text_lower = text.lower()

        for cmd in self.commands:
            if text_lower == cmd:
                return {"cmd_args": ""}
            if text_lower.startswith(cmd + " "):
                return {"cmd_args": text[len(cmd) + 1:].strip()}

        return False
