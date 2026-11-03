"""Файлы в личный чат жильца: в Mini App сохранить файл на телефон ненадёжно, а чат с ботом работает везде."""
import asyncio

from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import BufferedInputFile
from loguru import logger

from core.constants import FILE_SEND_TIMEOUT_S
from services.households import DomainError


async def send_to_chat(bot, actor: int, content: bytes, filename: str, caption: str) -> dict:
    if bot is None:
        raise DomainError("Отправка в чат сейчас недоступна. Скачайте файл на устройство.")
    try:
        async with asyncio.timeout(FILE_SEND_TIMEOUT_S):
            await bot.send_document(actor, BufferedInputFile(content, filename=filename), caption=caption)
            username = (await bot.me()).username
    except TelegramForbiddenError as exc:
        raise DomainError("Бот не может написать вам в личку. Откройте чат с ботом, нажмите «Запустить» "
                          "и повторите.") from exc
    except (TelegramAPIError, OSError, TimeoutError) as exc:
        logger.warning("Файл не ушёл в личный чат: {}", type(exc).__name__)
        raise DomainError("Не удалось отправить файл в чат. Попробуйте ещё раз.") from exc
    return {"sent": True, "bot": username, "link": f"https://t.me/{username}"}
