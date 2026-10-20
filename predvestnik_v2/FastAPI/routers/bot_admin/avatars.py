"""Фото админки (люди и чаты: у чата ID отрицательный): байты по подписанной ссылке.

Картинку грузит сам браузер (<img>), заголовков входа у него нет, поэтому
маршрут живёт вне /bot-admin/api и не требует сессии: доступ даёт короткий
HMAC-пропуск в адресе. Его минтит services.admin_avatars.avatar_url() только
в ответах разделов, которые уже проверили права.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from services import admin_avatars

router = APIRouter(tags=["bot-admin"])


@router.get("/bot-admin/avatar/{uid}", include_in_schema=False)
async def admin_avatar(uid: int, t: str = Query("", max_length=128)) -> Response:
    """Фото по подписанной ссылке. Без фото — прозрачный плейсхолдер: под ним
    виден цветной кружок с инициалом, <img> не ломается."""
    if admin_avatars.verify_token(t) != uid:
        raise HTTPException(403, "Ссылка на фото устарела — обновите список.")
    data = await admin_avatars.bytes_for(uid)
    if not data:
        return Response(admin_avatars.PLACEHOLDER, media_type="image/svg+xml",
                        headers={"Cache-Control": "private, max-age=1800"})
    return Response(data, media_type=admin_avatars.image_mime(data),
                    headers={"Cache-Control": "private, max-age=21600"})
