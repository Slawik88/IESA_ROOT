"""Как пост патч-ноута уходит в тему канала: всегда одним постом, без «простыни» из нескольких сообщений.

Без картинок — сообщение с кнопкой. Одно фото — фото с подписью и кнопкой. Несколько — альбом с подписью
под ним; у альбома в Telegram кнопок нет, поэтому вместо кнопки в конце подписи ссылка «👉 Открыть …».
Только если подпись не влезла в 1024 знака (создатель сильно удлинил текст), текст идёт отдельным сообщением.
Если Telegram отказал на втором шаге, уже отправленные фото удаляются, чтобы в канале не висел обрывок.
"""
from __future__ import annotations

import html

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


def _url(button: dict | None) -> str:
    return miniapp_url(rules.BUTTONS[button["key"]][1]) if button else ""


def album_caption(text: str, button: dict | None) -> str:
    url = _url(button)
    return f'{text}\n\n👉 <a href="{url}">{html.escape(button["label"], quote=False)}</a>' if url else text


def plan(text: str, images: int, button: dict | None = None) -> str:
    if not images:
        return "text"
    if images == 1:
        return "photo" if fmt.tg_len(fmt.plain_text(text)) <= rules.MAX_CAPTION else "photos_then_text"
    return "album" if fmt.tg_len(fmt.plain_text(album_caption(text, button))) <= rules.MAX_CAPTION else "photos_then_text"


def describe(text: str, images: int, button: dict | None = None) -> str:
    """Для предпросмотра: что именно появится в канале."""
    kind = plan(text, images, button)
    if kind == "text":
        return "Один пост: текст и кнопка."
    if kind == "photo":
        return "Один пост: фото, под ним текст и кнопка."
    if kind == "album":
        return f"Один пост: альбом из {images} фото, под ним текст и ссылка на приложение (у альбомов нет кнопок)."
    return "Текст длиннее 1024 знаков и не влезает подписью: фото уйдут отдельно, текст следом. Лучше сократите."


def keyboard(button: dict | None) -> InlineKeyboardMarkup | None:
    url = _url(button)
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


async def _steps(bot, row: dict, files: list, sent: list[int]) -> None:
    text, button = row["text_html"], row["button"]
    common = {"message_thread_id": rules.THREAD_ID, "parse_mode": "HTML"}
    kind = plan(text, len(files), button)
    if kind == "photo":
        sent.append((await bot.send_photo(rules.CHAT_ID, files[0], caption=text, reply_markup=keyboard(button), **common)).message_id)
        return
    if kind == "album":
        media = [InputMediaPhoto(media=f, **({"caption": album_caption(text, button), "parse_mode": "HTML"} if not i else {}))
                 for i, f in enumerate(files)]
        sent.extend(m.message_id for m in await bot.send_media_group(rules.CHAT_ID, media, message_thread_id=rules.THREAD_ID))
        return
    if len(files) == 1:
        sent.append((await bot.send_photo(rules.CHAT_ID, files[0], message_thread_id=rules.THREAD_ID)).message_id)
    elif files:
        album = await bot.send_media_group(rules.CHAT_ID, [InputMediaPhoto(media=f) for f in files],
                                           message_thread_id=rules.THREAD_ID)
        sent.extend(m.message_id for m in album)
    sent.append((await bot.send_message(rules.CHAT_ID, text, reply_markup=keyboard(button),
                                        link_preview_options=LinkPreviewOptions(is_disabled=True), **common)).message_id)


async def send(bot, db, row: dict) -> list[int]:
    """Отправить пост; вернуть id всех сообщений. Rejected — ничего не осталось, DeliveryUnknown — нужна сверка."""
    files, sent = await _files(db, row), []
    try:
        await _steps(bot, row, files, sent)
    except _DEFINITE as error:
        if sent and not await _cleanup(bot, sent):
            raise DeliveryUnknown(sent) from None
        raise service.Rejected(_reason(error)) from None
    except Exception:
        raise DeliveryUnknown(sent) from None
    return sent


def _reason(error) -> str:
    return str(getattr(error, "message", "") or type(error).__name__)[:160]


async def edit_sent(bot, row: dict, text: str) -> None:
    """Исправить текст уже опубликованного поста (опечатка). Фото и состав поста не меняются."""
    ids, n, button = row["message_ids"], len(row["images"]), row["button"]
    kind = plan(row["text_html"], n, button)
    if plan(text, n, button) != kind:
        raise service.PatchNoteError("Новый текст меняет вид поста (не влезает подписью). Сократите его.")
    try:
        if kind == "text" or kind == "photos_then_text":
            await bot.edit_message_text(text=text, chat_id=rules.CHAT_ID, message_id=ids[-1], parse_mode="HTML",
                                        reply_markup=keyboard(button), link_preview_options=LinkPreviewOptions(is_disabled=True))
        elif kind == "photo":
            await bot.edit_message_caption(chat_id=rules.CHAT_ID, message_id=ids[0], caption=text, parse_mode="HTML",
                                           reply_markup=keyboard(button))
        else:
            await bot.edit_message_caption(chat_id=rules.CHAT_ID, message_id=ids[0], caption=album_caption(text, button),
                                           parse_mode="HTML")
    except _DEFINITE as error:
        if "not modified" in _reason(error):
            return
        raise service.PatchNoteError(f"Telegram не принял правку: {_reason(error)}. В канале остался прежний текст.") from None
    except Exception:
        raise service.PatchNoteError("Ответ Telegram не получен. Откройте пост в канале: правка могла пройти.") from None
