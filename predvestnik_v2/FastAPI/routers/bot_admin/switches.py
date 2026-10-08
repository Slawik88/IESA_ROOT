"""Раздел «Функции»: выключатели бота и сайта, плюс проверка сайта на входе."""
from __future__ import annotations

import os

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from FastAPI.auth import verify_session_token, verify_webapp_data
from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from services import feature_switches as fs

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"])
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
    if chat_id and feature.startswith("site"):
        raise HTTPException(400, "Сайт выключается только везде, не по чату.")
    await fs.set_switch(db, chat_id, feature, bool(data.get("enabled")), actor_id=user["id"],
                        reason=str(data.get("reason") or ""))
    return await fs.state(db, chat_id)


def _is_developer(request: Request) -> bool:
    init = request.headers.get("x-init-data", "")
    user = verify_webapp_data(init) if init else None
    uid = int(user["id"]) if user else verify_session_token(request.headers.get("x-session-token", ""))
    return bool(_DEV_ID) and uid == _DEV_ID


_CLOSED_PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/><title>Предвестник</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0e0f14;color:#e8e9ef;
font:16px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;text-align:center;padding:24px}</style></head>
<body><div><div style="font-size:42px">🔮</div><h2>Временно закрыто</h2><p>{reason}</p></div></body></html>"""


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
        return HTMLResponse(_CLOSED_PAGE.replace("{reason}", html.escape(reason)), status_code=503)
    return JSONResponse({"detail": reason, "feature": hit[0]}, status_code=503)
