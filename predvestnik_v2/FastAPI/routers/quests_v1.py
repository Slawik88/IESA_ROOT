"""Authenticated Mini App surface for clear server-authoritative quests."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db, require_tg_user
from infrastructure.repositories.quests_v1 import ensure_tables
from infrastructure.repositories.economy_ledger import ensure_tables as ensure_ledger_tables
from services import quests_v1 as quests
from services.vip import is_vip_active


router = APIRouter(prefix='/quests-v1', tags=['quests-v1'])


class RerollRequest(BaseModel):
    period: str = Field(pattern='^(daily|weekly)$')
    slot: int = Field(ge=0, le=4)
    action_id: str = Field(min_length=1, max_length=96)


class RewardClaimRequest(BaseModel):
    kind: str = Field(pattern='^(daily|weekly|combined)$')


@router.get('/me')
async def my_quests(db=Depends(get_db), user=Depends(require_tg_user)):
    await ensure_tables(db)
    user_id = int(user['id'])
    sources = await quests.available_sources(db, user_id=user_id)
    return await quests.overview(db, user_id=user_id, vip_active=await is_vip_active(db, user_id), sources=sources)


@router.post('/reroll')
async def reroll_quest(body: RerollRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        await ensure_tables(db)
        user_id = int(user['id'])
        sources = await quests.available_sources(db, user_id=user_id)
        return await quests.reroll(db, user_id=user_id, vip_active=await is_vip_active(db, user_id),
                                   period=body.period, slot=body.slot, action_id=body.action_id, sources=sources)
    except (quests.QuestError, quests.QuestConflict) as error:
        raise HTTPException(409, str(error)) from error


@router.post('/claim-reward')
async def claim_quest_reward(body: RewardClaimRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    try:
        await ensure_tables(db)
        await ensure_ledger_tables(db)
        user_id = int(user['id'])
        sources = await quests.available_sources(db, user_id=user_id)
        return await quests.claim_reward(
            db, user_id=user_id, vip_active=await is_vip_active(db, user_id), kind=body.kind, sources=sources,
        )
    except (quests.QuestError, quests.QuestConflict) as error:
        raise HTTPException(409, str(error)) from error
