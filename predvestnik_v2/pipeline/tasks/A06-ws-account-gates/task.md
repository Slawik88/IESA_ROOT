# A06 — shared WebSocket applies the HTTP gameplay account gates

**Risk:** T2 (authorization). **Status:** draft PR stacked on A03 (#33), not released.
**Source:** owner audit 2026-10-14, A06.

## Goal and acceptance
A validly signed but forbidden account cannot pass `/ws/{user_id}`; a foreign ID is still
rejected; restore/appeal flows keep their own policy.

## Decisions
- Parity with HTTP gameplay (`deps.require_tg_user`): preprod allowlist + `users.deleted_at`
  via the shared `deps.assert_account_active` (same extraction as A13, identical hunk). A
  missing `users` row passes, as on HTTP.
- No global-ban gate: HTTP has none on master (only display in `profile.py`); adding one is a
  new policy for the owner. `require_tg_user_base` docstring corrected accordingly.
- DB failure before accept → close 1011 (fail closed). On an open session a watchdog
  re-checks credential validity (session token / initData expiry) and the account gates every
  300 s; not allowed → 1008; a transient DB error keeps the session.
- Restore does not use WS (`account.py` is HTTP on `require_tg_user_base`), so closing WS for
  deleted accounts only loses the app-version prompt.
- The preprod persona cookie never opens WS (`connectWS` needs initData or a session token).

## Critique (independent, pre-implementation)
Approve with changes; all adopted (shared helper, 1011 fail-closed, credential re-check,
watchdog inside `asyncio.wait` with close by the outer code, test matrix).

## Review (independent, post-implementation)
ACCEPT-WITH-NITS. Applied: `app.01.js` no longer schedules a reconnect after a 1008 close
(revoked session / stale initData); the next visibility change retries once. A handshake
rejection before accept reaches the browser as 1006 and keeps the existing capped backoff (60 s).
Accepted as designed: a DB error during the 5-minute re-check keeps an admitted session (the
admission check itself fails closed). Not tested: the real re-check closure with a credential
expiring mid-session.

## Checks
- New `tools/test_ws_account_gates_pg.py` (real PostgreSQL): valid connects; foreign ID,
  deleted, preprod non-allowlisted → 1008; DB down → 1011; watchdog closes with 1008.
- `tools/test_ws_session_bounds.py` (A03) still OK.
