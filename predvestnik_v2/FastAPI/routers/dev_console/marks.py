"""dev_console/marks.py: give and take back hand-given player marks. Every change needs a reason and lands in two logs."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from core.marks_v1 import MARKS
from infrastructure.repositories import admin_log
from services import marks_v1 as marks

from ._common import _send_admin_gift, require_console_perm

router = APIRouter()


class MarkRequest(BaseModel):
    user_id: int
    mark_id: str = Field(min_length=1, max_length=40)
    reason: str = Field(default="", max_length=200)


@router.get("/marks")
async def dev_marks(user_id: int = Query(...), db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "marks_manage")
    return await marks.admin_view(db, user_id)


async def _change(action: str, body: MarkRequest, db, user) -> dict:
    await require_console_perm(db, user, "marks_manage")
    try:
        title = await (marks.grant if action == "grant" else marks.revoke)(db, body.user_id, body.mark_id, int(user["id"]), body.reason)
    except marks.MarkConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    await admin_log.add(db, user["id"], body.user_id, "mark", f"{'+' if action == 'grant' else '-'} {title}", 1.0 if action == "grant" else -1.0,
                        body.reason, 0.0 if action == "grant" else 1.0, 1.0 if action == "grant" else 0.0)
    if action == "grant":
        await _send_admin_gift(db, body.user_id, [{"label": f"Регалия «{title}»", "amount": 1, "kind": "mark", "glyph": MARKS[body.mark_id]["glyph"]}], body.reason)
    await db.commit()
    return {"ok": True, "message": f"Метка «{title}» {'выдана' if action == 'grant' else 'снята'}."}


@router.post("/marks/grant")
async def dev_marks_grant(body: MarkRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    return await _change("grant", body, db, user)


@router.post("/marks/revoke")
async def dev_marks_revoke(body: MarkRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    return await _change("revoke", body, db, user)
