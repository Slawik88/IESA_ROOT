"""Terminal API for retired wager mini-games."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user, require_module
from services.skill_games import get_active_session_summary, refund_active_sessions

router = APIRouter(
    prefix="/games2",
    tags=["skill-games"],
    dependencies=[Depends(require_module("module_games"))],
)


class StakeRequest(BaseModel):
    stake: float


class CellRequest(BaseModel):
    cell: int


class GuessRequest(BaseModel):
    digits: list[int]


class AlchemySubmitRequest(BaseModel):
    session_id: int
    moves: list[str]


@router.get("/state")
async def skill_state(db=Depends(get_db), user=Depends(require_tg_user)):
    recovery = await get_active_session_summary(db, user["id"])
    return {
        "retired": True,
        "message": "Сапёр, Сейф и Алхимия со ставками закрыты. Актуальные игры находятся в Центре Предвестника.",
        **recovery,
    }


@router.post("/retire-active")
async def retire_active(db=Depends(get_db), user=Depends(require_tg_user)):
    result = await refund_active_sessions(db, user["id"])
    return {
        "ok": True,
        **result,
        "message": "Активные старые ставки возвращены по номиналу.",
    }


def _closed() -> None:
    raise HTTPException(410, "Старая игра со ставками закрыта. Откройте Центр Предвестника.")


@router.post("/sapper/start")
async def sapper_start(body: StakeRequest):
    _closed()


@router.post("/sapper/open")
async def sapper_open(body: CellRequest):
    _closed()


@router.post("/sapper/cashout")
async def sapper_cashout():
    _closed()


@router.post("/safe/start")
async def safe_start(body: StakeRequest):
    _closed()


@router.post("/safe/guess")
async def safe_guess(body: GuessRequest):
    _closed()


@router.post("/alchemy/start")
async def alchemy_start(body: StakeRequest):
    _closed()


@router.post("/alchemy/submit")
async def alchemy_submit(body: AlchemySubmitRequest):
    _closed()
