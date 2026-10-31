"""
tests/test_permissions.py — права: владелец всемогущ, участники — по выдаче.
"""
import pytest

from core import permissions as perms
from services import households
from services.households import DomainError

OWNER = 100
ALLY = 200
STRANGER = 300


async def _house(database):
    house_id = await households.create_house(OWNER, "Владелец", "Дом прав")
    house = await households.get_house(house_id)
    await households.join_house(house, ALLY, "Напарник")
    return house


async def test_owner_has_all(database):
    house = await _house(database)
    for permission in perms.PERMISSIONS:
        assert await households.can(house["id"], OWNER, permission.code)


async def test_member_starts_empty(database):
    house = await _house(database)
    assert not await households.can(house["id"], ALLY, "manage_schedule")
    assert not await households.can(house["id"], STRANGER, "manage_schedule")


async def test_grant_revoke(database):
    house = await _house(database)
    hid = house["id"]
    await households.set_grant(hid, ALLY, "confirm_contributions", True)
    assert await households.can(hid, ALLY, "confirm_contributions")
    assert not await households.can(hid, ALLY, "manage_schedule")  # остальные не выданы

    await households.set_grant(hid, ALLY, "confirm_contributions", False)
    assert not await households.can(hid, ALLY, "confirm_contributions")


async def test_unknown_permission_code(database):
    house = await _house(database)
    with pytest.raises(ValueError):
        await households.can(house["id"], OWNER, "несуществующее")


async def test_require_raises_for_denied(database):
    house = await _house(database)
    with pytest.raises(DomainError):
        await households.require(house["id"], ALLY, "manage_members")


async def test_leave_house_rules(database):
    house = await _house(database)
    with pytest.raises(DomainError):
        await households.leave_house(house["id"], OWNER)  # владелец не выходит
    await households.leave_house(house["id"], ALLY)
    assert not await households.can(house["id"], ALLY, "manage_schedule")


async def test_settings_defaults_and_validation(database):
    """Реестр настроек: дефолты читаются, недопустимые значения отвергаются."""
    house = await _house(database)
    hid = house["id"]
    from services import settings as settings_service

    values = await settings_service.house_settings(hid)
    assert values["confirm_contributions"] is True
    assert values["morning_hour"] == 9

    await settings_service.set_house_setting(hid, "morning_hour", 7)
    assert (await settings_service.house_setting(hid, "morning_hour")) == 7

    from services.households import DomainError as Err
    with pytest.raises(Err):
        await settings_service.set_house_setting(hid, "morning_hour", 25)
    with pytest.raises(Err):
        await settings_service.set_house_setting(hid, "неизвестное", 1)
