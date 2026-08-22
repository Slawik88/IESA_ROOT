# bot/handlers/games.py — R7: старое казино (кости/монетка/угадай число/рулетка,
# чисто удача) снесено. Заменено скилл-играми в мини-аппе (Сапёр/Сейф/Алхимия —
# реальный навык вместо голого рандома). Хендлер оставлен только как
# редирект в единственную новую игровую петлю — Разлом колокола.
import os

from aiogram import Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.filters.text_commands import TextCmd
from bot.middlewares.module_check_mw import ModuleCheckMiddleware
from bot.keyboards.cta import answer_group_only

router = Router(name="games_router")
router.message.middleware(ModuleCheckMiddleware("module_games"))


def _arena_games_kb() -> InlineKeyboardMarkup | None:
    bot_username = os.getenv("BOT_USERNAME", "")
    if not bot_username:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="🔔 Открыть Разлом",
        url=f"https://t.me/{bot_username}?startapp=game")]])


@router.message(TextCmd(["игры", "казино", "азарт", "кости", "монетка",
                         "числа", "угадай число", "рулетка"]))
async def cmd_games_moved(message: types.Message):
    if message.chat.type == "private":
        return await answer_group_only(message)
    await message.answer(
        "🎲 <b>Старое казино ушло в историю.</b>\n"
        "Кости, монетка, Сапёр, Сейф и Алхимия со ставками закрыты. "
        "Основная игра теперь одна: 🔔 Разлом колокола — важен правильный выбор руны, а не спам.\n"
        "Открой мини-апп → Игра → Разлом.",
        reply_markup=_arena_games_kb(), parse_mode="HTML")
