"""
bot/handlers/money.py — Баланс Квартиры: взносы, траты, чеки, баланс.
"""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import cb, keyboards as kb
from bot.states import Contribution, Expense
from bot.util import fmt_date, guard, resolve_house, safe_edit
from core.constants import MAX_PHOTOS_PER_EXPENSE
from core.money import format_amount, parse_amount
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

@router.callback_query(F.data == cb.contribute())
@guard
async def start_contribution(cbq: CallbackQuery, state: FSMContext):
    house, settings = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await state.set_state(Contribution.waiting_amount)
    await cbq.message.answer(
        f"Сколько вы скинулись в Баланс Квартиры «{house['name']}»?\n"
        f"Например: 3000 или 2500,50",
    )
    await cbq.answer()


@router.message(Contribution.waiting_amount, F.text)
@guard
async def contribution_amount(message: Message, state: FSMContext):
    house, settings = await _context(message.from_user.id)
    if house is None:
        await state.clear()
        await message.answer("Сначала выберите дом через /start")
        return
    amount_kop = parse_amount(message.text)
    today = settings_service.house_today(settings)
    contribution = await money.declare_contribution(house["id"], message.from_user.id,
                                                    amount_kop, today)
    await state.clear()

    currency = settings["currency"]
    await message.answer(
        f"💸 Взнос {format_amount(amount_kop, currency)} за {today[:7]} заявлен.\n"
        f"Владелец дома подтвердит получение — уведомлю здесь.",
        reply_markup=kb.back_to_menu(),
    )
    await _notify_confirmers(message.bot, house, settings, contribution, currency)


async def _notify_confirmers(bot, house, settings, contribution, currency):
    """Тем, у кого право подтверждать взносы, — кнопки решения."""
    declarer = await households.membership(house["id"], contribution["tg_id"])
    who = declarer["display_name"] if declarer else "Жилец"
    texts = {}
    for member in await households.members(house["id"]):
        if await households.can(house["id"], member["tg_id"], "confirm_contributions"):
            texts[member["tg_id"]] = (
                f"💸 {who} заявил взнос {format_amount(contribution['amount_kop'], currency)} "
                f"за {contribution['month']}. Подтверждаете?"
            )
    if not texts:
        return
    await notify.deliver(
        bot, house, "contribution_declared", texts,
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
    contribution = await money.resolve_contribution(contribution_id, confirm, cbq.from_user.id)
    await state.clear()
    currency = settings["currency"]
    verb = "подтверждён" if confirm else "отклонён"
    await cbq.answer(f"Взнос {verb}")
    try:
        await cbq.message.edit_text(
            f"{'✅' if confirm else '❌'} Взнос {format_amount(contribution['amount_kop'], currency)} "
            f"за {contribution['month']} {verb}.")
    except Exception:
        pass
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

@router.callback_query(F.data == cb.expense_new())
@guard
async def start_expense(cbq: CallbackQuery, state: FSMContext):
    house, settings = await _context(cbq.from_user.id)
    if house is None:
        await cbq.answer("Сначала выберите дом", show_alert=True)
        return
    await state.set_state(Expense.waiting_amount)
    await state.update_data(house_id=house["id"], photos=[])
    await cbq.message.answer("Сколько потратили? Например: 1200 или 350,50")
    await cbq.answer()


@router.message(Expense.waiting_amount, F.text)
@guard
async def expense_amount(message: Message, state: FSMContext):
    amount_kop = parse_amount(message.text)
    await state.update_data(amount_kop=amount_kop)
    await state.set_state(Expense.choosing_category)
    house, settings = await _context(message.from_user.id)
    categories = await money.categories(house["id"])
    await message.answer("Категория траты:", reply_markup=kb.categories_keyboard(categories))


@router.callback_query(Expense.choosing_category, F.data.regexp(r"^exp_cat:(\d+)$"))
@guard
async def expense_category(cbq: CallbackQuery, state: FSMContext):
    category_id = int(cb.parse(cbq.data)[1])
    await state.update_data(category_id=category_id)
    await state.set_state(Expense.choosing_mode)
    await cbq.message.edit_text("Откуда деньги?", reply_markup=kb.mode_keyboard())
    await cbq.answer()


@router.callback_query(Expense.choosing_mode, F.data.regexp(r"^exp_mode:(house|personal)$"))
@guard
async def expense_mode(cbq: CallbackQuery, state: FSMContext):
    mode = cb.parse(cbq.data)[1]
    await state.update_data(mode=mode)
    await state.set_state(Expense.waiting_photos)
    hint = ("Пришлите фото чека (можно несколько).\n"
            "Когда всё — «Готово, сохранить»." if mode == MODE_HOUSE else
            "Пришлите фото чека (можно несколько) — по нему вернём деньги из котла.\n"
            "Когда всё — «Готово, сохранить».")
    await cbq.message.edit_text(hint, reply_markup=kb.photos_keyboard())
    await cbq.answer()


@router.message(Expense.waiting_photos, F.photo)
@guard
async def expense_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = list(data.get("photos", []))
    if len(photos) >= MAX_PHOTOS_PER_EXPENSE:
        await message.answer("Чеков достаточно — нажмите «Готово, сохранить».")
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(f"📸 Чек {len(photos)} принят. Можно прислать ещё или нажать «Готово».")


@router.message(Expense.waiting_photos)
@guard
async def expense_photo_other(message: Message, state: FSMContext):
    await message.answer("Жду фото чека. Если чека нет — нажмите «Готово, сохранить».")


@router.callback_query(Expense.waiting_photos, F.data == cb.expense_photos_done())
@guard
async def expense_photos_done(cbq: CallbackQuery, state: FSMContext):
    await state.set_state(Expense.waiting_description)
    await cbq.message.answer(
        "Добавить описание? Напишите текст — или нажмите «Без описания».",
        reply_markup=kb.description_keyboard(),
    )
    await cbq.answer()


@router.message(Expense.waiting_description, F.text)
@guard
async def expense_description(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    summary = await persist_expense(message.bot, message.from_user.id, data, message.text)
    await message.answer(summary, reply_markup=kb.back_to_menu())


@router.callback_query(Expense.waiting_description, F.data == cb.expense_desc_skip())
@guard
async def expense_description_skip(cbq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    summary = await persist_expense(cbq.bot, cbq.from_user.id, data, "")
    await cbq.message.answer(summary, reply_markup=kb.back_to_menu())
    await cbq.answer("Сохранено")


async def persist_expense(bot, tg_id: int, data: dict, description: str) -> str:
    """Сохранить трату из накопленных шагов и разослать уведомление. Текст-итог."""
    house = await households.get_house(data["house_id"])
    settings = await settings_service.house_settings(house["id"])
    today = settings_service.house_today(settings)
    await money.add_expense(
        house["id"], tg_id, data["amount_kop"], data.get("category_id"),
        today, data["mode"], description, data.get("photos", []),
    )
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
            f"{category_name} ({MODE_LABEL[data['mode']]})")


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
    photos = await money.expense_photos(expense_id)
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
