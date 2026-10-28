"""Фото людей для админки: подписанные ссылки; сами фото — в общем кэше в базе.

Фото берёт services/avatar_photos.py (Bot API → 128 px WebP → таблица avatar_photos), поэтому
деплой его не теряет. Админка видит фото **всех** игроков, а не только VIP (правило Mini App
сюда не относится). Токен бота наружу не уходит: карточка получает относительную ссылку с
коротким HMAC-пропуском `uid:exp:sig`, а байты отдаёт /bot-admin/avatar/{uid}.

Пропуск подписан ключом от BOT_TOKEN: нет токена — нет и ссылок, фронт покажет
инициал, а не битую картинку. Ссылку минтит `avatar_url()`; её вызывают только
ответы разделов, которые уже проверили права, поэтому у самой картинки
отдельного гейта нет — вместо него короткоживущий пропуск.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time

from services import avatar_photos

TOKEN_TTL = 3 * 3600          # срок жизни подписанной ссылки

# Прозрачный плейсхолдер: под ним в карточке виден цветной кружок с инициалом,
# поэтому <img> не ломается и браузер не пишет ошибку в консоль.
PLACEHOLDER = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"></svg>'


def _secret() -> bytes | None:
    token = os.getenv("BOT_TOKEN", "")
    return hashlib.sha256((token + ":admin-avatar").encode()).digest() if token else None


def create_token(user_id: int) -> str:
    """Подписанный пропуск на просмотр одной аватарки: '{uid}:{exp}:{hmac}'."""
    secret, uid = _secret(), int(user_id)
    if secret is None or uid <= 0:
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
        return uid if uid > 0 else None
    except (TypeError, ValueError):
        return None


def avatar_url(user_id: int | None) -> str | None:
    """Относительная ссылка на фото (BASE подставит фронт); None — покажем инициал."""
    try:
        uid = int(user_id or 0)
    except (TypeError, ValueError):
        return None
    if uid <= 0:
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


async def bytes_for(user_id: int) -> bytes | None:
    """Фото игрока (WebP) или None; «фото нет» тоже кэшируется — в базе, на 30 минут."""
    return await avatar_photos.image_for_admin(int(user_id))
