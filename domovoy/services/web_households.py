"""Команды домашнего кабинета: настройки, жильцы, приглашения и уборка."""

from dataclasses import asdict
from urllib.parse import parse_qs, urlparse

from core import permissions as perms, settings_registry as registry
from core.constants import MAX_HOUSE_NAME_LEN, MAX_MEMBER_NAME_LEN
from infrastructure import repositories as repo
from services import cleaning, households, money, settings
from services.households import DomainError
from services.transaction_dates import parse_month


def _display_name(value: str) -> str:
    name = value.strip()
    if not name or len(name) > MAX_MEMBER_NAME_LEN:
        raise DomainError("Введите имя, которым вас будут видеть соседи")
    return name


async def create_house(actor: int, first_name: str, username: str | None, name: str, display_name: str) -> dict:
    display_name = _display_name(display_name)
    name = name.strip()
    await repo.users.upsert_user(actor, first_name, username)
    house_id, created = await households.create_house_once(actor, display_name, name)
    return {"house_id": house_id, "created": created}


def _invite_token(value: str) -> str:
    token = value.strip()
    if "://" in token:
        try:
            query = parse_qs(urlparse(token).query)
        except ValueError as exc:
            raise DomainError("Приглашение не распознано. Скопируйте ссылку или код полностью.") from exc
        token = (query.get("invite") or query.get("start") or [""])[0]
    token = token.removeprefix("join_")
    if (
        not token
        or len(token) > 128
        or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in token)
    ):
        raise DomainError("Приглашение не распознано. Скопируйте ссылку или код полностью.")
    return token


async def join_house(actor: int, first_name: str, username: str | None, invite: str, display_name: str) -> dict:
    display_name = _display_name(display_name)
    house = await households.get_house_by_invite(_invite_token(invite))
    if house is None:
        raise DomainError("Приглашение недействительно. Попросите новое у жильцов дома.")
    await repo.users.upsert_user(actor, first_name, username)
    joined = await households.join_house(house, actor, display_name)
    return {"house_id": house["id"], "joined": joined}


async def management(house_id: int, actor: int, month: str | None) -> dict:
    await households.require_member(house_id, actor)
    house = await households.get_house(house_id)
    membership = await households.membership(house_id, actor)
    values = await settings.house_settings(house_id)
    today = settings.house_today(values)
    month = parse_month(month or today[:7])
    await cleaning.ensure_days(house_id, today)
    permissions = {
        permission.code: await households.can(house_id, actor, permission.code) for permission in perms.PERMISSIONS
    }
    manageable = (
        {member["tg_id"] for member in await households.grantor_candidates(house_id, actor)}
        if permissions["manage_members"]
        else set()
    )
    members = [
        {
            **dict(member),
            "grants": sorted(await households.grants_of(house_id, member["tg_id"])),
            "can_manage": member["tg_id"] in manageable,
        }
        for member in await households.members(house_id)
    ]
    notify_definitions = [
        definition
        for definition in registry.NOTIFY_SETTINGS
        if not definition.for_owner_only or permissions["confirm_contributions"]
    ]
    notify_values = await settings.notify_settings(house_id, actor)
    version = await repo.schedule.get_latest_version(house_id)
    return {
        "house": {"id": house_id, "name": house["name"], "chat_bound": house["chat_id"] is not None},
        "actor": actor,
        "profile": {"display_name": membership["display_name"], "can_leave": membership["role"] != perms.ROLE_OWNER},
        "permissions": permissions,
        "permission_definitions": [asdict(permission) for permission in perms.PERMISSIONS],
        "house_settings": values,
        "house_setting_definitions": [asdict(definition) for definition in registry.HOUSE_SETTINGS],
        "notify_settings": {definition.key: notify_values[definition.key] for definition in notify_definitions},
        "notify_setting_definitions": [
            {
                **asdict(definition),
                "choice_labels": {channel: registry.channel_label(channel) for channel in registry.NOTIFY_CHANNELS},
            }
            for definition in notify_definitions
        ],
        "members": members,
        "categories": [dict(category) for category in await money.categories(house_id)],
        "schedule": {
            "weekday_map": await cleaning.weekday_map(house_id),
            "version": version["id"] if version else None,
            "history": [dict(day) for day in await cleaning.month_history(house_id, month)],
            "month": month,
            "today": today,
        },
    }


