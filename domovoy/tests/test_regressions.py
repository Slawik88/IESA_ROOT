"""Проверки сбоев, границ домов и конкурентных операций аудита 2026-11-01."""
import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot import cb, keyboards
from bot.handlers import cleaning as cleaning_handlers, money as money_handlers, settings as settings_handlers
from bot.states import TransactionForm
from bot.handlers import transaction_form
from core.money import AmountError, format_amount, parse_amount
from infrastructure import repositories as repo
from infrastructure.db import db
from infrastructure.schema import _pg_statement, _upgrade_telegram_ids
from services import cleaning, households, money, notify, reports, scheduler, settings
from services.households import DomainError


@pytest.fixture
async def house(database):
    house_id = await households.create_house(100, "Хозяин", "Дом аудита")
    result = await households.get_house(house_id)
    await households.join_house(result, 200, "Жилец")
    return result


@pytest.fixture
async def state():
    storage = MemoryStorage()
    yield FSMContext(storage, StorageKey(bot_id=123456, chat_id=100, user_id=100))
    await storage.close()


@pytest.fixture
async def telegram():
    bot = Bot("123456:TEST_TOKEN")
    bot.session.make_request = AsyncMock(return_value=True)
    yield bot
    await bot.session.close()


def callback(bot, data, user_id=100):
    return CallbackQuery(
        id="audit-callback", from_user=User(id=user_id, is_bot=False, first_name="Хозяин"),
        chat_instance="audit", data=data,
        message=Message(message_id=1, date=datetime(2026, 11, 1),
                        chat=Chat(id=user_id, type="private")).as_(bot),
    ).as_(bot)


@pytest.mark.parametrize("kop,text", [(-1, "-0,01 ₽"), (-150, "-1,50 ₽"), (-10000, "-100 ₽")])
def test_negative_balance_format(kop, text):
    assert format_amount(kop, "₽") == text


def test_excessively_long_amount_has_readable_error():
    with pytest.raises(AmountError):
        parse_amount("9" * 5000)


async def test_report_with_negative_balance_and_only_pending_contributions(house):
    await money.declare_contribution(house["id"], 100, 10000, "2026-10-31")
    await money.add_expense(house["id"], 100, 150, None, "2026-10-31", "house", "", [])
    text = await reports.month_report_text(house, "2026-10")
    assert "Текущий баланс котла: -1,50 ₽" in text
    assert "Ожидают подтверждения взносы: 1" in text


async def test_contributions_without_confirmation_are_credited(house):
    await settings.set_house_setting(house["id"], "confirm_contributions", False)
    contribution = await money.declare_contribution(house["id"], 200, 12300, "2026-11-01")
    assert contribution["status"] == "confirmed"
    assert contribution["confirmed_by"] == 200
    assert (await money.pot_balance(house["id"]))["balance"] == 12300
    assert not await money.pending_contributions(house["id"])


async def test_foreign_contribution_cannot_be_resolved(house):
    foreign_id = await households.create_house(300, "Другой хозяин", "Другой дом")
    contribution = await money.declare_contribution(foreign_id, 300, 10000, "2026-11-01")
    with pytest.raises(DomainError):
        await money.resolve_contribution(contribution["id"], True, 100, house_id=house["id"])
    with pytest.raises(DomainError):
        await money.resolve_contribution(contribution["id"], True, 100)
    assert (await repo.money.get_contribution(contribution["id"]))["status"] == "declared"


async def test_concurrent_contribution_decisions_have_one_winner(house):
    contribution = await money.declare_contribution(house["id"], 100, 10000, "2026-11-01")
    results = await asyncio.gather(
        money.resolve_contribution(contribution["id"], True, 100),
        money.resolve_contribution(contribution["id"], False, 100), return_exceptions=True,
    )
    assert sum(isinstance(result, DomainError) for result in results) == 1
    assert (await repo.money.get_contribution(contribution["id"]))["status"] in ("confirmed", "rejected")


async def test_receipts_are_scoped_to_house(house):
    foreign_id = await households.create_house(300, "Другой хозяин", "Другой дом")
    expense_id = await money.add_expense(foreign_id, 300, 100, None, "2026-11-01", "house", "", ["secret"])
    with pytest.raises(DomainError):
        await money.expense_photos(house["id"], expense_id)
    assert (await money.expense_photos(foreign_id, expense_id))[0]["file_id"] == "secret"


