"""HTTP-адаптер управления домом; авторизацию обеспечивает общий middleware."""

import json
from typing import Any
from urllib.parse import parse_qsl

from aiogram.exceptions import TelegramAPIError
from fastapi import APIRouter, Request
from loguru import logger
from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from core.constants import MAX_CATEGORY_NAME_LEN, MAX_HOUSE_NAME_LEN, MAX_MEMBER_NAME_LEN
from services import households, web_households
from services.households import DomainError

router = APIRouter(prefix="/api")


class CreateHouse(BaseModel):
    name: StrictStr = Field(min_length=1, max_length=MAX_HOUSE_NAME_LEN)
    display_name: StrictStr = Field(min_length=1, max_length=MAX_MEMBER_NAME_LEN)


class JoinHouse(BaseModel):
    invite_token: StrictStr = Field(min_length=1, max_length=2048)
    display_name: StrictStr = Field(min_length=1, max_length=MAX_MEMBER_NAME_LEN)


class Profile(BaseModel):
    display_name: StrictStr = Field(min_length=1, max_length=MAX_MEMBER_NAME_LEN)


class HouseName(BaseModel):
    name: StrictStr = Field(min_length=1, max_length=MAX_HOUSE_NAME_LEN)


class SettingValue(BaseModel):
    value: Any


class NotificationValue(BaseModel):
    value: StrictStr = Field(min_length=1, max_length=16)


class PermissionValue(BaseModel):
    granted: StrictBool


class DeleteHouse(BaseModel):
    confirm_name: StrictStr = Field(min_length=1, max_length=MAX_HOUSE_NAME_LEN)


class Heir(BaseModel):
    target: StrictInt


class Category(BaseModel):
    name: StrictStr = Field(min_length=1, max_length=MAX_CATEGORY_NAME_LEN)


class WeekSchedule(BaseModel):
    weekday_map: dict[int, StrictInt | None] = Field(min_length=1, max_length=1000)
    version: StrictInt | None


def actor_profile(request: Request) -> tuple[int, str, str | None]:
    """Берём имя только из уже проверенных Telegram initData, не из тела запроса."""
    try:
        raw = request.headers["authorization"][4:]
        user = json.loads(dict(parse_qsl(raw))["user"])
        if user["id"] != request.state.actor:
            raise ValueError("actor")
        name = user.get("first_name")
        username = user.get("username")
        return (
            request.state.actor,
            name[:128] if isinstance(name, str) and name else "Жилец",
            username if isinstance(username, str) else None,
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise DomainError("Откройте приложение заново из личного чата") from exc


@router.post("/houses")
async def create(request: Request, payload: CreateHouse):
    return await web_households.create_house(*actor_profile(request), payload.name, payload.display_name)


@router.post("/houses/join")
async def join(request: Request, payload: JoinHouse):
    return await web_households.join_house(*actor_profile(request), payload.invite_token, payload.display_name)


@router.get("/houses/{house_id}/management")
async def management(request: Request, house_id: int, month: str | None = None):
    return await web_households.management(house_id, request.state.actor, month)


@router.post("/houses/{house_id}/settings/{key}")
async def house_setting(request: Request, house_id: int, key: str, payload: SettingValue):
    await web_households.set_house_setting(house_id, request.state.actor, key, payload.value)
    return {"ok": True}


@router.post("/houses/{house_id}/profile")
async def profile(request: Request, house_id: int, payload: Profile):
    await web_households.rename(house_id, request.state.actor, payload.display_name)
    return {"ok": True}


@router.post("/houses/{house_id}/name")
async def house_name(request: Request, house_id: int, payload: HouseName):
    await web_households.rename_house(house_id, request.state.actor, payload.name)
    return {"ok": True}


@router.post("/houses/{house_id}/notifications/{key}")
async def notification(request: Request, house_id: int, key: str, payload: NotificationValue):
    await web_households.set_notification(house_id, request.state.actor, key, payload.value)
    return {"ok": True}


async def with_link(request: Request, result: dict) -> dict:
    """Код приглашения + готовая ссылка на бота, если Telegram доступен (иначе остаётся код)."""
    bot = request.app.state.bot
    if bot is None:
        return {**result, "link": None}
    try:
        username = (await bot.me()).username
    except (TelegramAPIError, OSError) as exc:
        logger.warning("Приглашение без ссылки: {}", exc)
        return {**result, "link": None}
    return {**result, "link": households.invite_link({"invite_token": result["invite_token"]}, username)}


@router.get("/houses/{house_id}/invite")
async def invite(request: Request, house_id: int):
    return await with_link(request, await web_households.invite(house_id, request.state.actor))


@router.post("/houses/{house_id}/invite/rotate")
async def rotate_invite(request: Request, house_id: int):
    return await with_link(request, await web_households.invite(house_id, request.state.actor, rotate=True))


@router.post("/houses/{house_id}/members/{target}/permissions/{code}")
async def permission(request: Request, house_id: int, target: int, code: str, payload: PermissionValue):
    await web_households.set_permission(house_id, request.state.actor, target, code, payload.granted)
    return {"ok": True}


@router.post("/houses/{house_id}/categories")
async def add_category(request: Request, house_id: int, payload: Category):
    return await web_households.add_category(house_id, request.state.actor, payload.name)


@router.delete("/houses/{house_id}/categories/{category_id}")
@router.post("/houses/{house_id}/categories/{category_id}/delete")
async def remove_category(request: Request, house_id: int, category_id: int):
    await web_households.remove_category(house_id, request.state.actor, category_id)
    return {"ok": True}


@router.post("/houses/{house_id}/categories/{category_id}/rename")
async def rename_category(request: Request, house_id: int, category_id: int, payload: Category):
    await web_households.rename_category(house_id, request.state.actor, category_id, payload.name)
    return {"ok": True}


@router.post("/houses/{house_id}/delete")
async def delete_house(request: Request, house_id: int, payload: DeleteHouse):
    return await web_households.delete_house(house_id, request.state.actor, payload.confirm_name, request.app.state.bot)


@router.post("/houses/{house_id}/owner")
async def transfer_ownership(request: Request, house_id: int, payload: Heir):
    return await web_households.transfer_ownership(house_id, request.state.actor, payload.target, request.app.state.bot)


@router.post("/houses/{house_id}/members/{target}/remove")
async def remove_member(request: Request, house_id: int, target: int):
    return await web_households.remove_member(house_id, request.state.actor, target, request.app.state.bot)


@router.post("/houses/{house_id}/cleaning/{day_id}/reopen")
async def reopen_cleaning(request: Request, house_id: int, day_id: int):
    await web_households.reopen_cleaning(house_id, request.state.actor, day_id)
    return {"ok": True}


@router.post("/houses/{house_id}/schedule")
async def schedule(request: Request, house_id: int, payload: WeekSchedule):
    return await web_households.save_schedule(house_id, request.state.actor, payload.weekday_map, payload.version)


@router.post("/houses/{house_id}/cleaning/{day_id}/close")
async def close_cleaning(request: Request, house_id: int, day_id: int):
    await web_households.close_cleaning(house_id, request.state.actor, day_id)
    return {"ok": True}


@router.post("/houses/{house_id}/cleaning/{day_id}/cancel")
async def cancel_cleaning(request: Request, house_id: int, day_id: int):
    await web_households.cancel_cleaning(house_id, request.state.actor, day_id)
    return {"ok": True}


@router.post("/houses/{house_id}/leave")
async def leave(request: Request, house_id: int):
    await web_households.leave(house_id, request.state.actor)
    return {"ok": True}