async def set_house_setting(house_id: int, actor: int, key: str, value) -> None:
    await households.require(house_id, actor, "manage_house_settings")
    definition = registry.HOUSE_SETTING_BY_KEY.get(key)
    if definition is None or type(value) is not type(definition.default):
        raise DomainError("Значение настройки не подходит")
    await settings.set_house_setting(house_id, key, value)


async def rename(house_id: int, actor: int, display_name: str) -> None:
    await households.require_member(house_id, actor)
    await households.rename_member(house_id, actor, _display_name(display_name))


async def rename_house(house_id: int, actor: int, name: str) -> None:
    await households.require(house_id, actor, "manage_house_settings")
    name = name.strip()
    if not name or len(name) > MAX_HOUSE_NAME_LEN:
        raise DomainError(f"Название дома — от 1 до {MAX_HOUSE_NAME_LEN} символов")
    await repo.houses.rename_house(house_id, name)


async def set_notification(house_id: int, actor: int, key: str, value: str) -> None:
    await households.require_member(house_id, actor)
    definition = registry.NOTIFY_SETTING_BY_KEY.get(key)
    if definition is None:
        raise DomainError("Неизвестное уведомление")
    if definition.for_owner_only:
        await households.require(house_id, actor, "confirm_contributions")
    await settings.set_notify_setting(house_id, actor, key, value)


async def invite(house_id: int, actor: int, *, rotate: bool = False) -> dict:
    await households.require(house_id, actor, "manage_members")
    token = (
        await households.new_invite_token(house_id)
        if rotate
        else (await households.get_house(house_id))["invite_token"]
    )
    return {"invite_token": token}


async def set_permission(house_id: int, actor: int, target: int, code: str, granted: bool) -> None:
    await households.require(house_id, actor, "manage_members")
    candidates = await households.grantor_candidates(house_id, actor)
    if not any(member["tg_id"] == target for member in candidates):
        raise DomainError("Нельзя менять права владельца, свои права или права выбывшего жильца")
    await households.set_grant(house_id, target, code, granted)


async def add_category(house_id: int, actor: int, name: str) -> dict:
    await households.require(house_id, actor, "manage_categories")
    return {"category_id": await money.add_category(house_id, name, reuse_existing=True)}


async def remove_category(house_id: int, actor: int, category_id: int) -> None:
    await households.require(house_id, actor, "manage_categories")
    await money.remove_category(house_id, category_id)


async def save_schedule(house_id: int, actor: int, weekday_map: dict[int, int | None], version: int | None) -> dict:
    await households.require(house_id, actor, "manage_schedule")
    values = await settings.house_settings(house_id)
    unchanged = weekday_map == await cleaning.weekday_map(house_id)
    result = await cleaning.save_weekday_map(
        house_id,
        weekday_map,
        settings.house_today(values),
        expected_version=version,
    )
    return {"version": result, "unchanged": unchanged}


async def close_cleaning(house_id: int, actor: int, day_id: int) -> None:
    await households.require_member(house_id, actor)
    values = await settings.house_settings(house_id)
    await cleaning.close_day_for(house_id, day_id, actor, settings.house_today(values))


async def cancel_cleaning(house_id: int, actor: int, day_id: int) -> None:
    await households.require_member(house_id, actor)
    await cleaning.cancel_day(house_id, day_id, actor)


async def leave(house_id: int, actor: int) -> None:
    await households.require_member(house_id, actor)
    await households.leave_house(house_id, actor)
