"""Storage of «Гонка за Пропуском» (core.pass_race): the start of each season's race and the players who reached it.

Additive schema only (CREATE ... IF NOT EXISTS under an advisory lock, like league_pass).  The place of a player is not
stored: it is computed from reached_at and status (core.pass_race.seated), so a rejection hands the place on by itself.
"""
from __future__ import annotations

from datetime import datetime

from core import pass_race as rules

def _epoch(value: datetime) -> float:
    """Moments go to SQL as epoch seconds: the adapter strips the zone from datetimes, and a session that is not in UTC
    would then shift them (local test clusters run in Europe/Berlin)."""
    return value.timestamp()


_COLUMNS = "season, user_id, reached_at, status, marked_by, marked_at, note, owner_alerted_at, player_told_at, recovered"


async def ensure_tables(db) -> None:
    if await _schema_ready(db):
        return
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('pass-race-schema',0))")
        if not await _schema_ready(db):
            await _install_tables(db)


async def _schema_ready(db) -> bool:
    async with db.execute("SELECT to_regclass('pass_race_runs') IS NOT NULL AND to_regclass('pass_race_entries') IS NOT NULL") as cur:
        return bool((await cur.fetchone())[0])


async def _install_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pass_race_runs (
            season     INTEGER PRIMARY KEY CHECK (season >= 2),
            started_at TIMESTAMPTZ NOT NULL,
            resumed_at TIMESTAMPTZ NOT NULL,       -- the last switch-on: a crossing before it (during a pause) never counts
            started_by BIGINT NOT NULL
        )
    """)
    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS pass_race_entries (
            season           INTEGER NOT NULL,
            user_id          BIGINT NOT NULL,
            reached_at       TIMESTAMPTZ NOT NULL,
            status           TEXT NOT NULL DEFAULT '{rules.PENDING}'
                             CHECK (status IN ({", ".join(f"'{s}'" for s in rules.STATUSES)})),
            marked_by        BIGINT,
            marked_at        TIMESTAMPTZ,
            note             TEXT NOT NULL DEFAULT '',
            owner_alerted_at TIMESTAMPTZ,
            player_told_at   TIMESTAMPTZ,
            recovered        BOOLEAN NOT NULL DEFAULT FALSE,   -- found by the sweep after a failed live recording
            PRIMARY KEY (season, user_id)
        )
    """)


async def lock_race(db, season: int) -> None:
    """One writer at a time per race: the order of places is the order of this lock."""
    await db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?, 0))", (f"pass-race:{int(season)}",))


async def run(db, season: int) -> dict | None:
    async with db.execute("SELECT season, started_at, resumed_at, started_by FROM pass_race_runs WHERE season = ?", (int(season),)) as cur:
        row = await cur.fetchone()
    return {"season": int(row[0]), "started_at": row[1], "resumed_at": row[2], "started_by": int(row[3])} if row else None


async def start(db, *, season: int, actor_id: int) -> None:
    """The first switch-on of a season fixes its start; later ones keep it and only mark the end of the pause."""
    await db.execute("INSERT INTO pass_race_runs (season, started_at, resumed_at, started_by) "
                     "VALUES (?, CLOCK_TIMESTAMP(), CLOCK_TIMESTAMP(), ?) "
                     "ON CONFLICT (season) DO UPDATE SET resumed_at = CLOCK_TIMESTAMP()", (int(season), int(actor_id)))


async def add_entry(db, *, season: int, user_id: int, reached_at: datetime | None = None) -> datetime | None:
    """Record the crossing (after lock_race).  Live: the server clock, never earlier than the last recorded one (a clock
    step back cannot reorder places).  Recovered: the time of the crossing from the receipts.  None: already recorded."""
    if reached_at is None:
        sql = ("INSERT INTO pass_race_entries (season, user_id, reached_at) SELECT ?, ?, GREATEST(CLOCK_TIMESTAMP(), "
               "(SELECT MAX(reached_at) + INTERVAL '1 microsecond' FROM pass_race_entries WHERE season = ?)) "
               "ON CONFLICT (season, user_id) DO NOTHING RETURNING reached_at")
        args = (int(season), int(user_id), int(season))
    else:
        sql = ("INSERT INTO pass_race_entries (season, user_id, reached_at, recovered) VALUES (?, ?, TO_TIMESTAMP(?), TRUE) "
               "ON CONFLICT (season, user_id) DO NOTHING RETURNING reached_at")
        args = (int(season), int(user_id), _epoch(reached_at))
    async with db.execute(sql, args) as cur:
        row = await cur.fetchone()
    return row[0] if row else None


def _entry(row) -> dict:
    keys = [c.strip() for c in _COLUMNS.split(",")]
    return dict(zip(keys, row))


async def entries(db, season: int) -> list[dict]:
    async with db.execute(f"SELECT {_COLUMNS} FROM pass_race_entries WHERE season = ? ORDER BY reached_at, user_id",
                          (int(season),)) as cur:
        return [_entry(r) for r in await cur.fetchall()]


async def entry_for_update(db, *, season: int, user_id: int) -> dict | None:
    async with db.execute(f"SELECT {_COLUMNS} FROM pass_race_entries WHERE season = ? AND user_id = ? FOR UPDATE",
                          (int(season), int(user_id))) as cur:
        row = await cur.fetchone()
    return _entry(row) if row else None


async def set_status(db, *, season: int, user_id: int, status: str, actor_id: int, note: str) -> None:
    await db.execute("UPDATE pass_race_entries SET status = ?, marked_by = ?, marked_at = CLOCK_TIMESTAMP(), note = ? "
                     "WHERE season = ? AND user_id = ?", (status, int(actor_id), note, int(season), int(user_id)))


