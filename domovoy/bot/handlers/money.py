"""
bot/handlers/money.py — Баланс Квартиры: взносы, траты, чеки, баланс.
"""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot import cb, keyboards as kb
from bot.util import fmt_date, guard, resolve_house, safe_edit
from core.money import format_amount
from services import households, money, notify
from services import settings as settings_service
from services.money import MODE_HOUSE, MODE_PERSONAL

router = Router(name="money")

MODE_LABEL = {MODE_HOUSE: "из котла", MODE_PERSONAL: "за свои"}


async def _context(tg_id: int):
    house = await resolve_house(tg_id)
    if house is None:
        return None, None
    settings = await settings_service.house_settings(house["id"])
    return house, settings


# ── Взносы («Скинулся») ──────────────────────────────────────────────────────

async def _notify_confirmers(bot, house, settings, contribution, currency):
    """Тем, у кого право подтверждать взносы, — кнопки решения."""
    await notify.contribution_declared(
        bot, house, contribution, currency,
        markup=kb.contribution_decision_keyboard(contribution["id"]),
    )


@router.callback_query(F.data.regexp(r"^cres:(\d+):(0|1)$"))
@guard
async def resolve_contribution(cbq: CallbackQuery, state: FSMContext):
    house, settings = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    parts = cb.parse(cbq.data)
    contribution_id, confirm = int(parts[1]), parts[2] == "1"
    await households.require(house["id"], cbq.from_user.id, "confirm_contributions")
    contribution = await money.resolve_contribution(
        contribution_id, confirm, cbq.from_user.id, house_id=house["id"],
    )
    await state.clear()
    currency = settings["currency"]
    verb = "подтверждён" if confirm else "отклонён"
    await cbq.answer(f"Взнос {verb}")
    await safe_edit(cbq,
                    f"{'✅' if confirm else '❌'} Взнос "
                    f"{format_amount(contribution['amount_kop'], currency)} "
                    f"за {contribution['month']} {verb}.")
    await notify.deliver(
        cbq.bot, house, "contribution_confirmed",
        {contribution["tg_id"]: (
            f"{'✅' if confirm else '❌'} Ваш взнос "
            f"{format_amount(contribution['amount_kop'], currency)} за {contribution['month']} {verb}."
        )},
    )


# ── Баланс ───────────────────────────────────────────────────────────────────

async def render_balance(cbq: CallbackQuery) -> None:
    house, settings = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    currency = settings["currency"]
    balance = await money.pot_balance(house["id"])
    contributions = await money.pending_contributions(house["id"])
    outstanding = await money.outstanding_personal(house["id"])

    lines = [f"💰 Баланс Квартиры «{house['name']}»", "",
             f"Котел: {format_amount(balance['balance'], currency)}",
             f"Подтверждённые взносы: {format_amount(balance['confirmed_total'], currency)}",
             f"Траты из котла: {format_amount(balance['house_spent'], currency)}"]
    if balance["reimbursed"]:
        lines.append(f"Возвращено из котла: {format_amount(balance['reimbursed'], currency)}")
    if outstanding:
        lines.append("")
        lines.append("Ждут возврата из котла:")
        for row in outstanding:
            lines.append(f"  {row['display_name']}: {format_amount(row['amount_kop'], currency)}")

    can_confirm = await households.can(house["id"], cbq.from_user.id, "confirm_contributions")
    await safe_edit(cbq, "\n".join(lines), kb.balance_keyboard(len(contributions), can_confirm))


@router.callback_query(F.data == cb.balance())
@guard
async def show_balance(cbq: CallbackQuery, state: FSMContext):
    await state.clear()
    await render_balance(cbq)
    await cbq.answer()


@router.callback_query(F.data == cb.pending())
@guard
async def show_pending(cbq: CallbackQuery):
    house, settings = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await households.require(house["id"], cbq.from_user.id, "confirm_contributions")
    pending_rows = await money.pending_contributions(house["id"])
    currency = settings["currency"]
    lines = ["⏳ Взносы, ждущие подтверждения:", ""]
    for row in pending_rows:
        lines.append(f"• {row['display_name'] or '?'} — "
                     f"{format_amount(row['amount_kop'], currency)} за {row['month']}")
    await safe_edit(cbq, "\n".join(lines), kb.pending_keyboard(pending_rows, currency))
    await cbq.answer()


# ── Траты ────────────────────────────────────────────────────────────────────

