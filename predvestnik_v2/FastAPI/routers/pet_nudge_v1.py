"""Mini App adapter for the gentle pet reminder (core/pet_nudge_v1.py)."""
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from services import pet_nudge_v1 as service

router = APIRouter(prefix="/pet-nudge", tags=["pet-nudge"])


class AnswerRequest(BaseModel):
    choice: str = Field(pattern="^(open|later)$")


@router.post("/visit")
async def visit(db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    try:
        return await service.app_opened(db, int(user["id"]))
    except Exception:
        logger.exception("pet nudge visit failed")
        raise HTTPException(503, "Попробуйте позже.")


@router.post("/answer")
async def answer(body: AnswerRequest, db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    try:
        await service.answered(db, int(user["id"]), body.choice)
    except Exception:
        logger.exception("pet nudge answer failed")
        raise HTTPException(503, "Попробуйте позже.")
    return {"ok": True}
