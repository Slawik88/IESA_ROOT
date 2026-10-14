# ECO-04 PR-A — chest keys by stars (key tiers)

Risk: T2 (paid keys, balances, limits, concurrency). Stacked on PR #24 (ECO-02, branch `claude/project-thread-xfqm4g`); merges together with it. Owner confirmed R1/R2 and "all recommended numbers" (2026-10-14). Flag order R7: season pass → routes → level-up together with PR-A.

## Rules (owner-fixed, handoff §3.3)
- A key of tier N opens the same chest; star outcomes below N become N★ (`stars = max(stars_for_roll(roll), N)`). Tier 1 = current key. Odds shown to the player per tier: 3★ 80% exactly 3★, 4★ 89%, 6★ 97%.
- Offers and limits (UTC; week = ISO week starting Monday 00:00 UTC):
  | offer_id | tier | price | limit |
  |---|---|---|---|
  | bronze_mora | 3 | 800 Mora | 3 / week |
  | silver_craft | 4 | 300 Mora + 200 Essence | 1 / week |
  | silver_zarniki | 4 | 120 ✨ | 2 / day (`PAID_KEY_DAILY_LIMIT`, counted together with legacy 10 ✨ purchases of the same UTC day) |
  | platinum_diamonds | 6 | 5 💎 + 3000 Mora | 1 / week |
  | platinum_zarniki | 6 | 300 ✨ | 1 / day |
- All five offers are behind `pets_level_up_v1` (same switch as pet level-ups). Flag off: nothing changes for players (legacy 10 ✨ 1★ purchase keeps working, tier offers refused, overview shows no offers). Flag on: legacy `/chests-v1/purchase` is refused ("replaced by Silver"), tier offers sold.
- Prices and limits live in one constant `KEY_OFFERS` in `core/chests_v1.py`.

## Design
- Tier is derived from `source_kind` (no new column on append-only grants): existing kinds → 1; new kinds `offer_bronze_mora`(3), `offer_silver_craft`(4), `offer_silver_zarniki`(4), `offer_platinum_diamonds`(6), `offer_platinum_zarniki`(6). `KEY_TIER_BY_SOURCE` in core; the grants CHECK on `source_kind` is widened in `ensure_tables` the same way PR #24 did.
- Legacy paid keys (`zarniki_purchase`, any catalog) are tier 1 and openable: the catalog filter in `next_unspent_grant` and `locked_paid_keys` is removed; `locked_paid_keys` stays in the API and returns 0.
- `chest_key_accounts_v1.balance` stays the total of all tiers (existing ledger/spend invariants unchanged). Per-tier balance = count of unspent, unrevoked grants of the current epoch by tier.
- Open: `POST /chests-v1/prepare` gains optional `key_tier` (default 1, allowed 1/3/4/6). `next_unspent_grant(..., key_tier=N)` picks the oldest grant of exactly that tier (FIFO by `created_at,id`) `FOR UPDATE`; the spend still decrements the total balance with the guarded update. `request_hash` includes `key_tier`. `roll_outcome(..., min_stars=N)`. Reveal metadata gets `key_tier`.
- Purchase: `POST /chests-v1/offers/{offer_id}/buy {action_id, catalog_version, catalog_digest}`. One transaction under `lock_user`: replay by `(user_id, action_id)` (same request → same receipt, different → 409); flag check; catalog check; limit count; ledger debit of all ledger currencies in one `apply_balance_change` (reason `chest_key_offer_<offer>`, idempotency `chest-offer:<purchase_id>`); Essence debit via `skins_v3.essence_apply` (idempotency `chest-offer:<purchase_id>`); grant one key of the tier; append-only receipt row in new table `chest_key_offer_purchases_v1(id, user_id, action_id, offer_id, key_tier, request_hash, price JSONB, economy_operation_id, purchased_on DATE UTC, purchased_week DATE UTC Monday, created_at, UNIQUE(user_id, action_id))`. Shortage of any currency → nothing debited (transaction rollback) and a clear 409 ("Не хватает: …").
- Overview adds `key_balances` by tier, `tier_odds` per tier, `offers` (price, limit, used, remaining, window) when the flag is on, `tiers_enabled`; `key_balance` stays the total.
- Quests: `chest_revealed` counts every tier (unchanged metric); quest `key_balance` stays the total. Quest help texts mentioning "two keys a day" and "same odds" are updated.
- Mini App chest screen: tier balance chips, open with a chosen tier, odds table for the chosen tier, Silver 120 ✨ replaces the 10 ✨ buy button when the flag is on. The full shop screen is PR-B.
- `tools/economy_sim_v4.py` replaced by the routes version once the file is available (currently missing in this environment; noted for the owner).

