"""Файлы и общий журнал денег: все действия доступны из раздела денег."""
import base64
import csv
import io
import json
import secrets
from collections import Counter

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from bot import cb, keyboards as kb
from bot.states import MoneyTransfer
from bot.util import guard, resolve_house, safe_edit
from core.constants import TRANSFER_MAX_BYTES, TRANSACTION_PAGE_SIZE
from core.money import format_amount
from infrastructure.repositories import transactions
from services import households, money, settings, transfers
from services.households import DomainError
from services.transaction_dates import parse_month

router = Router(name="money_files")


async def _context(actor: int):
    house = await resolve_house(actor)
    if house is None:
        raise DomainError("Сначала выберите дом через /start")
    return house, await settings.house_settings(house["id"])


async def _files(event: CallbackQuery | Message, month: str):
    house, _ = await _context(event.from_user.id)
    allowed = await households.can(house["id"], event.from_user.id, "import_transactions")
    text = (f"Файлы · {house['name']}\nПериод: {'вся история' if month == 'all' else month}\n\n"
            "CSV / TSV — таблицы для Excel и Google Sheets.\nJSON — перенос истории в Домового.\n"
            "Экспорт содержит взносы и траты, без фотографий чеков.\n"
            "Импорт сначала покажет проверку и изменение баланса. Ничего не удаляется.")
    markup = kb.money_files_keyboard(month, allowed)
    if isinstance(event, CallbackQuery):
        await safe_edit(event, text, markup)
    else:
        await event.answer(text, reply_markup=markup)


@router.callback_query(F.data == cb.money_files())
@guard
async def files_root(event: CallbackQuery, state: FSMContext):
    _, values = await _context(event.from_user.id)
    await state.clear()
    await _files(event, settings.house_today(values)[:7])
    await event.answer()


@router.callback_query(F.data.regexp(r"^files_period:(current|all|custom)$"))
@guard
async def export_period(event: CallbackQuery, state: FSMContext):
    house, values = await _context(event.from_user.id)
    period = cb.parse(event.data)[1]
    await state.clear()
    if period == "custom":
        await state.set_state(MoneyTransfer.export_month)
        await state.update_data(house_id=house["id"])
        await safe_edit(event, "Какой месяц выгрузить? Напишите, например: 2026-10.",
                        kb.import_review_keyboard(None))
    else:
        await _files(event, "all" if period == "all" else settings.house_today(values)[:7])
    await event.answer()


@router.message(MoneyTransfer.export_month, F.text)
@guard
async def export_month_entered(message: Message, state: FSMContext):
    month = parse_month(message.text)
    await state.clear()
    await _files(message, month)


@router.callback_query(F.data.regexp(r"^file_export:(csv|tsv|json):(all|\d{4}-\d{2})$"))
@guard
async def export_document(event: CallbackQuery):
    house, _ = await _context(event.from_user.id)
    _, extension, month = cb.parse(event.data)
    await event.answer("Готовлю файл…")
    content = await transfers.export_file(house["id"], event.from_user.id, extension,
                                         None if month == "all" else month)
    await event.message.answer_document(
        BufferedInputFile(content, filename=f"domovoy-{house['id']}-{month}.{extension}"),
        caption="Операции дома. Фото чеков остаются в боте.",
    )


@router.callback_query(F.data.regexp(r"^file_template:(csv|json)$"))
@guard
async def template_document(event: CallbackQuery):
    house, _ = await _context(event.from_user.id)
    await households.require(house["id"], event.from_user.id, "import_transactions")
    extension = cb.parse(event.data)[1]
    if extension == "csv":
        output = io.StringIO()
        csv.writer(output, delimiter=";").writerow(transfers.FIELDS)
        content = output.getvalue().encode("utf-8-sig")
    else:
        content = json.dumps({"format": "domovoy-money", "version": 1, "transactions": []}).encode()
    await event.message.answer_document(
        BufferedInputFile(content, filename=f"domovoy-template.{extension}"),
        caption="Заполните шаблон или измените экспорт. kind: expense / contribution; "
                "date: 2026-10-25; amount: 150.50; member_tg_id — ID жильца. "
                "Для трат mode: house / personal. source_key — уникальный ключ записи.",
    )
    await event.answer()


@router.callback_query(F.data == "file_import")
@guard
async def start_import(event: CallbackQuery, state: FSMContext):
    house, _ = await _context(event.from_user.id)
    await households.require(house["id"], event.from_user.id, "import_transactions")
    await state.clear()
    await state.set_state(MoneyTransfer.waiting_file)
    await state.update_data(house_id=house["id"])
    members = await households.members(house["id"])
    people = "\n".join(f"{member['display_name']}: {member['tg_id']}" for member in members)
    await safe_edit(event, "Пришлите CSV, TSV или JSON до 2 МБ, не больше 1000 операций.\n"
                    "Используйте наш шаблон или экспорт. Чужие банковские форматы нужно привести к шаблону.\n"
                    "Повторные ключи пропускаются, изменённые записи требуют другого ключа.\n\n"
                    f"ID жильцов для member_tg_id:\n{people}", kb.import_review_keyboard(None))
    await event.answer()