async def test_expense_and_receipts_roll_back_together(house, monkeypatch):
    from infrastructure.db import _SqliteConn

    original = _SqliteConn.insert

    async def fail_photo(conn, sql, *args):
        if "INSERT INTO expense_photos" in sql:
            raise RuntimeError("Хранилище недоступно")
        return await original(conn, sql, *args)

    monkeypatch.setattr(_SqliteConn, "insert", fail_photo)
    with pytest.raises(RuntimeError):
        await money.add_expense(house["id"], 100, 100, None, "2026-11-01", "house", "", ["photo"])
    assert not await money.recent_expenses(house["id"], 10)


async def test_concurrent_sqlite_transactions_are_isolated(house):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def rollback():
        with pytest.raises(RuntimeError, match="rollback"):
            async with db.transaction() as conn:
                await conn.execute("UPDATE houses SET name = ? WHERE id = ?", "Не сохранится", house["id"])
                entered.set()
                await release.wait()
                raise RuntimeError("rollback")

    task = asyncio.create_task(rollback())
    await entered.wait()
    other_write = asyncio.create_task(repo.houses.set_chat(house["id"], -1001234567890))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(task, other_write)
    result = await households.get_house(house["id"])
    assert result["name"] == house["name"]
    assert result["chat_id"] == -1001234567890


@pytest.mark.parametrize("amount", [0, -100, 1.5, True, 1_000_000_001])
async def test_service_rejects_invalid_money(house, amount):
    with pytest.raises(DomainError):
        await money.declare_contribution(house["id"], 100, amount, "2026-11-01")
    with pytest.raises(DomainError):
        await money.add_expense(house["id"], 100, amount, None, "2026-11-01", "house", "", [])


async def test_departed_member_cannot_save_expense_or_remain_in_schedule(house):
    await cleaning.save_weekday_map(house["id"], {200: 0}, "2026-11-01")
    await households.leave_house(house["id"], 200)
    with pytest.raises(DomainError):
        await money.add_expense(house["id"], 200, 100, None, "2026-11-01", "house", "", [])
    assert await cleaning.ensure_days(house["id"], "2026-12-01") == 0
    assert not await cleaning.open_days_up_to(house["id"], "2026-12-31")
    assert await households.join_house(house, 200, "Вернулся")
    assert (await households.membership(house["id"], 200))["status"] == "active"


async def test_disabled_notifications_stay_disabled_without_chat(house):
    await settings.set_notify_setting(house["id"], 100, "expense_added", "off")
    await settings.set_notify_setting(house["id"], 200, "expense_added", "chat")
    bot = SimpleNamespace(send_message=AsyncMock())
    await notify.deliver(bot, house, "expense_added", {100: "Не отправлять", 200: "Отправлять"})
    bot.send_message.assert_awaited_once_with(200, "Отправлять", reply_markup=None)


async def test_chat_receives_personal_event_without_common_text(house):
    await households.set_chat_id(house["id"], -1001234567890)
    house = await households.get_house(house["id"])
    await settings.set_notify_setting(house["id"], 100, "morning_reminder", "chat")
    await settings.set_notify_setting(house["id"], 200, "morning_reminder", "off")
    bot = SimpleNamespace(send_message=AsyncMock())
    await notify.deliver(bot, house, "morning_reminder", {100: "Напоминание", 200: "Выключено"})
    bot.send_message.assert_awaited_once_with(-1001234567890, "Напоминание", reply_markup=None)


async def test_evening_reminder_lists_all_overdue_days(house):
    await repo.schedule.add_day(house["id"], 100, "2026-10-20")
    await repo.schedule.add_day(house["id"], 100, "2026-10-27")
    bot = SimpleNamespace(send_message=AsyncMock())
    await scheduler._evening_job(bot, house, "2026-11-01")
    text = bot.send_message.await_args.args[1]
    assert "2026-10-20" in text and "2026-10-27" in text


