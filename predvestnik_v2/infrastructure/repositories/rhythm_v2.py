"""Persistence primitives for server-owned Rune Rhythm runs."""
from __future__ import annotations

import json

from infrastructure.repositories import public_profiles_v1 as public_profiles


async def ensure_tables(db) -> None:
    await public_profiles.ensure_tables(db)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS rhythm_v2_runs (
            run_id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            mode TEXT NOT NULL CHECK (mode IN ('normal','augments')),
            ruleset_version TEXT NOT NULL,
            seed BYTEA NOT NULL,
            offers_json JSONB NOT NULL,
            selected_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            status TEXT NOT NULL CHECK (status IN ('choosing','active','finished','cancelled')),
            health INTEGER NOT NULL CHECK (health >= 0),
            score BIGINT NOT NULL DEFAULT 0 CHECK (score >= 0),
            combo INTEGER NOT NULL DEFAULT 0 CHECK (combo >= 0),
            correct_streak INTEGER NOT NULL DEFAULT 0 CHECK (correct_streak >= 0),
            correct_taps INTEGER NOT NULL DEFAULT 0 CHECK (correct_taps >= 0),
            mistakes INTEGER NOT NULL DEFAULT 0 CHECK (mistakes >= 0),
            next_signal_no INTEGER NOT NULL DEFAULT 1 CHECK (next_signal_no >= 1),
            integrity_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (integrity_status IN ('pending','offline_exposed','clear','review_required','quarantined','legacy_unverified')),
            integrity_reason TEXT NULL,
            integrity_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
            integrity_checked_at TIMESTAMPTZ NULL,
            signal_opened_at TIMESTAMPTZ NULL,
            version INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ NULL
        )
    """)
    # Existing results were created before the integrity boundary existed.  They
    # must never silently inherit competitive trust from a new DEFAULT.
    await db.execute("ALTER TABLE rhythm_v2_runs ADD COLUMN IF NOT EXISTS integrity_status TEXT NULL")
    await db.execute("ALTER TABLE rhythm_v2_runs ADD COLUMN IF NOT EXISTS integrity_reason TEXT NULL")
    await db.execute("ALTER TABLE rhythm_v2_runs ADD COLUMN IF NOT EXISTS integrity_evidence JSONB NULL")
    await db.execute("ALTER TABLE rhythm_v2_runs ADD COLUMN IF NOT EXISTS integrity_checked_at TIMESTAMPTZ NULL")
    await db.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid='rhythm_v2_runs'::regclass
                  AND conname='rhythm_v2_runs_integrity_status_check'
                  AND POSITION('review_required' IN pg_get_constraintdef(oid))=0
            ) THEN
                ALTER TABLE rhythm_v2_runs DROP CONSTRAINT rhythm_v2_runs_integrity_status_check;
                ALTER TABLE rhythm_v2_runs ADD CONSTRAINT rhythm_v2_runs_integrity_status_check
                    CHECK (integrity_status IN ('pending','offline_exposed','clear','review_required','quarantined','legacy_unverified'));
            END IF;
        END $$
    """)
    await db.execute("ALTER TABLE rhythm_v2_runs ALTER COLUMN integrity_status SET DEFAULT 'pending'")
    await db.execute("UPDATE rhythm_v2_runs SET integrity_status='legacy_unverified', integrity_evidence='{}'::jsonb "
                     "WHERE integrity_status IS NULL")
    await db.execute("UPDATE rhythm_v2_runs SET integrity_evidence='{}'::jsonb WHERE integrity_evidence IS NULL")
    await db.execute("ALTER TABLE rhythm_v2_runs ADD COLUMN IF NOT EXISTS transport_lease TEXT NULL")
    await db.execute("ALTER TABLE rhythm_v2_runs ADD COLUMN IF NOT EXISTS transport_lease_expires_at TIMESTAMPTZ NULL")
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS rhythm_v2_one_open_run_per_user
        ON rhythm_v2_runs(user_id) WHERE status IN ('choosing','active')
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS rhythm_v2_transport_tickets (
            ticket_hash TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES rhythm_v2_runs(run_id),
            user_id BIGINT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS rhythm_v2_actions (
            run_id TEXT NOT NULL REFERENCES rhythm_v2_runs(run_id),
            action_id TEXT NOT NULL,
            request_json JSONB NOT NULL,
            result_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (run_id, action_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS rhythm_v2_leaderboard (
            user_id BIGINT NOT NULL,
            mode TEXT NOT NULL CHECK (mode IN ('normal','augments')),
            ruleset_version TEXT NOT NULL,
            best_score BIGINT NOT NULL CHECK (best_score >= 0),
            best_run_id TEXT NOT NULL REFERENCES rhythm_v2_runs(run_id),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, mode, ruleset_version)
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS rhythm_v2_leaderboard_rank
        ON rhythm_v2_leaderboard(mode, ruleset_version, best_score DESC, updated_at ASC)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS rhythm_v2_clear_finished_rank
        ON rhythm_v2_runs(mode, ruleset_version, score DESC, finished_at ASC)
        WHERE status='finished' AND integrity_status='clear' AND score>0
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS rhythm_v2_integrity_reviews (
            review_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES rhythm_v2_runs(run_id),
            reviewer_id BIGINT NOT NULL,
            decision TEXT NOT NULL CHECK (decision IN ('clear','quarantined')),
            reason TEXT NOT NULL,
            evidence_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION reject_rhythm_v2_integrity_review_rewrite()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'rhythm v2 integrity reviews are append-only'; END;
        $$
    """)
    await db.execute("DROP TRIGGER IF EXISTS rhythm_v2_integrity_reviews_append_only ON rhythm_v2_integrity_reviews")
    await db.execute("""
        CREATE TRIGGER rhythm_v2_integrity_reviews_append_only
        BEFORE UPDATE OR DELETE ON rhythm_v2_integrity_reviews
        FOR EACH ROW EXECUTE FUNCTION reject_rhythm_v2_integrity_review_rewrite()
    """)


def dumps(value) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def load(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


async def lock_owned_run(db, *, run_id: str, user_id: int) -> dict | None:
    async with db.execute(
        "SELECT *, CLOCK_TIMESTAMP() AS server_now FROM rhythm_v2_runs "
        "WHERE run_id=? AND user_id=? FOR UPDATE",
        (str(run_id), int(user_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_action(db, *, run_id: str, action_id: str) -> dict | None:
    async with db.execute(
        "SELECT request_json,result_json FROM rhythm_v2_actions WHERE run_id=? AND action_id=?",
        (str(run_id), str(action_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def insert_action(db, *, run_id: str, action_id: str, request: dict, result: dict) -> None:
    await db.execute(
        "INSERT INTO rhythm_v2_actions(run_id,action_id,request_json,result_json) VALUES (?,?,?::jsonb,?::jsonb)",
        (str(run_id), str(action_id), dumps(request), dumps(result)),
    )


async def update_run(db, *, run_id: str, state: dict) -> None:
    # PGAdapter sends aware datetimes as naive UTC for legacy compatibility.
    # Explicit AT TIME ZONE below prevents PostgreSQL from reinterpreting them
    # as the host's local UTC+02 wall time.
    opened_at = state["signal_opened_at"]
    finished_at = state.get("finished_at")
    await db.execute(
        "UPDATE rhythm_v2_runs SET status=?,selected_json=?::jsonb,health=?,score=?,combo=?,correct_streak=?,"
        "correct_taps=?,mistakes=?,next_signal_no=?,signal_opened_at=(?::timestamp AT TIME ZONE 'UTC'),finished_at=(?::timestamp AT TIME ZONE 'UTC'),version=version+1 WHERE run_id=?",
        (state["status"], dumps(state["selected"]), int(state["health"]), int(state["score"]),
         int(state["combo"]), int(state["correct_streak"]), int(state["correct_taps"]), int(state["mistakes"]),
         int(state["next_signal_no"]), opened_at, finished_at, str(run_id)),
    )


async def set_integrity(db, *, run_id: str, status: str, reason: str, evidence: dict) -> None:
    """Persist a server verdict once; quarantine may never become clear by accident."""
    if status not in {"offline_exposed", "clear", "quarantined", "review_required"}:
        raise ValueError("unsupported Rhythm integrity status")
    await db.execute(
        "UPDATE rhythm_v2_runs SET integrity_status=?,integrity_reason=?,integrity_evidence=?::jsonb,integrity_checked_at=CLOCK_TIMESTAMP() "
        "WHERE run_id=? AND (integrity_status='pending' OR (?='quarantined' AND integrity_status='offline_exposed'))",
        (status, str(reason), dumps(evidence), str(run_id), status),
    )


async def integrity_status(db, *, run_id: str) -> str:
    async with db.execute("SELECT integrity_status FROM rhythm_v2_runs WHERE run_id=?", (str(run_id),)) as cursor:
        row = await cursor.fetchone()
    return str(row[0]) if row and row[0] else "legacy_unverified"


async def lock_run(db, *, run_id: str) -> dict | None:
    async with db.execute(
        "SELECT *,CLOCK_TIMESTAMP() AS server_now FROM rhythm_v2_runs WHERE run_id=? FOR UPDATE",
        (str(run_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def integrity_review(db, *, review_id: str) -> dict | None:
    async with db.execute(
        "SELECT review_id,run_id,reviewer_id,decision,reason,evidence_json,created_at "
        "FROM rhythm_v2_integrity_reviews WHERE review_id=?",
        (str(review_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def lock_integrity_review_id(db, *, review_id: str) -> None:
    """Serialize replay/conflict decisions for one global review id."""
    async with db.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))",
        (str(review_id),),
    ) as cursor:
        await cursor.fetchone()


async def insert_integrity_review(db, *, review_id: str, run_id: str, reviewer_id: int,
                                  decision: str, reason: str, evidence: dict) -> None:
    await db.execute(
        "INSERT INTO rhythm_v2_integrity_reviews(review_id,run_id,reviewer_id,decision,reason,evidence_json) "
        "VALUES (?,?,?,?,?,?::jsonb)",
        (str(review_id), str(run_id), int(reviewer_id), str(decision), str(reason), dumps(evidence)),
    )


async def apply_integrity_review(db, *, run_id: str, decision: str, reason: str) -> bool:
    async with db.execute(
        "UPDATE rhythm_v2_runs SET integrity_status=?,integrity_reason=?,integrity_checked_at=CLOCK_TIMESTAMP() "
        "WHERE run_id=? AND status='finished' AND integrity_status='review_required' RETURNING run_id",
        (str(decision), f"manual_review:{reason}", str(run_id)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def pending_integrity_reviews(db, *, limit: int) -> list[dict]:
    async with db.execute(
        "SELECT r.run_id,r.user_id,r.mode,r.ruleset_version,r.score,r.correct_taps,r.mistakes,r.finished_at,"
        "r.integrity_reason,r.integrity_evidence,"
        "COALESCE((SELECT JSONB_AGG((a.result_json->>'server_elapsed_ms')::integer ORDER BY a.created_at) "
        "FROM rhythm_v2_actions a WHERE a.run_id=r.run_id "
        "AND a.result_json->>'server_elapsed_ms' IS NOT NULL),'[]'::jsonb) AS timing_ms "
        "FROM rhythm_v2_runs r WHERE r.status='finished' AND r.integrity_status='review_required' "
        "ORDER BY r.finished_at ASC,r.run_id ASC LIMIT ?",
        (int(limit),),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def upsert_leaderboard(db, *, run_id: str, user_id: int, mode: str,
                             ruleset_version: str, score: int) -> None:
    # A run with no correct tap is still a valid completed attempt, but it is
    # not a meaningful competitive result and must not fill the global top.
    if int(score) <= 0:
        return
    await public_profiles.ensure_reference(db, user_id=int(user_id))
    await db.execute(
        "INSERT INTO rhythm_v2_leaderboard(user_id,mode,ruleset_version,best_score,best_run_id) "
        "SELECT ?,?,?,?,? WHERE EXISTS (SELECT 1 FROM rhythm_v2_runs WHERE run_id=? AND user_id=? "
        "AND status='finished' AND integrity_status='clear') "
        "ON CONFLICT (user_id,mode,ruleset_version) DO UPDATE SET "
        "best_score=EXCLUDED.best_score,best_run_id=EXCLUDED.best_run_id,updated_at=NOW() "
        "WHERE EXCLUDED.best_score > rhythm_v2_leaderboard.best_score OR NOT EXISTS ("
        "SELECT 1 FROM rhythm_v2_runs current_best WHERE current_best.run_id=rhythm_v2_leaderboard.best_run_id "
        "AND current_best.user_id=rhythm_v2_leaderboard.user_id AND current_best.mode=rhythm_v2_leaderboard.mode "
        "AND current_best.ruleset_version=rhythm_v2_leaderboard.ruleset_version "
        "AND current_best.status='finished' AND current_best.integrity_status='clear' AND current_best.score>0)",
        (int(user_id), str(mode), str(ruleset_version), int(score), str(run_id), str(run_id), int(user_id)),
    )


async def leaderboard(db, *, user_id: int, mode: str, ruleset_version: str) -> dict:
    async with db.execute(
        "WITH best AS (SELECT DISTINCT ON (user_id) user_id,score AS best_score,finished_at "
        "FROM rhythm_v2_runs WHERE mode=? AND ruleset_version=? AND score>0 "
        "AND status='finished' AND integrity_status='clear' "
        "ORDER BY user_id,score DESC,finished_at ASC,run_id ASC), "
        "ranked AS (SELECT user_id,best_score,RANK() OVER (ORDER BY best_score DESC,finished_at ASC,user_id ASC) AS place "
        "FROM best) SELECT user_id,best_score,place FROM ranked ORDER BY place LIMIT 20",
        (str(mode), str(ruleset_version)),
    ) as cursor:
        top = [dict(row) for row in await cursor.fetchall()]
    players = await public_profiles.player_projection(db, user_ids=[row["user_id"] for row in top])
    public_top = [
        {"place": int(row["place"]), "best_score": int(row["best_score"]),
         "player": players[int(row["user_id"])]}
        for row in top
    ]
    async with db.execute(
        "WITH best AS (SELECT DISTINCT ON (user_id) user_id,score AS best_score,finished_at "
        "FROM rhythm_v2_runs WHERE mode=? AND ruleset_version=? AND score>0 "
        "AND status='finished' AND integrity_status='clear' "
        "ORDER BY user_id,score DESC,finished_at ASC,run_id ASC), "
        "ranked AS (SELECT user_id,best_score,RANK() OVER (ORDER BY best_score DESC,finished_at ASC,user_id ASC) AS place "
        "FROM best) SELECT place,best_score FROM ranked WHERE user_id=?",
        (str(mode), str(ruleset_version), int(user_id)),
    ) as cursor:
        personal = await cursor.fetchone()
    return {"top": public_top, "personal": dict(personal) if personal else None}


async def store_transport_ticket(db, *, ticket_hash: str, run_id: str, user_id: int) -> None:
    # Tickets are deliberately one-use and short lived.  Prune only records
    # that have been unusable for an hour so reconnect retries cannot turn the
    # transport table into an unbounded append-only log.
    await db.execute(
        "DELETE FROM rhythm_v2_transport_tickets WHERE expires_at<CLOCK_TIMESTAMP()-INTERVAL '1 hour'"
    )
    await db.execute(
        "INSERT INTO rhythm_v2_transport_tickets(ticket_hash,run_id,user_id,expires_at) "
        "VALUES (?,?,?,CLOCK_TIMESTAMP()+INTERVAL '60 seconds')",
        (ticket_hash, str(run_id), int(user_id)),
    )


async def consume_transport_ticket(db, *, ticket_hash: str, run_id: str, lease: str) -> dict | None:
    """Atomically consume a one-use ticket and claim the run's live lease."""
    async with db.connection.transaction():
        async with db.execute(
            "UPDATE rhythm_v2_transport_tickets SET consumed_at=CLOCK_TIMESTAMP() "
            "WHERE ticket_hash=? AND run_id=? AND consumed_at IS NULL AND expires_at>CLOCK_TIMESTAMP() RETURNING user_id",
            (ticket_hash, str(run_id)),
        ) as cursor:
            ticket = await cursor.fetchone()
        if not ticket:
            return None
        user_id = int(ticket["user_id"])
        async with db.execute(
            "UPDATE rhythm_v2_runs SET transport_lease=?,transport_lease_expires_at=CLOCK_TIMESTAMP()+INTERVAL '30 seconds', "
            "signal_opened_at=COALESCE(signal_opened_at,CLOCK_TIMESTAMP()) "
            "WHERE run_id=? AND user_id=? AND status='active' AND integrity_status='pending' "
            "AND (transport_lease_expires_at IS NULL OR transport_lease_expires_at<CLOCK_TIMESTAMP()) RETURNING *",
            (str(lease), str(run_id), user_id),
        ) as cursor:
            run = await cursor.fetchone()
        if not run:
            return None
    return dict(run)


async def extend_transport_lease(db, *, run_id: str, user_id: int, lease: str) -> bool:
    async with db.execute(
        "UPDATE rhythm_v2_runs SET transport_lease_expires_at=CLOCK_TIMESTAMP()+INTERVAL '30 seconds' "
        "WHERE run_id=? AND user_id=? AND transport_lease=? AND transport_lease_expires_at>CLOCK_TIMESTAMP()",
        (str(run_id), int(user_id), str(lease)),
    ):
        pass
    async with db.execute(
        "SELECT 1 FROM rhythm_v2_runs WHERE run_id=? AND user_id=? AND transport_lease=? AND transport_lease_expires_at>CLOCK_TIMESTAMP()",
        (str(run_id), int(user_id), str(lease)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def release_transport_lease(db, *, run_id: str, user_id: int, lease: str) -> None:
    await db.execute(
        "UPDATE rhythm_v2_runs SET transport_lease=NULL,transport_lease_expires_at=NULL "
        "WHERE run_id=? AND user_id=? AND transport_lease=?",
        (str(run_id), int(user_id), str(lease)),
    )
