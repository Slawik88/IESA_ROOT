"""Personal dust balances and confirmed VIP exchange; no client-owned rewards."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StrictInt
from loguru import logger
from FastAPI.deps import get_db, require_tab_enabled, require_tg_user
from core.star_dust import DustError
from services import star_dust as service

router = APIRouter(prefix='/star-dust', tags=['star-dust'])
gate = Depends(require_tab_enabled('star_dust_v1'))


class VipRequest(BaseModel):
    expected_user_id: StrictInt
    days: StrictInt = Field(ge=1, le=2147483647)
    expected_cost: StrictInt = Field(ge=100)
    action_id: str = Field(min_length=8, max_length=96)


async def guard(call):
    try: return await call
    except DustError as exc: raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        logger.exception('star dust request failed')
        raise HTTPException(503, 'Звёздная пыль временно недоступна. Повторите позже.') from exc


@router.get('/me', dependencies=[gate])
async def me(db=Depends(get_db), user=Depends(require_tg_user)):
    return await guard(service.overview(db, int(user['id'])))


@router.post('/vip', dependencies=[gate])
async def buy(body: VipRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    if body.expected_user_id != int(user['id']): raise HTTPException(403, 'Аккаунт изменился. Откройте меню заново.')
    return await guard(service.buy_vip(db, user_id=int(user['id']), **body.model_dump(exclude={'expected_user_id'})))
