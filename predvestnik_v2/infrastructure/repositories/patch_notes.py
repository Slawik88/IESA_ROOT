"""Патч-ноуты: рабочая копия поста (что отправится), статус доставки и загруженные создателем фото.

Источник — файлы FastAPI/static/patch-notes/*.json (их пишут при выпуске). Здесь живёт то, что создатель
поправил в админке, поэтому правка переживает любую выкладку. JSON хранится текстом.
"""
from __future__ import annotations

import json

PENDING = ("draft", "failed")          # можно править и отправлять
UNCERTAIN = ("sending", "unknown")     # исход отправки не подтверждён: нужна сверка


async def ensure_tables(db) -> None:
    await db.execute("""CREATE TABLE IF NOT EXISTS patch_notes (
        note_id TEXT PRIMARY KEY, note_date TEXT NOT NULL,
        source_digest TEXT NOT NULL, source_text TEXT NOT NULL, source_images TEXT NOT NULL, source_button TEXT,
        source_flags TEXT NOT NULL DEFAULT '[]', source_newer BOOLEAN NOT NULL DEFAULT FALSE,
        text_html TEXT NOT NULL, images TEXT NOT NULL, button TEXT,
        edited BOOLEAN NOT NULL DEFAULT FALSE, edited_by BIGINT, edited_at TIMESTAMPTZ,
        revision INT NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'draft',
        message_ids TEXT NOT NULL DEFAULT '[]', error TEXT, attempt_at TIMESTAMPTZ,
        sent_at TIMESTAMPTZ, sent_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    await db.execute("""CREATE TABLE IF NOT EXISTS patch_note_uploads (
        id BIGSERIAL PRIMARY KEY, note_id TEXT NOT NULL, sha256 TEXT NOT NULL, mime TEXT NOT NULL,
        width INT NOT NULL, height INT NOT NULL, data BYTEA NOT NULL,
        created_by BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    await db.execute("CREATE INDEX IF NOT EXISTS patch_note_uploads_note ON patch_note_uploads(note_id)")
    # Какие пункты файла вошли в этот пост: пункты, дописанные после отправки, уходят в пост-дополнение.
    await db.execute("ALTER TABLE patch_notes ADD COLUMN IF NOT EXISTS source_file TEXT")
    await db.execute("ALTER TABLE patch_notes ADD COLUMN IF NOT EXISTS item_ids TEXT NOT NULL DEFAULT '[]'")
    # Тема официальной группы, в которой бот видел сообщение (подтверждает назначение перед отправкой).
    await db.execute("""CREATE TABLE IF NOT EXISTS official_update_topic (
        chat_id BIGINT NOT NULL, thread_id BIGINT NOT NULL,
        last_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(chat_id,thread_id)
    )""")


def _row(row) -> dict | None:
    if not row:
        return None
    out = dict(row)
    for key in ("source_images", "images", "message_ids", "source_flags", "item_ids"):
        out[key] = json.loads(out[key] or "[]")
    for key in ("source_button", "button"):
        out[key] = json.loads(out[key]) if out.get(key) else None
    return out


async def topic_seen(db, chat_id: int, thread_id: int) -> None:
    await db.execute("INSERT INTO official_update_topic(chat_id,thread_id) VALUES (?,?) "
                     "ON CONFLICT(chat_id,thread_id) DO UPDATE SET last_observed_at=NOW()", (chat_id, thread_id))


async def topic_verified(db, chat_id: int, thread_id: int) -> bool:
    async with db.execute("SELECT 1 FROM official_update_topic WHERE chat_id=? AND thread_id=?", (chat_id, thread_id)) as cursor:
        return bool(await cursor.fetchone())


async def get(db, note_id: str) -> dict | None:
    async with db.execute("SELECT * FROM patch_notes WHERE note_id=?", (note_id,)) as cursor:
        return _row(await cursor.fetchone())


async def list_notes(db) -> list[dict]:
    async with db.execute("SELECT * FROM patch_notes ORDER BY (status IN ('draft','failed','sending','unknown')) DESC, "
                          "note_date DESC, note_id DESC LIMIT 60") as cursor:
        return [_row(r) for r in await cursor.fetchall()]


async def pending_count(db) -> int:
    async with db.execute("SELECT COUNT(*) FROM patch_notes WHERE status IN ('draft','failed','sending','unknown')") as cursor:
        return int((await cursor.fetchone())[0])


async def by_file(db) -> dict[str, list[dict]]:
    """Посты по файлу-источнику: основной и дополнения (только поля, нужные синхронизации)."""
    async with db.execute("SELECT note_id, COALESCE(source_file, note_id) AS source_file, source_digest, status, item_ids "
                          "FROM patch_notes ORDER BY note_id") as cursor:
        rows = await cursor.fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["source_file"], []).append({**dict(r), "item_ids": json.loads(r["item_ids"] or "[]")})
    return out


async def upsert_source(db, note_id: str, note_date: str, digest: str, text: str, images: list, button: dict | None,
                        flags: list, source_file: str, item_ids: list[str]) -> None:
    """Новый файл — новый черновик. Изменённый файл обновляет черновик, если создатель его не правил;
    иначе правка создателя остаётся, а в админке появляется «Предвестник дополнил черновик»."""
    imgs, btn, fl = json.dumps(images, ensure_ascii=False), json.dumps(button, ensure_ascii=False), json.dumps(flags)
    await db.execute(
        "INSERT INTO patch_notes(note_id,note_date,source_digest,source_text,source_images,source_button,source_flags,text_html,images,button,"
        "source_file,item_ids) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(note_id) DO UPDATE SET item_ids=EXCLUDED.item_ids, "
        "source_digest=EXCLUDED.source_digest, source_text=EXCLUDED.source_text, source_images=EXCLUDED.source_images, "
        "source_button=EXCLUDED.source_button, source_flags=EXCLUDED.source_flags, note_date=EXCLUDED.note_date, "
        "text_html=CASE WHEN patch_notes.edited THEN patch_notes.text_html ELSE EXCLUDED.text_html END, "
        "images=CASE WHEN patch_notes.edited THEN patch_notes.images ELSE EXCLUDED.images END, "
        "button=CASE WHEN patch_notes.edited THEN patch_notes.button ELSE EXCLUDED.button END, "
        "source_newer=patch_notes.edited, revision=patch_notes.revision+1 "
        "WHERE patch_notes.source_digest<>EXCLUDED.source_digest AND patch_notes.status IN ('draft','failed')",
        (note_id, note_date, digest, text, imgs, btn, fl, text, imgs, btn, source_file, json.dumps(item_ids)))


async def save_edit(db, note_id: str, revision: int, text: str, images: list, button: dict | None, actor: int) -> bool:
    cursor = await db.execute(
        "UPDATE patch_notes SET text_html=?, images=?, button=?, edited=TRUE, edited_by=?, edited_at=NOW(), "
        "revision=revision+1 WHERE note_id=? AND revision=? AND status IN ('draft','failed')",
        (text, json.dumps(images, ensure_ascii=False), json.dumps(button, ensure_ascii=False), actor, note_id, revision))
    return cursor.rowcount == 1


async def reset_to_source(db, note_id: str, revision: int) -> bool:
    cursor = await db.execute(
        "UPDATE patch_notes SET text_html=source_text, images=source_images, button=source_button, edited=FALSE, "
        "source_newer=FALSE, revision=revision+1 WHERE note_id=? AND revision=? AND status IN ('draft','failed')",
        (note_id, revision))
    return cursor.rowcount == 1


async def set_skipped(db, note_id: str, skipped: bool) -> bool:
    if skipped:
        sql = "UPDATE patch_notes SET status='skipped', revision=revision+1 WHERE note_id=? AND status IN ('draft','failed')"
    else:
        sql = "UPDATE patch_notes SET status='draft', revision=revision+1 WHERE note_id=? AND status='skipped'"
    cursor = await db.execute(sql, (note_id,))
    return cursor.rowcount == 1


async def lock(db) -> None:
    await db.execute("SELECT pg_advisory_xact_lock(7710403)")


async def uncertain_delivery(db) -> bool:
    async with db.execute("SELECT 1 FROM patch_notes WHERE status IN ('sending','unknown') LIMIT 1") as cursor:
        return bool(await cursor.fetchone())


async def mark(db, note_id: str, status: str, *, message_ids: list[int] | None = None, error: str | None = None,
               actor: int | None = None) -> None:
    await db.execute(
        "UPDATE patch_notes SET status=?, message_ids=COALESCE(?, message_ids), error=?, revision=revision+1, "
        "attempt_at=CASE WHEN ?='sending' THEN NOW() ELSE attempt_at END, "
        "sent_at=CASE WHEN ?='sent' THEN NOW() ELSE sent_at END, sent_by=COALESCE(?, sent_by) WHERE note_id=?",
        (status, json.dumps(message_ids) if message_ids is not None else None, error, status, status, actor, note_id))


async def sending_expired(db, note_id: str) -> bool:
    async with db.execute("SELECT attempt_at IS NULL OR attempt_at<NOW()-INTERVAL '2 minutes' FROM patch_notes WHERE note_id=?",
                          (note_id,)) as cursor:
        row = await cursor.fetchone()
    return bool(row and row[0])


async def add_upload(db, note_id: str, sha256: str, mime: str, width: int, height: int, data: bytes, actor: int) -> int:
    async with db.execute("INSERT INTO patch_note_uploads(note_id,sha256,mime,width,height,data,created_by) "
                          "VALUES (?,?,?,?,?,?,?) RETURNING id", (note_id, sha256, mime, width, height, data, actor)) as cursor:
        return int((await cursor.fetchone())[0])


async def get_upload(db, upload_id: int) -> dict | None:
    async with db.execute("SELECT id,note_id,sha256,mime,width,height,data FROM patch_note_uploads WHERE id=?",
                          (upload_id,)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def upload_meta(db, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    async with db.execute("SELECT id,note_id,sha256 FROM patch_note_uploads WHERE id = ANY(?::bigint[])", (ids,)) as cursor:
        return {int(r["id"]): dict(r) for r in await cursor.fetchall()}
