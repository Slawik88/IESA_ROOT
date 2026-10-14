# A11 — deletion confirmation code: TTL, attempt limit, one-time use

**Risk:** T2 (destructive action authorization). **Status:** draft PR, not released.
**Source:** owner audit 2026-10-14, A11.

## Goal and acceptance
An expired or attempt-exhausted code is not accepted, even by a direct API call.

## Decisions
- Code from `secrets.randbelow` (was `random.randint`).
- TTL 15 min from `requested_at`; 5 wrong codes burn it; a new code at most every 10 min
  (`core/constants.py` `ACCOUNT_DELETE_CODE_*`). Wrong phrase does not spend an attempt.
- Consumption is one conditional `UPDATE ... RETURNING` (fresh, attempts left, matching code,
  `source='self'`), and it nulls the code, so it works once and races cannot double-use it.
- New column `account_deletions.confirm_attempts` added by `init_db` (`ADD COLUMN IF NOT EXISTS`,
  default 0); no manual migration.
- Found while tracing: an inactivity-warning row (`source='inactivity'`, no code) could be moved
  to cooling with an empty code + phrase, skipping the DM-ownership barrier. Now only
  `source='self'` rows with a code can be confirmed.
- An expired/exhausted self request no longer blocks a new request forever (only the resend
  interval applies). Cancellation during cooling is unchanged.

## Review (independent; T2 critique and review were combined post-implementation)
ACCEPT-WITH-NITS. Applied: `request_deletion` checks and replaces under
`pg_advisory_xact_lock(user_id)`, so parallel requests cannot both pass the resend interval;
an expired self-request no longer suppresses inactivity warnings in `daily_tick`. Left as is:
after closing the confirm dialog there is no screen to re-enter an already-sent code until
the 10-minute resend interval passes (the error text explains the wait).

## Checks
- New `tools/test_account_deletion_code_pg.py` (real PostgreSQL, rolled back): attempt limit,
  resend interval, fresh budget after re-request, one-time use, TTL, inactivity row with empty
  code, wrong phrase does not count.
- `tools/test_account_deletion_family_guard_pg.py`: OK.
- `tools/test_bot_economy_review_pg.py` (fresh DB, runs `daily_tick` incl. inactivity warnings): OK.

## Post-review fix (project review thread)
Bug: an expired self request still blocked the inactivity warning, because its
`warned_at IS NULL` matched the shared branch of the step-2 predicate. Fix: the
`warned_at` conditions now apply only to `source = 'inactivity'` rows. Regression
case added to `tools/test_account_deletion_code_pg.py` (expired self request -> warned;
fresh self request -> still blocks). It failed before the fix and passes after it.
