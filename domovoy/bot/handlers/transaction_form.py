"""Одна карточка новой операции: быстрый ввод, правка полей и подтверждение."""
import secrets
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import cb, keyboards as kb
from bot.handlers.money import _notify_confirmers, persist_expense
from bot.states import TransactionForm
from bot.util import guard, safe_edit
from core.constants import MAX_DESCRIPTION_LEN, MAX_PHOTOS_PER_EXPENSE
from core.money import format_amount, parse_amount
from services import households, money, settings
from services.households import DomainError
from services.transaction_dates import parse_date, parse_month

router = Router(name="transaction_form")


async def _draft(state: FSMContext, actor: int) -> tuple[dict, dict]:
    data = await state.get_data()
    if not data.get("house_id") or not data.get("kind"):
        raise DomainError("Черновик устарел. Начните операцию заново.")
    await households.require_member(data["house_id"], actor)
    return data, await settings.house_settings(data["house_id"])


async def _review(event: CallbackQuery | Message, state: FSMContext):
    data, values = await _draft(state, event.from_user.id)
    await state.set_state(TransactionForm.review)
    house = await households.get_house(data["house_id"])
    title = "Трата" if data["kind"] == "expense" else "Взнос"
    lines = [f"{title} · {house['name']}", "", f"Сумма: {format_amount(data['amount_kop'], values['currency'])}",
             f"Дата: {data['date']}"]
    if data["kind"] == "expense":
        categories = {row["id"]: row["name"] for row in await money.categories(data["house_id"])}
        lines += [f"Категория: {categories.get(data.get('category_id'), 'Без категории')}",
                  "Оплата: " + ("из общего котла" if data["mode"] == "house" else "за свои, ждёт возврата"),
                  f"Описание: {data.get('description') or '—'}", f"Чеков: {len(data.get('photos', []))}"]
    else:
        lines += [f"За месяц: {data['month']}", "После сохранения: " + (
            "ожидает подтверждения" if values["confirm_contributions"] else "сразу зачислится в котёл")]
    lines += ["", "Проверьте запись. Любое поле можно изменить кнопкой ниже."]
    markup = kb.transaction_review_keyboard(data["kind"], data["token"])
    if isinstance(event, CallbackQuery):
        await safe_edit(event, "\n".join(lines), markup)
    else:
        await event.answer("\n".join(lines), reply_markup=markup)


@router.callback_query(F.data.in_({cb.expense_new(), cb.contribute()}))
@guard
async def start_transaction(event: CallbackQuery, state: FSMContext):
    from bot.util import resolve_house

    house = await resolve_house(event.from_user.id)
    if house is None:
        raise DomainError("Сначала выберите дом через /start")
    values = await settings.house_settings(house["id"])
    today = settings.house_today(values)
    kind = "expense" if event.data == cb.expense_new() else "contribution"
    await state.clear()
    await state.set_state(TransactionForm.amount)
    await state.update_data(house_id=house["id"], kind=kind, date=today, month=today[:7],
                            mode="house", category_id=None, description="", photos=[], token=secrets.token_hex(4))
    await safe_edit(event, ("Сколько потратили?" if kind == "expense" else "Сколько внесли?") +
                    f"\nДом: {house['name']}\nНапример: 1200 или 350,50.\n"
                    "Затем можно выбрать прошлую дату и проверить запись.", kb.transaction_cancel_keyboard())
    await event.answer()


@router.message(TransactionForm.amount, F.text)
@guard
async def amount_entered(message: Message, state: FSMContext):
    await _draft(state, message.from_user.id)
    await state.update_data(amount_kop=parse_amount(message.text))
    await _review(message, state)


@router.callback_query(
    TransactionForm.review, F.data.regexp(r"^tx:(amount|date|month|category|mode|description|photos)$"),
)
@guard
async def edit_field(event: CallbackQuery, state: FSMContext):
    data, _ = await _draft(state, event.from_user.id)
    field = cb.parse(event.data)[1]
    if field in ("category", "mode", "description", "photos") and data["kind"] != "expense":
        raise DomainError("Это поле доступно только у траты")
    if field == "mode":
        await state.update_data(mode="personal" if data["mode"] == "house" else "house")
        await _review(event, state)
    elif field == "category":
        await state.set_state(TransactionForm.category)
        await safe_edit(event, "Выберите категорию:", kb.transaction_categories_keyboard(
            await money.categories(data["house_id"])))
    elif field == "date":
        await state.set_state(TransactionForm.date)
        await safe_edit(event, "Когда была операция?\nВыберите день или напишите дату: 25.10.2026.",
                        kb.transaction_date_keyboard())
    else:
        next_state = {"amount": TransactionForm.amount, "month": TransactionForm.month,
                      "description": TransactionForm.description, "photos": TransactionForm.photos}[field]
        await state.set_state(next_state)
        prompts = {"amount": "Введите новую сумму:", "month": "За какой месяц взнос? Например: 2026-10.",
                   "description": "Напишите описание (до 200 символов). «—» — убрать описание.",
                   "photos": "Пришлите фото чеков (до 10). Вернитесь в карточку, когда закончите."}
        await safe_edit(event, prompts[field], kb.transaction_back_keyboard())
    await event.answer()


