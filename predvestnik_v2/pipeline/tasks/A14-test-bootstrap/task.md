# A14 — Test DB bootstrap for the release gate

Tier: T1 (test tooling only; production code untouched).

## Problem
`tools/run_preprod_tests.ps1` ran tests against whatever schema the preprod DB had.
On an empty DB, PG tests failed on missing tables (e.g. `skins_v3_essence_accounts`),
so gate results depended on DB history. JS tests (`tools/test_*.js`) were not run.

## Change
- `tools/bootstrap_test_db.py` (new): loopback DSN only. Runs the production startup
  schema path: `init_db` -> `ensure_chat_schema` -> `ensure_runtime_schema` -> FastAPI
  `lifespan` ensure list (its background loops are replaced by no-ops first). No
  separate operator migration: `ensure_chat_schema` already installs the family
  registry and wallet (`bot/chat/family.py`). Drops `PREDVESTNIK_DATABASE_URL` so the
  pool cannot fall back to a non-loopback DB. Idempotent, also on a used test DB.
- `tools/run_preprod_tests.ps1`: runs the bootstrap after env setup with
  `ErrorActionPreference=Continue` (loguru writes to stderr), throws on non-zero exit;
  runs `tools/test_*.js` with node after the Python tests and counts them in totals.

## Verification (Linux replica of the ps1 runner, PG16, fresh `predvestnik_preprod`)
- Bootstrap twice on the same DB: OK both times (idempotent).
- Full gate, empty DB, no bootstrap: pass=125 fail=29.
- Full gate, fresh DB + bootstrap: pass=129 fail=25. No test regressed.
  Fixed by bootstrap: account_deletion_family_guard_pg, achievements_v1_pg,
  admin_bind_repository_pg, balance_events_pg.
- Needs a local `.env.test` (preprod guard); an empty throwaway file was used.

## Remaining 25 failures (pre-existing, not schema; out of A14 scope)
- Cross-test state on the shared DB (fixed IDs 1001/2001, no cleanup); pass alone on a
  fresh DB: bot_admin_entry/matrix/metrics/owner/reports/review/security/player_tools,
  bot_health, chat_bot_pg (sampled entry_pg and chat_bot_pg alone: PASS).
- Fail alone too (stale test vs current code or missing seed/flags): bot_admin_people
  (`KeyError: 'players'`), bot_admin_promo, bot_admin_chats_reports, member_tags,
  mafia_v1 / mafia_v1_sim, chests_v1 / chests_v1_mixed / pets_v1 (`QuestConflict`:
  not enough quest types), chat_bots, current_game_docs.
- Preprod allowlist: bot_feature_switches, profile_query_budget use TG IDs outside
  `PREPROD_ALLOWED_TG_IDS=101,202`.
- Fake DB object: account_recovery_bot (`db=object()`), fails on master as well.

## Follow-ups (owner decision)
- Per-test DB reset or unique IDs for the bot_admin family.
- Triage the "fail alone" group one by one.

## Independent review (subagent, not the author)
Findings and fixes:
1. Non-loopback fallback via `PREDVESTNIK_DATABASE_URL` when run by hand -> env var dropped.
2. Lifespan background loops took one step on shutdown -> replaced with no-ops before entry.
3. Operator migrations' strict audits fail on a used test DB -> step removed (startup path
   already installs both, verified with `to_regclass`).
4. Bootstrap stderr under `ErrorActionPreference=Stop` -> wrapped like the tests, restored in
   `finally`; same `finally` for the node loop.
Nit `.env.test` presence check: not added (preprod guard already names the file).
