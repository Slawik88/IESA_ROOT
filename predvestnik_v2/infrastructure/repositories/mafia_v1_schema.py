"""DDL for the chat Mafia v1 tables (idempotent, run at bot and web start)."""
from __future__ import annotations


async def ensure_schema(db) -> None:
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
    await _ensure_v2_columns(db)


async def _ensure_v2_columns(db) -> None:
    """Columns/tables added after the first release; every statement is re-runnable."""
    for column in (
        "tempo TEXT NOT NULL DEFAULT 'normal' CHECK (tempo IN ('fast','normal','slow'))",
        "last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        "idle_phases INTEGER NOT NULL DEFAULT 0 CHECK (idle_phases >= 0)",
        "card_updated_at TIMESTAMPTZ NULL",
        "phase_started_at TIMESTAMPTZ NULL",
        "pause_detail TEXT NULL",
        "pending_event_json JSONB NULL",
        "roles_auto BOOLEAN NOT NULL DEFAULT TRUE",
        "last_bump_at TIMESTAMPTZ NULL",
    ):
        await db.execute(f"ALTER TABLE mafia_v1_matches ADD COLUMN IF NOT EXISTS {column}")
    await db.execute("""
        CREATE INDEX IF NOT EXISTS mafia_v1_pending_events
        ON mafia_v1_matches(id) WHERE pending_event_json IS NOT NULL
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS mafia_v1_lobby_idle
        ON mafia_v1_matches(last_activity_at) WHERE phase = 'lobby'
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS mafia_v1_dm_prompts (
            match_id BIGINT NOT NULL REFERENCES mafia_v1_matches(id) ON DELETE RESTRICT,
            phase_number INTEGER NOT NULL,
            user_id BIGINT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('action','team')),
            message_id BIGINT NOT NULL,
            PRIMARY KEY(match_id, phase_number, user_id, kind)
        )
    """)
