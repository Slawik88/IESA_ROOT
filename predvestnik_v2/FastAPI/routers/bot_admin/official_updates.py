"""Creator-only screenshot-led posts to the owner-designated official topic."""
import hashlib
import os
import re
from pathlib import Path

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section, guard
from FastAPI.routers.bot_admin.people import get_bot
from core import official_updates as policy
from infrastructure.repositories import official_updates as repo, system_flags
from services import official_updates as service

router = APIRouter(prefix="/bot-admin/api/official-updates", tags=["official-updates"])
ASSETS = Path(__file__).resolve().parents[2] / "static" / "announcements"


async def creator(user=Depends(section("broadcast"))):
    if int(user["rank"]) < 6:
        raise HTTPException(403, "Публиковать в официальной группе может создатель.")
    return user


guard(creator)


class DraftBody(BaseModel):
    release_key: str = Field(min_length=8, max_length=80)
    kind: str
    caption: str = Field(min_length=30, max_length=900)
    image_name: str


class PublishBody(BaseModel):
    expected_digest: str = Field(pattern="^[a-f0-9]{64}$")


class ReconcileBody(BaseModel):
    expected_digest: str = Field(pattern="^[a-f0-9]{64}$")
    message_id: int | None = Field(default=None, gt=0)
    confirmed_absent: bool = False
    reason: str = Field(min_length=12, max_length=300)


def image_path(name: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}\.png", name):
        raise HTTPException(400, "Выберите подготовленный PNG-скриншот.")
    path = ASSETS / name
    if not path.is_file() or not 1000 <= path.stat().st_size <= 9_000_000:
        raise HTTPException(400, "Скриншот не найден или его размер не подходит.")
    if path.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
        raise HTTPException(400, "Файл не является PNG.")
    return path


def version() -> str:
    from FastAPI.main import _ASSET_VER
    return _ASSET_VER


def public(row: dict) -> dict:
    label, url = policy.action(row["kind"])
    return {k: row.get(k) for k in ("release_key", "kind", "caption", "image_name", "content_digest", "asset_version", "status", "message_id", "error")} | {"button": label, "button_url": url}


@router.get("")
async def posts(user=Depends(creator), db=Depends(get_db)):
    await repo.ensure_tables(db)
    return {"target": policy.UPDATES_URL, "topic_verified": await repo.topic_verified(db, policy.CHAT_ID, policy.THREAD_ID),
            "items": [public(row) for row in await repo.list_posts(db)],
            "images": sorted(p.name for p in ASSETS.glob("*.png"))[:50], "kinds": list(policy.DESTINATIONS), "version": version()}


@router.post("/draft")
async def draft(body: DraftBody, user=Depends(creator), db=Depends(get_db)):
    path = image_path(body.image_name)
    try:
        row = await service.draft(db, key=body.release_key, kind=body.kind, caption=body.caption, image=body.image_name,
                                  image_digest=hashlib.sha256(path.read_bytes()).hexdigest(), version=version(), actor=int(user["id"]))
        return public(row)
    except service.PublicationError as error:
        raise HTTPException(409, str(error))


@router.post("/{key}/publish")
async def publish(key: str, body: PublishBody, user=Depends(creator), db=Depends(get_db)):
    async def preflight(row):
        if os.environ.get("PREDVESTNIK_ENV", "production") != "production":
            raise service.PublicationError("Публикация из тестового окружения отключена.")
        bot = get_bot()
        me = await bot.me()
        if str(me.username).lower() != policy.BOT_USERNAME.lower():
            raise service.PublicationError("Это не рабочий Предвестник. Проверьте настройки экземпляра.")
        chat = await bot.get_chat(policy.CHAT_ID)
        member = await bot.get_chat_member(policy.CHAT_ID, me.id)
        if not chat.is_forum or member.status != "administrator":
            raise service.PublicationError("Не подтверждены группа с темами и права рабочего бота.")
        if not await repo.topic_verified(db, policy.CHAT_ID, policy.THREAD_ID):
            raise service.PublicationError("Бот ещё не видел тему обновлений. Напишите в ней обычное сообщение, чтобы подтвердить назначение.")
        flag = policy.DESTINATIONS[row["kind"]][2]
        if flag and not await system_flags.is_enabled(db, flag):
            raise service.PublicationError("Объявляемая функция ещё не включена для игроков.")
        if hashlib.sha256(image_path(row["image_name"]).read_bytes()).hexdigest() != row["image_digest"]:
            raise service.PublicationError("Изображение изменилось после предпросмотра.")
    async def send(row):
        label, url = policy.action(row["kind"])
        try:
            message = await get_bot().send_photo(policy.CHAT_ID, FSInputFile(image_path(row["image_name"])),
                caption=row["caption"], message_thread_id=policy.THREAD_ID,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, url=url)]]))
            return message.message_id
        except (TelegramBadRequest, TelegramForbiddenError):
            raise service.Rejected() from None
    try:
        return await service.publish(db, key=key, expected_digest=body.expected_digest, version=version(), preflight=preflight, send=send)
    except service.PublicationError as error:
        raise HTTPException(409, str(error))


@router.post("/{key}/reconcile")
async def reconcile(key: str, body: ReconcileBody, user=Depends(creator), db=Depends(get_db)):
    from services import admin_people
    await repo.ensure_tables(db)
    async with db.connection.transaction():
        await repo.lock(db)
        row = await repo.get(db, key)
        if not row or row["content_digest"] != body.expected_digest or row["status"] not in {"sending", "unknown"}:
            raise HTTPException(409, "Публикация не требует сверки или изменилась.")
        async with db.execute("SELECT attempt_at<CLOCK_TIMESTAMP()-INTERVAL '2 minutes' FROM official_update_posts WHERE release_key=?", (key,)) as cursor:
            expired = bool((await cursor.fetchone())[0])
        if row["status"] == "sending" and not expired:
            raise HTTPException(409, "Отправка ещё может идти. Подождите две минуты.")
        if bool(body.message_id) == body.confirmed_absent:
            raise HTTPException(400, "Укажите найденное сообщение или подтвердите, что пост точно отсутствует.")
        await repo.mark(db, key, "sent" if body.message_id else "failed", message_id=body.message_id,
                        error=None if body.message_id else "Создатель подтвердил отсутствие публикации.")
        await admin_people.audit(db, int(user["id"]), "official_update_reconcile", details={"release_key": key, "message_id": body.message_id, "reason": body.reason})
    return {"ok": True}