## Acceptance
- Tests (new `tools/test_chest_key_tiers_pg.py` + rules test): each of the 5 limit counters incl. UTC day/week boundary; FIFO within a tier and the opened key's tier equals the requested tier; tier N never yields fewer than N stars; legacy paid key (old catalog) opens under new tables and `locked_paid_keys == 0`; shortage of either currency debits nothing; replay returns the same receipt; flag off refuses offers and keeps legacy purchase; flag on refuses legacy purchase; concurrency: pool of 16 connections, 40 tasks of mixed buys/opens per tier — limits never exceeded, balances = grants − spends, no negative balances.
- Existing: test_chest_keys_multi_pg, test_chests_v1_pg, test_chests_v1_mixed_pg, test_chests_v1_rules, test_chests_v1_economy, test_quests_v1_pg, test_pets_v1_pg, test_pet_levels_*; audit_economy_mutations clean.
- Simulator run with `--tables` on the final tables, bound to the commit.

## Critique (independent, pre-implementation) and decisions
Verdict: proceed with changes. Applied:
1. Grants CHECK: new named constraint `chest_key_grants_v1_source_kind_tiers`; the DO block drops other source_kind CHECKs only while it is absent. Rollback to pre-PR-A code is unsupported once offer grants exist (old `ensure_tables` would re-add the narrow CHECK and fail; old FIFO would open tier-6 keys as 1★). Bot and web deploy together from one app.
2. `request_hash` includes `key_tier` only when it is not 1, so pre-deploy retries still replay. Client keeps one pending action id per tier.
3. No key of the requested tier → 409 "Нет ключа этого уровня"; stale-catalog branch removed.
4. Per-tier counts vs `balance`: early canary opens may lack an allocation row. Fail-safe: tier-1 count is capped so that the sum of tiers never exceeds `balance`; prod check query added to the owner query list.
5. `POLICY_VERSION` is not bumped (quest-key replays compare it).
6. `catalog_payload` includes `KEY_OFFERS` and the tier rule (digest changes; clients refresh once). Pending opens prepared under the old digest still reveal (test). Asset cache is busted by `_ASSET_VER` (max mtime).
7. Offers are not refundable through the support refund path in PR-A (legacy `zarniki_purchase` refunds unchanged).
8. `purchased_on` / `purchased_week` are computed once in the transaction from one `CLOCK_TIMESTAMP()` read, inserted explicitly and used for counting.
9. Lock order as pet level-ups: `lock_user` → chest account → ledger → Essence; `skins_v3.ensure_tables` before the transaction.
10. All currencies are checked before any debit; the 409 lists every shortage.
11. Offers table is append-only (trigger list); index on grants `(user_id, account_epoch, source_kind, created_at)`; offer kinds are not accepted by the generic grant paths; limits count per user across account epochs.

## Checks (branch claude/eco04-pr-a-key-tiers, local PostgreSQL 16)
- New: test_chest_key_tiers_rules (card value per tier 308/438/630/1699 = handoff), test_chest_key_tiers_pg (5 counters, UTC day/week boundary, FIFO per tier, stars ≥ tier, legacy key = tier 1 and locked 0, shortages debit nothing and name every missing currency, replay, flag gate, old-digest open reveals, 16 connections × 40 tasks race fills every limit exactly).
- Updated: test_chest_keys_multi_pg (stale paid key now opens), test_chests_v1_visual_contract.
- Green: chests_v1 rules/economy/http/visual/pg/mixed, quests_v1_pg, pets_v1_pg, pet_levels rules/pg/race, inventory_v1_pg, startup_schema_contract, audit_economy_mutations.
- Test env note: quest assignment needs `game_rhythm_v2`, `game_minesweeper_v2`, `content_chests_v1` on in the test DB; with them off chests/pets PG tests fail on master too.
- Simulator: `sim_output.txt` (tables blob recorded in its header). Simulator key prices (tools/economy_sim_v4.py) equal `KEY_OFFERS`. The routes variant of the simulator is not in this environment.
- «Что нового»: none in this PR, nothing changes for players while `pets_level_up_v1` is off; the entry ships with the flag decision.
- Prod query for the owner (read-only), before enabling: per user, unspent current-epoch grants vs `chest_key_accounts_v1.balance`.
