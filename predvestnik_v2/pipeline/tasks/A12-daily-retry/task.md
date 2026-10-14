# A12 — daily maintenance retries a failed job the same day

**Risk:** T1 (operational reliability). **Status:** draft PR, not released. **Source:** audit A12.

## Goal and acceptance
First call fails, a later call after recovery performs the missed work the same day.

## Decisions
- `services/scheduler.py`: the single `_daily_gc_day` marker (set before any work) is replaced
  by per-job success markers `_daily_done[name] = today`, set only after the job succeeds.
- A failed job is retried on the next maintenance pass (the loop sleeps 600 s), so no extra
  backoff is added. One job's failure no longer skips the other.
- Repeat safety: `daily_tick` steps select by state (cooling expired, warned_at vs last
  activity, pending_restore past deadline), so a rerun does not resend the same DMs; with
  A02 (#32) finalization is atomic and retry-safe.
- Markers stay in process memory (a restart reruns today's jobs once, as before).

## Checks
- New offline `tools/test_daily_maintenance_retry.py`: failure retried same day, success once
  per day, independent jobs, next day reruns.
