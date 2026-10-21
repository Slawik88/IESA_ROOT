"""Патч-ноуты в официальный канал: черновики из файлов, правка создателем, отправка по кнопке.

Ничего не уходит само. Предвестник готовит пост дня из файла FastAPI/static/patch-notes/<дата>.json,
создатель проверяет и правит его в админке и сам нажимает «Отправить». Повтор и потерянный ответ Telegram
не создают дубль: неподтверждённая отправка блокирует новые до ручной сверки.
"""
from __future__ import annotations

import hashlib
import json
import re

from loguru import logger

from core import patch_notes as rules
from infrastructure.repositories import patch_notes as repo
from services import patch_notes_format as fmt


class PatchNoteError(ValueError):
    pass


class Rejected(Exception):
    """Telegram однозначно отказал; уже отправленные части удалены."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _button(key: str, label: str | None = None) -> dict:
    return {"key": key, "label": label or rules.BUTTONS[key][0]}


def _target(stem: str, rows: list[dict]) -> tuple[str, list[str]]:
    """Куда класть пункты файла: открытый черновик или новое дополнение; и какие пункты уже ушли (или пропущены)."""
    done = [r for r in rows if r["status"] not in repo.PENDING]
    used = [i for r in done for i in r["item_ids"]]
    open_rows = [r for r in rows if r["status"] in repo.PENDING]
    if open_rows:   # пункты другого открытого черновика (вернули из «Не публикуем») не дублируем
        target = open_rows[0]["note_id"]
        return target, used + [i for r in open_rows[1:] for i in r["item_ids"]]
    return (stem if not rows else f"{stem}-dop{len(rows)}"), used


async def sync(db) -> list[dict]:
    """Перечитать файлы патч-ноутов. Возвращает файлы с ошибками: их видно в админке, черновика нет.

    Пункт, дописанный в файл после отправки поста дня, не теряется: он уходит в отдельный пост-дополнение."""
    await repo.ensure_tables(db)
    known, problems = await repo.by_file(db), []
    for path in fmt.note_files():
        try:
            note = fmt.load(path)
            errors = fmt.validate(note)
        except (ValueError, OSError) as error:
            errors = [f"файл не читается: {type(error).__name__}"]
        if errors:
            problems.append({"note_id": path.stem, "errors": errors[:8]})
            continue
        rows = known.get(path.stem, [])
        note_id, used = _target(path.stem, rows)
        items = [i for i in note["items"] if i["id"] not in used]
        if not items:
            continue
        part = {**note, "items": items}
        if note_id != path.stem:   # дополнение к уже отправленному посту дня: другой заголовок, чтобы не повторяться в канале
            part["headline"] = ("Ещё: " + note["headline"])[:rules.MAX_HEADLINE]
        text, images, btn = fmt.compose(part), fmt.images(part), _button(fmt.button(part))
        digest = _sha(json.dumps([text, images, btn], ensure_ascii=False).encode())
        if any(r["note_id"] == note_id and r["source_digest"] == digest for r in rows):
            continue
        await repo.upsert_source(db, note_id, note["date"], digest, text, images, btn, fmt.flags(part),
                                 path.stem, [i["id"] for i in items])
    await repo.drop_orphan_uploads(db)
    return problems


def repo_image(name: str) -> bytes:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,90}", name) or not name.endswith(rules.IMAGE_EXT):
        raise PatchNoteError("Неверное имя картинки.")
    path = rules.IMAGES_DIR / name
    if not path.is_file():
        raise PatchNoteError(f"Картинки {name} нет в выпуске.")
    return path.read_bytes()


async def image_bytes(db, note_id: str, image: dict) -> tuple[bytes, str]:
    """Байты и mime картинки поста по её ссылке (файл выпуска, загрузка создателя или обложка)."""
    from services import patch_notes_images as pictures
    ref = str(image.get("ref", ""))
    if ref == "cover":
        return pictures.cover(str(image.get("title") or "Обновление"), str(image.get("kind") or "new")), "image/png"
    if ref.startswith("repo:"):
        name = ref[5:]
        return repo_image(name), "image/png" if name.endswith(".png") else "image/jpeg"
    if ref.startswith("upload:") and ref[7:].isdigit():
        row = await repo.get_upload(db, int(ref[7:]))
        if row and row["note_id"] == note_id:
            return bytes(row["data"]), row["mime"]
    raise PatchNoteError("Картинка не найдена.")


async def content_digest(db, row: dict) -> str:
    """Отпечаток того, что уйдёт в канал: текст, кнопка и содержимое каждой картинки."""
    parts = [row["text_html"], json.dumps(row["button"], ensure_ascii=False), str(rules.CHAT_ID), str(rules.THREAD_ID)]
    uploads = await repo.upload_meta(db, [int(i["ref"][7:]) for i in row["images"] if i["ref"].startswith("upload:")])
    for image in row["images"]:
        ref = image["ref"]
        if ref.startswith("repo:"):
            try:
                parts.append(_sha(repo_image(ref[5:])))
            except PatchNoteError:
                parts.append("missing:" + ref)
        elif ref.startswith("upload:"):
            parts.append((uploads.get(int(ref[7:])) or {}).get("sha256", "missing"))
        else:
            parts.append(json.dumps(image, ensure_ascii=False, sort_keys=True))
    return _sha("\n".join(parts).encode())


def _clean_images(images: list, uploads: dict[int, dict], note_id: str) -> list[dict]:
    if not isinstance(images, list) or len(images) > rules.MAX_IMAGES:
        raise PatchNoteError(f"Не больше {rules.MAX_IMAGES} картинок в посте.")
    out = []
    for image in images:
        ref, alt = str(image.get("ref", "")), str(image.get("alt") or "")[:200]
        if ref == "cover":
            title = str(image.get("title") or "").strip()
            if not 3 <= len(title) <= rules.MAX_TITLE:
                raise PatchNoteError("Заголовок обложки: от 3 до 80 знаков.")
            kind = image.get("kind") if image.get("kind") in rules.KINDS else "new"
            out.append({"ref": "cover", "title": title, "kind": kind, "alt": alt or f"Обложка: {title}"})
        elif ref.startswith("repo:"):
            repo_image(ref[5:])
            out.append({"ref": ref, "alt": alt})
        elif ref.startswith("upload:") and ref[7:].isdigit() and (uploads.get(int(ref[7:])) or {}).get("note_id") == note_id:
            out.append({"ref": ref, "alt": alt})
        else:
            raise PatchNoteError("Одна из картинок не найдена. Обновите страницу.")
    return out


def check_text(text: str) -> str:
    text = text.replace("\r\n", "\n").strip()
    errors = fmt.markup_errors(text)
    if errors:
        raise PatchNoteError("Разметка: " + "; ".join(errors[:3]) + ".")
    size = fmt.tg_len(fmt.plain_text(text))
    if not 20 <= size <= rules.MAX_CAPTION:
        raise PatchNoteError(f"Текст поста: от 20 до {rules.MAX_CAPTION} знаков (сейчас {size}). Короче — лучше.")
    return text


def check_button(button) -> dict | None:
    if not button:
        return None
    key, label = button.get("key"), str(button.get("label") or "").strip()
    if key not in rules.BUTTONS:
        raise PatchNoteError("Неизвестный раздел для кнопки.")
    if not 2 <= len(label) <= rules.MAX_BUTTON_LABEL:
        raise PatchNoteError(f"Подпись кнопки: от 2 до {rules.MAX_BUTTON_LABEL} знаков.")
    return {"key": key, "label": label}


async def edit(db, note_id: str, revision: int, text: str, images: list, button, actor: int) -> dict:
    await repo.ensure_tables(db)
    text, button = check_text(text), check_button(button)
    ids = [int(i["ref"][7:]) for i in images if isinstance(i, dict) and str(i.get("ref", "")).startswith("upload:") and i["ref"][7:].isdigit()]
    images = _clean_images(images, await repo.upload_meta(db, ids), note_id)
    if not await repo.save_edit(db, note_id, revision, text, images, button, actor):
        raise PatchNoteError("Черновик уже изменился или отправлен. Обновите страницу, чтобы не затереть чужую правку.")
    return await repo.get(db, note_id)


async def edit_sent(db, note_id: str, revision: int, text: str, actor: int, editor) -> dict:
    """Исправить опечатку в уже опубликованном посте: editor(row, text) меняет сообщение в канале, потом пишем себе."""
    await repo.ensure_tables(db)
    text = check_text(text)
    row = await repo.get(db, note_id)
    if not row or row["status"] != "sent" or row["revision"] != revision or not row["message_ids"]:
        raise PatchNoteError("Пост изменился или ещё не опубликован. Обновите страницу.")
    await editor(row, text)
    await repo.save_sent_text(db, note_id, revision, text, actor)
    return await repo.get(db, note_id)


async def add_upload(db, note_id: str, raw: bytes, actor: int) -> dict:
    from services import patch_notes_images as pictures
    row = await repo.get(db, note_id)
    if not row or row["status"] not in repo.PENDING:
        raise PatchNoteError("Фото можно добавить только в неотправленный черновик.")
    try:
        data, mime, width, height = pictures.normalize_upload(raw)
    except pictures.ImageRejected as error:
        raise PatchNoteError(str(error)) from None
    upload_id = await repo.add_upload(db, note_id, _sha(data), mime, width, height, data, actor)
    return {"ref": f"upload:{upload_id}", "width": width, "height": height}


async def publish(db, note_id: str, *, expected_digest: str, actor: int, preflight, send) -> dict:
    """Отправить один пост. preflight(row) проверяет назначение; send(row) возвращает id сообщений."""
    await repo.ensure_tables(db)
    row = await repo.get(db, note_id)
    if not row:
        raise PatchNoteError("Патч-ноут не найден.")
    if row["status"] == "sent":
        return {"ok": True, "replayed": True, "message_ids": row["message_ids"]}
    if row["status"] not in repo.PENDING or await content_digest(db, row) != expected_digest:
        raise PatchNoteError("Пост изменился после проверки. Откройте его заново и посмотрите ещё раз.")
    await preflight(row)
    async with db.connection.transaction():
        await repo.lock(db)
        row = await repo.get(db, note_id)
        if row["status"] == "sent":
            return {"ok": True, "replayed": True, "message_ids": row["message_ids"]}
        if row["status"] not in repo.PENDING or await content_digest(db, row) != expected_digest:
            raise PatchNoteError("Пост изменился во время отправки. Откройте его заново.")
        if await repo.uncertain_delivery(db):
            raise PatchNoteError("Другой пост ещё отправляется или ждёт сверки. Сначала сверьте его.")
        await repo.mark(db, note_id, "sending", error=None, actor=actor)
    return await _deliver(db, row, actor, send)


async def _deliver(db, row: dict, actor: int, send) -> dict:
    note_id = row["note_id"]
    try:
        message_ids = await send(row)
    except PatchNoteError as error:   # картинка пропала до первого шага: в канал ничего не ушло
        await repo.mark(db, note_id, "failed", error=str(error))
        raise
    except Rejected as error:
        await repo.mark(db, note_id, "failed", error=f"Telegram отклонил пост: {error}. Ничего не опубликовано.")
        raise PatchNoteError(f"Telegram отклонил пост: {error}. В канале ничего не осталось, можно исправить и отправить снова.") from None
    except Exception as error:
        partial = list(getattr(error, "message_ids", []) or [])
        logger.warning("patch note {} delivery unknown: {}", note_id, type(error).__name__)
        await repo.mark(db, note_id, "unknown", message_ids=partial,
                        error="Ответ Telegram не получен. Проверьте тему вручную и отметьте результат.")
        raise PatchNoteError("Исход отправки неизвестен. Не отправляйте повторно: проверьте тему и нажмите «Сверить».") from None
    await repo.mark(db, note_id, "sent", message_ids=[int(m) for m in message_ids], error=None, actor=actor)
    return {"ok": True, "replayed": False, "message_ids": message_ids}


async def reconcile(db, note_id: str, *, found: bool, message_id: int | None) -> None:
    """Ручная сверка после потерянного ответа: пост найден в теме или его точно нет."""
    async with db.connection.transaction():
        await repo.lock(db)
        row = await repo.get(db, note_id)
        if not row or row["status"] not in repo.UNCERTAIN:
            raise PatchNoteError("Этот пост не ждёт сверки.")
        if row["status"] == "sending" and not await repo.sending_expired(db, note_id):
            raise PatchNoteError("Отправка ещё может идти. Подождите две минуты.")
        if found:
            ids = row["message_ids"] or ([message_id] if message_id else [])
            await repo.mark(db, note_id, "sent", message_ids=ids, error=None)
        else:
            await repo.mark(db, note_id, "failed", error="Создатель проверил тему: поста нет. Можно отправить снова.")
