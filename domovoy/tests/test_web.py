"""Закрытый веб: чужая подпись, дом, отозванное участие и повтор записи."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import pytest

from core import config
from infrastructure.repositories import transactions
from infrastructure.repositories import schedule
from services import households
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