async def test_monthly_scheduler_does_not_repeat_report(house, monkeypatch):
    monkeypatch.setattr(settings, "house_now", lambda _: datetime(2026, 11, 1, 11))
    bot = SimpleNamespace(send_message=AsyncMock())
    await scheduler._tick_house(bot, house)
    first_count = bot.send_message.await_count
    assert first_count == 2  # отчёт двум жильцам, графика нет
    await scheduler._tick_house(bot, house)
    assert bot.send_message.await_count == first_count


async def test_today_renders_overdue_close_button(house, state, telegram):
    await repo.users.set_active_house(100, house["id"])
    await repo.schedule.add_day(house["id"], 100, "2026-10-20")
    await cleaning_handlers.show_today(callback(telegram, cb.today()), state)
    methods = [call.args[1] for call in telegram.session.make_request.await_args_list]
    edit = next(method for method in methods if method.__api_method__ == "editMessageText")
    assert any(button.callback_data.startswith("done:")
               for row in edit.reply_markup.inline_keyboard for button in row)


async def test_expense_card_renders_and_counts_photos(house, telegram):
    await repo.users.set_active_house(100, house["id"])
    expense_id = await money.add_expense(house["id"], 100, 100, None, "2026-11-01", "house", "", ["photo"])
    await money_handlers.show_expense_card(callback(telegram, cb.expense_card(expense_id)))
    methods = [call.args[1] for call in telegram.session.make_request.await_args_list]
    edit = next(method for method in methods if method.__api_method__ == "editMessageText")
    assert any(button.text == "📎 Чеки (1)" for row in edit.reply_markup.inline_keyboard for button in row)


async def test_invalid_description_preserves_draft(house, state, telegram):
    await state.set_state(TransactionForm.description)
    await state.update_data(house_id=house["id"], kind="expense", amount_kop=100, mode="house", photos=["photo"])
    message = Message(message_id=2, date=datetime(2026, 11, 1), chat=Chat(id=100, type="private"),
                      from_user=User(id=100, is_bot=False, first_name="Хозяин"), text="x" * 201).as_(telegram)
    await transaction_form.expense_description(message, state)
    assert await state.get_state() == TransactionForm.description.state
    assert (await state.get_data())["photos"] == ["photo"]
    assert not await money.recent_expenses(house["id"], 10)


async def test_revoked_schedule_right_is_checked_at_save(house, state, telegram):
    await state.update_data(house_id=house["id"], draft={200: 0})
    await cleaning_handlers.save_schedule(callback(telegram, cb.schedule_save(), user_id=200), state)
    assert not await cleaning.weekday_map(house["id"])


async def test_close_other_member_day_returns_name(house, state, telegram):
    await repo.users.set_active_house(100, house["id"])
    await repo.schedule.add_day(house["id"], 200, "2026-10-20")
    day = (await cleaning.days_on(house["id"], "2026-10-20"))[0]
    await cleaning_handlers.close_for_someone(callback(telegram, cb.day_close(day["id"])), state)
    saved = await repo.schedule.get_day(day["id"])
    assert saved["status"] == "done" and saved["closed_by"] == 100
    assert saved["display_name"] == "Жилец"


async def test_cleaning_close_cancel_race_has_one_winner(house):
    await repo.schedule.add_day(house["id"], 100, "2026-10-20")
    day = (await cleaning.days_on(house["id"], "2026-10-20"))[0]
    results = await asyncio.gather(
        cleaning.close_day_for(house["id"], day["id"], 100, "2026-11-01"),
        cleaning.cancel_day(house["id"], day["id"], 100), return_exceptions=True,
    )
    assert sum(isinstance(result, DomainError) for result in results) == 1
    assert (await repo.schedule.get_day(day["id"]))["status"] in ("done", "canceled")


async def test_invite_refresh_invalidates_old_link(house, telegram):
    await repo.users.set_active_house(100, house["id"])
    telegram.me = AsyncMock(return_value=SimpleNamespace(username="Domovskii_bot"))
    await settings_handlers.refresh_invite(callback(telegram, cb.settings_invite_refresh()))
    assert await households.get_house_by_invite(house["invite_token"]) is None
    assert (await households.get_house(house["id"]))["invite_token"] != house["invite_token"]


