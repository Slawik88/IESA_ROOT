"""Authenticated Mini App surface of the free games season pass (dark behind the season_pass_v1 flag)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.economy_ledger import ensure_tables as ensure_ledger_tables
from infrastructure.repositories.season_pass import ensure_tables
from services import season_pass

router = APIRouter(prefix="/season-pass", tags=["season-pass"])


class ClaimRequest(BaseModel):
    season: int = Field(ge=1, le=10_000)


@router.get("/me")
async def my_pass(db=Depends(get_db), user=Depends(require_tg_user)):
    await ensure_tables(db)
    return await season_pass.status(db, user_id=int(user["id"]))


@router.post("/claim")
async def claim_levels(body: ClaimRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        await ensure_tables(db)
        await ensure_ledger_tables(db)
        return await season_pass.claim(db, user_id=int(user["id"]), season=body.season)
    except season_pass.SeasonPassError as error:
        raise HTTPException(409, str(error)) from error