@router.message(MoneyTransfer.waiting_file, F.document)
@guard
async def import_uploaded(message: Message, state: FSMContext):
    data = await state.get_data()
    await households.require(data["house_id"], message.from_user.id, "import_transactions")
    if not message.document.file_size or message.document.file_size > TRANSFER_MAX_BYTES:
        raise DomainError("Файл должен быть не больше 2 МБ")
    extension = (message.document.file_name or "").rsplit(".", 1)[-1].lower()
    if extension not in transfers.FORMATS:
        raise DomainError("Нужен файл .csv, .tsv или .json")
    buffer = io.BytesIO()
    await message.bot.download(message.document, destination=buffer)
    content = buffer.getvalue()
    preview = await transfers.preview_import(data["house_id"], message.from_user.id, content, extension)
    values = await settings.house_settings(data["house_id"])
    counts = Counter(row["kind"] for row in preview.rows)
    lines = ["Проверка файла", f"Новых трат: {counts['expense']}, взносов: {counts['contribution']}",
             f"Дублей пропущено: {preview.duplicates}", f"Ошибок: {len(preview.errors)}",
             f"Изменение котла: {format_amount(preview.balance_delta, values['currency'])}"]
    lines += [f"{row['date']} · {row['kind']} · {format_amount(row['amount_kop'], values['currency'])}"
              for row in preview.rows[:5]]
    token = None
    if preview.errors:
        lines += ["", "Файл не записан. Исправьте ошибки и загрузите заново.", *preview.errors[:5]]
    elif preview.rows:
        token = secrets.token_hex(4)
        await state.set_state(MoneyTransfer.review)
        await state.update_data(payload=base64.b64encode(content).decode(), extension=extension, token=token)
        lines += ["", "Взносы и статусы будут перенесены как в файле. Подтвердить запись?"]
    else:
        lines += ["", "Все записи уже есть. Баланс не изменится."]
    await message.answer("\n".join(lines), reply_markup=kb.import_review_keyboard(token))


@router.callback_query(MoneyTransfer.review, F.data.regexp(r"^file_apply:[a-f0-9]{8}$"))
@guard
async def confirm_import(event: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if cb.parse(event.data)[1] != data["token"]:
        raise DomainError("Это кнопка другого файла. Используйте последний предпросмотр.")
    added, skipped = await transfers.import_file(data["house_id"], event.from_user.id,
                                                base64.b64decode(data["payload"]), data["extension"])
    await state.clear()
    await safe_edit(event, f"Готово. Добавлено: {added}. Дублей пропущено: {skipped}.",
                    kb.transaction_success_keyboard("expense"))
    await event.answer("Импорт завершён")


@router.callback_query(F.data.regexp(r"^money_hist:(current|\d{4}-\d{2}):(\d+)$"))
@guard
async def history(event: CallbackQuery, state: FSMContext):
    house, values = await _context(event.from_user.id)
    _, month, page_raw = cb.parse(event.data)
    month = settings.house_today(values)[:7] if month == "current" else parse_month(month)
    page = int(page_raw)
    rows = [row for row in await transactions.all_rows(house["id"]) if row["month"] == month]
    page = min(page, max(0, (len(rows) - 1) // TRANSACTION_PAGE_SIZE))
    shown = rows[page * TRANSACTION_PAGE_SIZE:(page + 1) * TRANSACTION_PAGE_SIZE]
    lines = [f"Операции · {house['name']} · {month}", ""]
    buttons = []
    for row in shown:
        kind = "Трата" if row["kind"] == "expense" else "Взнос"
        status = {"confirmed": "зачтён", "declared": "ждёт подтверждения", "rejected": "отклонён"}[row["status"]]
        suffix = "" if row["kind"] == "expense" else f" · {status}"
        lines.append(f"{row['date']} · {kind} · {format_amount(row['amount_kop'], values['currency'])}"
                     f"\n{row['display_name'] or '?'}{suffix}")
        if row["kind"] == "expense":
            buttons.append([InlineKeyboardButton(text=f"Трата {row['date']} · "
                                                 f"{format_amount(row['amount_kop'], values['currency'])}",
                                                 callback_data=cb.expense_card(row["id"]))])
    if not shown:
        lines += ["За этот месяц операций пока нет. Можно добавить их задним числом."]
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton(text="← Страница", callback_data=cb.money_history(month, page-1)))
    if (page+1) * TRANSACTION_PAGE_SIZE < len(rows):
        navigation.append(InlineKeyboardButton(text="Страница →", callback_data=cb.money_history(month, page+1)))
    if navigation:
        buttons.append(navigation)
    buttons.append([InlineKeyboardButton(text="‹ Месяц", callback_data=cb.money_history(money.shift_month(month, -1))),
                    InlineKeyboardButton(text="Месяц ›", callback_data=cb.money_history(money.shift_month(month, 1)))])
    buttons += [[InlineKeyboardButton(text="➕ Трата", callback_data=cb.expense_new()),
                 InlineKeyboardButton(text="Внести деньги", callback_data=cb.contribute())],
                [InlineKeyboardButton(text="← Деньги", callback_data=cb.balance())]]
    await state.clear()
    await safe_edit(event, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons))
    await event.answer()
