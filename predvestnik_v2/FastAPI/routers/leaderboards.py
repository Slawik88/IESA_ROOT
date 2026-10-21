"""Mini App leaderboards: message tops and win tops for Mafia/Minesweeper (Rhythm keeps its own router)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from FastAPI.deps import get_db, require_tab_enabled, require_tg_user
from services import leaderboards_v1

router = APIRouter(prefix="/leaderboards", tags=["leaderboards"])
_game_minesweeper_gate = Depends(require_tab_enabled("game_minesweeper_v2"))
_game_mafia_gate = Depends(require_tab_enabled("game_mafia_v1"))


async def _game_top(db, user, game: str, page: int) -> dict:
    try:
        return await leaderboards_v1.game_top(db, user_id=int(user["id"]), game=game, page=page)
    except Exception as exc:
        logger.exception("leaderboards.game failed")
        raise HTTPException(status_code=500, detail="Топ временно недоступен") from exc


@router.get("/game/minesweeper", dependencies=[_game_minesweeper_gate])
async def minesweeper_top(
    page: int = Query(default=0, ge=0, le=100), db=Depends(get_db), user=Depends(require_tg_user),
) -> dict:
    return await _game_top(db, user, "minesweeper", page)


@router.get("/game/mafia", dependencies=[_game_mafia_gate])
async def mafia_top(
    page: int = Query(default=0, ge=0, le=100), db=Depends(get_db), user=Depends(require_tg_user),
) -> dict:
    return await _game_top(db, user, "mafia", page)


@router.get("/messages")
async def messages_top(
    period: Literal["week", "all_time"] = "week", db=Depends(get_db), user=Depends(require_tg_user),
) -> dict:
    try:
        return await leaderboards_v1.message_top(db, user_id=int(user["id"]), period=period)
    except Exception as exc:  # the home screen degrades quietly, the failure stays in the log
        logger.exception("leaderboards.messages failed")
        raise HTTPException(status_code=500, detail="Топ временно недоступен") from exc


@router.get("/messages/full")
async def messages_top_full(
    scope: Literal["global", "chats", "local"] = "global",
    period: Literal["day", "week", "month", "all_time"] = "week",
    chat_id: int | None = Query(default=None),
    page: int = Query(default=0, ge=0, le=100),
    db=Depends(get_db), user=Depends(require_tg_user),
) -> dict:
    try:
        return await leaderboards_v1.message_top_page(
            db, user_id=int(user["id"]), scope=scope, period=period, chat_id=chat_id, page=page)
    except leaderboards_v1.NotAMember as exc:
        raise HTTPException(status_code=403, detail="Топ чата доступен только его участникам") from exc
    except Exception as exc:
        logger.exception("leaderboards.messages_full failed")
        raise HTTPException(status_code=500, detail="Топ временно недоступен") from exc