def test_delegated_settings_are_visible_without_house_settings():
    markup = keyboards.settings_root_keyboard(False, False, can_manage_members=True, can_manage_categories=True)
    actions = {button.callback_data for row in markup.inline_keyboard for button in row}
    assert {cb.settings_perms(), cb.settings_invite(), cb.settings_categories()} <= actions
    assert cb.settings_house() not in actions


def test_postgres_telegram_identifiers_are_bigint():
    sql = _pg_statement("CREATE TABLE t (tg_id INTEGER, chat_id INTEGER, amount_kop INTEGER)")
    assert "tg_id BIGINT" in sql and "chat_id BIGINT" in sql
    assert "amount_kop INTEGER" in sql


async def test_postgres_upgrade_only_changes_registered_columns():
    conn = SimpleNamespace(fetch=AsyncMock(return_value=[
        {"table_name": "houses", "column_name": "chat_id"},
        {"table_name": "unrelated", "column_name": "tg_id"},
        {"table_name": "expenses", "column_name": "amount_kop"},
    ]), execute=AsyncMock())
    await _upgrade_telegram_ids(conn)
    conn.execute.assert_awaited_once_with('ALTER TABLE "houses" ALTER COLUMN "chat_id" TYPE BIGINT')


@pytest.fixture(scope="module")
def dispatcher():
    from bot.dispatcher import build_dispatcher

    return build_dispatcher()


async def test_dispatcher_routes_today(house, dispatcher, telegram):
    await repo.users.set_active_house(100, house["id"])
    await dispatcher.feed_update(telegram, Update(update_id=1, callback_query=callback(telegram, cb.today())))
    methods = [call.args[1].__api_method__ for call in telegram.session.make_request.await_args_list]
    assert "editMessageText" in methods and "answerCallbackQuery" in methods


async def test_dispatcher_blocks_house_data_in_group(house, dispatcher, telegram):
    await repo.users.set_active_house(100, house["id"])
    event = callback(telegram, cb.balance())
    group_message = event.message.model_copy(update={"chat": Chat(id=-1001234567890, type="supergroup")})
    event = event.model_copy(update={"message": group_message})
    await dispatcher.feed_update(telegram, Update(update_id=2, callback_query=event))
    methods = [call.args[1] for call in telegram.session.make_request.await_args_list]
    assert len(methods) == 1
    assert methods[0].__api_method__ == "answerCallbackQuery"
    assert "личке" in methods[0].text


async def test_dispatcher_answers_stale_callback(dispatcher, telegram):
    await dispatcher.feed_update(telegram, Update(update_id=3, callback_query=callback(telegram, "obsolete")))
    methods = [call.args[1] for call in telegram.session.make_request.await_args_list]
    assert len(methods) == 1
    assert methods[0].__api_method__ == "answerCallbackQuery"
    assert "устарела" in methods[0].text


async def test_transaction_review_edits_date_then_saves_once(house, state, telegram):
    await repo.users.set_active_house(100, house["id"])
    await transaction_form.start_transaction(callback(telegram, cb.expense_new()), state)
    message = Message(message_id=2, date=datetime(2026, 11, 1), chat=Chat(id=100, type="private"),
                      from_user=User(id=100, is_bot=False, first_name="Хозяин"), text="120,50").as_(telegram)
    await transaction_form.amount_entered(message, state)
    assert not await money.recent_expenses(house["id"], 10)
    await transaction_form.edit_field(callback(telegram, cb.transaction_field("date")), state)
    await transaction_form.date_entered(message.model_copy(update={"text": "12.10.2026"}), state)
    data = await state.get_data()
    assert data["date"] == "2026-10-12" and data["amount_kop"] == 12050
    await transaction_form.save_transaction(callback(telegram, cb.transaction_save(data["token"])), state)
    assert await state.get_state() is None
    rows = await money.recent_expenses(house["id"], 10)
    assert len(rows) == 1 and rows[0]["spent_on"] == "2026-10-12"


async def test_stale_save_button_does_not_commit_current_draft(house, state, telegram):
    await state.set_state(TransactionForm.review)
    await state.update_data(house_id=house["id"], kind="expense", token="1234abcd", amount_kop=100)
    await transaction_form.save_transaction(callback(telegram, cb.transaction_save("00000000")), state)
    assert not await money.recent_expenses(house["id"], 10)
    assert await state.get_state() == TransactionForm.review.state
