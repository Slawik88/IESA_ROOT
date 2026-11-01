"""Закрытый веб: чужая подпись, дом, отозванное участие и повтор записи."""
import hashlib
import hmac
import json
import time
import asyncio
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import pytest

from core import config
from infrastructure.repositories import transactions
from infrastructure.repositories import schedule
from services import households
from services import money, transfers
from core.transaction_versions import expense_version
from infrastructure.db import db
from services.web_auth import verify_init_data
from services.households import DomainError
from web.app import create_app

TOKEN = "123456:TEST_HOME_BOT"


def signed(actor=100, token=TOKEN, age=0):
    values = {"auth_date": str(int(time.time()) - age), "user": json.dumps({"id": actor, "first_name": "Тест"})}
    key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    check = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    values["hash"] = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


@pytest.fixture
async def client(monkeypatch, database):
    monkeypatch.setattr(config, "BOT_TOKEN", TOKEN)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test") as client:
        yield client


@pytest.fixture
async def house(database):
    return await households.create_house(100, "Хозяин", "Закрытый дом")


def headers(actor=100, **kwargs):
    return {"Authorization": "tma " + signed(actor, **kwargs)}


@pytest.mark.parametrize("authorization", [None, "Bearer predvestnik-session", "tma forged"])
async def test_unauthenticated_requests_reveal_nothing(client, authorization):
    result = await client.get("/api/houses", headers={"Authorization": authorization} if authorization else {})
    assert result.status_code == 404 and "Домовой" not in result.text
    assert result.headers["cache-control"] == "no-store"


async def test_predvestnik_signature_and_expired_data_are_rejected(client):
    for data in (headers(token="654321:PREDVESTNIK"), headers(age=3601), headers(age=-120)):
        assert (await client.get("/api/houses", headers=data)).status_code == 404


def test_duplicate_init_data_parameters_are_rejected():
    with pytest.raises(DomainError):
        verify_init_data(signed() + "&auth_date=1", TOKEN)


async def test_house_and_session_do_not_leak_invite_or_other_homes(client, house):
    result = await client.get(f"/api/houses/{house}", headers=headers())
    assert result.status_code == 200
    assert "invite_token" not in result.text
    foreign = await households.create_house(300, "Чужой", "Чужой дом")
    result = await client.get(f"/api/houses/{foreign}", headers=headers())
    assert result.status_code == 422 and "Чужой дом" not in result.text


async def test_departed_member_loses_access_with_still_valid_signature(client, house):
    await households.join_house(await households.get_house(house), 200, "Жилец")
    assert (await client.get(f"/api/houses/{house}", headers=headers(200))).status_code == 200
    await households.leave_house(house, 200)
    assert (await client.get(f"/api/houses/{house}", headers=headers(200))).status_code == 422


