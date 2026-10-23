"""Authenticated cross-chat Mafia API. Never invokes the local Mafia adapter."""
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field, model_validator

from FastAPI.deps import get_db, require_tab_enabled, require_tg_user
from core.mafia_online import FLAG, OnlineError
from services import global_moderation, mafia_online as game, mafia_online_chat as chat

router = APIRouter(prefix="/mafia-online", tags=["mafia-online"], dependencies=[Depends(require_tab_enabled(FLAG))])
MAX_ID = 2**63 - 1
RoomId = Annotated[int, Path(gt=0, le=MAX_ID)]


async def participant(user=Depends(require_tg_user), db=Depends(get_db)):
    if await global_moderation.is_blocked(db, int(user["id"])) or await global_moderation.ban_info(db, int(user["id"])):
        raise HTTPException(403, "Доступ к общим играм ограничен.")
    return user


class Settings(BaseModel):
    seats: int = Field(default=8, ge=4, le=20)
    tempo: Literal["fast", "normal", "slow"] = "normal"
    roles_auto: bool = True
    roles: list[Literal["doctor", "detective", "don"]] = Field(default_factory=list, max_length=3)
    vote_mode: Literal["secret", "open"] = "secret"
    visibility: Literal["public", "invite"] = "public"


class Join(BaseModel):
    invite: str = Field(default="", pattern=r"^(?:[0-9a-f]{16})?$", max_length=16)


class Control(BaseModel):
    command: Literal["start", "leave", "cancel", "pause", "resume", "skip", "settings", "claim"]
    phase_number: int | None = Field(default=None, ge=0)
    settings: Settings | None = None
    nonce: UUID | None = None
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid_settings(self):
        if self.command == "settings" and self.settings is None:
            raise ValueError("Для сохранения нужны настройки стола.")
        return self


class Action(BaseModel):
    phase_number: int = Field(ge=1)
    kind: Literal["vote", "mafia_target", "doctor_save", "detective_check"]
    target: int | None = Field(default=None, gt=0, le=MAX_ID)


class Message(BaseModel):
    channel: Literal["table", "mafia", "afterlife"] = "table"
    text: str = Field(min_length=1, max_length=600)
    nonce: UUID
    reply_to: int | None = Field(default=None, gt=0, le=MAX_ID)


class Moderation(BaseModel):
    kind: Literal["report", "hide", "mute", "unmute"]
    target: int | None = Field(default=None, gt=0, le=MAX_ID)
    message_id: int | None = Field(default=None, gt=0, le=MAX_ID)
    reason: str = Field(default="", max_length=200)


async def checked(awaitable):
    try:
        return await awaitable
    except OnlineError as error:
        raise HTTPException(error.status, str(error)) from None


@router.get("")
async def hub(user=Depends(participant), db=Depends(get_db)):
    return await checked(game.hub(db, int(user["id"])))


@router.post("/quick")
async def quick(user=Depends(participant), db=Depends(get_db)):
    return {"room_id": await checked(game.quick(db, user))}


@router.post("/rooms")
async def create(body: Settings, user=Depends(participant), db=Depends(get_db)):
    return {"room_id": await checked(game.create(db, user, **body.model_dump()))}


@router.post("/rooms/{room_id}/join")
async def join(room_id: RoomId, body: Join, user=Depends(participant), db=Depends(get_db)):
    return {"room_id": await checked(game.join(db, room_id, user, body.invite))}


@router.get("/rooms/{room_id}")
async def room(room_id: RoomId, channel: Literal["table", "mafia", "afterlife"] = "table",
               after: int = Query(0, ge=0, le=MAX_ID), before: int = Query(0, ge=0, le=MAX_ID), user=Depends(participant), db=Depends(get_db)):
    return await checked(game.get(db, room_id, int(user["id"]), channel, after, before))


@router.post("/rooms/{room_id}/control")
async def control(room_id: RoomId, body: Control, user=Depends(participant), db=Depends(get_db)):
    return await checked(game.control(db, room_id, int(user["id"]), body.command, body.phase_number,
                               nonce=body.nonce, expected_version=body.expected_version,
                               **(body.settings.model_dump() if body.settings else {})))


@router.post("/rooms/{room_id}/action")
async def action(room_id: RoomId, body: Action, user=Depends(participant), db=Depends(get_db)):
    await checked(game.action(db, room_id, int(user["id"]), body.phase_number, body.kind, body.target))
    return {"ok": True}


@router.post("/rooms/{room_id}/messages")
async def message(room_id: RoomId, body: Message, user=Depends(participant), db=Depends(get_db)):
    return await checked(chat.send(db, room_id, int(user["id"]), body.channel, body.text, body.nonce, body.reply_to))


@router.post("/rooms/{room_id}/moderation")
async def moderation(room_id: RoomId, body: Moderation, user=Depends(participant), db=Depends(get_db)):
    await checked(chat.moderate(db, room_id, int(user["id"]), **body.model_dump()))
    return {"ok": True}
