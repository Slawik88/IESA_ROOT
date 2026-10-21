"""Раздел «Патч-ноуты»: черновики постов дня для официального канала, правка и отправка. Только создатель."""
from __future__ import annotations

import base64
import binascii
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import guard, section
from FastAPI.routers.bot_admin.people import get_bot
from core import patch_notes as rules
from core.official_updates import BOT_USERNAME
from infrastructure.repositories import patch_notes as repo, system_flags
from services import admin_people, patch_notes as service, patch_notes_format as fmt, patch_notes_send as sender

router = APIRouter(prefix="/bot-admin/api/patch-notes", tags=["patch-notes"])
_NOTE_RE = re.compile(r"\d{4}-\d{2}-\d{2}(-[a-z0-9-]{1,40})?")


async def creator(user=Depends(section("patchnotes"))):
    if int(user["rank"]) < 6:
        raise HTTPException(403, "Патч-ноуты в официальный канал публикует только создатель.")
    return user


guard(creator)


class EditBody(BaseModel):
    revision: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=20000)
    images: list[dict] = Field(default_factory=list, max_length=rules.MAX_IMAGES)
    button: dict | None = None


class RevisionBody(BaseModel):
    revision: int = Field(ge=1)


class UploadBody(BaseModel):
    data_base64: str = Field(min_length=100, max_length=14_000_000)


class SkipBody(BaseModel):
    skip: bool


class PublishBody(BaseModel):
    expected_digest: str = Field(pattern="^[a-f0-9]{64}$")
    confirm_flags: bool = False


class ReconcileBody(BaseModel):
    found: bool
    message_id: int | None = Field(default=None, gt=0)
    reason: str = Field(min_length=8, max_length=300)


async def _note(db, note_id: str) -> dict:
    if not _NOTE_RE.fullmatch(note_id):
        raise HTTPException(404, "Патч-ноут не найден.")
    await repo.ensure_tables(db)
    row = await repo.get(db, note_id)
    if not row:
        raise HTTPException(404, "Патч-ноут не найден. Обновите список.")
    return row


async def _disabled_flags(db, row: dict) -> list[str]:
    return [f for f in row["source_flags"] if not await system_flags.is_enabled(db, f)]


def _summary(row: dict) -> dict:
    keep = ("note_id", "note_date", "status", "edited", "source_newer", "error", "sent_at", "message_ids")
    title = fmt.plain_text(row["text_html"]).strip().split("\n", 1)[0][:90]
    return {k: row.get(k) for k in keep} | {"title": title, "images": len(row["images"])}


@router.get("")
async def notes(user=Depends(creator), db=Depends(get_db)):
    problems = await service.sync(db)
    library = sorted(p.name for p in rules.IMAGES_DIR.glob("*") if p.suffix in rules.IMAGE_EXT)[-80:] if rules.IMAGES_DIR.is_dir() else []
    return {"target": rules.UPDATES_URL, "topic_verified": await repo.topic_verified(db, rules.CHAT_ID, rules.THREAD_ID),
            "items": [_summary(r) for r in await repo.list_notes(db)], "problems": problems, "library": library,
            "buttons": [{"key": k, "label": v[0]} for k, v in rules.BUTTONS.items()],
            "limits": {"message": rules.MAX_MESSAGE, "caption": rules.MAX_CAPTION, "images": rules.MAX_IMAGES}}


@router.get("/{note_id}")
async def note(note_id: str, user=Depends(creator), db=Depends(get_db)):
    row = await _note(db, note_id)
    return {k: row.get(k) for k in ("note_id", "note_date", "status", "edited", "source_newer", "error", "revision",
                                    "text_html", "images", "button", "message_ids", "sent_at")} | {
        "source_text": row["source_text"] if row["source_newer"] else None,
        "digest": await service.content_digest(db, row), "plan": sender.describe(row["text_html"], len(row["images"])),
        "disabled_flags": await _disabled_flags(db, row)}


@router.get("/{note_id}/image")
async def image(note_id: str, ref: str = Query(max_length=120), title: str = Query(default="", max_length=80),
                kind: str = Query(default="new", max_length=8), user=Depends(creator), db=Depends(get_db)):
    await _note(db, note_id)
    try:
        data, mime = await service.image_bytes(db, note_id, {"ref": ref, "title": title, "kind": kind})
    except service.PatchNoteError as error:
        raise HTTPException(404, str(error))
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=300"})


