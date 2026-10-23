"""Rhythm runs that must pass the automatic screen before a season's places are frozen."""
from __future__ import annotations

import json

LOCAL_RESULT = "local:result:v1"


async def local_runs(db, *, mode: str, starts_at, ends_at, limit: int = 5000) -> list[dict]:
    """Clear, phone-timed runs of the window with their journal, best scores first."""
    async with db.execute(
        "SELECT r.run_id, r.user_id, r.seed, a.request_json FROM rhythm_v2_runs r "
        "JOIN rhythm_v2_actions a ON a.run_id = r.run_id AND a.action_id = ? "
        "WHERE r.mode=? AND r.status='finished' AND r.integrity_status='clear' AND r.score>0 "
        "AND r.finished_at>=(?::timestamp AT TIME ZONE 'UTC') AND r.finished_at<(?::timestamp AT TIME ZONE 'UTC') "
        "ORDER BY r.score DESC LIMIT ?",
        (LOCAL_RESULT, str(mode), starts_at, ends_at, int(limit)),
    ) as cursor:
        rows = [dict(row) for row in await cursor.fetchall()]
    for row in rows:
        request = row["request_json"]
        row["actions"] = (json.loads(request) if isinstance(request, str) else request or {}).get("actions") or []
    return rows


async def hold_for_review(db, *, run_id: str, reason: str, evidence: dict) -> bool:
    """Move a clear run to review: it leaves the table until a person clears it (``review_run``)."""
    async with db.execute(
        "UPDATE rhythm_v2_runs SET integrity_status='review_required', integrity_reason=?, "
        "integrity_evidence=?::jsonb, integrity_checked_at=CLOCK_TIMESTAMP() "
        "WHERE run_id=? AND integrity_status='clear' RETURNING run_id",
        (reason, json.dumps(evidence), str(run_id)),
    ) as cursor:
        return bool(await cursor.fetchone())
