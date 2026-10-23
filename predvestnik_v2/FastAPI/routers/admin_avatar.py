"""admin_avatar.py — фотографии игроков для админских карточек.

Фото берутся из Bot API (getUserProfilePhotos → getFile → download) и
кэшируются на процесс (6 ч, включая негативный кэш «фото нет»). Bot-токен
наружу не уходит: фронт получает только подписанную ссылку и грузит байты
через этот роутер. Ссылку минтит `avatar_url()` — её вызывают ТОЛЬКО те
эндпоинты, которые уже проверили админские права (чат-модератор, глобальная
модерация, дев-консоль), поэтому отдельного гейта у картинки нет — вместо
него короткоживущий HMAC-токен на пару (user_id, срок).
"""
import asyncio
import hashlib
import hmac
import os
import time

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter(prefix="/admin/avatar", tags=["admin-avatar"])

_AVATAR_TTL = 6 * 3600          # позитивный кэш: фото меняется редко
_AVATAR_MISS_TTL = 30 * 60      # негативный кэш: не долбим Bot API «безфотными»
_TOKEN_TTL = 3 * 3600           # срок жизни подписанной ссылки
_MAX_BYTES = 2 * 1024 * 1024    # больше Telegram-аватарок не бывает
_MIN_SIDE = 160                 # берём размер не меньше 160px по ширине

_CACHE: dict[int, tuple[bytes | None, float]] = {}
_LOCKS: dict[int, asyncio.Lock] = {}
_SEM = asyncio.Semaphore(6)     # бережём Bot API: не больше 6 параллельных доборов

_PLACEHOLDER = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"></svg>'


def _img_mime(data: bytes) -> str:
    """Telegram отдаёт аватарки в разных форматах — не врём браузеру про JPEG."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _secret() -> bytes:
    return hashlib.sha256((os.getenv("BOT_TOKEN", "") + "admin-avatar").encode()).digest()


def create_avatar_token(user_id: int) -> str:
    """Подписанный пропуск на просмотр одной аватарки: '{uid}:{exp}:{hmac}'."""
    expires = int(time.time()) + _TOKEN_TTL
    payload = f"{int(user_id)}:{expires}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_avatar_token(token: str) -> int | None:
    try:
        uid_s, expires_s, sig = token.split(":")
        payload = f"{uid_s}:{expires_s}"
        expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig) or time.time() > int(expires_s):
            return None
        return int(uid_s)
    except Exception:
        return None


def avatar_url(user_id: int | None) -> str | None:
    """Относительная ссылка на аватарку для фронта (BASE подставит JS).

    None для некорректного ID; если BOT_TOKEN не задан, картинка вернёт
    плейсхолдер — ссылку всё равно отдаём, чтобы UI не мигал."""
    try:
        uid = int(user_id or 0)
    except (TypeError, ValueError):
        return None
    if uid <= 0:
        return None
    return f"/admin/avatar/{uid}?t={create_avatar_token(uid)}"


def attach_avatar_urls(rows: list[dict], key: str, field: str = "avatar_url") -> None:
    """In-place: rows[i][field] = подписанная ссылка по rows[i][key]."""
    for r in rows:
        r[field] = avatar_url(r.get(key))


def _pick_photo_size(sizes: list[dict]) -> dict | None:
    """Telegram отдаёт список размеров от меньшего к большему — берём первый
    достаточно крупный, иначе самый большой (маленькие фото лучше, чем никаких)."""
    usable = [s for s in sizes if (s.get("width") or 0) >= _MIN_SIDE]
    if usable:
        usable.sort(key=lambda s: (s.get("width") or 0, s.get("height") or 0))
        return usable[0]
    return sizes[-1] if sizes else None


async def _download(user_id: int) -> bytes | None:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return None
    api = f"https://api.telegram.org/bot{token}"
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{api}/getUserProfilePhotos",
                            params={"user_id": int(user_id), "limit": 1})
            data = r.json()
            photos = ((data.get("result") or {}).get("photos") or [])
            if not data.get("ok") or not photos:
                return None
            size = _pick_photo_size(photos[0])
            if not size or not size.get("file_id"):
                return None
            if (size.get("file_size") or 0) > _MAX_BYTES:
                return None
            f = (await c.get(f"{api}/getFile", params={"file_id": size["file_id"]})).json()
            path = ((f.get("result") or {}).get("file_path"))
            if not f.get("ok") or not path:
                return None
            img = await c.get(f"https://api.telegram.org/file/bot{token}/{path}")
            if img.status_code != 200 or not img.content or len(img.content) > _MAX_BYTES:
                return None
            return img.content
    except Exception:
        return None


async def avatar_bytes(user_id: int) -> bytes | None:
    """Кэшированные байты аватарки или None («нет фото» тоже кэшируется)."""
    now = time.time()
    hit = _CACHE.get(user_id)
    if hit and now - hit[1] < (_AVATAR_TTL if hit[0] else _AVATAR_MISS_TTL):
        return hit[0]
    lock = _LOCKS.get(user_id)
    if lock is None:
        lock = _LOCKS[user_id] = asyncio.Lock()
    async with lock:
        now = time.time()
        hit = _CACHE.get(user_id)
        if hit and now - hit[1] < (_AVATAR_TTL if hit[0] else _AVATAR_MISS_TTL):
            return hit[0]
        async with _SEM:
            data = await _download(user_id)
        if len(_CACHE) > 5000:      # страховка от разрастания (как _AVATAR_CACHE)
            _CACHE.clear()
        if len(_LOCKS) > 5000:
            _LOCKS.clear()
        _CACHE[user_id] = (data, time.time())
        return data


@router.get("/{user_id}")
async def admin_avatar(user_id: int, t: str = Query("", max_length=128)) -> Response:
    """Байты аватарки по подписанной ссылке. Без фото — прозрачный плейсхолдер:
    под ним в карточке виден цветной кружок с инициалом ника, `<img>` не ломается
    и браузер не пишет ошибку в консоль."""
    if verify_avatar_token(t) != int(user_id):
        raise HTTPException(403, "Ссылка устарела — обновите список.")
    data = await avatar_bytes(user_id)
    if not data:
        return Response(_PLACEHOLDER, media_type="image/svg+xml",
                        headers={"Cache-Control": "private, max-age=1800"})
    return Response(data, media_type=_img_mime(data),
                    headers={"Cache-Control": "private, max-age=21600"})