async def claim_owner_alert(db, *, season: int, user_id: int) -> bool:
    """Exactly one «place taken» message per player: the first caller wins."""
    async with db.execute("UPDATE pass_race_entries SET owner_alerted_at = CLOCK_TIMESTAMP() "
                          "WHERE season = ? AND user_id = ? AND owner_alerted_at IS NULL RETURNING 1",
                          (int(season), int(user_id))) as cur:
        return bool(await cur.fetchone())


async def release_owner_alert(db, *, season: int, user_id: int) -> None:
    """No owner got the message: the next sweep tries again."""
    await db.execute("UPDATE pass_race_entries SET owner_alerted_at = NULL WHERE season = ? AND user_id = ?", (int(season), int(user_id)))


async def mark_player_told(db, *, season: int, user_id: int) -> None:
    await db.execute("UPDATE pass_race_entries SET player_told_at = CLOCK_TIMESTAMP() WHERE season = ? AND user_id = ?",
                     (int(season), int(user_id)))


async def seasons_to_alert(db) -> list[int]:
    async with db.execute("SELECT DISTINCT season FROM pass_race_entries WHERE owner_alerted_at IS NULL AND status <> ?",
                          (rules.REJECTED,)) as cur:
        return sorted(int(r[0]) for r in await cur.fetchall())


async def open_seasons(db) -> list[int]:
    """Seasons with places still waiting for the owner (checked or not paid yet)."""
    async with db.execute("SELECT DISTINCT season FROM pass_race_entries WHERE status IN (?, ?)", (rules.PENDING, rules.VERIFIED)) as cur:
        return sorted(int(r[0]) for r in await cur.fetchall())


async def missed_crossings(db, *, season: int, since: datetime, full_xp: int) -> list[tuple[int, datetime]]:
    """Players whose receipts crossed full_xp at or after `since` but who have no entry: a live recording that failed.
    The crossing moment is the receipt that brought the season total to full_xp."""
    async with db.execute("""
        WITH done AS (SELECT user_id FROM league_pass_progress WHERE season = ? AND xp >= ?),
        r AS (SELECT user_id, created_at, SUM(xp) OVER (PARTITION BY user_id ORDER BY created_at, source, event_id
                                                        ROWS UNBOUNDED PRECEDING) AS total
              FROM league_pass_receipts WHERE season = ? AND user_id IN (SELECT user_id FROM done)),
        c AS (SELECT user_id, MIN(created_at) AS crossed_at FROM r WHERE total >= ? GROUP BY user_id)
        SELECT c.user_id, c.crossed_at FROM c
        WHERE c.crossed_at >= TO_TIMESTAMP(?) AND NOT EXISTS (SELECT 1 FROM pass_race_entries e WHERE e.season = ? AND e.user_id = c.user_id)
        ORDER BY c.crossed_at, c.user_id""", (int(season), int(full_xp), int(season), int(full_xp), _epoch(since), int(season))) as cur:
        return [(int(r[0]), r[1]) for r in await cur.fetchall()]


async def usernames(db, ids) -> dict[int, str | None]:
    ids = sorted({int(i) for i in ids if i})
    if not ids:
        return {}
    async with db.execute("SELECT user_tg_id, user_tg_username FROM users WHERE user_tg_id = ANY(?::bigint[])", (ids,)) as cur:
        return {int(r[0]): r[1] for r in await cur.fetchall()}


async def _count(db, table: str, sql: str, args: tuple) -> int | None:
    async with db.execute("SELECT to_regclass(?) IS NOT NULL", (table,)) as cur:
        if not (await cur.fetchone())[0]:
            return None
    async with db.execute(sql, args) as cur:
        return int((await cur.fetchone())[0])


async def unchecked_games(db, *, user_id: int, since: datetime, league_season: str) -> dict[str, int | None]:
    """Games of the season the server could not vouch for: Rhythm not yet or not cleanly checked (or timed on the phone),
    Minesweeper played without the network, ranked levels marked for a human look.  None: the game has no table here."""
    uid = int(user_id)
    return {
        "rhythm": await _count(
            db, "rhythm_v2_runs",
            "SELECT COUNT(*) FROM rhythm_v2_runs WHERE user_id = ? AND status = 'finished' AND finished_at >= TO_TIMESTAMP(?) "
            "AND (integrity_status IN ('pending','review_required','quarantined','offline_exposed','legacy_unverified') "
            "OR integrity_evidence->>'client_timed' = 'true')", (uid, _epoch(since))),
        "minesweeper": await _count(
            db, "minesweeper_v2_runs",
            "SELECT COUNT(*) FROM minesweeper_v2_runs r WHERE r.user_id = ? AND r.status IN ('won','lost') AND r.finished_at >= TO_TIMESTAMP(?) "
            "AND EXISTS (SELECT 1 FROM minesweeper_v2_actions a WHERE a.run_id = r.run_id AND a.action_id = 'local:packet:v1')",
            (uid, _epoch(since))),
        "ranked_marked": await _count(
            db, "league_demo_runs",
            "SELECT COUNT(*) FROM league_demo_runs WHERE user_id = ? AND season = ? "
            "AND jsonb_array_length(COALESCE(result_json->'detail'->'review', '[]'::jsonb)) > 0", (uid, league_season)),
    }


async def put_flag(db, enabled: bool) -> None:
    """The race's system flag (FastAPI, «Что нового» and patch notes read it); no commit: the caller's transaction."""
    await db.execute("INSERT INTO system_flags (key, enabled, label) VALUES (?, ?, ?) "
                     "ON CONFLICT (key) DO UPDATE SET enabled = EXCLUDED.enabled",
                     (rules.FLAG, int(bool(enabled)), "🏁 Гонка за Пропуском: 50 ⭐ первым четверым"))
