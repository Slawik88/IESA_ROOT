"""Кто открыл админку и что ему можно."""
from __future__ import annotations

import os

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, Response

from FastAPI.auth import create_session_token, session_issued_at, verify_session_token, verify_webapp_data, webapp_auth_date
from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.safe import AdminRoute
from bot.chat.global_ranks import BOT_RANKS, CREATOR, bot_rank_name, get_bot_rank
from infrastructure.preprod import require_preprod_user
from services import admin_access, admin_people, admin_security

# Минимальная глобальная роль для раздела (1 тестер … 5 разработчик, 6 создатель).
SECTIONS: dict[str, tuple[str, int]] = {
    "people": ("Игроки и чаты", 2),
    "reports": ("Жалобы", 2),
    "metrics": ("Метрики", 4),
    "journal": ("Журнал", 4),
    "broadcast": ("Рассылка", 5),
    "promo": ("Промокоды", 5),
    "switches": ("Функции", 5),
    "settings": ("Настройки", 5),
    "health": ("Состояние", 4),
    "access": ("Права", 6),   # только создатель: матрица прав ролей и вход владельцев чатов
}
router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"], route_class=AdminRoute)


async def identify(x_init_data: str, x_session_token: str, db) -> int:
    """Кто пришёл: подпись Telegram или сессия, стенд, «завершить сессии». Роль здесь не проверяется."""
    user_id, issued = None, None
    if x_init_data:
        data = verify_webapp_data(x_init_data)
        user_id = int(data["id"]) if data else None
        issued = webapp_auth_date(x_init_data) if user_id else None
    if not user_id and x_session_token:
        user_id = verify_session_token(x_session_token)
        issued = session_issued_at(x_session_token) if user_id else None
    if not user_id:
        raise HTTPException(401, "Войдите через Telegram.")
    if not require_preprod_user(int(user_id)):
        raise HTTPException(403, "Тестовый стенд закрыт для этого аккаунта.")
    revoked = await admin_security.revoked_before(db, int(user_id))
    if revoked and (issued is None or issued <= int(revoked)):   # вход начат до «завершить сессии» (время в целых секундах): нужен новый
        raise HTTPException(401, "Сессии завершены. Откройте админку заново: напишите боту «бот админка».")
    return int(user_id)


async def staff_user(x_init_data: str = Header(default=""), x_session_token: str = Header(default=""),
                     db=Depends(get_db)) -> dict:
    user_id = await identify(x_init_data, x_session_token, db)
    rank = await get_bot_rank(db, user_id)
    if rank <= 0:
        raise HTTPException(403, "Админка доступна только персоналу бота.")
    return admin_access.staff_principal(user_id, rank, await admin_access.load_grants(db))   # права ролей читаются на каждый запрос


def guard(dep):
    """Метка «эта зависимость — страж админки»: по ней тест-страж находит открытые маршруты."""
    dep.admin_guard = True
    return dep


guard(staff_user)


def section(key: str):
    """Зависимость: пользователь с ролью не ниже нужной для раздела."""
    async def check(user=Depends(staff_user)) -> dict:
        admin_access.require_staff(user)
        if user["rank"] < admin_access.min_rank(user, f"section:{key}", SECTIONS[key][1]):
            raise HTTPException(403, f"Раздел «{SECTIONS[key][0]}» вам недоступен.")
        return user
    return guard(check)


# Кука разработчика: при выключенном сайте обычная загрузка страниц идёт без заголовков
# авторизации, и только по ней site_gate узнаёт разработчика (switches._is_developer).
DEV_COOKIE = "pv_admin_dev"


@router.get("/badges")
async def badges(user=Depends(staff_user), db=Depends(get_db)):
    """Числа для значков на вкладках: сейчас — новые жалобы, которые никто ещё не взял."""
    out: dict[str, int] = {}
    if user["rank"] >= admin_access.min_rank(user, "section:reports", SECTIONS["reports"][1]):
        from services import reports as reports_service
        await reports_service._ensure(db)
        out["reports"] = (await reports_service.counts(db))["new"]
    return out


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else ""))


@router.get("/me")
async def me(request: Request, response: Response, user=Depends(staff_user), db=Depends(get_db)):
    try:   # вход в журнал; сбой журнала не должен закрывать админку
        via = "telegram" if request.headers.get("x-init-data") else "browser"
        note = await admin_security.record_login(db, user["id"], _client_ip(request), request.headers.get("user-agent", ""), via)
        if note["new_device"] and not admin_security.is_owner(user["id"], user["rank"]):
            who = await admin_security._name(db, user["id"])
            await admin_security.alert(db, f"Вход в админку с нового устройства: {who} ({admin_security.device_label(request.headers.get('user-agent', ''), via)}). "
                                           "Если это не он, завершите его сессии в карточке игрока.")
    except Exception as exc:
        from loguru import logger
        logger.warning(f"admin login journal skipped: {exc}")
    if user["rank"] >= CREATOR:
        response.set_cookie(DEV_COOKIE, create_session_token(user["id"]), httponly=True, secure=True,
                            samesite="none", path=(os.getenv("ROOT_PATH", "").rstrip("/") or "/"))
    return {
        "user_id": user["id"], "rank": user["rank"], "rank_name": bot_rank_name(user["rank"]),
        "sections": [{"key": k, "title": t, "min_rank": admin_access.min_rank(user, f"section:{k}", r)} for k, (t, r) in SECTIONS.items()
                     if user["rank"] >= admin_access.min_rank(user, f"section:{k}", r)],
        "ranks": [bot_rank_name(i) for i in range(len(BOT_RANKS))], "creator": user["rank"] >= CREATOR,
    }


@router.get("/logins")
async def logins(days: int = 30, user_id: int = 0, user=Depends(staff_user), db=Depends(get_db)):
    """Журнал входов в админку: только создатель (в нём адреса сотрудников)."""
    if user["rank"] < CREATOR:
        raise HTTPException(403, "Журнал входов видит только создатель.")
    return {"items": await admin_security.logins(db, days, user_id or None)}


@router.post("/sessions/revoke")
async def revoke_sessions(data: dict = Body(default={}), user=Depends(staff_user), db=Depends(get_db)):
    """Завершить сессии админки: свои (любой сотрудник) или всех сотрудников (только создатель)."""
    everyone = bool(data.get("all"))
    if everyone and user["rank"] < CREATOR:
        raise HTTPException(403, "Завершить сессии всех сотрудников может только создатель.")
    await admin_security.revoke(db, 0 if everyone else user["id"])
    await admin_people.audit(db, user["id"], "sessions_revoke", details={"all": everyone})
    await admin_security.after_action(db, user, "sessions_revoke")
    return {"ok": True, "message": "Сессии завершены. Откройте админку заново из Telegram: напишите боту «бот админка»."}
