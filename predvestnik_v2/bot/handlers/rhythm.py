"""Chat entry for the approved Rune Rhythm Mini App game.

The former chat contracts wrote progression into the retired Reconstruction
campaign. This adapter deliberately has no game-state writer: a player gets a
clear route to the current activities hub instead.
"""
from __future__ import annotations

import os

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.filters.text_commands import TextCmd
from core.miniapp_links import miniapp_url
from bot.middlewares.module_check_mw import ModuleCheckMiddleware


router = Router(name="rhythm_router")
router.message.middleware(ModuleCheckMiddleware("module_rhythm"))
router.callback_query.middleware(ModuleCheckMiddleware("module_rhythm"))
_BOT = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot").strip().lstrip("@")


def _hub_markup() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎮 Открыть Центр Предвестника", url=miniapp_url("games"))
    return builder.as_markup()


async def _open_rhythm(message: types.Message) -> None:
    await message.answer(
        "◌ <b>РИТМ</b>\n\n"
        "Бесконечный забег с рунами находится в Центре Предвестника. "
        "Там доступны обычный режим, режим аугментаций и отдельные таблицы лидеров.\n\n"
        "Старые ежедневные контракты и связанная с ними кампания сохранены в истории и больше не создают прогресс.",
        reply_markup=_hub_markup(),
        parse_mode="HTML",
    )


@router.message(Command("rhythm"))
@router.message(TextCmd(["ритм", "ритм дня", "контракт ритма", "мой контракт"]))
async def cmd_rhythm(message: types.Message) -> None:
    await _open_rhythm(message)
