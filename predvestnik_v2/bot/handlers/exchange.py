"""Fail-closed compatibility handlers for the retired Mora/Diamond exchange."""
from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData

from bot.filters.text_commands import TextCmd
from bot.keyboards.cta import answer_group_only

router = Router(name="exchange_router")


class ExchCB(CallbackData, prefix="exch"):
    action: str
    amount: float = 0.0
    user_id: int = 0


_CLOSED = (
    "💱 Прямой обмен Моры и Алмазов закрыт: у валют разные задачи. "
    "Баланс сохранён, а доступные способы получения всегда указаны рядом с наградой."
)


@router.message(TextCmd(["обмен", "конвертация", "обменять"]))
async def cmd_exchange(message: types.Message):
    if message.chat.type == "private":
        return await answer_group_only(message)
    await message.answer(_CLOSED)


@router.callback_query(ExchCB.filter())
async def cb_exchange_closed(query: types.CallbackQuery):
    await query.answer(_CLOSED, show_alert=True)
