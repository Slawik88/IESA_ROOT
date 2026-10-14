# A04 — /api/ready reflects real readiness

**Risk:** T2 (production infrastructure: deploy health may depend on this endpoint).
**Status:** draft PR, not released. **Source:** owner audit 2026-10-14, A04.

## Goal and acceptance
- Namespace exists but a required table is missing → 503.
- Correct, finished startup → 200. `/api/health` (liveness) stays independent.

## Decisions
- New `infrastructure/readiness.py`: process flag `startup_complete` + `REQUIRED_TABLES`
  (users, user_chat_stats, chat_settings, global_module_toggles, account_deletions,
  web_notifications, system_flags, economic_operations), checked with one `to_regclass` query.
- The flag is set as the last step of `bot/startup_schema.ensure_runtime_schema` (bot and
  local stand share it; it raises on any failure, so the flag is never set on a half schema)
  and after the standalone FastAPI lifespan ensure loop.
- Operator migrations (marriage registry etc.) are not demanded; nothing is migrated to turn
  readiness green.
- 503 reason (`startup ... not finished` / missing table names) is logged; the response body
  stays generic.

## Review (independent)
ACCEPT-WITH-NITS. Applied: the standalone lifespan marks ready only when no ensure failed.
Reviewer also ran the real startup order on a fresh empty DB: 503 before init, 503 after
`init_db` alone (flag unset), 200 after `ensure_runtime_schema`. Not added: a fresh-DB variant
of the test (A14 covers bootstrap).

## Open question for the owner
Which path does the DigitalOcean health check probe? Bot start comments say the port must
answer before DB init. If DO probes `/api/ready`, a deploy now stays unhealthy until init_db +
runtime schema finish (by design, but slower). `tools/verify_production_http.py` still expects
200 after startup.

## Checks
- New `tools/test_readiness_pg.py` (real PostgreSQL): 503 before startup completes, 200 after
  the real `ensure_runtime_schema`, 503 with a required table absent, health 200 throughout.
