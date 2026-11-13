"""Швейцарский франк по умолчанию без пересчёта сохранённых сумм."""
import json

import pytest

from services import households, money, settings, transfers


async def test_default_chf_exports_roundtrip_without_changing_amount(database):
    house = await households.create_house(100, "Саша", "Новый дом")
    assert (await settings.house_settings(house))["currency"] == "CHF"
    await money.add_expense(house, 100, 12345, None, "2026-10-10", "house", "Покупка", [])
    content = await transfers.export_file(house, 100, "json")
    rows = json.loads(content)["transactions"]
    assert rows[0]["currency"] == "CHF" and rows[0]["amount"] == "123.45"
    assert await transfers.import_file(house, 100, content, "json") == (0, 1)
    assert (await money.pot_balance(house))["balance"] == -12345


@pytest.mark.parametrize("currency", ["₽", "€"])
async def test_explicit_house_currency_stays_selected(database, currency):
    house = await households.create_house(100, "Саша", "Старый дом")
    await settings.set_house_setting(house, "currency", currency)
    await money.add_expense(house, 100, 12345, None, "2026-10-10", "house", "Покупка", [])
    assert await settings.house_setting(house, "currency") == currency
    content = json.loads(await transfers.export_file(house, 100, "json"))
    assert content["transactions"][0]["currency"] == currency
    assert content["transactions"][0]["amount"] == "123.45"


async def test_old_ruble_export_is_not_silently_relabelled_as_chf(database):
    house = await households.create_house(100, "Саша", "Дом")
    content = json.dumps({"format": "domovoy-money", "version": 1, "transactions": [{
        "source_key": "old:1", "kind": "expense", "date": "2026-10-10", "member_tg_id": 100,
        "amount": "123.45", "currency": "₽", "mode": "house",
    }]}).encode()
    preview = await transfers.preview_import(house, 100, content, "json")
    assert preview.errors
    assert (await money.pot_balance(house))["balance"] == 0
