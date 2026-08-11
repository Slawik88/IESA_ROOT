# Economic ledger contract

Status: local/dev foundation, 2026-08-11. This document defines accounting
invariants; it does **not** set final prices, rewards or exchange rates.

## Why `wallet_log` is not the ledger

`wallet_log` remains the compact history shown to the player. It is a projection,
not a safe source of truth:

- legacy code can change `users.user_balance_*` without writing it;
- it stores the balance after the operation but not the balance before it;
- a composite purchase can create several rows with the same final balance;
- it has no request idempotency, operation grouping or payload-conflict check;
- balances and deltas are `FLOAT8`, which is insufficient for exact reconciliation.

The source of truth for migrated operations is now:

- `economic_operations`: one logical request and its idempotency gate;
- `economic_ledger`: one immutable row per changed currency with exact
  `balance_before + delta = balance_after` arithmetic;
- `wallet_log`: written in the same transaction as a compatibility/UI projection.

## Currency roles

These roles are boundaries for the coming rebalance, not final tuning:

| Currency | Role | Must do | Must not do |
|---|---|---|---|
| Мора | soft progression | frequent earn/spend loop, upgrades and ordinary services | become a disguised premium paywall |
| Алмазы | rare progression | scarce accelerators and meaningful account choices | duplicate Зарники or be required for every action |
| Тёмная Мора | mode-specific | circulate inside shadow content with controlled exits | leak into every shop and erase mode identity |
| Зарники | premium cosmetics | cosmetics, status expression and explicit premium convenience | directly sell combat dominance or silently replace every currency |

Every future price/reward decision must name its currency role, intended source,
intended sink and target time-to-earn. A number without those four fields is not a
balance decision.

## Mutation invariants

`infrastructure.repositories.economy_ledger.apply_balance_change` enforces:

1. Only the four registered currency codes are accepted.
2. Boolean, NaN and infinite amounts are rejected.
3. Amounts are canonicalized to six decimal places for deterministic storage.
4. A protected balance cannot go below zero.
5. Operation gate, row lock, balances, ledger rows and `wallet_log` projection
   commit or roll back together.
6. Replaying the same `(user_id, idempotency_key)` and same semantic payload
   returns the original operation without another balance change.
7. Reusing the key with different deltas/reason/reference raises an
   `IdempotencyConflict`; it is never silently accepted.
8. Multi-currency operations share one `operation_id` and one wallet projection.

`allow_negative=True` exists only for an explicitly reviewed migration/admin
case. Gameplay code must not use it.

## Idempotency at adapter boundaries

- Telegram Stars uses `telegram_payment_charge_id`. A duplicate update cannot
  credit Зарники or the referral commission twice.
- Web exchange accepts `Idempotency-Key`. It is scoped by exchange direction;
  an exact retry succeeds even after the original request consumed quota.
- Зарники exchange accepts the same header through `/wallet/exchange-zarniki`.
- Calls without a key remain backwards compatible and receive a unique operation
  key, but they cannot be protected from a client retry. New write endpoints must
  always supply a stable request key.

## Migration state

All code paths using `add_balance` now enter the canonical ledger automatically.
The first explicitly retry-safe boundaries are Telegram Stars and both web
exchange families.

There are still legacy direct writers. Run:

```bash
python tools/audit_economy_mutations.py
```

The audit currently classifies the remaining writers in 17 files and fails if a
new unclassified bypass appears. Main migration groups:

1. `infrastructure/repositories/economy.py`: transfers, dedicated spend helpers,
   shop purchase and admin absolute set.
2. `services/cosmetics.py`: collection/lineup purchases.
3. Shadow economy: `dark_mora`, gates, merchant and dark market.
4. Player systems: zoo, relics, clans, marriages, raids and scheduler rewards.
5. Crypto exchange and the remaining FastAPI adapters with direct SQL.

`services/account_deletion.py` (account erasure) and idempotent startup migrations
in `bot/core/database.py` are tracked exceptions, not gameplay writers.

## Rollout gate

Before production deployment:

- create both tables through normal database initialization;
- run ledger unit tests and the direct-writer audit;
- execute one credit, one debit, one multi-currency exchange, one exact replay and
  one conflicting replay on the local/staging database;
- reconcile balances against ledger arithmetic for the test users;
- do not backfill invented historical balances. Old `wallet_log` rows stay marked
  as legacy history; canonical accounting begins at the deployment boundary.

No production database was read or changed while building this foundation.
