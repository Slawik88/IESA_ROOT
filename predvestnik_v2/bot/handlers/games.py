# bot/handlers/games.py — R7: старое казино (кости/монетка/угадай число/рулетка,
# чисто удача) снесено. Заменено скилл-играми в мини-аппе (Сапёр/Сейф/Алхимия —
# реальный навык вместо голого рандома). Хендлер оставлен только как
# web-редирект со старых текстовых команд — сам роутер в чат-модуле больше
# не считает ставки (services/games.py удалён вместе с FastAPI/routers/games.py).
import os

from aiogram import Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.filters.text_commands import TextCmd
from bot.middlewares.module_check_mw import ModuleCheckMiddleware

router = Router(name="games_router")
router.message.middleware(ModuleCheckMiddleware("module_games"))


def _arena_games_kb() -> InlineKeyboardMarkup | None:
    bot_username = os.getenv("BOT_USERNAME", "")
    if not bot_username:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="🎮 Открыть Игры",
        url=f"https://t.me/{bot_username}?startapp=games")]])


@router.message(TextCmd(["игры", "казино", "азарт", "кости", "монетка",
                         "числа", "угадай число", "рулетка"]))
async def cmd_games_moved(message: types.Message):
    if message.chat.type == "private":
        return
    await message.answer(
        "🎲 <b>Старое казино ушло в историю.</b>\n"
        "Кости/монетка/число/рулетка были чистой удачей — вместо них теперь "
        "скилл-игры: 💣 Теневой Сапёр, 🔐 Взлом сейфа и ⚗️ Алхимия "
        "(merge-2048 на время). Выигрыш решает мастерство, а не рандом.\n"
        "Всё это — в мини-аппе, Арена → Игры.",
        reply_markup=_arena_games_kb(), parse_mode="HTML")
