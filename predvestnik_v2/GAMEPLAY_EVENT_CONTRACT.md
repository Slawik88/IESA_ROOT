# Gameplay event contract

Status: local/dev foundation, 2026-08-12. The contract records meaningful player
decisions and outcomes; it does not change rewards, prices or combat balance.

## Source of truth

- `core/gameplay_events.py` — versioned event names and strict payload schemas.
- `infrastructure/repositories/gameplay_events.py` — append-only PostgreSQL writer,
  exact retry detection and payload-conflict protection.
- `gameplay_events` — raw event ledger. Aggregates and dashboards are projections;
  they must never rewrite this table.

`site_analytics` remains navigation telemetry. Opening a tab is not a meaningful
game action and must not be used as a substitute for battle/progression retention.
`economic_ledger` remains the source for resource changes; gameplay events may
reference economic outcomes later, but must not duplicate accounting truth.

## Invariants

1. Every event name is registered and versioned before use.
2. Required/allowed fields are explicit. Unknown keys are rejected.
3. Payloads are bounded by depth, collection size and 8 KiB serialized size.
4. Authentication data, usernames, contact fields and message text are rejected,
   including when nested inside another object.
5. NaN and infinity are rejected so JSON and aggregates remain deterministic.
6. `(user_id, idempotency_key)` is retry-safe. An exact replay returns the existing
   semantic event; a different payload under the same key raises a conflict.
   User-level milestones use no `run_id`, so a retry after a lost run remains the
   same semantic event; battle events always retain their concrete `run_id`.
7. `game_version` and `balance_version` are stored on every row. Metrics must not
   merge incompatible balance versions silently.
8. Render ticks, polling, heartbeats and empty frame advances are not gameplay
   events. They may exist in transport/state persistence, never in meaningful KPIs.

## First vertical slice

Reconstruction 3.0 currently emits:

| Event | Meaning |
|---|---|
| `game_onboarding_step` | first encounter started/completed; first permanent reward chosen |
| `battle_start` | a new server-authoritative run was created |
| `battle_action` | one visible signal was resolved by a player choice |
| `battle_upgrade` | one of the offered between-wave upgrades was selected |
| `battle_end` | the run reached won/lost with final mastery counters |
| `progression_upgrade` | the permanent post-run Memory was chosen |

The old `combat_action` stream emitted one row for every `frame` request. It has
been removed before production: frame traffic is state transport, not a decision.

## Next instrumentation groups

1. First-hour entry and content-blocked reasons outside the reconstruction flag.
2. Legacy/live battle start/end with a declared engine/mode.
3. Quest offered/completed and period grain.
4. Shop view and purchase attempt/result linked to economic operation IDs.
5. Data-quality queries for missing end events, impossible durations, incompatible
   versions, duplicated idempotency keys and unknown event names.

Each group is a separate reviewed wave. Do not instrument every legacy handler by
writing arbitrary payloads directly to the table.
