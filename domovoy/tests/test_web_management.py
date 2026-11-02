"""Управление домом через сайт: авторизация, права и безопасные повторы."""

import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx
import pytest

from core import config
from infrastructure.repositories import houses, schedule, users
from services import cleaning, households, money, settings
from web.app import create_app

TOKEN = "123456:TEST_HOME_BOT"


def headers(actor=100):
    values = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": actor, "first_name": "Имя Telegram", "username": "neighbor"}),
    }
    key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    check = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    values["hash"] = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    return {"Authorization": "tma " + urlencode(values)}


@pytest.fixture
async def client(monkeypatch, database):
    monkeypatch.setattr(config, "BOT_TOKEN", TOKEN)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test") as client:
        yield client


@pytest.fixture
async def house(database):
    house_id = await households.create_house(100, "Владелец", "Управление через сайт")
    await households.join_house(await households.get_house(house_id), 200, "Сосед")
    return house_id


async def test_new_telegram_user_can_create_and_retry_without_duplicate_home(client):
    actor = 971001
    results = await asyncio.gather(
        *[
            client.post(
                "/api/houses",
                headers=headers(actor),
                json={
                    "name": "Новый дом через сайт",
                    "display_name": "Саша",
                },
            )
            for _ in range(2)
        ]
    )
    assert all(result.status_code == 200 for result in results)
    assert results[0].json()["house_id"] == results[1].json()["house_id"]
    assert sorted(result.json()["created"] for result in results) == [False, True]
    user = await users.get_user(actor)
    assert user["first_name"] == "Имя Telegram" and user["username"] == "neighbor"
    homes = (await client.get("/api/houses", headers=headers(actor))).json()["houses"]
    assert len(homes) == 1


async def test_join_url_is_idempotent_and_does_not_rename_existing_member(client, house):
    token = (await households.get_house(house))["invite_token"]
    actor = 971002
    payload = {"invite_token": f"https://t.me/example_bot?start=join_{token}", "display_name": "Аня"}
    first = await client.post("/api/houses/join", headers=headers(actor), json=payload)
    second = await client.post(
        "/api/houses/join", headers=headers(actor), json={**payload, "display_name": "Другое имя"}
    )
    assert first.json() == {"house_id": house, "joined": True}
    assert second.json() == {"house_id": house, "joined": False}
    assert (await households.membership(house, actor))["display_name"] == "Аня"
    assert (await users.get_user(actor)) is not None


@pytest.mark.parametrize("invite", ["https://[", "https://example.test/?other=123", "has a space", "join_"])
async def test_malformed_invites_are_domain_errors(client, invite):
    result = await client.post(
        "/api/houses/join",
        headers=headers(300),
        json={
            "invite_token": invite,
            "display_name": "Сосед",
        },
    )
    assert result.status_code == 422


async def test_management_has_registry_permissions_and_no_invite_or_foreign_house(client, house):
    token = (await households.get_house(house))["invite_token"]
    result = await client.get(f"/api/houses/{house}/management", headers=headers(200))
    assert result.status_code == 200 and token not in result.text and "invite_token" not in result.text
    data = result.json()
    assert data["profile"] == {"display_name": "Сосед", "can_leave": True}
    assert not any(data["permissions"].values())
    assert not any(member["can_manage"] for member in data["members"])
    assert "contribution_declared" not in data["notify_settings"]
    assert {item["key"] for item in data["house_setting_definitions"]} == set(data["house_settings"])
    assert (await client.get(f"/api/houses/{house}/management", headers=headers(300))).status_code == 422


@pytest.mark.parametrize(
    "path,method,payload",
    [
        ("management", "GET", None),
        ("invite", "GET", None),
        ("settings/currency", "POST", {"value": "CHF"}),
        ("profile", "POST", {"display_name": "Имя"}),
        ("schedule", "POST", {"weekday_map": {"100": 0}}),
    ],
)
async def test_new_routes_share_private_authentication(client, house, path, method, payload):
    result = await client.request(method, f"/api/houses/{house}/{path}", json=payload)
    assert result.status_code == 404
    assert result.headers["cache-control"] == "no-store"


async def test_settings_require_grant_and_exact_registry_types(client, house):
    path = f"/api/houses/{house}/settings/morning_hour"
    assert (await client.post(path, headers=headers(200), json={"value": 8})).status_code == 422
    await households.set_grant(house, 200, "manage_house_settings", True)
    for invalid in (True, "8", 99, None, {}):
        assert (await client.post(path, headers=headers(200), json={"value": invalid})).status_code == 422
    assert (await client.post(path, headers=headers(200), json={"value": 8})).status_code == 200
    assert await settings.house_setting(house, "morning_hour") == 8
    assert (
        await client.post(f"/api/houses/{house}/settings/unknown", headers=headers(), json={"value": True})
    ).status_code == 422


