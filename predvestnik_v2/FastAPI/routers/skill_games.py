"""FastAPI/routers/skill_games.py — R7: интеллектуальные мини-игры (Сапёр, Сейф).
Тонкий адаптер над services/skill_games.py — вся логика и раскладки там
(server-authoritative, клиенту секреты не отдаются до конца сессии)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user, require_module
from core.constants import (
    SAPPER_MIN_BET, SAPPER_MAX_BET, SAFE_MIN_BET, SAFE_MAX_BET,
    SAFE_ATTEMPTS, SAFE_WIN_MULT, SKILL_GAME_COOLDOWN_MIN,
)
from infrastructure.repositories import minigames as mg_repo
from services import skill_games as sg

router = APIRouter(prefix="/games2", tags=["skill-games"],
                   dependencies=[Depends(require_module("module_games"))])


class StakeRequest(BaseModel):
    stake: float


class CellRequest(BaseModel):
    cell: int


class GuessRequest(BaseModel):
    digits: list[int]


@router.get("/state")
async def skill_state(db=Depends(get_db), user=Depends(require_tg_user)):
    """Лобби: активные сессии, лестница сапёра, лимиты, кулдаун."""
    uid = user["id"]
    sapper = await mg_repo.get_active(db, uid, "sapper")
    safe = await mg_repo.get_active(db, uid, "safe")
    since = await mg_repo.seconds_since_last_start(db, uid)
    cd = SKILL_GAME_COOLDOWN_MIN * 60
    return {
        "sapper": sg._sapper_public(sapper) if sapper else None,
        "safe": sg._safe_public(safe) if safe else None,
        "ladder": sg.sapper_ladder(),
        "limits": {
            "sapper": [SAPPER_MIN_BET, SAPPER_MAX_BET],
            "safe": [SAFE_MIN_BET, SAFE_MAX_BET],
        },
        "safe_attempts": SAFE_ATTEMPTS,
        "safe_win_mult": SAFE_WIN_MULT,
        "cooldown_left_sec": max(0, cd - since) if since is not None else 0,
    }


@router.post("/sapper/start")
async def sapper_start(body: StakeRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    r = await sg.sapper_start(db, user["id"], float(body.stake))
    if not r.get("ok"):
        raise HTTPException(400, r.get("error", "Ошибка."))
    return r


@router.post("/sapper/open")
async def sapper_open(body: CellRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    r = await sg.sapper_open(db, user["id"], int(body.cell))
    if not r.get("ok"):
        raise HTTPException(400, r.get("error", "Ошибка."))
    return r


@router.post("/sapper/cashout")
async def sapper_cashout(db=Depends(get_db), user=Depends(require_tg_user)):
    r = await sg.sapper_cashout(db, user["id"])
    if not r.get("ok"):
        raise HTTPException(400, r.get("error", "Ошибка."))
    return r


@router.post("/safe/start")
async def safe_start(body: StakeRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    r = await sg.safe_start(db, user["id"], float(body.stake))
    if not r.get("ok"):
        raise HTTPException(400, r.get("error", "Ошибка."))
    return r


@router.post("/safe/guess")
async def safe_guess(body: GuessRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    r = await sg.safe_guess(db, user["id"], [int(d) for d in body.digits])
    if not r.get("ok"):
        raise HTTPException(400, r.get("error", "Ошибка."))
    return r