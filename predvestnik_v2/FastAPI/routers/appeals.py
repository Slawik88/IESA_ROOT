"""FastAPI/routers/appeals.py — admin_audit B1: апелляции ИГРОКА с сайта.

Работает и для ЗАБАНЕННЫХ (require_tg_user_base — без 403-гейта): оспорить санкцию
можно в любой момент и любым способом. Диалог един с ЛС-каналом бота: сообщения
и фото из обоих каналов попадают в одну нить.
"""
import base64
import json
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user_base
from infrastructure.repositories import global_moderation as gm_repo
from services import global_moderation as gmod

router = APIRouter(prefix="/appeals", tags=["appeals"])

DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", "0") or 0)


@router.get("/my")
async def my_appeal(db=Depends(get_db), user=Depends(require_tg_user_base)):
    """Моя санкция + открытая апелляция с нитью (для формы на сайте)."""
    uid = int(user["id"])
    sanction = await gm_repo.get_active_sanction_for_user(db, uid)
    appeal = await gm_repo.get_open_appeal(db, uid)
    thread = await gm_repo.appeal_thread(db, appeal["id"]) if appeal else []
    return {
        "sanction": ({
            "id": sanction["id"], "type": sanction["sanction_type"],
            "reason": sanction.get("reason"),
            "expires_at": sanction["expires_at"].isoformat() if sanction.get("expires_at") else None,
        } if sanction else None),
        "appeal": ({"id": appeal["id"], "status": appeal["status"]} if appeal else None),
        "thread": [
            {"is_staff": bool(m["is_staff"]), "text": m["text"],
             "photos": json.loads(m.get("photos_json") or "[]"),
             "created_at": str(m["created_at"])}
            for m in thread
        ],
    }


class AppealMessageRequest(BaseModel):
    text: str = ""
    photo_ids: list[str] = []


@router.post("/message")
async def appeal_message(body: AppealMessageRequest, db=Depends(get_db),
                         user=Depends(require_tg_user_base)):
    """Сообщение в нить апелляции (создаёт новую при активной санкции)."""
    uid = int(user["id"])
    ok, msg, appeal_id = await gmod.appeal_add_message(
        db, uid, body.text, body.photo_ids or [])
    if not ok:
        raise HTTPException(400, msg)
    await gmod.notify_staff_about_appeal(db, appeal_id, uid, body.text, DEVELOPER_ID)
    return {"ok": True, "message": msg, "appeal_id": appeal_id}


class AppealPhotoRequest(BaseModel):
    data_b64: str            # содержимое файла в base64 (без data:-префикса)
    filename: str = "photo.jpg"


@router.post("/photo")
async def appeal_photo(body: AppealPhotoRequest, db=Depends(get_db),
                       user=Depends(require_tg_user_base)):
    """Загрузка фото с сайта (base64-JSON — без multipart-зависимости) →
    пересылается в TG (хранилище = ЛС разработчика) → возвращает file_id для
    appeal_message. Фото с сайта и из ЛС живут в одном формате (Telegram
    file_id) и одинаково видны модерации."""
    uid = int(user["id"])
    if not await gm_repo.get_active_sanction_for_user(db, uid) \
            and not await gm_repo.get_open_appeal(db, uid):
        raise HTTPException(400, "Фото можно прикладывать только к апелляции.")
    try:
        raw = body.data_b64.split(",", 1)[-1]   # терпим data:image/...;base64,
        data = base64.b64decode(raw, validate=False)
    except Exception:
        raise HTTPException(400, "Не удалось прочитать файл.")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "Файл больше 8 МБ.")
    token = os.getenv("BOT_TOKEN", "")
    if not token or not DEVELOPER_ID:
        raise HTTPException(500, "Загрузка фото временно недоступна.")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data={"chat_id": str(DEVELOPER_ID),
                  "caption": f"📎 Вложение апелляции от {uid} (через сайт)",
                  "disable_notification": "true"},
            files={"photo": (body.filename or "photo.jpg", data)},
        )
    j = r.json()
    if not j.get("ok"):
        raise HTTPException(400, "Telegram отклонил файл (только изображения).")
    photos = j["result"].get("photo") or []
    if not photos:
        raise HTTPException(400, "Не удалось получить file_id.")
    return {"ok": True, "file_id": photos[-1]["file_id"]}
