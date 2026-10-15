"""Ввод промокода игроком из Mini App: те же коды и те же награды, что у «бот промокод КОД» (services/promo_v2)."""
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from services import promo_player, promo_v2

router = APIRouter(prefix="/promo-v2", tags=["promo-v2"])

# Подбор кодов перебором: после FAILS_LIMIT неудачных вводов за FAILS_WINDOW секунд — 429. Память процесса, на воркер.
FAILS_LIMIT, FAILS_WINDOW = 10, 600
_fails: dict[int, deque] = defaultdict(deque)


def _fail_wait(user_id: int, now: float) -> int:
    queue = _fails[user_id]
    while queue and queue[0] <= now - FAILS_WINDOW:
        queue.popleft()
    if not queue:
        _fails.pop(user_id, None)
        return 0
    return int(queue[0] + FAILS_WINDOW - now) + 1 if len(queue) >= FAILS_LIMIT else 0


class RedeemRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


@router.get("/me")
async def me(db=Depends(get_db), user=Depends(require_tg_user)) -> dict:
    """Экран «Промокоды»: коды, которые игрок может забрать сейчас, и его история (services/promo_player)."""
    return await promo_player.player_view(db, int(user["id"]))


@router.post("/redeem")
async def redeem(body: RedeemRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    uid, now = int(user["id"]), time.monotonic()
    wait = _fail_wait(uid, now)
    if wait:
        raise HTTPException(429, f"Слишком много неверных кодов. Попробуйте через {(wait + 59) // 60} мин.")
    try:
        result = await promo_v2.redeem(db, user_id=uid, code=body.code, chat_id=None)
    except promo_v2.PromoError as exc:
        _fails[uid].append(now)
        raise HTTPException(400, str(exc))
    return {"ok": True, "code": result.code, "granted": result.granted}
