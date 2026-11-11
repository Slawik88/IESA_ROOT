"""Раздел «Функции»: выключатели бота и сайта, события за звёзды владельца («Гонка за Пропуском»), проверка сайта на входе."""
from __future__ import annotations

import os

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from FastAPI.auth import verify_session_token, verify_webapp_data
from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from FastAPI.routers.bot_admin.safe import AdminRoute
from bot.chat.global_ranks import CREATOR
from services import admin_access, admin_people, pass_race
from services import feature_switches as fs

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"], route_class=AdminRoute)
_user = section("switches")
_ROOT = os.getenv("ROOT_PATH", "").rstrip("/")
_DEV_ID = int(os.getenv("DEVELOPER_ID", "0") or 0)


def _known(feature: str) -> bool:
    keys = {i["key"] for g in fs.catalog() for i in g["items"]}
    keys |= {x["key"] for g in fs.catalog() for i in g["items"] for x in i.get("items", [])}
    return feature in keys


@router.get("/switches")
async def get_switches(chat_id: int = 0, user=Depends(_user), db=Depends(get_db)):
    title = None
    if chat_id:
        admin_access.require_chat(user, chat_id)
        async with db.execute("SELECT chat_title FROM chat_settings WHERE chat_id = ?", (chat_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Чат не найден.")
        title = row[0] or str(chat_id)
    return {"catalog": fs.catalog(), "state": await fs.state(db, chat_id), "chat": {"id": chat_id, "title": title}}


@router.post("/switches")
async def set_switch(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    feature = str(data.get("feature") or "")
    chat_id = int(data.get("chat_id") or 0)
    if not _known(feature):
        raise HTTPException(400, "Неизвестная функция.")
    if chat_id:
        admin_access.require_chat(user, chat_id)
    if chat_id and feature.startswith("site"):
        raise HTTPException(400, "Сайт выключается только везде, не по чату.")
    if chat_id and feature == "group:widgets":
        raise HTTPException(400, "Виджеты живут только в личке с ботом: они выключаются только везде, не по чату.")
    if feature.startswith("event:"):
        _creator(user)
        if chat_id:
            raise HTTPException(400, "События включаются только везде, не по чату.")
    if chat_id:
        async with db.execute("SELECT 1 FROM chat_settings WHERE chat_id = ?", (chat_id,)) as cur:
            if not await cur.fetchone():
                raise HTTPException(404, "Чат не найден.")
    try:
        await fs.set_switch(db, chat_id, feature, bool(data.get("enabled")), actor_id=user["id"],
                            reason=str(data.get("reason") or ""))
    except pass_race.RaceError as exc:
        raise HTTPException(400, str(exc))
    await admin_people.audit(db, user["id"], "switch", chat_id=chat_id or None,
                             details={"feature": feature, "enabled": bool(data.get("enabled")), "chat": chat_id or None,
                                      "reason": str(data.get("reason") or "")[:200]})
    return await fs.state(db, chat_id)


# ── «Гонка за Пропуском»: места, проверка, отметки (только создатель: деньги) ─────────────────────────────

def _creator(user: dict) -> None:
    if user["rank"] < CREATOR:
        raise HTTPException(403, "Гонкой за Пропуском управляет только создатель.")


@router.get("/pass-race")
async def pass_race_state(user=Depends(_user), db=Depends(get_db)):
    _creator(user)
    await pass_race.announce_pending(db)   # запасной путь: место, о котором ещё не написали
    return await pass_race.admin_view(db)


@router.get("/pass-race/check/{uid}")
async def pass_race_check(uid: int, season: int = 0, user=Depends(_user), db=Depends(get_db)):
    _creator(user)
    return await pass_race.check_card(db, user_id=uid, season=season or None)


@router.post("/pass-race/mark")
async def pass_race_mark(data: dict = Body(...), user=Depends(_user), db=Depends(get_db)):
    _creator(user)
    try:
        uid, season = int(data.get("user_id") or 0), int(data.get("season") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "Нужны id игрока и сезон.")
    try:
        result = await pass_race.mark(db, user_id=uid, status=str(data.get("status") or ""), actor_id=user["id"],
                                      season=season or None, note=str(data.get("note") or ""))
    except pass_race.RaceError as exc:
        raise HTTPException(400, str(exc))
    return {**result, "race": await pass_race.admin_view(db)}


def _is_developer(request: Request) -> bool:
    init = request.headers.get("x-init-data", "")
    user = verify_webapp_data(init) if init else None
    uid = int(user["id"]) if user else verify_session_token(request.headers.get("x-session-token", ""))
    if not uid:   # загрузка страницы: заголовков нет, есть кука, выданная админкой
        from FastAPI.routers.bot_admin.auth import DEV_COOKIE
        uid = verify_session_token(request.cookies.get(DEV_COOKIE, ""))
    return bool(_DEV_ID) and uid == _DEV_ID


_CLOSED_PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/><title>Предвестник</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0e0f14;color:#e8e9ef;
font:16px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;text-align:center;padding:24px;box-sizing:border-box}
a{display:inline-flex;margin-top:14px;padding:11px 18px;border:1px solid #71694e;border-radius:14px;color:#f3df91;
text-decoration:none;background:#191921}</style></head>
<body><div><div style="font-size:42px">🔮</div><h2>Временно закрыто</h2><p>{reason}</p>
<a href="{admin_url}">Админ-панель</a></div></body></html>"""


async def site_gate(request: Request, call_next):
    """Выключенная часть сайта отвечает 503 до любого обработчика. Разработчик проходит, чтобы проверить починку."""
    area = fs.site_area(request.url.path, _ROOT)
    if area is False:
        return await call_next(request)
    features = ["site"] + ([f"site:{area}"] if area else [])
    try:
        hit = await fs.disabled(None, features, None)
    except Exception:
        return await call_next(request)   # выключатели недоступны — сайт не роняем
    if hit is None or _is_developer(request):
        return await call_next(request)
    reason = hit[1] or "Этот раздел временно выключен. Скоро вернём."
    if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
        import html
        closed_page = _CLOSED_PAGE.replace("{reason}", html.escape(reason))
        closed_page = closed_page.replace("{admin_url}", f"{_ROOT}/bot-admin")
        return HTMLResponse(closed_page, status_code=503)
    return JSONResponse({"detail": reason, "feature": hit[0]}, status_code=503)
