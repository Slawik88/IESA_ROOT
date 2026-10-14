# A13 — avatar download no longer holds a pooled DB connection

**Risk:** T1 (availability). **Status:** draft PR, not released. **Source:** owner audit 2026-10-14, A13.

## Goal and acceptance
An artificially slow Telegram must not delay unrelated wallet/profile requests.

## Decisions
- `/profile/avatar` authenticates with `require_tg_user_base` (no pooled connection for the
  request), takes one short connection for the deletion gate + VIP check, releases it, then
  downloads. The deletion gate is the shared `deps.assert_account_active`, also used by
  `require_tg_user` (no drift).
- Downloads are single-flight per user (`_AVATAR_INFLIGHT`) and a request waits at most
  `_AVATAR_BUDGET_SEC = 8`; a slower download keeps running and fills the 6 h cache.
- `/profile/me` and the public profile still hold their request connection, so they no longer
  wait for Telegram: cache hit or `null` + background download. The Mini App already loads
  its own avatar separately via `/profile/avatar` (`app.02.js:282`); another VIP's public card
  shows the placeholder on the very first uncached view.
- Not done: a pool-wait timeout/queue metric (audit A01 suggestion; A01 itself is absent on master).

## Checks
- New `tools/test_avatar_pool_pg.py` (real PostgreSQL, pool size 2): six concurrent avatar
  requests with a hanging Telegram leave both pool slots acquirable, share one download,
  answer within the budget; a deleted account still gets 403.
