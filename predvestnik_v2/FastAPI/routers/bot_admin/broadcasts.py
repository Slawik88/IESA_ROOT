"""Раздел «Рассылка»: сообщение от бота в чаты или игрокам в личку — всем или по сегменту, сразу или по расписанию."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from FastAPI.deps import get_db
from FastAPI.routers.bot_admin.auth import section
from FastAPI.routers.bot_admin.people import get_bot
from FastAPI.routers.bot_admin.safe import AdminRoute
from services import admin_people
from services import broadcasts as broadcasts_service

router = APIRouter(prefix="/bot-admin/api", tags=["bot-admin"], route_class=AdminRoute)
_user = section("broadcast")
_ready = False


async def _tables(db=Depends(get_db)):
    """Таблица рассылок создаётся при старте бота; если старт не дошёл до неё, создаём здесь (повторно безопасно)."""
    global _ready
    if not _ready:
        await broadcasts_service.ensure_schema(db)
        _ready = True


def _bad_markup(exc: Exception) -> HTTPException:
    text = str(exc)
    if "parse entities" in text or "Unsupported start tag" in text or "can't find end" in text:
        return HTTPException(400, "Ошибка в HTML-разметке: " + text.split("Bad Request:")[-1].strip()[:200])
    if "chat not found" in text or "bot can't initiate" in text or "blocked" in text:
        return HTTPException(409, "Бот не может написать вам в личку: откройте диалог с ботом и нажмите «Старт».")
    if "BUTTON_URL_INVALID" in text or "wrong http url" in text.lower():
        return HTTPException(400, "Telegram не принял ссылку кнопки.")
    return HTTPException(409, "Telegram отказал: " + text[:200])


def _button(data: dict):
    try:
        btn = broadcasts_service.normalize_button(data.get("button"))
    except broadcasts_service.BroadcastError as exc:
        raise HTTPException(400, str(exc))
    return {"text": btn[0], "url": btn[1]} if btn else None


def _markup_of(button):
    return broadcasts_service._markup(button["text"], button["url"]) if button else None


@router.get("/broadcasts")
async def broadcasts(user=Depends(_user), db=Depends(get_db), _=Depends(_tables)):
    return {"items": await broadcasts_service.listing(db),
            "audiences": [{"key": k, "title": t} for k, t in broadcasts_service.KINDS.items()],
            "sizes": await broadcasts_service.audience_sizes(db),
            "templates": await broadcasts_service.templates(db)}


@router.post("/broadcasts/preview")
async def broadcast_preview(data: dict = Body(...), user=Depends(_user), db=Depends(get_db), _=Depends(_tables)):
    """Сколько получателей у сегмента — до отправки."""
    try:
        return await broadcasts_service.preview(db, data.get("segment"), str(data.get("audience") or "") or None)
    except broadcasts_service.BroadcastError as exc:
        raise HTTPException(400, str(exc))


@router.post("/broadcasts/test")
async def broadcast_test(data: dict = Body(...), user=Depends(_user)):
    """Пробная отправка себе в личку: проверить вид, кнопку и HTML до рассылки."""
    text = str(data.get("text") or "").strip()
    if not 1 <= len(text) <= broadcasts_service.MAX_TEXT:
        raise HTTPException(400, f"Текст — от 1 до {broadcasts_service.MAX_TEXT} символов.")
    button = _button(data)
    try:
        await broadcasts_service.send(get_bot(), user["id"], text, bool(data.get("html")), _markup_of(button))
    except Exception as exc:
        raise _bad_markup(exc)
    return {"ok": True, "message": "Отправлено вам в личку."}


@router.get("/broadcasts/templates")
async def templates(user=Depends(_user), db=Depends(get_db), _=Depends(_tables)):
    return {"items": await broadcasts_service.templates(db)}


@router.post("/broadcasts/templates")
async def template_save(data: dict = Body(...), user=Depends(_user), db=Depends(get_db), _=Depends(_tables)):
    button = _button(data)
    try:
        tid = await broadcasts_service.save_template(db, user["id"], str(data.get("title") or ""),
                                                     str(data.get("text") or ""), bool(data.get("html")), button)
    except broadcasts_service.BroadcastError as exc:
        raise HTTPException(400, str(exc))
    await admin_people.audit(db, user["id"], "broadcast_template",
                             details={"template": tid, "title": str(data.get("title") or "")[:60], "removed": False})
    return {"ok": True, "id": tid, "message": "Шаблон сохранён.", "items": await broadcasts_service.templates(db)}


@router.delete("/broadcasts/templates/{tid}")
async def template_delete(tid: int, user=Depends(_user), db=Depends(get_db), _=Depends(_tables)):
    if not await broadcasts_service.delete_template(db, tid):
        raise HTTPException(404, "Шаблона нет.")
    await admin_people.audit(db, user["id"], "broadcast_template", details={"template": tid, "removed": True})
    return {"ok": True, "message": "Шаблон удалён.", "items": await broadcasts_service.templates(db)}


@router.post("/broadcasts")
async def broadcast_create(data: dict = Body(...), user=Depends(_user), db=Depends(get_db), _=Depends(_tables)):
    audience = str(data.get("audience") or "") or None
    text = str(data.get("text") or "").strip()
    html = bool(data.get("html"))
    button = _button(data)
    request_id = str(data.get("request_id") or "")[:64]
    try:   # сначала проверки, потом пробная отправка: отказ не должен оставлять администратору лишнее сообщение
        duplicate = await broadcasts_service.precheck(db, user["id"], audience, text, request_id,
                                                      segment=data.get("segment"), scheduled_at=data.get("scheduled_at"))
    except broadcasts_service.BroadcastError as exc:
        raise HTTPException(400, str(exc))
    if (html or button) and not duplicate:   # разметку и кнопку проверяем на себе: битое не уйдёт сотням получателей
        try:
            await broadcasts_service.send(get_bot(), user["id"], text, html, _markup_of(button))
        except Exception as exc:
            raise _bad_markup(exc)
    try:
        seg = broadcasts_service.normalize_segment(data.get("segment"), audience)
        made = await broadcasts_service.create(
            db, user["id"], audience, text, request_id, html,
            segment=seg, button=button, scheduled_at=data.get("scheduled_at"))
    except broadcasts_service.BroadcastError as exc:
        raise HTTPException(400, str(exc))
    if not made.new:
        return {"ok": True, "id": made.id, "message": "Уже создана."}
    await admin_people.audit(db, user["id"], "broadcast",
                             details={"audience": broadcasts_service.describe_segment(seg), "text": text[:500],
                                      "total": made.total, "broadcast": made.id, "scheduled": made.scheduled,
                                      "button": bool(button)})
    if made.scheduled:
        return {"ok": True, "id": made.id, "message": "Рассылка запланирована: получатели посчитаются в момент отправки."}
    await broadcasts_service.launch(get_bot(), broadcasts_service.pool_db_factory(), made.id)
    return {"ok": True, "id": made.id, "message": f"Рассылка запущена: {made.total} получателей."}


@router.get("/broadcasts/{bid}")
async def broadcast_report(bid: int, user=Depends(_user), db=Depends(get_db), _=Depends(_tables)):
    """Отчёт: сколько дошло, сколько ждёт, кому не дошло и почему."""
    rep = await broadcasts_service.report(db, bid)
    if not rep:
        raise HTTPException(404, "Рассылки нет.")
    return rep


@router.post("/broadcasts/{bid}/stop")
async def broadcast_stop(bid: int, user=Depends(_user), db=Depends(get_db), _=Depends(_tables)):
    if not await broadcasts_service.stop(db, bid):
        raise HTTPException(409, "Рассылка уже закончилась.")
    await admin_people.audit(db, user["id"], "broadcast_stop", details={"broadcast": bid})
    return {"ok": True, "message": "Рассылка остановлена."}


@router.post("/broadcasts/{bid}/resume")
async def broadcast_resume(bid: int, user=Depends(_user), db=Depends(get_db), _=Depends(_tables)):
    """Продолжить прерванную или остановленную рассылку для тех, кому ещё не отправлено."""
    try:
        left = await broadcasts_service.resume(db, bid)
    except broadcasts_service.BroadcastError as exc:
        raise HTTPException(409, str(exc))
    await admin_people.audit(db, user["id"], "broadcast_resume", details={"broadcast": bid, "left": left})
    await broadcasts_service.launch(get_bot(), broadcasts_service.pool_db_factory(), bid)
    return {"ok": True, "message": f"Продолжаю: осталось {left}."}


@router.post("/broadcasts/{bid}/retry")
async def broadcast_retry(bid: int, user=Depends(_user), db=Depends(get_db), _=Depends(_tables)):
    """Новая рассылка того же сообщения тем, кому не дошло."""
    try:
        made = await broadcasts_service.retry_failed(db, user["id"], bid)
    except broadcasts_service.BroadcastError as exc:
        raise HTTPException(409, str(exc))
    await admin_people.audit(db, user["id"], "broadcast",
                             details={"audience": f"Повтор недоставленным (рассылка №{bid})", "text": "",
                                      "total": made.total, "broadcast": made.id})
    await broadcasts_service.launch(get_bot(), broadcasts_service.pool_db_factory(), made.id)
    return {"ok": True, "id": made.id, "message": f"Повторная отправка: {made.total} получателей."}
