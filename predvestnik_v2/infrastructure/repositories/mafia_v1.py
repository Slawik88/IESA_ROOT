"""PostgreSQL persistence for the server-owned chat Mafia v1."""
from __future__ import annotations

import json


def dumps(value) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def load(value):
    return json.loads(value) if isinstance(value, str) else value


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS mafia_v1_matches (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            topic_id BIGINT NULL,
            initiator_id BIGINT NOT NULL,
            ruleset_version TEXT NOT NULL,
            max_players INTEGER NOT NULL CHECK (max_players BETWEEN 4 AND 20),
            enabled_roles_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            vote_mode TEXT NOT NULL CHECK (vote_mode IN ('open','secret')),
            phase TEXT NOT NULL CHECK (phase IN ('lobby','night','discussion','voting','paused','finished','cancelled')),
            phase_number INTEGER NOT NULL DEFAULT 0 CHECK (phase_number >= 0),
            phase_deadline TIMESTAMPTZ NULL,
            state_version INTEGER NOT NULL DEFAULT 1 CHECK (state_version > 0),
            lobby_message_id BIGINT NULL,
            phase_message_id BIGINT NULL,
            lobby_human_messages INTEGER NOT NULL DEFAULT 0 CHECK (lobby_human_messages >= 0),
            winner TEXT NULL CHECK (winner IN ('town','mafia','draw')),
            finished_reason TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ NULL,
            finished_at TIMESTAMPTZ NULL,
            paused_at TIMESTAMPTZ NULL,
            paused_phase TEXT NULL CHECK (paused_phase IS NULL OR paused_phase IN ('night','discussion','voting')),
            paused_remaining_seconds INTEGER NULL CHECK (paused_remaining_seconds IS NULL OR paused_remaining_seconds >= 0)
        )
    """)
    # Existing databases need the same pause provenance as new installs.
    await db.execute(
        "ALTER TABLE mafia_v1_matches ADD COLUMN IF NOT EXISTS paused_phase TEXT NULL "
        "CHECK (paused_phase IS NULL OR paused_phase IN ('night','discussion','voting'))"
    )
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS mafia_v1_one_active_match_per_chat_topic
        ON mafia_v1_matches(chat_id, COALESCE(topic_id, 0))
        WHERE phase IN ('lobby','night','discussion','voting','paused')
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS mafia_v1_players (
            match_id BIGINT NOT NULL REFERENCES mafia_v1_matches(id) ON DELETE RESTRICT,
            user_id BIGINT NOT NULL,
            join_order INTEGER NOT NULL CHECK (join_order > 0),
            username TEXT NULL,
            display_name TEXT NOT NULL,
            role TEXT NULL CHECK (role IS NULL OR role IN ('citizen','mafia','don','doctor','detective')),
            alive BOOLEAN NOT NULL DEFAULT TRUE,
            left_chat_at TIMESTAMPTZ NULL,
            dm_ready BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY(match_id, user_id),
            UNIQUE(match_id, join_order)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS mafia_v1_dm_ready (
            user_id BIGINT PRIMARY KEY,
            confirmed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS mafia_v1_actions (
            match_id BIGINT NOT NULL REFERENCES mafia_v1_matches(id) ON DELETE RESTRICT,
            phase_number INTEGER NOT NULL CHECK (phase_number > 0),
            user_id BIGINT NOT NULL,
            action_type TEXT NOT NULL CHECK (action_type IN ('vote','mafia_target','doctor_save','detective_check')),
            target_user_id BIGINT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(match_id, phase_number, user_id, action_type)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS mafia_v1_audit_events (
            id BIGSERIAL PRIMARY KEY,
            match_id BIGINT NOT NULL REFERENCES mafia_v1_matches(id) ON DELETE RESTRICT,
            event_type TEXT NOT NULL,
            actor_id BIGINT NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS mafia_v1_due_phases ON mafia_v1_matches(phase_deadline) WHERE phase IN ('night','discussion','voting')")


async def lock_chat(db, *, chat_id: int, topic_id: int | None) -> None:
    # A chat settings row is the stable, shared lock even before a match exists.
    await db.execute("INSERT INTO chat_settings(chat_id) VALUES (?) ON CONFLICT DO NOTHING", (int(chat_id),))
    async with db.execute("SELECT chat_id FROM chat_settings WHERE chat_id=? FOR UPDATE", (int(chat_id),)) as cursor:
        await cursor.fetchone()


async def purge_active(db, *, chat_id: int) -> bool:
    async with db.execute("SELECT COALESCE(is_purging,FALSE) FROM chat_settings WHERE chat_id=?", (int(chat_id),)) as cursor:
        row = await cursor.fetchone()
    return bool(row and row[0])


async def active_match(db, *, chat_id: int, topic_id: int | None, for_update: bool = False) -> dict | None:
    suffix = " FOR UPDATE" if for_update else ""
    async with db.execute(
        "SELECT *,CLOCK_TIMESTAMP() AS server_now FROM mafia_v1_matches "
        "WHERE chat_id=? AND COALESCE(topic_id,0)=COALESCE(?,0) "
        "AND phase IN ('lobby','night','discussion','voting','paused') ORDER BY id DESC LIMIT 1" + suffix,
        (int(chat_id), topic_id),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def lock_match(db, *, match_id: int) -> dict | None:
    async with db.execute("SELECT *,CLOCK_TIMESTAMP() AS server_now FROM mafia_v1_matches WHERE id=? FOR UPDATE", (int(match_id),)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def due_match_ids(db, *, limit: int = 25) -> list[int]:
    async with db.execute(
        "SELECT id FROM mafia_v1_matches WHERE phase IN ('night','discussion','voting') "
        "AND phase_deadline<=CLOCK_TIMESTAMP() ORDER BY phase_deadline ASC LIMIT ?",
        (int(limit),),
    ) as cursor:
        return [int(row[0]) for row in await cursor.fetchall()]


async def get_match(db, *, match_id: int) -> dict | None:
    async with db.execute("SELECT *,CLOCK_TIMESTAMP() AS server_now FROM mafia_v1_matches WHERE id=?", (int(match_id),)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def mark_dm_ready(db, *, user_id: int) -> None:
    await db.execute(
        "INSERT INTO mafia_v1_dm_ready(user_id) VALUES (?) "
        "ON CONFLICT(user_id) DO UPDATE SET confirmed_at=CLOCK_TIMESTAMP()",
        (int(user_id),),
    )


async def dm_ready_users(db, *, user_ids: list[int]) -> set[int]:
    if not user_ids:
        return set()
    placeholders = ",".join("?" for _ in user_ids)
    async with db.execute(
        f"SELECT user_id FROM mafia_v1_dm_ready WHERE user_id IN ({placeholders}) "
        "AND confirmed_at>CLOCK_TIMESTAMP()-INTERVAL '30 days'", list(map(int, user_ids)),
    ) as cursor:
        return {int(row[0]) for row in await cursor.fetchall()}


async def create_match(db, *, chat_id: int, topic_id: int | None, initiator_id: int, max_players: int,
                       enabled_roles: tuple[str, ...], vote_mode: str, ruleset_version: str) -> dict:
    async with db.execute(
        "INSERT INTO mafia_v1_matches(chat_id,topic_id,initiator_id,ruleset_version,max_players,enabled_roles_json,vote_mode,phase) "
        "VALUES (?,?,?,?,?,?::jsonb,?,'lobby') RETURNING *,CLOCK_TIMESTAMP() AS server_now",
        (int(chat_id), topic_id, int(initiator_id), ruleset_version, int(max_players), dumps(list(enabled_roles)), str(vote_mode)),
    ) as cursor:
        return dict(await cursor.fetchone())


async def players(db, *, match_id: int, for_update: bool = False) -> list[dict]:
    suffix = " FOR UPDATE" if for_update else ""
    async with db.execute("SELECT * FROM mafia_v1_players WHERE match_id=? ORDER BY join_order" + suffix, (int(match_id),)) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def player(db, *, match_id: int, user_id: int, for_update: bool = False) -> dict | None:
    suffix = " FOR UPDATE" if for_update else ""
    async with db.execute("SELECT * FROM mafia_v1_players WHERE match_id=? AND user_id=?" + suffix, (int(match_id), int(user_id))) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def add_player(db, *, match_id: int, user_id: int, username: str | None, display_name: str) -> bool:
    async with db.execute(
        "INSERT INTO mafia_v1_players(match_id,user_id,join_order,username,display_name) "
        "SELECT ?,?,COALESCE(MAX(join_order),0)+1,?,? FROM mafia_v1_players WHERE match_id=? "
        "ON CONFLICT(match_id,user_id) DO NOTHING RETURNING user_id",
        (int(match_id), int(user_id), username, str(display_name)[:128], int(match_id)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def remove_player(db, *, match_id: int, user_id: int) -> bool:
    async with db.execute("DELETE FROM mafia_v1_players WHERE match_id=? AND user_id=? RETURNING user_id", (int(match_id), int(user_id))) as cursor:
        return bool(await cursor.fetchone())


async def update_match(db, *, match_id: int, phase: str, phase_number: int, deadline, winner: str | None = None,
                       finished_reason: str | None = None, started: bool = False, paused_phase: str | None = None,
                       paused_remaining_seconds: int | None = None) -> None:
    await db.execute(
        "UPDATE mafia_v1_matches SET phase=?,phase_number=?,phase_deadline=(?::timestamp AT TIME ZONE 'UTC'),winner=?,finished_reason=?,"
        "started_at=CASE WHEN ? THEN COALESCE(started_at,CLOCK_TIMESTAMP()) ELSE started_at END,"
        "finished_at=CASE WHEN ? IN ('finished','cancelled') THEN CLOCK_TIMESTAMP() ELSE finished_at END,"
        "paused_at=CASE WHEN ?='paused' THEN CLOCK_TIMESTAMP() ELSE NULL END,paused_phase=?,paused_remaining_seconds=?,state_version=state_version+1 WHERE id=?",
        (str(phase), int(phase_number), deadline, winner, finished_reason, bool(started), str(phase), str(phase), paused_phase, paused_remaining_seconds, int(match_id)),
    )


async def update_settings(db, *, match_id: int, max_players: int, enabled_roles: tuple[str, ...], vote_mode: str) -> None:
    await db.execute(
        "UPDATE mafia_v1_matches SET max_players=?,enabled_roles_json=?::jsonb,vote_mode=?,state_version=state_version+1 WHERE id=? AND phase='lobby'",
        (int(max_players), dumps(list(enabled_roles)), str(vote_mode), int(match_id)),
    )


async def bind_lobby_message(db, *, match_id: int, message_id: int) -> None:
    await db.execute("UPDATE mafia_v1_matches SET lobby_message_id=?,lobby_human_messages=0,state_version=state_version+1 WHERE id=?", (int(message_id), int(match_id)))


async def bind_phase_message(db, *, match_id: int, message_id: int) -> None:
    await db.execute("UPDATE mafia_v1_matches SET phase_message_id=? WHERE id=?", (int(message_id), int(match_id)))


async def timed_matches(db, *, limit: int = 25) -> list[dict]:
    async with db.execute(
        "SELECT *,CLOCK_TIMESTAMP() AS server_now FROM mafia_v1_matches "
        "WHERE phase IN ('night','discussion','voting') ORDER BY phase_deadline ASC LIMIT ?", (int(limit),)
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def note_lobby_message(db, *, chat_id: int, topic_id: int | None) -> dict | None:
    async with db.execute(
        "UPDATE mafia_v1_matches SET lobby_human_messages=lobby_human_messages+1 "
        "WHERE chat_id=? AND COALESCE(topic_id,0)=COALESCE(?,0) AND phase='lobby' "
        "RETURNING *,CLOCK_TIMESTAMP() AS server_now", (int(chat_id), topic_id),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def reset_lobby_counter(db, *, match_id: int) -> None:
    await db.execute("UPDATE mafia_v1_matches SET lobby_human_messages=0,state_version=state_version+1 WHERE id=?", (int(match_id),))


async def set_roles(db, *, match_id: int, by_user: dict[int, str]) -> None:
    for user_id, role in by_user.items():
        await db.execute("UPDATE mafia_v1_players SET role=? WHERE match_id=? AND user_id=?", (str(role), int(match_id), int(user_id)))


async def upsert_action(db, *, match_id: int, phase_number: int, user_id: int, action_type: str, target_user_id: int | None) -> None:
    await db.execute(
        "INSERT INTO mafia_v1_actions(match_id,phase_number,user_id,action_type,target_user_id) VALUES (?,?,?,?,?) "
        "ON CONFLICT(match_id,phase_number,user_id,action_type) DO UPDATE SET target_user_id=EXCLUDED.target_user_id,created_at=CLOCK_TIMESTAMP()",
        (int(match_id), int(phase_number), int(user_id), str(action_type), target_user_id),
    )


async def actions(db, *, match_id: int, phase_number: int) -> list[dict]:
    async with db.execute("SELECT * FROM mafia_v1_actions WHERE match_id=? AND phase_number=?", (int(match_id), int(phase_number))) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def player_history(db, *, user_id: int, limit: int = 20) -> list[dict]:
    """Read only the requesting player's own role and match result."""
    async with db.execute(
        "SELECT m.id,m.chat_id,m.phase,m.winner,m.finished_reason,m.started_at,m.finished_at,p.role "
        "FROM mafia_v1_matches m JOIN mafia_v1_players p ON p.match_id=m.id "
        "WHERE p.user_id=? ORDER BY COALESCE(m.finished_at,m.created_at) DESC LIMIT ?",
        (int(user_id), max(1, min(int(limit), 50))),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def kill_player(db, *, match_id: int, user_id: int) -> bool:
    async with db.execute("UPDATE mafia_v1_players SET alive=FALSE WHERE match_id=? AND user_id=? AND alive=TRUE RETURNING user_id", (int(match_id), int(user_id))) as cursor:
        return bool(await cursor.fetchone())


async def audit(db, *, match_id: int, event_type: str, actor_id: int | None, payload: dict | None = None) -> None:
    await db.execute("INSERT INTO mafia_v1_audit_events(match_id,event_type,actor_id,payload_json) VALUES (?,?,?,?::jsonb)", (int(match_id), str(event_type), actor_id, dumps(payload or {})))
