# A02 — atomic account finalization

**Risk:** T2 (destructive data cleanup, concurrency with restore/economy writers).
**Source:** owner audit 2026-10-14, item A02. Audited checkout HEAD 049d81d2 is not on origin;
owner chose to work from `origin/master` (4933129). A01 does not exist on master (no nested
ban-cache acquire in `FastAPI/deps.py`), so A02 was taken next.
**Status:** implemented and verified locally; draft PR; not released.

## Goal and acceptance
- An error at any finalization step leaves no false `finalized` and no partial cleanup.
- Retry is safe: the account stays `pending_restore` and the next daily tick redoes the whole step.
- Concurrent restore vs finalize: whichever commits first wins; the other changes nothing.
- Append-only history (chest receipts, ledgers, moderation logs) is not deleted.

## Decisions
- `_finalize` runs in one transaction (`db.connection.transaction()`, savepoint when nested).
  Order: `SET LOCAL lock_timeout='5s'` → `pg_advisory_xact_lock(user_id)` (shared with
  chest/quest/pet/zarniki/echo/achievement writers) → `users` row `FOR UPDATE` (blocks direct
  ledger writers for the whole cleanup) → re-check `account_deletions` is `pending_restore`
  and past `restore_deadline`, `users.deleted_at` set.
- Per-statement `try/except` removed. Only `global_skin_v1_selection/owned` (created lazily)
  may be absent and are skipped via `to_regclass`; any other missing table fails closed.
- `daily_tick` step 4 isolates each account (`logger.exception`), orders by `restore_deadline`,
  and logs "финализирован" only after commit.
- `restore_account` takes the same advisory lock in a transaction; conditional
  `UPDATE ... WHERE status='pending_restore'` first, then clears `users.deleted_at`.

## Critique (independent, pre-implementation)
Approve with changes; all adopted except the attempts/last_error column (needs a schema change).
Findings recorded: economy ledger writers lock only the `users` row, not the advisory lock
(hence the added `FOR UPDATE`); `to_regclass` skip must be a whitelist; existing family-guard
test needed a past `restore_deadline`; lock timeout; restore ordering.

## Known limitations (not in this change)
- A credit committed **after** finalize still lands on a finalized account; zeroed balances
  have no ledger rows (pre-existing; audit risk items 3–4).
- 20 accounts that fail every time would occupy every step-4 slot (no attempts column).
- Restore stays possible after `restore_deadline` until finalize actually commits (existing
  grace behaviour, unchanged).
- A12 (daily marker set before work) still delays a failed tick's retry to the next UTC day.

## Checks
- `tools/test_account_deletion_atomic_pg.py` (new, real PostgreSQL 16, autocommit like the
  scheduler): injected failure on chest keys, pets, inventory, clan_members, user_chat_stats,
  users and the status write → account intact, `pending_restore`; retry → `finalized`.
  Restore-wins and finalize-wins races; non-due account untouched.
  On unchanged code it fails: `pets` failure → `status=finalized, pets=1`.
- `tools/test_account_deletion_family_guard_pg.py`: OK (fixture now sets a past deadline).
- `tools/test_bot_economy_review_pg.py` (fresh DB, runs `daily_tick`): OK.
- `tools/audit_economy_mutations.py`: guard OK.
- `tools/test_account_recovery_bot.py` fails identically on master (fake `db=object()` meets
  `global_moderation.is_blocked`); unrelated.
