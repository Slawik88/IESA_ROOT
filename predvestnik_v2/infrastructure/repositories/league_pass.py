"""Storage of the season pass from season 2: experience, its receipts, the casual daily cap and claims."""
from __future__ import annotations

from datetime import date, datetime
import json
from core import league_pass as rules


async def ensure_tables(db) -> None:
    if await _schema_ready(db):
        return
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('league-pass-schema',0))")
        if not await _schema_ready(db):
            await _install_tables(db)


async def _schema_ready(db) -> bool:
    async with db.execute("""
        SELECT to_regclass('league_pass_progress') IS NOT NULL
          AND to_regclass('league_pass_claims') IS NOT NULL
          AND to_regclass('league_pass_claims_v2') IS NOT NULL
          AND to_regclass('league_pass_repeat') IS NOT NULL
          AND to_regclass('league_pass_receipts') IS NOT NULL
          AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema()
                      AND table_name='league_pass_days' AND column_name='pet_xp')
          AND EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='league_pass_legacy_guard'
                      AND tgrelid=to_regclass('league_pass_claims') AND NOT tgisinternal)
    """) as cursor:
        return bool((await cursor.fetchone())[0])


async def _install_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS league_pass_progress (
            user_id BIGINT NOT NULL,
            season INTEGER NOT NULL CHECK (season >= 2),
            xp INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, season)
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS league_pass_claims_v2 (
            user_id BIGINT NOT NULL, season INTEGER NOT NULL,
            level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 40),
            track TEXT NOT NULL CHECK (track IN ('free','vip')),
            reward_json JSONB NOT NULL, claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, season, level, track)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS league_pass_repeat (
            user_id BIGINT NOT NULL, season INTEGER NOT NULL,
            claimed INTEGER NOT NULL DEFAULT 0 CHECK (claimed >= 0),
            next_claim_at TIMESTAMPTZ,
            PRIMARY KEY (user_id, season)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS league_pass_days (
            user_id BIGINT NOT NULL,
            day DATE NOT NULL,
            casual_xp INTEGER NOT NULL DEFAULT 0 CHECK (casual_xp >= 0),
            PRIMARY KEY (user_id, day)
        )
    """)
    # pets have their own daily cap (core.league_pass.PET_DAILY_CAP), added 23.10.2026; checked first so an
    # ordinary restart takes no table lock
    async with db.execute("SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() "
                          "AND table_name='league_pass_days' AND column_name='pet_xp'") as cursor:
        present = await cursor.fetchone()
    if not present:
        await db.execute("ALTER TABLE league_pass_days ADD COLUMN IF NOT EXISTS pet_xp INTEGER NOT NULL DEFAULT 0 CHECK (pet_xp >= 0)")
    # One receipt per (player, source, event): a replayed game or level never adds experience twice.
    await db.execute("""
        CREATE TABLE IF NOT EXISTS league_pass_receipts (
            user_id BIGINT NOT NULL,
            source TEXT NOT NULL,
            event_id TEXT NOT NULL,
            season INTEGER NOT NULL,
            xp INTEGER NOT NULL CHECK (xp >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, source, event_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS league_pass_claims (
            user_id BIGINT NOT NULL,
            season INTEGER NOT NULL,
            level INTEGER NOT NULL CHECK (level BETWEEN 1 AND 30),
            track TEXT NOT NULL CHECK (track IN ('free','vip')),
            reward_json JSONB NOT NULL,
            claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, season, level, track)
        )
    """)
    # Old web/bot processes must not pay the original full row after a new half-row.
    # Keep this guard through the rollback window; legacy readers cannot understand v2 receipts.
    await db.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='league_pass_legacy_guard'
                         AND tgrelid='league_pass_claims'::regclass AND NOT tgisinternal) THEN
            CREATE FUNCTION league_pass_reject_legacy_write() RETURNS trigger LANGUAGE plpgsql AS $body$
            BEGIN
              IF EXISTS (SELECT 1 FROM league_pass_claims_v2 WHERE user_id=NEW.user_id AND season=NEW.season)
                 OR EXISTS (SELECT 1 FROM league_pass_repeat WHERE user_id=NEW.user_id AND season=NEW.season) THEN
                RAISE EXCEPTION 'Season pass upgraded: retry with current application';
              END IF;
              RETURN NEW;
            END $body$;
            CREATE TRIGGER league_pass_legacy_guard BEFORE INSERT ON league_pass_claims
              FOR EACH ROW EXECUTE FUNCTION league_pass_reject_legacy_write();
          END IF;
        END $$
    """)


async def lock_user(db, *, user_id: int) -> None:
    await db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?, 0))", (f"league-pass:{int(user_id)}",))


