"""
tests/test_money.py — деньги: разбор сумм, баланс, взносы, траты, возвраты.
"""
import pytest

from core.money import AmountError, format_amount, parse_amount
from services import households, money
from services.households import DomainError


# ── Чистые функции ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,kop", [
    ("1200", 120000),
    ("1 200", 120000),
    ("1200,50", 120050),
    ("1200.5", 120050),
    ("0.99", 99),
    ("10 000", 1000000),
    ("1\u202f234,50", 123450),
    ("1’234.50", 123450),
    ("1'234.50", 123450),
])
def test_parse_amount_ok(raw, kop):
    assert parse_amount(raw) == kop


@pytest.mark.parametrize("raw", ["", "abc", "12.3.4", "-5", "0", "10.123", "1,2,3", "1'2", "12'34.50", "'123"])
def test_parse_amount_error(raw):
    with pytest.raises(AmountError):
        parse_amount(raw)


def test_format_amount():
    assert format_amount(120000, "₽") == "1 200 ₽"
    assert format_amount(120050, "₽") == "1 200,50 ₽"
    assert format_amount(50, "₽") == "0,50 ₽"


def test_shift_month():
    assert money.shift_month("2026-01", -1) == "2025-12"
    assert money.shift_month("2026-10", 2) == "2026-12"
    assert money.shift_month("2026-12", 1) == "2027-01"


# ── Поток денег на живой БД ──────────────────────────────────────────────────

async def _make_house(database, owner=100, name="Тест"):
    house_id = await households.create_house(owner, "Владелец", name)
    return await households.get_house(house_id)


async def test_balance_math(database, today):
    house = await _make_house(database)
    hid = house["id"]

    contribution = await money.declare_contribution(hid, 100, 300000, today)
    assert contribution["status"] == "declared"
    # Не подтверждён — в балансе не участвует.
    assert (await money.pot_balance(hid))["balance"] == 0

    await money.resolve_contribution(contribution["id"], True, 100)
    assert (await money.pot_balance(hid))["confirmed_total"] == 300000

    await money.add_expense(hid, 100, 120000, None, today, money.MODE_HOUSE, "молоко", [])
    assert (await money.pot_balance(hid))["balance"] == 180000

    # «За свои» не трогает котёл, пока не возвращена.
    personal_id = await money.add_expense(hid, 100, 60000, None, today, money.MODE_PERSONAL, "швабра", [])
    assert (await money.pot_balance(hid))["balance"] == 180000
    await money.reimburse_expense(hid, personal_id, 100)
    assert (await money.pot_balance(hid))["balance"] == 120000
    assert (await money.pot_balance(hid))["reimbursed"] == 60000


async def test_contribution_double_resolve(database, today):
    house = await _make_house(database)
    contribution = await money.declare_contribution(house["id"], 100, 100000, today)
    await money.resolve_contribution(contribution["id"], True, 100)
    with pytest.raises(DomainError):
        await money.resolve_contribution(contribution["id"], False, 100)


async def test_double_reimburse(database, today):
    house = await _make_house(database)
    expense_id = await money.add_expense(house["id"], 100, 10000, None, today, money.MODE_PERSONAL, "", [])
    await money.reimburse_expense(house["id"], expense_id, 100)
    with pytest.raises(DomainError):
        await money.reimburse_expense(house["id"], expense_id, 100)


async def test_expense_validation(database, today):
    house = await _make_house(database)
    with pytest.raises(DomainError):
        await money.add_expense(house["id"], 100, 1000, 999, today, money.MODE_HOUSE, "", [])
    with pytest.raises(DomainError):
        await money.add_expense(house["id"], 100, 1000, None, today, "бартер", "", [])
    long = "x" * 201
    with pytest.raises(DomainError):
        await money.add_expense(house["id"], 100, 1000, None, today, money.MODE_HOUSE, long, [])


async def test_categories_lifecycle(database):
    house = await _make_house(database)
    hid = house["id"]
    # Дефолтные категории засеяны.
    names = {c["name"] for c in await money.categories(hid)}
    assert "Продукты" in names

    category_id = await money.add_category(hid, "Инструменты")
    with pytest.raises(DomainError):
        await money.add_category(hid, "инструменты")

    # Категорию с тратами удалить нельзя.
    today = "2026-10-31"
    await money.add_expense(hid, 100, 5000, category_id, today, money.MODE_HOUSE, "", [])
    with pytest.raises(DomainError):
        await money.remove_category(hid, category_id)

    empty_id = await money.add_category(hid, "Пустышка")
    await money.remove_category(hid, empty_id)
    assert empty_id not in {c["id"] for c in await money.categories(hid)}
