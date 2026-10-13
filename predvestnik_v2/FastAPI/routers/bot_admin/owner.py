"""Маршруты владельцев чатов (ADM-02, этап 1: заглушка).

Владелец — отдельный принципал (`kind="owner"`, `rank=0`), а не ранг: ни `section()`, ни числовые проверки сотрудников
его не пропускают. Маршруты для владельцев живут только в этом роутере и со своими ответами; всё, что здесь не объявлено,
для них закрыто. До этапа 2 (решение по входу, свежая проверка владения, урезанные карточки) вход закрыт целиком.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from FastAPI.routers.bot_admin.auth import guard
from FastAPI.routers.bot_admin.safe import AdminRoute

router = APIRouter(prefix="/bot-admin/api/owner", tags=["bot-admin-owner"], route_class=AdminRoute)


async def owner_user() -> dict:
    raise HTTPException(403, "Вход для владельцев чатов пока не открыт.")


guard(owner_user)


@router.get("/me")
async def owner_me(user=Depends(owner_user)):
    return user
