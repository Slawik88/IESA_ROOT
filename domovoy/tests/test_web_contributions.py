"""Правки взносов: состояния, участие, CAS, аудит и неизменный импортный ключ."""
import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from core import config
from core.transaction_versions import contribution_version
from infrastructure.db import db, _SqliteConn
from infrastructure.repositories import contribution_changes, transactions
from infrastructure.repositories import money as money_repo
from services import households, money, transfers, web_contributions
from web.app import create_app
from test_web import TOKEN, headers


@pytest.fixture
async def client(monkeypatch, database):
    monkeypatch.setattr(config, "BOT_TOKEN", TOKEN)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test") as client:
        yield client


@pytest.fixture
async def house(database):
    house_id = await households.create_house(100, "Владелец", "Правки взносов")
    await households.join_house(await households.get_house(house_id), 200, "Сосед")
    await households.join_house(await households.get_house(house_id), 300, "Другой сосед")
    return house_id


async def contribution(house_id: int, author: int = 200, status: str = "declared"):
    row = await money.declare_contribution(house_id, author, 10000, "2026-10-15", month="2026-10")
    if status != "declared":
        row = await money.resolve_contribution(row["id"], status == "confirmed", 100, house_id=house_id)
    return row


def payload(row, **values):
    return {"amount": "123.45", "date": "2026-09-12", "month": "2026-08",
            "version": contribution_version(row), **values}


def path(house_id, row, action="edit"):
    return f"/api/houses/{house_id}/contributions/{row['id']}/{action}"


async def test_journal_recent_and_direct_transaction_share_contribution_policy(client, house):
    own = await contribution(house)
    other = await contribution(house, 300)
    confirmed = await contribution(house, status="confirmed")
    rejected = await contribution(house, status="rejected")
    data = (await client.get(f"/api/houses/{house}?all_months=true", headers=headers(200))).json()
    rows = {row["id"]: row for row in data["rows"]}
    assert rows[own["id"]]["can_edit"] and rows[own["id"]]["can_delete"]
    for original in (other, confirmed, rejected):
        row = rows[original["id"]]
        assert not row["can_edit"] and not row["can_delete"] and row["read_only_reason"]
        assert row["version"] == contribution_version(original)
    assert all("can_delete" in row and row["version"] for row in data["recent"])
    endpoint = f"/api/houses/{house}/transactions/contribution/{own['id']}"
    direct = await client.get(endpoint, headers=headers(200))
    assert direct.json() == rows[own["id"]]
    assert (await client.get(endpoint)).status_code == 404
    foreign = await households.create_house(300, "Другой", "Другой дом")
    assert (await client.get(f"/api/houses/{foreign}/transactions/contribution/{own['id']}",
                             headers=headers(300))).status_code == 422
    owner_data = (await client.get(f"/api/houses/{house}?all_months=true", headers=headers())).json()
    assert all(row["can_edit"] and row["can_delete"] for row in owner_data["rows"])


async def test_own_pending_edit_keeps_status_and_audit_and_can_retry(client, house):
    row = await contribution(house)
    result = await client.post(path(house, row), headers=headers(200), json=payload(row))
    assert result.status_code == 200 and not result.json()["unchanged"]
    current = await money_repo.get_contribution(row["id"])
    assert (current["amount_kop"], current["paid_on"], current["month"], current["status"]) == (
        12345, "2026-09-12", "2026-08", "declared",
    )
    retry = await client.post(path(house, row), headers=headers(200), json=payload(row))
    assert retry.status_code == 200 and retry.json()["unchanged"]
    async with db.acquire() as conn:
        changes = await conn.fetch("SELECT * FROM contribution_changes WHERE contribution_id = ?", row["id"])
    assert len(changes) == 1 and changes[0]["actor"] == 200
    assert json.loads(changes[0]["before_json"])["amount_kop"] == 10000
    assert json.loads(changes[0]["after_json"])["amount_kop"] == 12345
    assert (await money.pot_balance(house))["balance"] == 0


@pytest.mark.parametrize("status", ["confirmed", "rejected"])
async def test_resolved_contribution_needs_confirmation_right_and_keeps_status(client, house, status):
    row = await contribution(house, status=status)
    assert (await client.post(path(house, row), headers=headers(200), json=payload(row))).status_code == 422
    assert (await client.post(path(house, row, "delete"), headers=headers(200),
                              json={"version": contribution_version(row)})).status_code == 422
    await households.set_grant(house, 300, "confirm_contributions", True)
    result = await client.post(path(house, row), headers=headers(300), json=payload(row))
    assert result.status_code == 200
    current = await money_repo.get_contribution(row["id"])
    assert current["status"] == status and current["tg_id"] == 200 and current["confirmed_by"] == 100
    assert (await money.pot_balance(house))["balance"] == (12345 if status == "confirmed" else 0)
    await households.set_grant(house, 300, "confirm_contributions", False)
    assert (await client.post(path(house, current, "delete"), headers=headers(300),
                              json={"version": contribution_version(current)})).status_code == 422


