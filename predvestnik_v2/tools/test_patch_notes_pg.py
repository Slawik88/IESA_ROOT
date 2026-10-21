#!/usr/bin/env python3
"""Патч-ноуты на настоящем PostgreSQL: черновик из файла, правка создателя, дополнение после отправки,
повтор без дубля, потерянный ответ и сверка, гонка двух отправок, фото, и порядок шагов отправки в Telegram.

Запуск: python tools/test_patch_notes_pg.py --dsn postgresql://…@127.0.0.1:…/… (только локальная база). Telegram не вызывается.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg  # noqa: E402
from PIL import Image  # noqa: E402

from core import patch_notes as rules  # noqa: E402
from infrastructure.pg_adapter import PGAdapter  # noqa: E402
from infrastructure.repositories import patch_notes as repo  # noqa: E402
from services import patch_notes as service  # noqa: E402

DAY = "2099-01-02"


def item(i: str, kind: str = "new", **extra) -> dict:
    base = {"id": f"qa-{i}-item", "kind": kind, "text": f"Текст пункта {i} для игроков."}
    if kind != "fix":
        base |= {"title": f"Пункт {i}", "image": "cover" if kind == "new" else None}
    return {k: v for k, v in (base | extra).items() if v is not None}


def write(folder: Path, items: list[dict], name: str = DAY, **extra) -> None:
    note = {"date": DAY, "headline": "Проверка патч-ноутов", "items": items} | extra
    (folder / f"{name}.json").write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")


async def denied(awaitable, needle: str = "") -> None:
    try:
        await awaitable
    except service.PatchNoteError as error:
        assert needle in str(error), str(error)
        return
    raise AssertionError("ожидали отказ")


async def no_preflight(row) -> None:
    return None


async def drafts_and_edits(db, folder: Path) -> None:
    write(folder, [item("a"), item("b", "fix")])
    (folder / "2099-01-03.json").write_text('{"date": "2099-01-03", "items": []}', encoding="utf-8")
    problems = await service.sync(db)
    assert [p["note_id"] for p in problems] == ["2099-01-03"], problems
    row = await repo.get(db, DAY)
    assert row["status"] == "draft" and "Пункт a" in row["text_html"] and row["images"][0]["ref"] == "cover"
    assert row["item_ids"] == ["qa-a-item", "qa-b-item"] and row["button"]["key"] == "home"
    await denied(service.edit(db, DAY, row["revision"] + 5, row["text_html"], row["images"], row["button"], 1), "Обновите")
    await denied(service.edit(db, DAY, row["revision"], "<b>не закрыт", [], None, 1), "Разметка")
    edited = await service.edit(db, DAY, row["revision"], "<b>Мой текст</b> поста для канала.", [], {"key": "games", "label": "Играть"}, 1)
    assert edited["edited"] and edited["images"] == [] and edited["button"] == {"key": "games", "label": "Играть"}
    write(folder, [item("a"), item("b", "fix"), item("c", "better")])
    await service.sync(db)
    after = await repo.get(db, DAY)
    assert after["source_newer"] and after["text_html"].startswith("<b>Мой текст</b>") and "Пункт c" in after["source_text"]
    assert await repo.reset_to_source(db, DAY, after["revision"])
    reset = await repo.get(db, DAY)
    assert not reset["edited"] and "Пункт c" in reset["text_html"] and not reset["source_newer"]
    print("OK: черновик из файла, ошибки файла видны, правка создателя переживает дополнение, возврат версии")


async def publish_flow(db, folder: Path) -> None:
    row = await repo.get(db, DAY)
    digest, sent = await service.content_digest(db, row), []

    async def send(r):
        sent.append(r["note_id"])
        return [501, 502]
    await denied(service.publish(db, DAY, expected_digest="0" * 64, actor=1, preflight=no_preflight, send=send), "изменился")
    first = await service.publish(db, DAY, expected_digest=digest, actor=1, preflight=no_preflight, send=send)
    again = await service.publish(db, DAY, expected_digest=digest, actor=1, preflight=no_preflight, send=send)
    assert first["message_ids"] == [501, 502] and again["replayed"] and sent == [DAY]
    await denied(service.edit(db, DAY, (await repo.get(db, DAY))["revision"], "Правка после отправки поста", [], None, 1))
    write(folder, [item("a"), item("b", "fix"), item("c", "better"), item("d", "fix")])
    await service.sync(db)
    extra = await repo.get(db, f"{DAY}-dop1")
    assert extra and extra["item_ids"] == ["qa-d-item"] and "Текст пункта d" in extra["text_html"]
    assert "Ещё: Проверка" in extra["text_html"], "дополнение не повторяет заголовок поста дня"
    assert "Пункт a" not in extra["text_html"] and (await repo.get(db, DAY))["status"] == "sent"
    await service.sync(db)
    assert (await repo.get(db, f"{DAY}-dop2")) is None, "повторная синхронизация не плодит дополнения"
    edits = []

    async def editor(r, text):
        edits.append(text)
    sent_row = await repo.get(db, DAY)
    await denied(service.edit_sent(db, DAY, sent_row["revision"] + 1, "Исправленный текст поста дня", 1, editor), "Обновите")
    fixed = await service.edit_sent(db, DAY, sent_row["revision"], "Исправленный текст поста дня", 1, editor)
    assert edits == ["Исправленный текст поста дня"] and fixed["text_html"] == edits[0] and fixed["status"] == "sent"
    await denied(service.edit_sent(db, f"{DAY}-dop1", 1, "Текст неотправленного поста", 1, editor), "не опубликован")
    print("OK: повтор не шлёт дубль, черновик после отправки закрыт, опечатка правится в канале, дописанное уходит в дополнение")


async def lost_answer(db) -> None:
    note = f"{DAY}-dop1"
    row = await repo.get(db, note)

    class Lost(Exception):
        message_ids = [777]

    async def lost(r):
        raise Lost()
    await denied(service.publish(db, note, expected_digest=await service.content_digest(db, row), actor=1,
                                 preflight=no_preflight, send=lost), "неизвестен")
    row = await repo.get(db, note)
    assert row["status"] == "unknown" and row["message_ids"] == [777]
    await denied(service.reconcile(db, DAY, found=True, message_id=None), "не ждёт")
    await service.reconcile(db, note, found=False, message_id=None)
    row = await repo.get(db, note)
    assert row["status"] == "failed"

    async def rejected(r):
        raise service.Rejected("Bad Request: can't parse entities")
    await denied(service.publish(db, note, expected_digest=await service.content_digest(db, row), actor=1,
                                 preflight=no_preflight, send=rejected), "отклонил")
    assert (await repo.get(db, note))["status"] == "failed"
    assert await repo.set_skipped(db, note, True) and (await repo.get(db, note))["status"] == "skipped"
    assert await repo.set_skipped(db, note, False) and (await repo.get(db, note))["status"] == "draft"
    print("OK: потерянный ответ блокирует повтор до сверки, отказ Telegram даёт повторить, «не публикуем» обратимо")


async def uploads(db) -> None:
    note = f"{DAY}-dop1"
    raw = io.BytesIO()
    Image.new("RGB", (900, 600), (30, 20, 80)).save(raw, "PNG")
    up = await service.add_upload(db, note, raw.getvalue(), 1)
    row = await repo.get(db, note)
    edited = await service.edit(db, note, row["revision"], row["text_html"], [{"ref": up["ref"], "alt": "Скриншот"}], row["button"], 1)
    data, mime = await service.image_bytes(db, note, edited["images"][0])
    assert mime == "image/jpeg" and Image.open(io.BytesIO(data)).size == (900, 600)
    await denied(service.image_bytes(db, DAY, edited["images"][0]), "не найдена")
    await denied(service.edit(db, DAY, 1, "Чужое фото в посте дня", [{"ref": up["ref"]}], None, 1))
    await denied(service.add_upload(db, DAY, raw.getvalue(), 1), "неотправленный")
    orphan = await service.add_upload(db, note, raw.getvalue(), 1)
    await db.execute("UPDATE patch_note_uploads SET created_at=NOW()-INTERVAL '3 days' WHERE id IN (?, ?)",
                     (int(orphan["ref"][7:]), int(up["ref"][7:])))
    await service.sync(db)
    assert await repo.get_upload(db, int(orphan["ref"][7:])) is None, "брошенное фото не убрано"
    assert await repo.get_upload(db, int(up["ref"][7:])), "фото из поста удалено"
    print("OK: фото создателя перекодируется, принадлежит своему посту, брошенные загрузки убираются")


async def order_hint(db) -> None:
    await db.execute("UPDATE patch_notes SET status='draft' WHERE note_id=?", (f"{DAY}-dop1",))
    ours = lambda ids: [i for i in ids if i.startswith(DAY)]   # в базе могут быть чужие черновики
    assert ours(await repo.older_pending(db, f"{DAY}-race-one")) == [f"{DAY}-dop1"]
    assert ours(await repo.older_pending(db, f"{DAY}-dop1")) == []
    pending = [r["note_id"] for r in await repo.list_notes(db) if r["note_id"].startswith(DAY) and r["status"] in repo.PENDING]
    assert pending == sorted(pending), "неотправленные идут от старых к новым"
    print("OK: неотправленные посты по порядку дней, подсказка «сначала более ранний»")


async def race(dsn: str, folder: Path) -> None:
    connections = [await asyncpg.connect(dsn) for _ in range(2)]
    for c in connections:
        await c.execute("SET search_path TO predvestnik,public")
    a, b = (PGAdapter(c) for c in connections)
    write(folder, [item("r1")], name=f"{DAY}-race-one")
    write(folder, [item("r2")], name=f"{DAY}-race-two")
    write(folder, [item("r3")], name=f"{DAY}-race-three")
    await service.sync(a)
    sent = []

    async def slow(r):
        sent.append(r["note_id"])
        await asyncio.sleep(.1)
        return [900]

    async def go(db, note):
        row = await repo.get(db, note)
        try:
            return await service.publish(db, note, expected_digest=await service.content_digest(db, row), actor=1,
                                         preflight=no_preflight, send=slow)
        except service.PatchNoteError:
            return None
    try:
        results = await asyncio.gather(go(a, f"{DAY}-race-one"), go(b, f"{DAY}-race-one"))
        assert len(sent) == 1 and sum(bool(r and not r["replayed"]) for r in results) == 1, (sent, results)
        sent.clear()
        results = await asyncio.gather(go(a, f"{DAY}-race-two"), go(b, f"{DAY}-race-three"))
        assert len(sent) == 1 and sum(r is not None for r in results) == 1, (sent, results)
        print("OK: два одновременных нажатия шлют пост один раз; два разных поста не уходят одновременно")
    finally:
        for c in connections:
            await c.close()


class FakeBot:
    def __init__(self, fail_on: str = "") -> None:
        self.calls, self.deleted, self.fail_on, self.next = [], [], fail_on, 10

    def _msg(self):
        self.next += 1
        return type("M", (), {"message_id": self.next})()

    async def _call(self, name, **kw):
        self.calls.append((name, kw))
        if name == self.fail_on:
            from aiogram.exceptions import TelegramBadRequest
            raise TelegramBadRequest(method=None, message="Bad Request: can't parse entities")
        return self._msg()

    async def send_message(self, chat_id, text, **kw):
        return await self._call("send_message", text=text, **kw)

    async def send_photo(self, chat_id, photo, **kw):
        return await self._call("send_photo", **kw)

    async def send_media_group(self, chat_id, media, **kw):
        await self._call("send_media_group", media=media, **kw)
        return [self._msg() for _ in media]

    async def edit_message_text(self, **kw):
        return await self._call("edit_message_text", **kw)

    async def edit_message_caption(self, **kw):
        return await self._call("edit_message_caption", **kw)

    async def delete_messages(self, chat_id, ids):
        self.deleted.extend(ids)
        return True


async def telegram_steps(db) -> None:
    from services import patch_notes_send as sender
    cover = {"ref": "cover", "title": "Обложка", "kind": "new"}
    row = {"note_id": DAY, "text_html": "<b>Коротко</b>", "images": [cover], "button": {"key": "games", "label": "Играть"}}
    bot = FakeBot()
    ids = await sender.send(bot, db, row)
    assert [c[0] for c in bot.calls] == ["send_photo"] and bot.calls[0][1]["caption"] == "<b>Коротко</b>" and len(ids) == 1
    assert bot.calls[0][1]["message_thread_id"] == rules.THREAD_ID and bot.calls[0][1]["parse_mode"] == "HTML"
    bot = FakeBot()
    ids = await sender.send(bot, db, {**row, "images": [cover, cover]})
    media = bot.calls[0][1]["media"]
    assert [c[0] for c in bot.calls] == ["send_media_group"] and len(ids) == 2, "несколько фото — один пост-альбом"
    assert media[0].caption.startswith("<b>Коротко</b>") and "👉 <a href=" in media[0].caption and media[1].caption is None
    long = {**row, "text_html": "я" * 1020, "images": [cover, cover, cover]}
    bot = FakeBot(fail_on="send_message")
    try:
        await sender.send(bot, db, long)
    except service.Rejected:
        assert len(bot.deleted) == 3 and len(set(bot.deleted)) == 3, bot.deleted
    else:
        raise AssertionError("отказ на тексте должен вернуть Rejected")
    bot = FakeBot()
    await sender.send(bot, db, {**row, "images": [], "button": None})
    assert bot.calls[0][0] == "send_message" and bot.calls[0][1]["reply_markup"] is None
    for images, method in (([], "edit_message_text"), ([cover], "edit_message_caption"), ([cover, cover], "edit_message_caption")):
        bot = FakeBot()
        await sender.edit_sent(bot, {**row, "images": images, "message_ids": [41, 42]}, "<b>Без опечатки</b>")
        assert bot.calls[0][0] == method, (images, bot.calls)
        assert bot.calls[0][1]["message_id"] == (42 if not images else 41)
    await denied(sender.edit_sent(FakeBot(), {**row, "images": [cover], "message_ids": [41]}, "я" * 1100), "вид поста")
    print("OK: отправка одним постом (фото или альбом с подписью), обрывок удаляется при отказе, опечатку правим в канале")


async def cleanup(db) -> None:
    await db.execute("DELETE FROM patch_note_uploads WHERE note_id LIKE ?", (DAY + "%",))
    await db.execute("DELETE FROM patch_notes WHERE note_id LIKE ? OR note_id LIKE ?", (DAY + "%", "2099-01-03%"))


async def main(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    await connection.execute("SET search_path TO predvestnik,public")
    db = PGAdapter(connection)
    saved = rules.NOTES_DIR, rules.IMAGES_DIR
    with tempfile.TemporaryDirectory() as tmp:
        rules.NOTES_DIR, rules.IMAGES_DIR = Path(tmp), Path(tmp) / "img"
        try:
            await repo.ensure_tables(db)
            await cleanup(db)
            await drafts_and_edits(db, Path(tmp))
            await publish_flow(db, Path(tmp))
            await lost_answer(db)
            await uploads(db)
            await race(dsn, Path(tmp))
            await order_hint(db)
            await telegram_steps(db)
        finally:
            await cleanup(db)
            rules.NOTES_DIR, rules.IMAGES_DIR = saved
            await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("only a loopback PostgreSQL DSN is allowed")
    asyncio.run(main(args.dsn))
