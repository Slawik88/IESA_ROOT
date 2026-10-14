# A12 — daily maintenance retries a failed job the same day

**Risk:** T1 (operational reliability). **Status:** draft PR stacked on A02 (#32), not released. **Source:** audit A12.

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
- At most 6 attempts per job per UTC day (`_DAILY_MAX_ATTEMPTS`); after that an error is
  logged and the job waits for the next day. Keeps the LIMIT-50 batches near their daily scale.
- Markers stay in process memory (a restart reruns today's jobs once, as before).

## Review (independent)
ACCEPT-WITH-NITS. Applied: stacked on A02 so a failing finalization cannot rerun
`retire_account` every pass (A02 makes it atomic); daily attempt cap; error log at the cap.

## Checks
- New offline `tools/test_daily_maintenance_retry.py`: failure retried same day, success once
  per day, independent jobs, next day reruns, permanent failure stops at the cap.
