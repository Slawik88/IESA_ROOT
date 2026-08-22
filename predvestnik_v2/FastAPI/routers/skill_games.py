"""Terminal API for retired wager mini-games."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user, require_module
from services.skill_games import refund_active_sessions

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
    async with db.execute(
        "SELECT COUNT(*) AS count, COALESCE(SUM(stake), 0) AS stake "
        "FROM minigame_sessions WHERE user_id = ? AND status = 'active'",
        (user["id"],),
    ) as cursor:
        row = await cursor.fetchone()
    return {
        "retired": True,
        "message": "Сапёр, Сейф и Алхимия со ставками закрыты. Основная игра — Разлом колокола.",
        "active_count": int(row["count"] or 0) if row else 0,
        "refundable_mora": float(row["stake"] or 0) if row else 0.0,
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
    raise HTTPException(410, "Старая игра со ставками закрыта. Откройте Разлом колокола.")


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
