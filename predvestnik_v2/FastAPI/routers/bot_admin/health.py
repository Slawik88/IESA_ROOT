"""Вкладка «Состояние»: жив ли бот и база, ошибки, чаты без прав, очереди; настройка ежедневного отчёта владельцу."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from FastAPI.routers.bot_admin.people import get_bot
from FastAPI.routers.bot_admin.safe import AdminRoute
from bot.chat.global_ranks import CREATOR
from services import admin_people, bot_health, owner_digest

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"], route_class=AdminRoute)
_user = section("health")
bot_health.install()


@router.get("/health")
async def health(user=Depends(_user), db=Depends(get_db)):
    data = await bot_health.snapshot(db, get_bot())
    data["digest"] = {**await owner_digest.get_settings(db), "can_edit": user["rank"] >= CREATOR}
    return data


@router.post("/health/digest")
async def digest_settings(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    if user["rank"] < CREATOR:
        raise HTTPException(403, "Отчёт настраивает только владелец.")
    try:
        saved = await owner_digest.save_settings(db, user["id"], bool(data.get("enabled")), int(data.get("hour", 9)))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc) if "Час" in str(exc) else "Час отправки — число от 0 до 23.")
    await admin_people.audit(db, user["id"], "digest_settings", details=saved)
    return {"ok": True, "digest": {**saved, "can_edit": True}, "message": "Сохранено."}


@router.post("/health/digest/test")
async def digest_test(user=Depends(_user), db=Depends(get_db)):
    """Прислать отчёт за вчера себе в личку, чтобы увидеть, как он выглядит."""
    try:
        await owner_digest.send_now(get_bot(), db, user["id"])
    except Exception:
        raise HTTPException(409, "Бот не может написать вам в личку: откройте диалог с ботом и нажмите «Старт».")
    return {"ok": True, "message": "Отправлено вам в личку."}