@router.callback_query(F.data == "tx_back")
@guard
async def back_to_review(event: CallbackQuery, state: FSMContext):
    data, _ = await _draft(state, event.from_user.id)
    if "amount_kop" not in data:
        raise DomainError("Сначала введите сумму или отмените операцию")
    await _review(event, state)
    await event.answer()


@router.callback_query(TransactionForm.category, F.data.regexp(r"^tx_cat:(\d+)$"))
@guard
async def category_picked(event: CallbackQuery, state: FSMContext):
    data, _ = await _draft(state, event.from_user.id)
    category_id = int(cb.parse(event.data)[1]) or None
    if category_id and category_id not in {row["id"] for row in await money.categories(data["house_id"])}:
        raise DomainError("Категория больше недоступна. Выберите другую.")
    await state.update_data(category_id=category_id)
    await _review(event, state)
    await event.answer()


async def _set_date(state: FSMContext, actor: int, raw: str):
    data, values = await _draft(state, actor)
    picked = parse_date(raw, settings.house_today(values))
    changes = {"date": picked}
    if data["kind"] == "contribution" and not data.get("month_custom"):
        changes["month"] = picked[:7]
    await state.update_data(**changes)


@router.callback_query(TransactionForm.date, F.data.regexp(r"^tx_date:(today|yesterday)$"))
@guard
async def date_picked(event: CallbackQuery, state: FSMContext):
    _, values = await _draft(state, event.from_user.id)
    picked = date.fromisoformat(settings.house_today(values))
    if event.data.endswith("yesterday"):
        picked -= timedelta(days=1)
    await _set_date(state, event.from_user.id, picked.isoformat())
    await _review(event, state)
    await event.answer()


@router.message(TransactionForm.date, F.text)
@guard
async def date_entered(message: Message, state: FSMContext):
    await _set_date(state, message.from_user.id, message.text)
    await _review(message, state)


@router.message(TransactionForm.month, F.text)
@guard
async def month_entered(message: Message, state: FSMContext):
    await _draft(state, message.from_user.id)
    await state.update_data(month=parse_month(message.text), month_custom=True)
    await _review(message, state)


@router.message(TransactionForm.description, F.text)
@guard
async def expense_description(message: Message, state: FSMContext):
    await _draft(state, message.from_user.id)
    description = message.text.strip()
    if len(description) > MAX_DESCRIPTION_LEN:
        raise DomainError("Описание — до 200 символов. Сократите текст; остальные поля сохранены.")
    await state.update_data(description="" if description == "—" else description)
    await _review(message, state)


@router.message(TransactionForm.photos, F.photo)
@guard
async def photo_added(message: Message, state: FSMContext):
    data, _ = await _draft(state, message.from_user.id)
    photos = data["photos"]
    if len(photos) >= MAX_PHOTOS_PER_EXPENSE:
        raise DomainError("Уже 10 чеков. Вернитесь в карточку для сохранения.")
    await state.update_data(photos=[*photos, message.photo[-1].file_id])
    await message.answer(f"Чек {len(photos) + 1} принят.", reply_markup=kb.transaction_back_keyboard())


@router.callback_query(TransactionForm.review, F.data.regexp(r"^tx_save:[a-f0-9]{8}$"))
@guard
async def save_transaction(event: CallbackQuery, state: FSMContext):
    data, values = await _draft(state, event.from_user.id)
    if cb.parse(event.data)[1] != data["token"]:
        raise DomainError("Это кнопка другой записи. Сохраните текущую карточку.")
    await event.answer("Сохраняю…")
    if data["kind"] == "expense":
        text = await persist_expense(event.bot, event.from_user.id, data, data["description"], state=state)
    else:
        contribution = await money.declare_contribution(
            data["house_id"], event.from_user.id, data["amount_kop"], data["date"], month=data["month"],
        )
        text = (f"Взнос {format_amount(data['amount_kop'], values['currency'])} · {data['date']}\n"
                f"За месяц: {data['month']}. " +
                ("Зачислен." if contribution["status"] == "confirmed" else "Ожидает подтверждения."))
        # Сохранённая операция не должна повториться при сбое доставки уведомления.
        await state.clear()
        if contribution["status"] == "declared":
            await _notify_confirmers(event.bot, await households.get_house(data["house_id"]), values,
                                     contribution, values["currency"])
    await state.clear()
    await safe_edit(event, text, kb.transaction_success_keyboard(data["kind"]))