@pytest.mark.parametrize("change", [{"amount": "1.001"}, {"amount": "-1"}, {"amount": 1.5},
                                   {"date": "2099-01-01"}, {"month": "bad"}])
async def test_bad_values_are_rejected_without_change(client, house, change):
    row = await contribution(house)
    assert (await client.post(path(house, row), headers=headers(200), json=payload(row, **change))).status_code == 422
    assert contribution_version(await money_repo.get_contribution(row["id"])) == contribution_version(row)


async def test_foreign_house_and_other_pending_author_cannot_edit_or_delete(client, house):
    row = await contribution(house)
    foreign = await households.create_house(300, "Другой", "Чужой дом")
    for action, body in (("edit", payload(row)), ("delete", {"version": contribution_version(row)})):
        assert (await client.post(path(house, row, action), headers=headers(300), json=body)).status_code == 422
        assert (await client.post(path(foreign, row, action), headers=headers(300), json=body)).status_code == 422
    assert await money_repo.get_contribution(row["id"]) is not None


async def test_confirmation_between_read_and_write_blocks_old_form(client, house, monkeypatch):
    row = await contribution(house)
    real_edit = contribution_changes.edit

    async def confirm_before_write(*args):
        await money.resolve_contribution(row["id"], True, 100, house_id=house)
        return await real_edit(*args)

    monkeypatch.setattr(contribution_changes, "edit", confirm_before_write)
    result = await client.post(path(house, row), headers=headers(200), json=payload(row))
    assert result.status_code == 422
    current = await money_repo.get_contribution(row["id"])
    assert current["status"] == "confirmed" and current["amount_kop"] == 10000
    assert (await client.post(path(house, row, "delete"), headers=headers(),
                              json={"version": contribution_version(row)})).status_code == 422


@pytest.mark.parametrize("change", ["leave", "revoke"])
async def test_participation_or_right_revoked_before_commit_blocks_edit(client, house, monkeypatch, change):
    row = await contribution(house, status="confirmed" if change == "revoke" else "declared")
    actor = 300 if change == "revoke" else 200
    if change == "revoke":
        await households.set_grant(house, actor, "confirm_contributions", True)
    real_edit = contribution_changes.edit

    async def invalidate(*args):
        if change == "revoke":
            await households.set_grant(house, actor, "confirm_contributions", False)
        else:
            await households.leave_house(house, actor)
        return await real_edit(*args)

    monkeypatch.setattr(contribution_changes, "edit", invalidate)
    assert (await client.post(path(house, row), headers=headers(actor), json=payload(row))).status_code == 422
    assert (await money_repo.get_contribution(row["id"]))["amount_kop"] == 10000


async def test_parallel_edits_cannot_overwrite_each_other(client, house):
    row = await contribution(house)
    results = await asyncio.gather(*(client.post(path(house, row), headers=headers(200),
                                                 json=payload(row, amount=value)) for value in ("201", "202")))
    assert sorted(result.status_code for result in results) == [200, 422]
    async with db.acquire() as conn:
        audit = await conn.fetch("SELECT id FROM contribution_changes WHERE contribution_id = ?", row["id"])
    assert len(audit) == 1


async def test_delete_retry_has_one_audit_and_old_native_export_does_not_resurrect(client, house):
    row = await contribution(house, status="confirmed")
    exported = await transfers.export_file(house, 100, "json")
    body = {"version": contribution_version(row)}
    results = await asyncio.gather(*(client.post(path(house, row, "delete"), headers=headers(), json=body)
                                     for _ in range(2)))
    assert all(result.status_code == 200 for result in results)
    assert sorted(result.json()["duplicate"] for result in results) == [False, True]
    assert (await money.pot_balance(house))["balance"] == 0
    assert await transfers.import_file(house, 100, exported, "json") == (0, 1)
    assert await money_repo.get_contribution(row["id"]) is None
    async with db.acquire() as conn:
        audit = await conn.fetch("SELECT id FROM contribution_changes WHERE contribution_id = ?", row["id"])
    assert len(audit) == 1
    assert (await client.post(path(house, row, "delete"), headers=headers(300), json=body)).status_code == 422


