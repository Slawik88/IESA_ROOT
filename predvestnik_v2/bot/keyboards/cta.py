# bot/keyboards/cta.py — единые CTA «куда дальше» (UX_AUDIT Б1/Б2/Б4/Б6/Б14/Б15).
#
# Одна политика для команд, живущих в группе: в ЛС бот НЕ молчит, а говорит это
# прямо и даёт две кнопки — добавить бота в группу (?startgroup) и открыть
# мини-апп (?startapp). До этого по кодовой базе было ~60 молчаливых return
# и шесть разных формулировок «только в группах».
import os

from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

_BOT = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot")

ADD_TO_GROUP_URL = f"https://t.me/{_BOT}?startgroup=true"
MINIAPP_URL = f"https://t.me/{_BOT}?startapp"

GROUP_ONLY_TEXT = (
    "🌘 Эта команда живёт в <b>группе</b> — там идёт игра.\n\n"
    "Что можно прямо сейчас:\n"
    "➕ добавить бота в свою группу — и играть там\n"
    "🌐 или открыть мини-апп: профиль, магазин, Казарма и бои работают и отсюда"
)


def dm_cta_kb() -> types.InlineKeyboardMarkup:
    """Кнопки «➕ в группу» + «🌐 мини-апп» — для ЛС."""
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить бота в группу", url=ADD_TO_GROUP_URL)
    b.button(text="🌐 Открыть мини-апп", url=MINIAPP_URL)
    b.adjust(1)
    return b.as_markup()


async def answer_group_only(message: types.Message) -> None:
    """Единый ответ на группо-команду, написанную в ЛС (вместо молчания)."""
    await message.answer(GROUP_ONLY_TEXT, reply_markup=dm_cta_kb(), parse_mode="HTML")
