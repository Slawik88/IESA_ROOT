"""Curated important release posts: one screenshot, short caption, one destination.

Nothing is scheduled per commit or per game event. A creator explicitly previews
and publishes a deployed feature. Unknown delivery blocks automatic retries.
"""
import hashlib
import re

from core import official_updates as policy
from infrastructure.repositories import official_updates as repo


class PublicationError(ValueError):
    pass


class Rejected(Exception):
    pass


def digest(caption: str, image_digest: str, kind: str, version: str) -> str:
    return hashlib.sha256(f"{caption}\n{image_digest}\n{kind}\n{version}\n{policy.CHAT_ID}:{policy.THREAD_ID}".encode()).hexdigest()


async def draft(db, *, key: str, kind: str, caption: str, image: str, image_digest: str, version: str, actor: int) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{7,79}", key) or kind not in policy.DESTINATIONS:
        raise PublicationError("Проверьте ключ релиза и раздел.")
    caption = caption.strip()
    if not 30 <= len(caption) <= policy.MAX_CAPTION:
        raise PublicationError("Подпись: 30–900 символов, одна важная новость и понятный следующий шаг.")
    content = digest(caption, image_digest, kind, version)
    await repo.ensure_tables(db)
    await repo.create(db, key=key, kind=kind, caption=caption, image=image, image_digest=image_digest,
                      content_digest=content, version=version, actor=actor)
    row = await repo.get(db, key)
    if row["content_digest"] != content:
        raise PublicationError("Этот ключ уже закреплён за другим содержимым. Не меняйте просмотренный пост скрытно.")
    return row


async def publish(db, *, key: str, expected_digest: str, version: str, preflight, send) -> dict:
    await repo.ensure_tables(db)
    row = await repo.get(db, key)
    if not row or row["content_digest"] != expected_digest:
        raise PublicationError("Пост изменился или не найден. Сначала откройте предпросмотр.")
    if row["status"] == "sent":
        return {"ok": True, "replayed": True, "message_id": row["message_id"]}
    if row["asset_version"] != version:
        raise PublicationError("Версия приложения изменилась. Подготовьте актуальный скриншот и новый черновик.")
    await preflight(row)
    async with db.connection.transaction():
        await repo.lock(db)
        row = await repo.get(db, key)
        if row["status"] == "sent":
            return {"ok": True, "replayed": True, "message_id": row["message_id"]}
        if row["status"] in {"sending", "unknown"}:
            raise PublicationError("Предыдущая отправка не подтверждена. Сначала сверьте тему вручную; повтор заблокирован.")
        if await repo.uncertain_delivery(db):
            raise PublicationError("Другая публикация ещё отправляется или требует сверки. Дождитесь её результата.")
        if await repo.recently_sent(db):
            raise PublicationError("Важное обновление уже публиковалось за последние сутки. Объедините мелкие изменения в следующую сводку.")
        await repo.mark(db, key, "sending")
    try:
        message_id = await send(row)
    except Rejected:
        await repo.mark(db, key, "failed", error="Telegram отклонил отправку. Проверьте права, тему и изображение.")
        raise PublicationError("Telegram отклонил публикацию. Пост не отмечен доставленным.") from None
    except Exception:
        await repo.mark(db, key, "unknown", error="Ответ Telegram не получен. Перед повтором нужна ручная сверка темы.")
        raise PublicationError("Исход отправки неизвестен. Не отправляйте дубликат; сверьте тему.") from None
    await repo.mark(db, key, "sent", message_id=int(message_id))
    return {"ok": True, "message_id": int(message_id), "replayed": False}
