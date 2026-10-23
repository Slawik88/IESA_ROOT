"""Online chat reports: only staff with access to the Reports section, with an audit trail."""
from typing import Literal
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from core.mafia_online import OnlineError
from infrastructure.repositories import mafia_online as repo
from services import admin_people, mafia_online_chat as chat

router = APIRouter(prefix="/bot-admin/api/mafia-online-reports", tags=["bot-admin"])
staff = section("reports")


class Decision(BaseModel):
    kind: Literal["hide", "mute", "unmute", "resolve"]


@router.get("")
async def reports(user=Depends(staff), db=Depends(get_db), resolved: bool = False,
                  before: Annotated[int, Query(ge=0, le=2**63-1)] = 0):
    items = await repo.reports(db, resolved, before)
    return {"items": items, "next_before": items[-1]["id"] if len(items)==100 else 0}


@router.post("/{message_id}")
async def decide(message_id: Annotated[int, Path(gt=0, le=2**63-1)], body: Decision, user=Depends(staff), db=Depends(get_db)):
    try:
        async with db.connection.transaction():
            message = await repo.get_message(db, message_id)
            if not message:
                raise HTTPException(404, "Сообщение не найдено.")
            if body.kind != "resolve":
                await chat.moderate(db, message["room_id"], int(user["id"]), body.kind,
                                   message_id=message_id, target=message["user_id"], staff=True)
            await repo.resolve_report(db, message_id, int(user["id"]))
            await admin_people.audit(db, int(user["id"]), "mafia_online_" + body.kind,
                                      user_id=message["user_id"],
                                      details={"room_id": message["room_id"], "message_id": message_id})
    except OnlineError as error:
        raise HTTPException(error.status, str(error)) from None
    return {"ok": True}
