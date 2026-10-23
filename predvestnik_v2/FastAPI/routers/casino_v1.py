"""Mini App adapter for the casino «Зал Фортуны» (core/casino_v1.py). Behind the global flag game_casino_v1."""
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field, StrictInt

from FastAPI.deps import get_db, require_tab_enabled, require_tg_user
from services import casino_v1 as service

router = APIRouter(prefix="/casino-v1", tags=["casino-v1"])
_gate = Depends(require_tab_enabled("game_casino_v1"))


class BuyRequest(BaseModel):
    mora: StrictInt
    action_id: str = Field(min_length=8, max_length=96)


class PlayRequest(BaseModel):
    game: str = Field(pattern="^(slots|wheel|dice)$")
    stake: StrictInt
    chance: StrictInt | None = None
    action_id: str = Field(min_length=8, max_length=96)


async def _guard(call):
    try:
        return await call
    except service.CasinoError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        logger.exception("casino request failed")
        raise HTTPException(503, "Казино временно недоступно. Попробуйте позже.") from exc


@router.get("/me", dependencies=[_gate])
async def me(db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    return await _guard(service.overview(db, int(user["id"])))


@router.post("/gift", dependencies=[_gate])
async def gift(db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    return await _guard(service.claim_gift(db, int(user["id"])))


@router.post("/buy", dependencies=[_gate])
async def buy(body: BuyRequest, db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    return await _guard(service.buy_chips(db, int(user["id"]), mora=body.mora, action_id=body.action_id))


@router.post("/play", dependencies=[_gate])
async def play(body: PlayRequest, db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    params = {"chance": body.chance} if body.game == "dice" else {}
    return await _guard(service.play(db, int(user["id"]), game=body.game, stake=body.stake, params=params,
                                     action_id=body.action_id))
