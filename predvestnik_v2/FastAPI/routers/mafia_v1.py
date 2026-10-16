"""Read-only Mini App history for the chat-native Mafia game."""
from fastapi import APIRouter, Depends, HTTPException, Query

from FastAPI.deps import get_db, require_tab_enabled, require_tg_user
from services import mafia_v1 as mafia


router = APIRouter(prefix="/mafia-v1", tags=["mafia-v1"])
_feature_gate = Depends(require_tab_enabled("game_mafia_v1"))


@router.get("/me", dependencies=[_feature_gate])
async def my_mafia_history(db=Depends(get_db), user=Depends(require_tg_user)):
    """Statistics/history only: all game interaction remains in Telegram chat."""
    return await mafia.player_history(db, user_id=int(user["id"]))


@router.get("/matches/{match_id}/review", dependencies=[_feature_gate])
async def match_review(match_id: int, page: int = Query(0, ge=0, le=1000),
                       db=Depends(get_db), user=Depends(require_tg_user)):
    from services.mafia_review import review
    result = await review(db, user_id=int(user["id"]), match_id=match_id, page=page)
    if result is None:
        raise HTTPException(404, "Разбор доступен участникам завершённой партии, состоящим в её чате.")
    return result
