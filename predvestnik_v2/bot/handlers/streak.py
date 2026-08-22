"""Legacy streak record commands without currency rewards or paid recovery."""
from aiogram import Router, types
from aiogram.filters.callback_data import CallbackData

from bot.filters.text_commands import TextCmd
from bot.keyboards.cta import answer_group_only
from infrastructure.repositories import streak as streak_repo

router = Router(name="streak_router")


class StreakRecoverCallback(CallbackData, prefix="streak_rec"):
    user_id: int
    currency: str


def _streak_view_text(streak_row: dict) -> str:
    streak = int(streak_row.get("streak") or 0)
    if streak <= 0:
        return (
            "🔥 <b>РЕКОРД СЕРИИ</b>\n\n"
            "Старого рекорда пока нет. Сообщения больше не создают валюту или обязательный стрик."
        )
    return (
        "🔥 <b>РЕКОРД СТАРОЙ СЕРИИ</b>\n\n"
        f"Лучший сохранённый результат: <b>{streak} дней</b>.\n"
        "Он остаётся в профиле как история. Сообщения больше не дают Мору, Алмазы "
        "или жетоны; новая система ритма будет учитывать игровые дни без платного восстановления."
    )


@router.message(TextCmd(["стрик", "стрики", "серия", "ежедневный вход"]))
async def cmd_streak(message: types.Message, db):
    if message.chat.type == "private":
        return await answer_group_only(message)
    row = await streak_repo.get_global_streak(db, message.from_user.id)
    await message.answer(_streak_view_text(row), parse_mode="HTML")


@router.message(TextCmd(["стрик восстановить", "восстановить стрик"]))
async def cmd_streak_recover(message: types.Message, db):
    if message.chat.type == "private":
        return await answer_group_only(message)
    await message.answer(
        "Платное восстановление закрыто: старый рекорд сохранён и больше не уменьшается."
    )


@router.callback_query(StreakRecoverCallback.filter())
async def cb_streak_recover(query: types.CallbackQuery, callback_data: StreakRecoverCallback, db):
    if query.from_user.id != callback_data.user_id:
        return await query.answer("Это не ваша кнопка.", show_alert=True)
    await query.answer()
    await query.message.edit_text(
        "Платное восстановление закрыто. Сохранённый рекорд не уменьшается."
    )
