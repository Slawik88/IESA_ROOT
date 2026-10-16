"""Single-target publication receipts, separate from bulk broadcasts."""


async def ensure_tables(db) -> None:
    await db.execute("""CREATE TABLE IF NOT EXISTS official_update_posts (
        release_key TEXT PRIMARY KEY, kind TEXT NOT NULL, caption TEXT NOT NULL,
        image_name TEXT NOT NULL, image_digest TEXT NOT NULL, content_digest TEXT NOT NULL,
        asset_version TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
        actor_id BIGINT NOT NULL, message_id BIGINT, error TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), sent_at TIMESTAMPTZ
    )""")
    await db.execute("""CREATE TABLE IF NOT EXISTS official_update_topic (
        chat_id BIGINT NOT NULL, thread_id BIGINT NOT NULL,
        last_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(chat_id,thread_id)
    )""")
    await db.execute("ALTER TABLE official_update_posts ADD COLUMN IF NOT EXISTS attempt_at TIMESTAMPTZ")


async def topic_seen(db, chat_id: int, thread_id: int) -> None:
    await db.execute("INSERT INTO official_update_topic(chat_id,thread_id) VALUES (?,?) "
                     "ON CONFLICT(chat_id,thread_id) DO UPDATE SET last_observed_at=NOW()", (chat_id, thread_id))


async def topic_verified(db, chat_id: int, thread_id: int) -> bool:
    async with db.execute("SELECT 1 FROM official_update_topic WHERE chat_id=? AND thread_id=?", (chat_id, thread_id)) as cursor:
        return bool(await cursor.fetchone())


async def get(db, key: str) -> dict | None:
    async with db.execute("SELECT * FROM official_update_posts WHERE release_key=?", (key,)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def list_posts(db) -> list[dict]:
    async with db.execute("SELECT * FROM official_update_posts ORDER BY created_at DESC LIMIT 30") as cursor:
        return [dict(r) for r in await cursor.fetchall()]


async def create(db, *, key: str, kind: str, caption: str, image: str, image_digest: str,
                 content_digest: str, version: str, actor: int) -> None:
    await db.execute("INSERT INTO official_update_posts(release_key,kind,caption,image_name,image_digest,content_digest,asset_version,actor_id) "
                     "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(release_key) DO NOTHING",
                     (key, kind, caption, image, image_digest, content_digest, version, actor))


async def lock(db) -> None:
    await db.execute("SELECT pg_advisory_xact_lock(7710402)")


async def recently_sent(db) -> bool:
    async with db.execute("SELECT 1 FROM official_update_posts WHERE sent_at>NOW()-INTERVAL '24 hours' LIMIT 1") as cursor:
        return bool(await cursor.fetchone())


async def uncertain_delivery(db) -> bool:
    async with db.execute("SELECT 1 FROM official_update_posts WHERE status IN ('sending','unknown') LIMIT 1") as cursor:
        return bool(await cursor.fetchone())


async def mark(db, key: str, status: str, *, message_id: int | None = None, error: str | None = None) -> None:
    await db.execute("UPDATE official_update_posts SET status=?,message_id=COALESCE(?,message_id),error=?,"
                     "attempt_at=CASE WHEN ?='sending' THEN NOW() ELSE attempt_at END,"
                     "sent_at=CASE WHEN ?='sent' THEN NOW() ELSE sent_at END WHERE release_key=?",
                     (status, message_id, error, status, status, key))
