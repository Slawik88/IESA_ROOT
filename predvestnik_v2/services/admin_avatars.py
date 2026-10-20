"""Фото людей для админки: подписанные ссылки и серверный кэш.

Фото берётся из Bot API (getUserProfilePhotos → getFile → download) и живёт в
памяти процесса: 6 часов, если фото есть, и 30 минут, если его нет. Токен бота
наружу не уходит: карточка получает относительную ссылку с коротким
HMAC-пропуском `uid:exp:sig`, а байты отдаёт /bot-admin/avatar/{uid}.
Отрицательный ID — чат: его фото берётся через getChat (photo.small_file_id), чтобы чат узнавался по картинке, как в Telegram.

Пропуск подписан ключом от BOT_TOKEN: нет токена — нет и ссылок, фронт покажет
инициал, а не битую картинку. Ссылку минтит `avatar_url()`; её вызывают только
ответы разделов, которые уже проверили права, поэтому у самой картинки
отдельного гейта нет — вместо него короткоживущий пропуск.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import time

import httpx

PHOTO_TTL = 6 * 3600          # позитивный кэш: фото меняется редко
MISS_TTL = 30 * 60            # негативный кэш: не долбим Bot API «безфотными»
TOKEN_TTL = 3 * 3600          # срок жизни подписанной ссылки
MAX_BYTES = 2 * 1024 * 1024   # больше Telegram-аватарок не бывает
MIN_SIDE = 160                # берём размер не меньше 160px по ширине
CACHE_MAX = 5000              # страховка от разрастания памяти

# Прозрачный плейсхолдер: под ним в карточке виден цветной кружок с инициалом,
# поэтому <img> не ломается и браузер не пишет ошибку в консоль.
PLACEHOLDER = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"></svg>'

_CACHE: dict[int, tuple[bytes | None, float]] = {}
_LOCKS: dict[int, asyncio.Lock] = {}
_SEM = asyncio.Semaphore(6)   # бережём Bot API: не больше 6 параллельных доборов


def _secret() -> bytes | None:
    token = os.getenv("BOT_TOKEN", "")
    return hashlib.sha256((token + ":admin-avatar").encode()).digest() if token else None


def create_token(user_id: int) -> str:
    """Подписанный пропуск на просмотр одной аватарки: '{uid}:{exp}:{hmac}'."""
    secret, uid = _secret(), int(user_id)
    if secret is None or uid == 0:
        return ""
    payload = f"{uid}:{int(time.time()) + TOKEN_TTL}"
    signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def verify_token(token: str) -> int | None:
    """UID из пропуска или None: подпись не сошлась, срок вышел, формат чужой."""
    secret = _secret()
    if secret is None or not token or len(token) > 128:
        return None
    try:
        uid_raw, expires_raw, signature = token.split(":")
        expected = hmac.new(secret, f"{uid_raw}:{expires_raw}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature) or time.time() > int(expires_raw):
            return None
        uid = int(uid_raw)
        return uid or None
    except (TypeError, ValueError):
        return None


def avatar_url(user_id: int | None) -> str | None:
    """Относительная ссылка на фото (BASE подставит фронт); None — покажем инициал."""
    try:
        uid = int(user_id or 0)
    except (TypeError, ValueError):
        return None
    if uid == 0:
        return None
    token = create_token(uid)
    return f"/bot-admin/avatar/{uid}?t={token}" if token else None


def attach(rows: list[dict], key: str = "id", field: str = "avatar") -> list[dict]:
    """In-place: rows[i][field] = подписанная ссылка по rows[i][key]."""
    for row in rows:
        row[field] = avatar_url(row.get(key))
    return rows


def image_mime(data: bytes) -> str:
    """Telegram отдаёт фото в разных форматах — не врём браузеру про JPEG."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _pick_size(sizes: list[dict]) -> dict | None:
    """Размеры идут от меньшего к большему: берём первый от 160px, иначе самый большой."""
    usable = [s for s in sizes if (s.get("width") or 0) >= MIN_SIDE]
    if usable:
        usable.sort(key=lambda s: (s.get("width") or 0, s.get("height") or 0))
        return usable[0]
    return sizes[-1] if sizes else None


async def _fetch_file(client, api: str, token: str, file_id: str) -> bytes | None:
    found = (await client.get(f"{api}/getFile", params={"file_id": file_id})).json()
    path = (found.get("result") or {}).get("file_path")
    if not found.get("ok") or not path:
        return None
    photo = await client.get(f"https://api.telegram.org/file/bot{token}/{path}")
    if photo.status_code != 200 or not photo.content or len(photo.content) > MAX_BYTES:
        return None
    return photo.content


async def _download(user_id: int) -> bytes | None:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return None
    api = f"https://api.telegram.org/bot{token}"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            if user_id < 0:   # чат: фото группы, маленький размер (160×160) — его и показываем
                chat = (await client.get(f"{api}/getChat", params={"chat_id": int(user_id)})).json()
                file_id = ((chat.get("result") or {}).get("photo") or {}).get("small_file_id") if chat.get("ok") else None
                if not file_id:
                    return None
                return await _fetch_file(client, api, token, file_id)
            answer = (await client.get(f"{api}/getUserProfilePhotos",
                                       params={"user_id": int(user_id), "limit": 1})).json()
            photos = (answer.get("result") or {}).get("photos") or []
            if not answer.get("ok") or not photos:
                return None
            size = _pick_size(photos[0])
            if not size or not size.get("file_id") or (size.get("file_size") or 0) > MAX_BYTES:
                return None
            found = (await client.get(f"{api}/getFile", params={"file_id": size["file_id"]})).json()
            path = (found.get("result") or {}).get("file_path")
            if not found.get("ok") or not path:
                return None
            photo = await client.get(f"https://api.telegram.org/file/bot{token}/{path}")
            if photo.status_code != 200 or not photo.content or len(photo.content) > MAX_BYTES:
                return None
            return photo.content
    except Exception:
        return None


async def bytes_for(user_id: int) -> bytes | None:
    """Кэшированные байты фото или None; «фото нет» тоже кэшируется."""
    uid = int(user_id)
    now = time.time()
    hit = _CACHE.get(uid)
    if hit and now - hit[1] < (PHOTO_TTL if hit[0] else MISS_TTL):
        return hit[0]
    lock = _LOCKS.get(uid)
    if lock is None:
        lock = _LOCKS[uid] = asyncio.Lock()
    async with lock:
        now = time.time()
        hit = _CACHE.get(uid)
        if hit and now - hit[1] < (PHOTO_TTL if hit[0] else MISS_TTL):
            return hit[0]
        async with _SEM:
            data = await _download(uid)
        if len(_CACHE) > CACHE_MAX:
            _CACHE.clear()
        if len(_LOCKS) > CACHE_MAX:
            _LOCKS.clear()
        _CACHE[uid] = (data, time.time())
        return data