async def insert_receipt(db, *, user_id: int, source: str, event_id: str, season: int, xp: int) -> bool:
    async with db.execute(
        "INSERT INTO league_pass_receipts(user_id,source,event_id,season,xp) VALUES (?,?,?,?,?) "
        "ON CONFLICT DO NOTHING RETURNING 1", (int(user_id), source, str(event_id), int(season), int(xp)),
    ) as cursor:
        return bool(await cursor.fetchone())


_BUCKETS = {"casual": "casual_xp", "pet": "pet_xp"}   # daily caps: casual games and pets


async def day_xp(db, *, user_id: int, day: date) -> dict[str, int]:
    """Experience counted today under each daily cap; locks the row inside a transaction."""
    async with db.execute("SELECT casual_xp, pet_xp FROM league_pass_days WHERE user_id=? AND day=? FOR UPDATE",
                          (int(user_id), day)) as cursor:
        row = await cursor.fetchone()
    return {"casual": int(row[0]), "pet": int(row[1])} if row else {"casual": 0, "pet": 0}


async def add_day(db, *, user_id: int, day: date, bucket: str, xp: int) -> None:
    column = _BUCKETS[bucket]
    await db.execute(
        f"INSERT INTO league_pass_days(user_id,day,{column}) VALUES (?,?,?) "
        f"ON CONFLICT (user_id,day) DO UPDATE SET {column}=league_pass_days.{column}+EXCLUDED.{column}",
        (int(user_id), day, int(xp)),
    )


async def add_xp(db, *, user_id: int, season: int, xp: int) -> None:
    await db.execute(
        "INSERT INTO league_pass_progress(user_id,season,xp) VALUES (?,?,?) "
        "ON CONFLICT (user_id,season) DO UPDATE SET xp=league_pass_progress.xp+EXCLUDED.xp, updated_at=NOW()",
        (int(user_id), int(season), int(xp)),
    )


async def receipt(db, *, user_id: int, source: str, event_id: str) -> int | None:
    """Experience one event gave (0 when the daily cap was full), None when it gave nothing at all."""
    async with db.execute("SELECT xp FROM league_pass_receipts WHERE user_id=? AND source=? AND event_id=?",
                          (int(user_id), source, str(event_id))) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else None


async def xp(db, *, user_id: int, season: int) -> int:
    async with db.execute("SELECT xp FROM league_pass_progress WHERE user_id=? AND season=?",
                          (int(user_id), int(season))) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def claims(db, *, user_id: int, season: int) -> set[tuple[int, str]]:
    async with db.execute("SELECT level, track FROM league_pass_claims WHERE user_id=? AND season=?",
                          (int(user_id), int(season))) as cursor:
        legacy = {(int(r[0]), str(r[1])) for r in await cursor.fetchall()}
    async with db.execute("SELECT level, track FROM league_pass_claims_v2 WHERE user_id=? AND season=?",
                          (int(user_id), int(season))) as cursor:
        current = {(int(r[0]), str(r[1])) for r in await cursor.fetchall()}
    return current | {(level, track) for level, old in rules.TRACK_SOURCES.items() for track in rules.TRACKS if (old, track) in legacy}


async def insert_claim(db, *, user_id: int, season: int, level: int, track: str, reward: dict) -> bool:
    async with db.execute(
        "INSERT INTO league_pass_claims_v2(user_id,season,level,track,reward_json) VALUES (?,?,?,?,?::jsonb) "
        "ON CONFLICT DO NOTHING RETURNING 1",
        (int(user_id), int(season), int(level), track, json.dumps(reward)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def repeat_state(db, *, user_id: int, season: int) -> dict:
    async with db.execute("SELECT claimed, next_claim_at FROM league_pass_repeat WHERE user_id=? AND season=?",
                          (int(user_id), int(season))) as cursor:
        row = await cursor.fetchone()
    return {"claimed": int(row[0]), "next_claim_at": row[1]} if row else {"claimed": 0, "next_claim_at": None}


async def save_repeat(db, *, user_id: int, season: int, claimed: int, next_claim_at: datetime) -> None:
    await db.execute("INSERT INTO league_pass_repeat(user_id,season,claimed,next_claim_at) VALUES (?,?,?,?::text::timestamptz) "
                     "ON CONFLICT (user_id,season) DO UPDATE SET claimed=EXCLUDED.claimed,next_claim_at=EXCLUDED.next_claim_at",
                     (int(user_id), int(season), int(claimed), next_claim_at.isoformat()))
