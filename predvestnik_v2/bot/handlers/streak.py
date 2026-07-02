from aiogram import Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

from bot.filters.text_commands import TextCmd
from infrastructure.repositories import streak as streak_repo
from infrastructure.repositories import economy as eco_repo
from services.streak import (
    calc_streak_reward,
    calc_recovery_cost,
    is_recovery_valid,
)
from services.utils import format_currency
from core.constants import STREAK_BLOCK_SIZE

router = Router(name="streak_router")


class StreakRecoverCallback(CallbackData, prefix="streak_rec"):
    user_id: int
    currency: str  # "diamonds" | "mora"


def _streak_view_text(streak_row: dict) -> str:
    streak = streak_row.get("streak", 0)

    if streak == 0:
        return (
            "🔥 <b>СЕРИЯ ВХОДОВ</b>\n\n"
            "У вас ещё нет стрика.\n"
            "<i>Пишите в чат каждый день, чтобы получать ежедневные награды!</i>"
        )

    day_in_block = ((streak - 1) % STREAK_BLOCK_SIZE) + 1
    cycle = (streak - 1) // STREAK_BLOCK_SIZE
    next_reward = calc_streak_reward(streak + 1)

    filled = "🔥" * day_in_block + "⬜" * (STREAK_BLOCK_SIZE - day_in_block)
    days_to_block_end = STREAK_BLOCK_SIZE - day_in_block

    recovery_text = ""
    if streak_row.get("recovery_streak", 0) > 0 and is_recovery_valid(streak_row.get("recovery_expires")):
        old = streak_row["recovery_streak"]
        missed = streak_row["recovery_missed_days"]
        cost = calc_recovery_cost(missed)
        recovery_text = (
            f"\n\n⚠️ <b>Доступно восстановление</b>\n"
            f"Потеряли {old - streak} дней стрика (пропустили {missed} дн.)\n"
            f"Восстановить: <code>бот стрик восстановить</code>\n"
            f"<i>Стоимость: {format_currency(cost['diamonds'])} 💎 "
            f"или {format_currency(cost['mora'])} 🪙</i>"
        )

    return (
        f"🔥 <b>СЕРИЯ ВХОДОВ</b>\n\n"
        f"📅 Стрик: <b>{streak} дней</b> · Блок #{cycle + 1}\n"
        f"{filled}\n"
        f"<i>День {day_in_block} из {STREAK_BLOCK_SIZE}</i>\n\n"
        f"🎁 <b>Следующая награда:</b>\n"
        f"├ 🪙 Мора: <code>+{format_currency(next_reward['mora'])}</code>\n"
        f"└ 💎 Алмазы: <code>+{format_currency(next_reward['diamonds'])}</code>\n"
        + (f"\n🎉 До бонуса блока: <b>{days_to_block_end} дн.</b>" if days_to_block_end > 0 else "\n🎉 Сегодня <b>бонусный день блока!</b>")
        + recovery_text
    )


def _recovery_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💎 Восстановить за Алмазы",
        callback_data=StreakRecoverCallback(user_id=user_id, currency="diamonds"),
    )
    builder.button(
        text="🪙 Восстановить за Мору",
        callback_data=StreakRecoverCallback(user_id=user_id, currency="mora"),
    )
    builder.button(text="❌ Отмена", callback_data=StreakRecoverCallback(user_id=user_id, currency="cancel"))
    builder.adjust(1)
    return builder.as_markup()


@router.message(TextCmd(["стрик", "стрики", "серия", "ежедневный вход"]))
async def cmd_streak(message: types.Message, db):
    if message.chat.type == "private":
        return
    streak_row = await streak_repo.get_global_streak(db, message.from_user.id)
    await message.answer(_streak_view_text(streak_row), parse_mode="HTML")


