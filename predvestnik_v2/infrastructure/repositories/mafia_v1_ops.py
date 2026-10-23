"""Operational queries for Mafia v1: durable notifications, card pacing, lobby TTL, DM prompts."""
from __future__ import annotations

from uuid import uuid4

from infrastructure.repositories.mafia_v1 import dumps, load


async def touch_activity(db, *, match_id: int) -> None:
    await db.execute("UPDATE mafia_v1_matches SET last_activity_at=CLOCK_TIMESTAMP() WHERE id=?", (int(match_id),))


async def shorten_deadline(db, *, match_id: int, deadline) -> bool:
    """Pull the current phase deadline earlier; never extends it."""
    async with db.execute(
        "UPDATE mafia_v1_matches SET phase_deadline=LEAST(phase_deadline,(?::timestamp AT TIME ZONE 'UTC')),"
        "state_version=state_version+1 WHERE id=? AND phase IN ('night','discussion','voting') "
        "AND phase_deadline>(?::timestamp AT TIME ZONE 'UTC') RETURNING id",
        (deadline, int(match_id), deadline),
    ) as cursor:
        return bool(await cursor.fetchone())


async def restart_clock(db, *, match_id: int, phase: str, phase_number: int, seconds: int,
                        max_shift_seconds: int = 30) -> bool:
    """Start the phase timer when the buttons were actually delivered, not when the phase was committed.

    Moves only an untouched timer (not shortened by an early close, not paused) and only by the real
    delivery delay, capped: a slow Telegram never steals a player's night, nor stretches it unboundedly.
    """
    async with db.execute(
        "UPDATE mafia_v1_matches SET "
        "phase_deadline=phase_deadline+LEAST(CLOCK_TIMESTAMP()-phase_started_at,(?::int*INTERVAL '1 second')),"
        "phase_started_at=phase_started_at+LEAST(CLOCK_TIMESTAMP()-phase_started_at,(?::int*INTERVAL '1 second')),"
        "state_version=state_version+1 "
        "WHERE id=? AND phase=? AND phase_number=? AND phase_started_at IS NOT NULL "
        "AND CLOCK_TIMESTAMP()-phase_started_at>=INTERVAL '2 seconds' "
        "AND ABS(EXTRACT(EPOCH FROM phase_deadline-phase_started_at)-?::int)<1 RETURNING id",
        (int(max_shift_seconds), int(max_shift_seconds), int(match_id), str(phase), int(phase_number), int(seconds)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def claim_card_refresh(db, *, match_id: int, gap_seconds: float) -> bool:
    """Atomically win the right to edit a phase card (multi-process safe pacing)."""
    async with db.execute(
        "UPDATE mafia_v1_matches SET card_updated_at=CLOCK_TIMESTAMP() WHERE id=? AND "
        "(card_updated_at IS NULL OR card_updated_at<=CLOCK_TIMESTAMP()-(?::double precision*INTERVAL '1 second')) RETURNING id",
        (int(match_id), float(gap_seconds)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def claim_bump(db, *, match_id: int, gap_seconds: float) -> bool:
    """At most one card bump per gap, even with several processes or a message flood."""
    async with db.execute(
        "UPDATE mafia_v1_matches SET last_bump_at=CLOCK_TIMESTAMP() WHERE id=? AND "
        "(last_bump_at IS NULL OR last_bump_at<=CLOCK_TIMESTAMP()-(?::double precision*INTERVAL '1 second')) RETURNING id",
        (int(match_id), float(gap_seconds)),
    ) as cursor:
        return bool(await cursor.fetchone())


async def set_idle_phases(db, *, match_id: int, value: int) -> None:
    await db.execute("UPDATE mafia_v1_matches SET idle_phases=? WHERE id=?", (int(value), int(match_id)))


async def set_pending_event(db, *, match_id: int, event: dict) -> None:
    # token отличает это событие от более нового: опоздавшая доставка не отметит и не сотрёт чужое
    event = {**event, "token": uuid4().hex}
    await db.execute("UPDATE mafia_v1_matches SET pending_event_json=?::jsonb WHERE id=?", (dumps(event), int(match_id)))


async def mark_event_step(db, *, match_id: int, step: str, token: str | None = None) -> None:
    await db.execute(
        "UPDATE mafia_v1_matches SET pending_event_json=jsonb_set(pending_event_json,'{done}',"
        "COALESCE(pending_event_json->'done','[]'::jsonb)||to_jsonb(?::text),true) "
        "WHERE id=? AND pending_event_json IS NOT NULL AND (?::text IS NULL OR pending_event_json->>'token'=?::text)",
        (str(step), int(match_id), token, token),
    )


async def clear_pending_event(db, *, match_id: int, token: str | None = None) -> None:
    """Стереть событие; с token — только если оно ещё то самое (его не заменило более новое)."""
    await db.execute(
        "UPDATE mafia_v1_matches SET pending_event_json=NULL "
        "WHERE id=? AND (?::text IS NULL OR pending_event_json->>'token'=?::text)", (int(match_id), token, token),
    )


async def pending_event_ids(db, *, limit: int = 25) -> list[int]:
    async with db.execute(
        "SELECT id FROM mafia_v1_matches WHERE pending_event_json IS NOT NULL ORDER BY id LIMIT ?", (int(limit),),
    ) as cursor:
        return [int(row[0]) for row in await cursor.fetchall()]


async def claim_event(db, *, match_id: int, lease_seconds: int = 45) -> dict | None:
    """Lease the stored event to one deliverer; also counts the attempt.  None = nothing to do."""
    async with db.execute(
        "UPDATE mafia_v1_matches SET pending_event_json=jsonb_set(jsonb_set(pending_event_json,'{lease}',"
        "to_jsonb(EXTRACT(EPOCH FROM CLOCK_TIMESTAMP())::bigint+?::bigint),true),'{attempts}',"
        "to_jsonb(COALESCE((pending_event_json->>'attempts')::int,0)+1),true) "
        "WHERE id=? AND pending_event_json IS NOT NULL "
        "AND COALESCE((pending_event_json->>'lease')::bigint,0)<EXTRACT(EPOCH FROM CLOCK_TIMESTAMP())::bigint "
        "RETURNING pending_event_json", (int(lease_seconds), int(match_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return (load(row[0]) or {}) if row else None


async def release_event(db, *, match_id: int, delay_seconds: float = 0, token: str | None = None) -> None:
    """Let the next tick retry instead of waiting for the lease to expire (after ``delay_seconds``, 0 = at once)."""
    await db.execute(
        "UPDATE mafia_v1_matches SET pending_event_json=jsonb_set(pending_event_json,'{lease}',"
        "to_jsonb(CASE WHEN ?::double precision>0 THEN CEIL(EXTRACT(EPOCH FROM CLOCK_TIMESTAMP())+?::double precision)::bigint "
        "ELSE 0::bigint END),true) "
        "WHERE id=? AND pending_event_json IS NOT NULL AND (?::text IS NULL OR pending_event_json->>'token'=?::text)",
        (float(delay_seconds), float(delay_seconds), int(match_id), token, token),
    )


async def stale_lobby_ids(db, *, idle_seconds: int, limit: int = 25) -> list[int]:
    async with db.execute(
        "SELECT id FROM mafia_v1_matches WHERE phase='lobby' "
        "AND last_activity_at<CLOCK_TIMESTAMP()-(?::double precision*INTERVAL '1 second') ORDER BY id LIMIT ?",
        (float(idle_seconds), int(limit)),
    ) as cursor:
        return [int(row[0]) for row in await cursor.fetchall()]


async def save_prompt(db, *, match_id: int, phase_number: int, user_id: int, kind: str, message_id: int) -> None:
    await db.execute(
        "INSERT INTO mafia_v1_dm_prompts(match_id,phase_number,user_id,kind,message_id) VALUES (?,?,?,?,?) "
        "ON CONFLICT(match_id,phase_number,user_id,kind) DO UPDATE SET message_id=EXCLUDED.message_id",
        (int(match_id), int(phase_number), int(user_id), str(kind), int(message_id)),
    )


async def prompts(db, *, match_id: int, phase_number: int, kind: str | None = None) -> list[dict]:
    sql = "SELECT user_id,kind,message_id FROM mafia_v1_dm_prompts WHERE match_id=? AND phase_number=?"
    args: list = [int(match_id), int(phase_number)]
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    async with db.execute(sql, args) as cursor:
        return [{"user_id": int(r[0]), "kind": r[1], "message_id": int(r[2])} for r in await cursor.fetchall()]


async def prompts_before(db, *, match_id: int, phase_number: int) -> list[dict]:
    async with db.execute(
        "SELECT phase_number,user_id,kind,message_id FROM mafia_v1_dm_prompts WHERE match_id=? AND phase_number<?",
        (int(match_id), int(phase_number)),
    ) as cursor:
        return [{"phase_number": int(r[0]), "user_id": int(r[1]), "kind": r[2], "message_id": int(r[3])}
                for r in await cursor.fetchall()]


async def delete_prompts_before(db, *, match_id: int, phase_number: int) -> None:
    await db.execute("DELETE FROM mafia_v1_dm_prompts WHERE match_id=? AND phase_number<?", (int(match_id), int(phase_number)))


async def acted_pairs(db, *, match_id: int, phase_number: int) -> list[tuple[int, str]]:
    """(user_id, action_type) for every move already stored in this phase."""
    async with db.execute(
        "SELECT user_id,action_type FROM mafia_v1_actions WHERE match_id=? AND phase_number=?",
        (int(match_id), int(phase_number)),
    ) as cursor:
        return [(int(r[0]), str(r[1])) for r in await cursor.fetchall()]


async def mark_role_sent(db, *, match_id: int, user_id: int) -> None:
    await db.execute("UPDATE mafia_v1_players SET role_sent_at=CLOCK_TIMESTAMP() WHERE match_id=? AND user_id=?", (int(match_id), int(user_id)))