async def persist_expense(
    bot, tg_id: int, data: dict, description: str, *, state: FSMContext | None = None,
) -> str:
    """Сохранить трату из накопленных шагов и разослать уведомление. Текст-итог."""
    house = await households.get_house(data["house_id"])
    settings = await settings_service.house_settings(house["id"])
    today = settings_service.house_today(settings)
    await money.add_expense(
        house["id"], tg_id, data["amount_kop"], data.get("category_id"),
        data.get("date", today), data["mode"], description, data.get("photos", []),
    )
    if state is not None:
        await state.clear()
    currency = settings["currency"]
    category_name = "—"
    if data.get("category_id"):
        categories = {c["id"]: c["name"] for c in await money.categories(house["id"])}
        category_name = categories.get(data["category_id"], "—")
    member = await households.membership(house["id"], tg_id)
    who = member["display_name"] if member else "Жилец"
    await notify.broadcast(
        bot, house, "expense_added",
        f"🧾 {who}: {format_amount(data['amount_kop'], currency)} — {category_name} "
        f"({MODE_LABEL[data['mode']]})",
        exclude_tg_ids={tg_id},
    )
    return (f"🧾 Трата сохранена: {format_amount(data['amount_kop'], currency)} — "
            f"{category_name} ({MODE_LABEL[data['mode']]}) · {data.get('date', today)}")


@router.callback_query(F.data == cb.expenses_list())
@guard
async def show_expenses(cbq: CallbackQuery, state: FSMContext):
    await state.clear()
    house, settings = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    rows = await money.recent_expenses(house["id"], 10)
    if not rows:
        await safe_edit(cbq, "Трат пока нет. Добавьте первую: «➕ Трата».", kb.back_to_menu())
        await cbq.answer()
        return
    await safe_edit(cbq, f"🧾 Последние траты ({len(rows)}):", kb.expenses_list_keyboard(rows))
    await cbq.answer()


@router.callback_query(F.data.regexp(r"^exp:(\d+)$"))
@guard
async def show_expense_card(cbq: CallbackQuery):
    house, settings = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    expense_id = int(cb.parse(cbq.data)[1])
    expense = await money.get_expense(expense_id)
    if expense is None or expense["house_id"] != house["id"]:
        await cbq.answer("Трата не найдена", show_alert=True)
        return
    currency = settings["currency"]
    photos_count = await money.photos_count(expense_id)
    is_author = expense["tg_id"] == cbq.from_user.id
    can_manage = is_author or await households.can(house["id"], cbq.from_user.id, "manage_all_expenses")
    can_reimburse = await households.can(house["id"], cbq.from_user.id, "confirm_contributions")
    reimbursed = " · возвращена" if expense["reimbursed"] else ""
    await safe_edit(cbq, (
        f"🧾 Трата от {fmt_date(expense['spent_on'])}\n"
        f"Кто: {expense['display_name'] or '?'}\n"
        f"Сумма: {format_amount(expense['amount_kop'], currency)}\n"
        f"Категория: {expense['category_name'] or '—'}\n"
        f"Тип: {MODE_LABEL[expense['mode']]}{reimbursed}\n"
        + (f"Описание: {expense['description']}\n" if expense["description"] else "")
    ), kb.expense_card_keyboard(expense, photos_count, can_manage, can_reimburse))
    await cbq.answer()


@router.callback_query(F.data.regexp(r"^exp_photos:(\d+)$"))
@guard
async def send_expense_photos(cbq: CallbackQuery):
    house, settings = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    expense_id = int(cb.parse(cbq.data)[1])
    photos = await money.expense_photos(house["id"], expense_id)
    if not photos:
        await cbq.answer("Чеков нет", show_alert=True)
        return
    for photo in photos:
        await cbq.bot.send_photo(cbq.from_user.id, photo["file_id"])
    await cbq.answer(f"Чеков: {len(photos)}")


@router.callback_query(F.data.regexp(r"^exp_reimb:(\d+)$"))
@guard
async def reimburse_expense(cbq: CallbackQuery):
    house, settings = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    expense_id = int(cb.parse(cbq.data)[1])
    await households.require(house["id"], cbq.from_user.id, "confirm_contributions")
    await money.reimburse_expense(house["id"], expense_id, cbq.from_user.id)
    await cbq.answer("Возвращено из котла")
    await show_expense_card(cbq)


@router.callback_query(F.data.regexp(r"^exp_del:(\d+)$"))
@guard
async def delete_expense(cbq: CallbackQuery, state: FSMContext):
    house, settings = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    expense_id = int(cb.parse(cbq.data)[1])
    expense = await money.get_expense(expense_id)
    if expense is None:
        await cbq.answer("Трата не найдена", show_alert=True)
        return
    is_author = expense["tg_id"] == cbq.from_user.id
    if not is_author:
        await households.require(house["id"], cbq.from_user.id, "manage_all_expenses")
    await money.delete_expense(house["id"], expense_id)
    await state.clear()
    await cbq.answer("Трата удалена")
    rows = await money.recent_expenses(house["id"], 10)
    if rows:
        await safe_edit(cbq, f"🧾 Последние траты ({len(rows)}):", kb.expenses_list_keyboard(rows))
    else:
        await safe_edit(cbq, "Трат пока нет. Добавьте первую: «➕ Трата».", kb.back_to_menu())
