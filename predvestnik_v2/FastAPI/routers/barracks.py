"""Closed compatibility routes for the retired Barracks."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import require_tg_user

router = APIRouter(prefix="/barracks", tags=["barracks"])


class UnitRequest(BaseModel):
    unit_id: str


class SquadRequest(BaseModel):
    slots: dict[str, str | None]


@router.get("")
async def overview(user=Depends(require_tg_user)):
    _closed()


def _closed() -> None:
    raise HTTPException(410, "Старая Казарма закрыта. Откройте Разлом колокола.")


@router.post("/starter")
async def starter(body: UnitRequest, user=Depends(require_tg_user)):
    _closed()


@router.post("/summon")
async def summon(user=Depends(require_tg_user)):
    _closed()


@router.post("/levelup")
async def levelup(body: UnitRequest, user=Depends(require_tg_user)):
    _closed()


@router.post("/engrave")
async def engrave(body: UnitRequest, user=Depends(require_tg_user)):
    _closed()


@router.post("/unlock")
async def unlock(body: UnitRequest, user=Depends(require_tg_user)):
    _closed()


@router.post("/squad")
async def set_squad(body: SquadRequest, user=Depends(require_tg_user)):
    _closed()