async def test_web_original_intent_survives_edit_and_delete(client, house):
    original = {"request_id": str(uuid4()), "kind": "contribution", "amount": "100", "date": "2026-10-15"}
    endpoint = f"/api/houses/{house}/transactions"
    created = await client.post(endpoint, headers=headers(200), json=original)
    row = await money_repo.get_contribution(created.json()["id"])
    original_keys = await transactions.imported_keys(house)
    assert (await client.post(path(house, row), headers=headers(200), json=payload(row))).status_code == 200
    exported = await transfers.export_file(house, 100, "json")
    assert await transfers.import_file(house, 100, exported, "json") == (0, 1)
    assert (await client.post(endpoint, headers=headers(200), json=original)).json()["duplicate"]
    current = await money_repo.get_contribution(row["id"])
    assert current["amount_kop"] == 12345
    assert (await client.post(path(house, current, "delete"), headers=headers(200),
                              json={"version": contribution_version(current)})).status_code == 200
    assert (await client.post(endpoint, headers=headers(200), json=original)).json()["duplicate"]
    assert await transactions.imported_keys(house) == original_keys
    assert await money_repo.get_contribution(row["id"]) is None


@pytest.mark.parametrize("action", ["edit", "delete"])
async def test_audit_failure_rolls_back_contribution_mutation(client, house, monkeypatch, action):
    row = await contribution(house, status="confirmed")
    insert = _SqliteConn.insert

    async def fail_audit(conn, sql, *args):
        if "INSERT INTO contribution_changes" in sql:
            raise RuntimeError("audit unavailable")
        return await insert(conn, sql, *args)

    monkeypatch.setattr(_SqliteConn, "insert", fail_audit)
    body = payload(row) if action == "edit" else {"version": contribution_version(row)}
    with pytest.raises(RuntimeError, match="audit unavailable"):
        await client.post(path(house, row, action), headers=headers(), json=body)
    assert contribution_version(await money_repo.get_contribution(row["id"])) == contribution_version(row)
    assert (await money.pot_balance(house))["balance"] == 10000


@pytest.mark.parametrize("change", [{"amount": "1000"}, {"date": "2026-09-01"}, {"month": "2026-07"}])
async def test_decision_rejects_stale_amount_date_or_month_and_pending_versions_match(client, house, change):
    row = await contribution(house)
    overview = (await client.get(f"/api/houses/{house}?all_months=true", headers=headers())).json()
    pending = next(item for item in overview["pending"] if item["id"] == row["id"])
    journal = next(item for item in overview["rows"] if item["id"] == row["id"])
    assert pending["version"] == journal["version"] == contribution_version(row)
    endpoint = f"/api/houses/{house}/contributions/{row['id']}"
    assert (await client.post(endpoint, headers=headers(), json={"confirm": True})).status_code == 422
    original = {"amount": "100", "date": row["paid_on"], "month": row["month"], **change}
    edited = await client.post(path(house, row), headers=headers(200), json=payload(row, **original))
    assert edited.status_code == 200
    for decision in (True, False):
        stale = await client.post(endpoint, headers=headers(),
                                  json={"confirm": decision, "version": pending["version"]})
        assert stale.status_code == 422 and "Взнос изменился" in stale.json()["detail"]
    current = await money_repo.get_contribution(row["id"])
    assert current["status"] == "declared" and (await money.pot_balance(house))["balance"] == 0
    decision = {"confirm": True, "version": contribution_version(current)}
    assert (await client.post(endpoint, headers=headers(), json=decision)).status_code == 200
    retry = await client.post(endpoint, headers=headers(), json=decision)
    assert retry.status_code == 422 and "уже решён" in retry.json()["detail"]
    assert (await money.pot_balance(house))["balance"] == current["amount_kop"]


@pytest.mark.parametrize("change", [{"amount": "1000"}, {"date": "2026-09-01"}, {"month": "2026-07"}])
async def test_decision_cas_blocks_edit_between_check_and_status_sql(client, house, monkeypatch, change):
    row = await contribution(house)
    update_status = money_repo.set_contribution_status

    async def edit_before_status(*args, **kwargs):
        original = {"amount": "100", "date": row["paid_on"], "month": row["month"], **change}
        await web_contributions.edit(house, 200, row["id"], original, contribution_version(row))
        return await update_status(*args, **kwargs)

    monkeypatch.setattr(money_repo, "set_contribution_status", edit_before_status)
    result = await client.post(f"/api/houses/{house}/contributions/{row['id']}", headers=headers(),
                               json={"confirm": True, "version": contribution_version(row)})
    assert result.status_code == 422
    assert (await money_repo.get_contribution(row["id"]))["status"] == "declared"
    assert (await money.pot_balance(house))["balance"] == 0


async def test_simultaneous_confirm_and_author_edit_have_one_winner(client, house):
    row = await contribution(house)
    decision = client.post(f"/api/houses/{house}/contributions/{row['id']}", headers=headers(),
                           json={"confirm": True, "version": contribution_version(row)})
    edit = client.post(path(house, row), headers=headers(200), json=payload(row, amount="1000"))
    results = await asyncio.gather(decision, edit)
    assert sorted(result.status_code for result in results) == [200, 422]
    current = await money_repo.get_contribution(row["id"])
    assert (current["status"], current["amount_kop"]) in (("confirmed", 10000), ("declared", 100000))
