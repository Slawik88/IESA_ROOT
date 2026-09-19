"""Read-only Mini App history for the chat-native Mafia game."""
from fastapi import APIRouter, Depends

from FastAPI.deps import get_db, require_tab_enabled, require_tg_user
from services import mafia_v1 as mafia


router = APIRouter(prefix="/mafia-v1", tags=["mafia-v1"])
_feature_gate = Depends(require_tab_enabled("game_mafia_v1"))


@router.get("/me", dependencies=[_feature_gate])
async def my_mafia_history(db=Depends(get_db), user=Depends(require_tg_user)):
    """Statistics/history only: all game interaction remains in Telegram chat."""
    return await mafia.player_history(db, user_id=int(user["id"]))
