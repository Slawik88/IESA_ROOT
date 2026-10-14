# ECO-04 PR-E — retire Dark Mora and Echo Shards from player surfaces

Risk: T1 (display and texts only; no balance, ledger or schema change). Owner decision (handoff 2026-10-14, §3.9): balances are not touched or compensated; columns and tables stay.

## Findings before implementation
- Accruals are already stopped on master: `/dark-mora/contrabanda` and `/ritual` answer 410, `dark_mora` and `relics` routers are not mounted in `FastAPI/main.py`, promocodes with `reward_dark_mora` are refused (`services/promocodes.py`), chat echo has `economic_reward: None`, `add_dark_mora` has no callers. Echo Shards are minted only by `services/pets_v1.apply_duplicate_progression`, which has no production caller. So step (1) of §3.9 needs a guard test, not code.
- `FAMILY_CURRENCIES` / `WALLET_CURRENCIES` keep `dark_mora`; API shapes keep `dark_mora`, `family_balance_dark_mora`, `delta_dark_mora`, `echo_shards`.

## Scope (this PR)
- Mini App: currency modal row, dead header-slot code, family balance row, wallet history (🌑 delta, rows with only a Dark Mora delta), live-balance keys.
- Bot: profile card balance line and default Theme Lab template; `{темная_мора}` removed from tag help but still rendered for saved templates; family card hides Dark Mora; withdrawal no longer offers a Dark Mora button; AI `get_balance` tool no longer returns it.
- «Что нового» entry without money wording.
- Out of scope: admin panel (`static/bot-admin`), `ai_knowledge/*.md` (already says the currency is retired), DB columns, compensation tools.

## Acceptance
- `tools/test_legacy_currencies_retired_pg.py`: family wallet read with Dark Mora works and API keeps `family_balance_dark_mora`; family card, profile card, Theme Lab help and AI tool show no Dark Mora; ledger spend against the column works; Dark Mora promocode refused; account deletion zeroes the column; no caller of `add_dark_mora` / `apply_duplicate_progression`; retired endpoint answers 410. Fails on master, passes on the branch.
- Regression: ai_daily_cap_vip, chat_bot_pg, economy_ledger, family_wallet_transfer_pg, player_exchange_v1_pg, profile_release_experience, theme_purchase_postgres, vip_v2_pg, startup_schema_contract, audit_economy_mutations — OK. `test_family_wallet_schema_pg` fails identically on master (environment, pre-existing).

## Status
- Branch `claude/eco04-pr-e-legacy-currencies`; independent review pending.