async def test_house_rename_requires_house_permission_and_valid_name(client, house):
    path = f"/api/houses/{house}/name"
    original = (await households.get_house(house))["name"]
    for actor in (200, 300):
        assert (await client.post(path, headers=headers(actor), json={"name": "Чужое имя"})).status_code == 422
    for invalid in ("", "   ", "Д" * 33, 123, True):
        assert (await client.post(path, headers=headers(), json={"name": invalid})).status_code == 422
    assert (await households.get_house(house))["name"] == original
    result = await client.post(path, headers=headers(), json={"name": "  Наш дом  "})
    assert result.status_code == 200 and result.json() == {"ok": True}
    assert (await households.get_house(house))["name"] == "Наш дом"
    await households.set_grant(house, 200, "manage_house_settings", True)
    assert (await client.post(path, headers=headers(200), json={"name": "По договорённости"})).status_code == 200


async def test_management_chat_binding_is_boolean_without_chat_id(client, house):
    path = f"/api/houses/{house}/management"
    result = await client.get(path, headers=headers(200))
    assert result.json()["house"]["chat_bound"] is False
    await houses.set_chat(house, -1009876543210)
    result = await client.get(path, headers=headers(200))
    assert result.json()["house"]["chat_bound"] is True
    assert "chat_id" not in result.text and "1009876543210" not in result.text


async def test_profile_and_notifications_are_own_and_departure_revokes_access(client, house):
    assert (
        await client.post(f"/api/houses/{house}/profile", headers=headers(200), json={"display_name": " Новое имя "})
    ).status_code == 200
    assert (await households.membership(house, 200))["display_name"] == "Новое имя"
    assert (await households.membership(house, 100))["display_name"] == "Владелец"
    path = f"/api/houses/{house}/notifications/morning_reminder"
    assert (await client.post(path, headers=headers(200), json={"value": "off"})).status_code == 200
    assert (await settings.notify_settings(house, 200))["morning_reminder"] == "off"
    assert (await settings.notify_settings(house, 100))["morning_reminder"] == "private"
    assert (
        await client.post(
            f"/api/houses/{house}/notifications/contribution_declared", headers=headers(200), json={"value": "off"}
        )
    ).status_code == 422
    assert (await client.post(f"/api/houses/{house}/leave", headers=headers())).status_code == 422
    assert (await client.post(f"/api/houses/{house}/leave", headers=headers(200))).status_code == 200
    assert (await client.post(path, headers=headers(200), json={"value": "private"})).status_code == 422
    assert (await client.get(f"/api/houses/{house}/management", headers=headers(200))).status_code == 422


async def test_invite_is_separate_privileged_and_rotation_invalidates_old_code(client, house):
    path = f"/api/houses/{house}/invite"
    assert (await client.get(path, headers=headers(200))).status_code == 422
    old = (await client.get(path, headers=headers())).json()["invite_token"]
    current = (await client.post(path + "/rotate", headers=headers())).json()["invite_token"]
    assert old != current
    assert (
        await client.post(
            "/api/houses/join", headers=headers(300), json={"invite_token": old, "display_name": "Другой"}
        )
    ).status_code == 422
    assert (
        await client.post(
            "/api/houses/join", headers=headers(300), json={"invite_token": current, "display_name": "Другой"}
        )
    ).status_code == 200


async def test_member_manager_cannot_change_self_owner_or_foreign_member(client, house):
    base = f"/api/houses/{house}/members"
    assert (
        await client.post(base + "/200/permissions/manage_schedule", headers=headers(200), json={"granted": True})
    ).status_code == 422
    await households.set_grant(house, 200, "manage_members", True)
    for target in (100, 200, 300):
        assert (
            await client.post(
                base + f"/{target}/permissions/manage_schedule", headers=headers(200), json={"granted": True}
            )
        ).status_code == 422
    for granted in (True, True, False):
        assert (
            await client.post(base + "/200/permissions/manage_schedule", headers=headers(), json={"granted": granted})
        ).status_code == 200
    assert not await households.can(house, 200, "manage_schedule")


async def test_categories_require_right_and_cannot_remove_foreign_or_used(client, house):
    base = f"/api/houses/{house}/categories"
    assert (await client.post(base, headers=headers(200), json={"name": "Интернет"})).status_code == 422
    first = (await client.post(base, headers=headers(), json={"name": "Интернет"})).json()
    assert (await client.post(base, headers=headers(), json={"name": "интернет"})).json() == first
    foreign = await households.create_house(300, "Чужой", "Чужие категории")
    foreign_categories = (await client.get(f"/api/houses/{foreign}/management", headers=headers(300))).json()[
        "categories"
    ]
    assert (await client.delete(base + f"/{foreign_categories[0]['id']}", headers=headers())).status_code == 422
    assert (await client.delete(base + f"/{first['category_id']}", headers=headers())).status_code == 200
    category = (await client.post(base, headers=headers(), json={"name": "Книги"})).json()["category_id"]
    await money.add_expense(house, 100, 100, category, "2026-10-01", "house", "Книга", [])
    assert (await client.delete(base + f"/{category}", headers=headers())).status_code == 422


