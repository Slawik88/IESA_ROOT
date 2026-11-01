"""Деньги: перенос между домами, дубли, отказы и прошлые даты."""
import asyncio
import json

import pytest

from infrastructure.repositories import transactions
from services import households, money, settings, transfers
from services.households import DomainError
from services.transaction_dates import parse_date


def payload(rows):
    return json.dumps({"format": "domovoy-money", "version": 1, "transactions": rows}).encode()


def entry(**values):
    return {"source_key": "test:1", "kind": "expense", "date": "2026-10-12", "member_tg_id": 100,
            "amount": "120.50", "mode": "house", "category": "Продукты", "description": "молоко", **values}


@pytest.fixture
async def homes(database):
    first = await households.create_house(100, "Хозяин", "Первый")
    second = await households.create_house(100, "Хозяин", "Второй")
    return first, second


@pytest.mark.parametrize("extension", ["csv", "tsv", "json"])
async def test_roundtrip_preserves_balance_dates_and_statuses(homes, extension):
    first, second = homes
    await settings.set_house_setting(first, "confirm_contributions", False)
    await money.declare_contribution(first, 100, 50000, "2026-10-02", month="2026-09")
    await money.add_expense(first, 100, 12050, None, "2026-10-12", "house", "=SUM(A1:A2)", [])
    personal = await money.add_expense(first, 100, 5000, None, "2026-10-13", "personal", "чек", [])
    await money.reimburse_expense(first, personal, 100)
    content = await transfers.export_file(first, 100, extension)
    preview = await transfers.preview_import(second, 100, content, extension)
    assert not preview.errors and preview.balance_delta == 32950
    assert len(preview.rows) == 3
    assert (await transfers.import_file(second, 100, content, extension)) == (3, 0)
    assert (await money.pot_balance(second))["balance"] == 32950
    rows = await transactions.all_rows(second)
    contribution = next(row for row in rows if row["kind"] == "contribution")
    assert contribution["date"] == "2026-10-02" and contribution["month"] == "2026-09"
    assert any(row["description"] == "=SUM(A1:A2)" for row in rows)
    assert (await transfers.import_file(second, 100, content, extension)) == (0, 3)
    assert (await transfers.import_file(first, 100, content, extension)) == (0, 3)


async def test_invalid_row_blocks_entire_import(homes):
    first, _ = homes
    content = payload([entry(), entry(source_key="bad", amount="-500")])
    preview = await transfers.preview_import(first, 100, content, "json")
    assert len(preview.errors) == 1 and "Строка 2" in preview.errors[0]
    with pytest.raises(DomainError):
        await transfers.import_file(first, 100, content, "json")
    assert not await transactions.all_rows(first)
    assert not await transactions.imported_keys(first)


async def test_conflicting_source_key_is_not_silently_overwritten(homes):
    first, _ = homes
    await transfers.import_file(first, 100, payload([entry()]), "json")
    with pytest.raises(DomainError):
        await transfers.import_file(first, 100, payload([entry(amount="400")]), "json")
    assert (await money.pot_balance(first))["balance"] == -12050


async def test_import_permissions_are_rechecked(homes):
    first, _ = homes
    house = await households.get_house(first)
    await households.join_house(house, 200, "Жилец")
    with pytest.raises(DomainError):
        await transfers.preview_import(first, 200, payload([entry()]), "json")
    await households.set_grant(first, 200, "import_transactions", True)
    assert not (await transfers.preview_import(first, 200, payload([entry()]), "json")).errors
    await households.set_grant(first, 200, "import_transactions", False)
    with pytest.raises(DomainError):
        await transfers.import_file(first, 200, payload([entry()]), "json")


async def test_foreign_member_and_wrong_currency_are_rejected(homes):
    first, _ = homes
    for row in (entry(member_tg_id=300), entry(currency="€")):
        preview = await transfers.preview_import(first, 100, payload([row]), "json")
        assert preview.errors
        with pytest.raises(DomainError):
            await transfers.import_file(first, 100, payload([row]), "json")


async def test_concurrent_same_file_import_is_idempotent(homes):
    first, _ = homes
    results = await asyncio.gather(*(
        transfers.import_file(first, 100, payload([entry()]), "json") for _ in range(2)
    ))
    assert sum(result[0] for result in results) == 1
    assert len(await transactions.all_rows(first)) == 1


@pytest.mark.parametrize("content,extension", [
    (b"", "csv"), (b"not json", "json"), (b"[]", "json"),
    (b"kind;date;member_tg_id;amount\nexpense;2026-10-12;100;3;extra", "csv"),
    (b"\xff", "tsv"), (b"a" * (2 * 1024 * 1024 + 1), "csv"),
], ids=["empty", "invalid-json", "wrong-json-shape", "extra-csv-column", "invalid-utf8", "oversized"])
async def test_malformed_files_have_domain_errors(homes, content, extension):
    with pytest.raises(DomainError):
        await transfers.preview_import(homes[0], 100, content, extension)


async def test_backdated_contribution_keeps_actual_entry_time(homes):
    row = await money.declare_contribution(homes[0], 100, 12345, "2026-09-15", month="2026-08")
    assert row["paid_on"] == "2026-09-15"
    assert row["month"] == "2026-08"
    assert row["declared_at"][:10] != "2026-09-15"


async def test_invalid_or_future_dates_are_rejected_before_writing(homes):
    for day in ("2026-02-30", "2099-01-01", "not-date"):
        with pytest.raises(DomainError):
            await money.add_expense(homes[0], 100, 100, None, day, "house", "", [])
    assert parse_date("12.10.2026", "2026-11-01") == "2026-10-12"


async def test_csv_does_not_expose_executable_formulas(homes):
    await money.add_expense(homes[0], 100, 100, None, "2026-10-01", "house", "=1+1", [])
    content = await transfers.export_file(homes[0], 100, "csv")
    assert "'=1+1" in content.decode("utf-8-sig")


async def test_month_filter_uses_contribution_accounting_month(homes):
    await money.declare_contribution(homes[0], 100, 100, "2026-10-30", month="2026-09")
    content = await transfers.export_file(homes[0], 100, "json", "2026-09")
    assert len(json.loads(content)["transactions"]) == 1
    assert not json.loads(await transfers.export_file(homes[0], 100, "json", "2026-10"))["transactions"]