async def test_web_retry_does_not_duplicate_money(client, house):
    await households.join_house(await households.get_house(house), 200, "Жилец")
    payload = {"request_id": str(uuid4()), "kind": "expense", "amount": "120,50", "date": "2026-10-15"}
    path = f"/api/houses/{house}/transactions"
    first = await client.post(path, headers=headers(200), json=payload)
    second = await client.post(path, headers=headers(200), json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["added"] == 1 and second.json()["duplicate"]
    assert len(await transactions.all_rows(house)) == 1
    changed = await client.post(path, headers=headers(200), json={**payload, "amount": "300"})
    assert changed.status_code == 422
    assert len(await transactions.all_rows(house)) == 1


async def test_bad_amount_is_a_clear_error_without_write(client, house):
    response = await client.post(f"/api/houses/{house}/transactions", headers=headers(), json={
        "request_id": str(uuid4()), "kind": "expense", "date": "2026-10-12", "amount": "-50",
    })
    assert response.status_code == 422
    assert not await transactions.all_rows(house)


async def test_future_cleaning_day_cannot_be_closed(client, house):
    await schedule.add_day(house, 100, "2099-01-01")
    day = (await schedule.days_on(house, "2099-01-01"))[0]
    result = await client.post(f"/api/houses/{house}/clean/{day['id']}", headers=headers())
    assert result.status_code == 422
    assert (await schedule.get_day(day["id"]))["status"] == "open"


async def test_import_permission_is_not_implied_by_membership(client, house):
    await households.join_house(await households.get_house(house), 200, "Жилец")
    result = await client.post(f"/api/houses/{house}/import/preview", headers=headers(200),
                               json={"extension": "json", "content": "e30="})
    assert result.status_code == 422


async def test_neutral_shell_and_no_public_api_documentation(client):
    shell = await client.get("/")
    assert shell.status_code == 200 and "Закрытое приложение" in shell.text
    assert "Домовой" not in shell.text and "Закрытый дом" not in shell.text
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert (await client.get(path)).status_code == 404
    assert "noindex" in shell.headers["x-robots-tag"]
    assert shell.headers["referrer-policy"] == "no-referrer"


def edit_payload(original, **changes):
    return {"request_id": str(uuid4()), "kind": "expense", "amount": "120.50", "date": original["spent_on"],
            "category_id": original["category_id"], "mode": original["mode"], "description": original["description"],
            "version": expense_version(original), **changes}


async def test_edit_keeps_audit_and_retry_does_not_create_another_edit(client, house):
    expense_id = await money.add_expense(house, 100, 12050, None, "2026-10-12", "house", "Старое", [])
    original = await money.get_expense(expense_id)
    payload = edit_payload(original, amount="250", description="Исправлено", date="2026-10-11")
    path = f"/api/houses/{house}/expenses/{expense_id}/edit"
    assert (await client.post(path, headers=headers(), json=payload)).status_code == 200
    assert (await client.post(path, headers=headers(), json=payload)).json()["unchanged"]
    assert (await money.pot_balance(house))["balance"] == -25000
    async with db.acquire() as conn:
        edits = await conn.fetch(
            "SELECT actor, before_json, after_json FROM expense_edits WHERE expense_id = ?", expense_id,
        )
    assert len(edits) == 1 and edits[0]["actor"] == 100
    assert json.loads(edits[0]["before_json"])["amount_kop"] == 12050
    assert json.loads(edits[0]["after_json"])["amount_kop"] == 25000


async def test_expense_edit_requires_author_or_grant(client, house):
    await households.join_house(await households.get_house(house), 200, "Жилец")
    expense_id = await money.add_expense(house, 100, 12050, None, "2026-10-12", "house", "", [])
    payload = edit_payload(await money.get_expense(expense_id), description="Другой")
    path = f"/api/houses/{house}/expenses/{expense_id}/edit"
    assert (await client.post(path, headers=headers(200), json=payload)).status_code == 422
    await households.set_grant(house, 200, "manage_all_expenses", True)
    assert (await client.post(path, headers=headers(200), json=payload)).status_code == 200


async def test_foreign_expense_cannot_be_edited(client, house):
    foreign = await households.create_house(300, "Другой", "Другой дом")
    expense_id = await money.add_expense(foreign, 300, 12050, None, "2026-10-12", "house", "", [])
    payload = edit_payload(await money.get_expense(expense_id), description="Подмена")
    response = await client.post(f"/api/houses/{house}/expenses/{expense_id}/edit", headers=headers(), json=payload)
    assert response.status_code == 422
    assert (await money.get_expense(expense_id))["description"] == ""


async def test_concurrent_edits_do_not_overwrite_each_other(client, house):
    expense_id = await money.add_expense(house, 100, 12050, None, "2026-10-12", "house", "", [])
    original = await money.get_expense(expense_id)
    path = f"/api/houses/{house}/expenses/{expense_id}/edit"
    results = await asyncio.gather(*(
        client.post(path, headers=headers(), json=edit_payload(original, description=description))
        for description in ("Первая", "Вторая")
    ))
    assert sorted(result.status_code for result in results) == [200, 422]
    async with db.acquire() as conn:
        count = await conn.fetchrow("SELECT COUNT(*) AS n FROM expense_edits WHERE expense_id = ?", expense_id)
    assert count["n"] == 1


async def test_reimbursement_checks_current_version_and_retries_safely(client, house):
    expense_id = await money.add_expense(house, 100, 12050, None, "2026-10-12", "personal", "", [])
    original = await money.get_expense(expense_id)
    path = f"/api/houses/{house}/expenses/{expense_id}"
    await client.post(f"{path}/edit", headers=headers(), json=edit_payload(original, amount="150"))
    assert (await client.post(f"{path}/reimburse", headers=headers(),
                              json={"version": expense_version(original)})).status_code == 422
    current = await money.get_expense(expense_id)
    payload = {"version": expense_version(current)}
    assert (await client.post(f"{path}/reimburse", headers=headers(), json=payload)).status_code == 200
    assert (await client.post(f"{path}/reimburse", headers=headers(), json=payload)).status_code == 200
    assert (await money.pot_balance(house))["balance"] == -15000
    assert (await client.post(f"{path}/edit", headers=headers(),
                              json=edit_payload(await money.get_expense(expense_id), amount="170"))).status_code == 422


async def test_edit_and_reimburse_preserve_export_roundtrip_and_original_nonce(client, house):
    payload = {"request_id": str(uuid4()), "kind": "expense", "amount": "120.50",
               "date": "2026-10-12", "mode": "personal"}
    await client.post(f"/api/houses/{house}/transactions", headers=headers(), json=payload)
    expense_id = (await transactions.all_rows(house))[0]["id"]
    original = await money.get_expense(expense_id)
    await client.post(f"/api/houses/{house}/expenses/{expense_id}/edit", headers=headers(),
                      json=edit_payload(original, description="Уточнили"))
    current = await money.get_expense(expense_id)
    await client.post(f"/api/houses/{house}/expenses/{expense_id}/reimburse", headers=headers(),
                      json={"version": expense_version(current)})
    exported = await transfers.export_file(house, 100, "json")
    assert (await transfers.import_file(house, 100, exported, "json")) == (0, 1)
    retry = await client.post(f"/api/houses/{house}/transactions", headers=headers(), json=payload)
    assert retry.status_code == 200 and retry.json()["duplicate"]
    assert len(await transactions.all_rows(house)) == 1


async def test_search_summary_and_export_cover_all_pages(client, house):
    for index in range(25):
        await money.add_expense(house, 100, 100 + index, None, "2026-10-12", "house", f"Чай {index}", [])
    await money.add_expense(house, 100, 10000, None, "2026-10-12", "house", "Кофе", [])
    query = "all_months=true&q=чай&sort=largest"
    response = await client.get(f"/api/houses/{house}?{query}", headers=headers())
    data = response.json()
    assert response.status_code == 200 and data["total"] == 25 and len(data["rows"]) == 20
    assert data["rows"][0]["amount_kop"] == 124
    assert data["summary"]["expenses"] == sum(range(100, 125))
    export = await client.get(f"/api/houses/{house}/export/json?{query}", headers=headers())
    rows = export.json()["transactions"]
    assert len(rows) == 25 and all("Чай" in row["description"] for row in rows)


async def test_member_kind_and_waiting_return_filters(client, house):
    await households.join_house(await households.get_house(house), 200, "Жилец")
    await money.add_expense(house, 100, 100, None, "2026-10-12", "house", "", [])
    await money.add_expense(house, 200, 200, None, "2026-10-12", "personal", "", [])
    response = await client.get(
        f"/api/houses/{house}?all_months=true&member=200&mode=waiting_return", headers=headers(),
    )
    assert response.json()["total"] == 1 and response.json()["summary"]["waiting_return"] == 200
    assert response.json()["rows"][0]["can_edit"] is True
    member_view = await client.get(f"/api/houses/{house}?all_months=true&member=100", headers=headers(200))
    assert member_view.json()["rows"][0]["can_edit"] is False


async def test_audit_failure_rolls_back_financial_edit(client, house, monkeypatch):
    from infrastructure.db import _SqliteConn
    from services import web_commands

    expense_id = await money.add_expense(house, 100, 12050, None, "2026-10-12", "house", "", [])
    original = await money.get_expense(expense_id)
    insert = _SqliteConn.insert

    async def fail_audit(conn, sql, *args):
        if "INSERT INTO expense_edits" in sql:
            raise RuntimeError("audit unavailable")
        return await insert(conn, sql, *args)

    monkeypatch.setattr(_SqliteConn, "insert", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        await web_commands.edit_expense(house, 100, expense_id, edit_payload(original, amount="250"),
                                        expense_version(original))
    assert (await money.get_expense(expense_id))["amount_kop"] == 12050


async def test_return_between_read_and_edit_blocks_the_edit(house, monkeypatch):
    from infrastructure.repositories import money as repository
    from services import web_commands

    expense_id = await money.add_expense(house, 100, 12050, None, "2026-10-12", "personal", "", [])
    original = await money.get_expense(expense_id)
    edit = repository.edit_expense

    async def return_before_update(house_id, actor, before, after):
        await repository.reimburse_expense(expense_id, actor)
        return await edit(house_id, actor, before, after)

    monkeypatch.setattr(repository, "edit_expense", return_before_update)
    with pytest.raises(DomainError):
        await web_commands.edit_expense(house, 100, expense_id, edit_payload(original, amount="250"),
                                        expense_version(original))
    row = await money.get_expense(expense_id)
    assert row["reimbursed"] == 1 and row["amount_kop"] == 12050


async def test_local_date_search_and_departed_member_filter(client, house):
    await households.join_house(await households.get_house(house), 200, "Жилец")
    await money.add_expense(house, 200, 100, None, "2026-10-12", "house", "", [])
    await households.leave_house(house, 200)
    result = await client.get(f"/api/houses/{house}?all_months=true&q=12.10.2026&member=200", headers=headers())
    assert result.json()["total"] == 1
    assert any(person["id"] == 200 for person in result.json()["filter_members"])
