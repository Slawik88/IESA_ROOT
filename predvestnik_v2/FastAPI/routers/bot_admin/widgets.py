"""Вкладка «Виджеты» (только создатель, S30): плитка на каждый HTML-виджет, нажатие присылает его создателю в личку.

Адресат — всегда сам нажавший: виджеты в проде живут только в личке с ботом, и чужую личку отсюда не выбрать.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, Depends, HTTPException

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import guard, section
from FastAPI.routers.bot_admin.people import get_bot
from FastAPI.routers.bot_admin.safe import AdminRoute
from bot.chat.global_ranks import CREATOR
from bot.middlewares import outbound_throttle
from core import widgets as rules
from services import admin_people, widgets

router = APIRouter(prefix="/bot-admin/api/widgets", tags=["bot-admin"], route_class=AdminRoute)


async def creator(user=Depends(section("widgets"))):
    if int(user["rank"]) < CREATOR:
        raise HTTPException(403, "Виджеты пробует только создатель бота.")
    return user


guard(creator)


def _dm_error(exc: Exception) -> HTTPException:
    text = str(exc)
    if "chat not found" in text or "bot can't initiate" in text or "blocked" in text:
        return HTTPException(409, "Бот не может написать вам в личку: откройте диалог с ботом и нажмите «Старт».")
    if "method not found" in text.lower() or "not found" in text.lower():
        return HTTPException(409, "Telegram пока не знает виджетов для этого бота. Попробуйте позже.")
    return HTTPException(409, "Telegram отказал: " + text[:200])


@router.get("")
async def catalog(user=Depends(creator), db=Depends(get_db)):
    items = [{"key": s.key, "icon": s.icon, "title": s.title, "hint": s.hint, "size": rules.packed_size(rules.html(s.key))}
             for s in rules.REGISTRY.values()]
    return {"items": items, "limit": rules.MAX_PACKED_BYTES, "off": await widgets.switched_off(db)}


@router.post("/send")
async def send(data: dict = Body(...), user=Depends(creator), db=Depends(get_db)):
    key = str(data.get("key") or "")
    if rules.spec(key) is None:
        raise HTTPException(400, "Такого виджета нет.")
    try:
        with outbound_throttle.urgent():
            async with asyncio.timeout(rules.ANSWER_BUDGET_SEC):
                message = await widgets.send(get_bot(), db, user["id"], key)
    except TimeoutError:
        raise HTTPException(504, "Отправка заняла слишком много времени. Проверьте личку перед повтором.")
    except widgets.Refused as exc:
        raise HTTPException(409, str(exc))
    except Exception as exc:
        raise _dm_error(exc)
    await admin_people.audit(db, user["id"], "widget_test", details={"key": key, "message_id": message.message_id})
    return {"ok": True, "message": "Отправлено вам в личку."}