@router.put("/{note_id}")
async def edit(note_id: str, body: EditBody, user=Depends(creator), db=Depends(get_db)):
    await _note(db, note_id)
    try:
        await service.edit(db, note_id, body.revision, body.text, body.images, body.button, int(user["id"]))
    except service.PatchNoteError as error:
        raise HTTPException(409, str(error))
    return await note(note_id, user, db)


@router.post("/{note_id}/reset")
async def reset(note_id: str, body: RevisionBody, user=Depends(creator), db=Depends(get_db)):
    await _note(db, note_id)
    if not await repo.reset_to_source(db, note_id, body.revision):
        raise HTTPException(409, "Черновик уже изменился или отправлен. Обновите страницу.")
    return await note(note_id, user, db)


@router.post("/{note_id}/upload")
async def upload(note_id: str, body: UploadBody, user=Depends(creator), db=Depends(get_db)):
    await _note(db, note_id)
    try:
        raw = base64.b64decode(body.data_base64.split(",", 1)[-1], validate=True)
        return await service.add_upload(db, note_id, raw, int(user["id"]))
    except (binascii.Error, ValueError) as error:
        raise HTTPException(400, str(error) if isinstance(error, service.PatchNoteError) else "Файл повреждён при загрузке.")


@router.post("/{note_id}/skip")
async def skip(note_id: str, body: SkipBody, user=Depends(creator), db=Depends(get_db)):
    await _note(db, note_id)
    if not await repo.set_skipped(db, note_id, body.skip):
        raise HTTPException(409, "Состояние поста уже другое. Обновите список.")
    await admin_people.audit(db, int(user["id"]), "patch_note_skip" if body.skip else "patch_note_restore", details={"note_id": note_id})
    return {"ok": True}


async def _preflight(db, row: dict, confirm_flags: bool) -> None:
    if os.environ.get("PREDVESTNIK_ENV", "production") != "production":
        raise service.PatchNoteError("Отправка в канал из тестового окружения отключена.")
    bot = get_bot()
    me = await bot.me()
    if str(me.username).lower() != BOT_USERNAME.lower():
        raise service.PatchNoteError("Это не рабочий Предвестник. Проверьте настройки экземпляра.")
    chat = await bot.get_chat(rules.CHAT_ID)
    member = await bot.get_chat_member(rules.CHAT_ID, me.id)
    if not chat.is_forum or member.status not in {"administrator", "creator"}:
        raise service.PatchNoteError("Бот не администратор официальной группы с темами.")
    if not await repo.topic_verified(db, rules.CHAT_ID, rules.THREAD_ID):
        raise service.PatchNoteError("Бот ещё не видел тему обновлений. Напишите в ней любое сообщение и повторите.")
    disabled = await _disabled_flags(db, row)
    if disabled and not confirm_flags:
        raise service.PatchNoteError("В посте есть функции, выключенные для игроков: " + ", ".join(disabled) + ".")


@router.post("/{note_id}/publish")
async def publish(note_id: str, body: PublishBody, user=Depends(creator), db=Depends(get_db)):
    await _note(db, note_id)

    async def preflight(row):
        await _preflight(db, row, body.confirm_flags)

    async def send(row):   # DeliveryUnknown несёт id уже ушедших частей: сервис запишет их для сверки
        return await sender.send(get_bot(), db, row)
    try:
        result = await service.publish(db, note_id, expected_digest=body.expected_digest, actor=int(user["id"]),
                                       preflight=preflight, send=send)
    except service.PatchNoteError as error:
        raise HTTPException(409, str(error))
    await admin_people.audit(db, int(user["id"]), "patch_note_publish", details={"note_id": note_id, "messages": result["message_ids"]})
    return result


@router.post("/{note_id}/reconcile")
async def reconcile(note_id: str, body: ReconcileBody, user=Depends(creator), db=Depends(get_db)):
    await _note(db, note_id)
    try:
        await service.reconcile(db, note_id, found=body.found, message_id=body.message_id)
    except service.PatchNoteError as error:
        raise HTTPException(409, str(error))
    await admin_people.audit(db, int(user["id"]), "patch_note_reconcile",
                             details={"note_id": note_id, "found": body.found, "message_id": body.message_id, "reason": body.reason})
    return {"ok": True}