async def test_schedule_validates_members_rights_and_repeat_keeps_version(client, house):
    path = f"/api/houses/{house}/schedule"
    payload = {"weekday_map": {"100": 0, "200": 4}, "version": None}
    assert (await client.post(path, headers=headers(200), json=payload)).status_code == 422
    for invalid in ({"300": 0}, {"100": 7}, {"100": True}, {}):
        assert (
            await client.post(path, headers=headers(), json={"weekday_map": invalid, "version": None})
        ).status_code == 422
    first = (await client.post(path, headers=headers(), json=payload)).json()
    second = (await client.post(path, headers=headers(), json=payload)).json()
    assert not first["unchanged"] and second["unchanged"] and first["version"] == second["version"]
    data = (await client.get(f"/api/houses/{house}/management", headers=headers())).json()
    assert data["schedule"]["weekday_map"] == payload["weekday_map"]
    assert any(day["planned_date"] > data["schedule"]["today"] for day in data["schedule"]["history"])


async def test_schedule_stale_edit_after_bot_save_is_rejected_but_same_retry_is_safe(client, house):
    path = f"/api/houses/{house}/schedule"
    original = (await client.post(path, headers=headers(), json={"weekday_map": {"100": 0}, "version": None})).json()
    today = settings.house_today(await settings.house_settings(house))
    bot_version = await cleaning.save_weekday_map(house, {100: 2, 200: 4}, today)
    stale = await client.post(path, headers=headers(), json={"weekday_map": {"100": 1}, "version": original["version"]})
    assert stale.status_code == 422
    assert await cleaning.weekday_map(house) == {100: 2, 200: 4}
    retry = await client.post(
        path, headers=headers(), json={"weekday_map": {"100": 2, "200": 4}, "version": original["version"]}
    )
    assert retry.status_code == 200 and retry.json() == {"version": bot_version, "unchanged": True}


async def test_parallel_schedule_edits_from_same_version_cannot_overwrite_each_other(client, house):
    path = f"/api/houses/{house}/schedule"
    results = await asyncio.gather(
        *[
            client.post(path, headers=headers(), json={"weekday_map": {"100": weekday}, "version": None})
            for weekday in (0, 1)
        ]
    )
    assert sorted(result.status_code for result in results) == [200, 422]
    saved = next(index for index, result in enumerate(results) if result.status_code == 200)
    assert await cleaning.weekday_map(house) == {100: saved}


async def test_rotating_invite_between_lookup_and_join_prevents_membership(client, house, monkeypatch):
    token = (await households.get_house(house))["invite_token"]
    original = users.upsert_user

    async def rotate_before_join(actor, first_name, username):
        await original(actor, first_name, username)
        await households.new_invite_token(house)

    monkeypatch.setattr(users, "upsert_user", rotate_before_join)
    result = await client.post(
        "/api/houses/join", headers=headers(300), json={"invite_token": token, "display_name": "Сосед"}
    )
    assert result.status_code == 422
    assert await households.membership(house, 300) is None


async def test_parallel_category_creation_has_one_normalized_name(client, house):
    results = await asyncio.gather(
        *[
            client.post(f"/api/houses/{house}/categories", headers=headers(), json={"name": name})
            for name in ("Связь", "связь", " СВЯЗЬ ", "Связь")
        ]
    )
    assert all(result.status_code == 200 for result in results)
    assert len({result.json()["category_id"] for result in results}) == 1
    categories = await money.categories(house)
    assert sum(category["name"].casefold() == "связь" for category in categories) == 1


async def test_cleaning_close_cancel_scope_and_future_guard(client, house):
    today = settings.house_today(await settings.house_settings(house))
    await schedule.add_day(house, 200, today)
    day = next(day for day in await cleaning.days_on(house, today) if day["tg_id"] == 200)
    base = f"/api/houses/{house}/cleaning"
    assert (await client.post(base + f"/{day['id']}/cancel", headers=headers(200))).status_code == 422
    assert (await client.post(base + f"/{day['id']}/close", headers=headers(300))).status_code == 422
    assert (await client.post(base + f"/{day['id']}/close", headers=headers(200))).status_code == 200
    assert (await schedule.get_day(day["id"]))["status"] == "done"
    await schedule.add_day(house, 200, "2099-01-01")
    future = next(day for day in await cleaning.days_on(house, "2099-01-01") if day["tg_id"] == 200)
    assert (await client.post(base + f"/{future['id']}/close", headers=headers())).status_code == 422
    foreign = await households.create_house(300, "Другой", "Чужая уборка")
    assert (
        await client.post(f"/api/houses/{foreign}/cleaning/{future['id']}/cancel", headers=headers(300))
    ).status_code == 422
    assert (await client.post(base + f"/{future['id']}/cancel", headers=headers())).status_code == 200
