"""Как пост патч-ноута уходит в тему канала.

Без картинок — одно сообщение. Одна картинка и короткий текст (до 1024 знаков) — фото с подписью.
Иначе сначала фото (одно или альбом до 10), следом текст с кнопкой: у альбома в Telegram кнопок нет.
Если Telegram отказал на втором шаге, уже отправленные фото удаляются, чтобы в канале не висел обрывок.
"""
from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import (BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto,
                           LinkPreviewOptions)
from loguru import logger

from core import patch_notes as rules
from core.miniapp_links import miniapp_url
from services import patch_notes as service
from services import patch_notes_format as fmt

_DEFINITE = (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter)


class DeliveryUnknown(Exception):
    def __init__(self, message_ids: list[int]) -> None:
        super().__init__("delivery unknown")
        self.message_ids = message_ids


def plan(text: str, images: int) -> str:
    if not images:
        return "text"
    if images == 1 and fmt.tg_len(fmt.plain_text(text)) <= rules.MAX_CAPTION:
        return "photo"
    return "photos_then_text"


def describe(text: str, images: int) -> str:
    """Для предпросмотра: что именно появится в канале."""
    kind = plan(text, images)
    if kind == "text":
        return "Одно сообщение с текстом и кнопкой."
    if kind == "photo":
        return "Одно фото, под ним текст и кнопка."
    photos = "фото" if images == 1 else f"альбом из {images} фото"
    return f"Сначала {photos}, сразу следом текст с кнопкой (текст длиннее 1024 знаков или фото несколько)."


def keyboard(button: dict | None) -> InlineKeyboardMarkup | None:
    if not button:
        return None
    url = miniapp_url(rules.BUTTONS[button["key"]][1])
    if not url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=button["label"], url=url)]])


async def _files(db, row: dict) -> list[BufferedInputFile]:
    out = []
    for index, image in enumerate(row["images"]):
        data, mime = await service.image_bytes(db, row["note_id"], image)
        out.append(BufferedInputFile(data, filename=f"patch-{index + 1}.{'png' if mime == 'image/png' else 'jpg'}"))
    return out


async def _cleanup(bot, message_ids: list[int]) -> bool:
    try:
        return bool(await bot.delete_messages(rules.CHAT_ID, message_ids))
    except Exception as error:
        logger.warning("patch note cleanup failed: {}", type(error).__name__)
        return False


async def _steps(bot, text: str, files: list, markup, sent: list[int]) -> None:
    common = {"message_thread_id": rules.THREAD_ID, "parse_mode": "HTML"}
    kind = plan(text, len(files))
    if kind == "photo":
        sent.append((await bot.send_photo(rules.CHAT_ID, files[0], caption=text, reply_markup=markup, **common)).message_id)
        return
    if len(files) == 1:
        sent.append((await bot.send_photo(rules.CHAT_ID, files[0], message_thread_id=rules.THREAD_ID)).message_id)
    elif files:
        album = await bot.send_media_group(rules.CHAT_ID, [InputMediaPhoto(media=f) for f in files],
                                           message_thread_id=rules.THREAD_ID)
        sent.extend(m.message_id for m in album)
    sent.append((await bot.send_message(rules.CHAT_ID, text, reply_markup=markup,
                                        link_preview_options=LinkPreviewOptions(is_disabled=True), **common)).message_id)


async def send(bot, db, row: dict) -> list[int]:
    """Отправить пост; вернуть id всех сообщений. Rejected — ничего не осталось, DeliveryUnknown — нужна сверка."""
    files, sent = await _files(db, row), []
    try:
        await _steps(bot, row["text_html"], files, keyboard(row["button"]), sent)
    except _DEFINITE as error:
        if sent and not await _cleanup(bot, sent):
            raise DeliveryUnknown(sent) from None
        reason = str(getattr(error, "message", "") or type(error).__name__)[:160]
        raise service.Rejected(reason) from None
    except Exception:
        raise DeliveryUnknown(sent) from None
    return sent