@router.message(TextCmd(["стрик восстановить", "восстановить стрик"]))
async def cmd_streak_recover(message: types.Message, db):
    if message.chat.type == "private":
        return

    user_id = message.from_user.id
    streak_row = await streak_repo.get_global_streak(db, user_id)

    if streak_row.get("recovery_streak", 0) == 0:
        return await message.answer(
            "ℹ️ Нечего восстанавливать — штраф не применялся или уже истёк.",
            parse_mode="HTML",
        )

    if not is_recovery_valid(streak_row.get("recovery_expires")):
        return await message.answer(
            "⏰ <b>Окно восстановления истекло.</b>\n"
            "<i>Восстановление было доступно 48 часов с момента пропуска.</i>",
            parse_mode="HTML",
        )

    missed = streak_row["recovery_missed_days"]
    old_streak = streak_row["recovery_streak"]
    cost = calc_recovery_cost(missed)

    await message.answer(
        f"🔄 <b>ВОССТАНОВЛЕНИЕ СТРИКА</b>\n\n"
        f"Текущий стрик: <b>{streak_row['streak']}</b> дней\n"
        f"После восстановления: <b>{old_streak + 1}</b> дней\n"
        f"(Пропущено дней: <b>{missed}</b>)\n\n"
        f"Стоимость восстановления:\n"
        f"├ 💎 Алмазы: <code>{format_currency(cost['diamonds'])}</code>\n"
        f"└ 🪙 Мора: <code>{format_currency(cost['mora'])}</code>\n\n"
        f"<i>Выберите способ оплаты:</i>",
        reply_markup=_recovery_keyboard(user_id),
        parse_mode="HTML",
    )


@router.callback_query(StreakRecoverCallback.filter())
async def cb_streak_recover(query: types.CallbackQuery, callback_data: StreakRecoverCallback, db):
    if query.from_user.id != callback_data.user_id:
        return await query.answer("Это не ваша кнопка.", show_alert=True)

    await query.answer()

    if callback_data.currency == "cancel":
        await query.message.edit_text("❌ Восстановление отменено.")
        return

    user_id = callback_data.user_id
    streak_row = await streak_repo.get_global_streak(db, user_id)

    if streak_row.get("recovery_streak", 0) == 0:
        await query.message.edit_text("ℹ️ Нечего восстанавливать — штраф не применялся.")
        return

    if not is_recovery_valid(streak_row.get("recovery_expires")):
        await query.message.edit_text("⏰ Окно восстановления истекло.")
        return

    missed = streak_row["recovery_missed_days"]
    old_streak = streak_row["recovery_streak"]
    cost = calc_recovery_cost(missed)
    balance = await eco_repo.get_balance(db, user_id)

    if callback_data.currency == "diamonds":
        if balance["user_balance_diamonds"] < cost["diamonds"]:
            await query.message.edit_text(
                f"❌ <b>Недостаточно алмазов!</b>\n"
                f"Нужно: {format_currency(cost['diamonds'])} 💎\n"
                f"У вас: {format_currency(balance['user_balance_diamonds'])} 💎",
                parse_mode="HTML",
            )
            return
        from infrastructure.repositories.economy import spend_diamonds
        ok, _ = await spend_diamonds(db, user_id, cost["diamonds"])
    else:
        if balance["user_balance_mora"] < cost["mora"]:
            await query.message.edit_text(
                f"❌ <b>Недостаточно Моры!</b>\n"
                f"Нужно: {format_currency(cost['mora'])} 🪙\n"
                f"У вас: {format_currency(balance['user_balance_mora'])} 🪙",
                parse_mode="HTML",
            )
            return
        from infrastructure.repositories.economy import spend_mora
        ok, _ = await spend_mora(db, user_id, cost["mora"])

    if not ok:
        await query.message.edit_text("❌ Ошибка при списании. Попробуйте ещё раз.")
        return

    restored = old_streak + 1
    await streak_repo.update_global_streak_after_recovery(db, user_id, restored)
    await db.commit()

    currency_icon = "💎" if callback_data.currency == "diamonds" else "🪙"
    spent = cost["diamonds"] if callback_data.currency == "diamonds" else cost["mora"]
    await query.message.edit_text(
        f"✅ <b>Стрик восстановлен!</b>\n\n"
        f"Потрачено: {format_currency(spent)} {currency_icon}\n"
        f"Стрик: <b>{restored} дней</b> 🔥",
        parse_mode="HTML",
    )
