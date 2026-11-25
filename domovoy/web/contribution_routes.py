"""Тонкий адаптер правок взносов и открытия конкретной записи журнала."""
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from services import journal, web_contributions

router = APIRouter(prefix="/api/houses/{house_id}")


class ContributionEdit(BaseModel):
    amount: str = Field(min_length=1, max_length=32)
    date: str = Field(max_length=10)
    month: str = Field(default="", max_length=7)
    version: str = Field(min_length=64, max_length=64)


class ContributionRemoval(BaseModel):
    version: str = Field(min_length=64, max_length=64)


@router.post("/contributions/{contribution_id}/edit")
async def edit(request: Request, house_id: int, contribution_id: int, payload: ContributionEdit):
    return await web_contributions.edit(house_id, request.state.actor, contribution_id,
                                        payload.model_dump(), payload.version)


@router.post("/contributions/{contribution_id}/delete")
async def remove(request: Request, house_id: int, contribution_id: int, payload: ContributionRemoval):
    return await web_contributions.remove(house_id, request.state.actor, contribution_id, payload.version)


@router.get("/transactions/{kind}/{transaction_id}")
async def transaction(request: Request, house_id: int, kind: Literal["expense", "contribution"], transaction_id: int):
    return await journal.transaction(house_id, request.state.actor, kind, transaction_id)
