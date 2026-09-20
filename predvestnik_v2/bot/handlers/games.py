# bot/handlers/games.py — прежние режимы со ставками закрыты. Этот адаптер
# сохраняет только безопасный возврат их зависших сессий и ведёт игрока в
# утверждённый раздел Mini App: Ритм и один новый Сапёр.
from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.filters.text_commands import TextCmd
from bot.keyboards.cta import answer_group_only
from core.miniapp_links import miniapp_url
from services.skill_games import get_active_session_summary, refund_active_sessions
from services.utils import check_callback_owner

router = Router(name="games_router")


class LegacyGameRefundCB(CallbackData, prefix="game_refund"):
    user_id: int


def _arena_games_kb(user_id: int, active_count: int) -> InlineKeyboardMarkup | None:
    rows = []
    if active_count > 0:
        rows.append([InlineKeyboardButton(
            text="↩ Вернуть старую ставку",
            callback_data=LegacyGameRefundCB(user_id=user_id).pack(),
        )])
    games_url = miniapp_url("game")
    if games_url:
        rows.append([InlineKeyboardButton(
            text="🎮 Открыть игры",
            url=games_url)])
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(TextCmd(["игры", "казино", "азарт", "кости", "монетка",
                         "числа", "угадай число", "рулетка"]))
async def cmd_games_moved(message: types.Message, db):
    if message.chat.type == "private":
        return await answer_group_only(message)
    recovery = await get_active_session_summary(db, message.from_user.id)
    recovery_text = (
        f"\n\nУ тебя осталось старых ставок: <b>{recovery['active_count']}</b>. "
        f"К возврату: <b>{recovery['refundable_mora']:g} 🪙</b>."
        if recovery["active_count"] else ""
    )
    await message.answer(
        "🎮 <b>Игры Предвестника</b>\n"
        "🔔 <b>Ритм</b> — бесконечный забег на реакцию.\n"
        "💣 <b>Сапёр</b> — логическая игра с тремя сложностями и таблицами лидеров.\n"
        f"Открой Mini App → Игра, чтобы выбрать режим.{recovery_text}",
        reply_markup=_arena_games_kb(message.from_user.id, recovery["active_count"]),
        parse_mode="HTML")


@router.callback_query(LegacyGameRefundCB.filter())
async def cb_refund_legacy_games(
    query: types.CallbackQuery, callback_data: LegacyGameRefundCB, db
):
    if not await check_callback_owner(query, callback_data.user_id):
        return
    result = await refund_active_sessions(db, query.from_user.id)
    await query.answer("Возврат выполнен." if result["count"] else "Возвращать уже нечего.")
    if query.message:
        await query.message.edit_reply_markup(reply_markup=_arena_games_kb(query.from_user.id, 0))
