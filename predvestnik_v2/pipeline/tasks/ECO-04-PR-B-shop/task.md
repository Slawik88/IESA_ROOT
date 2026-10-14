# ECO-04 PR-B — Shop screen (keys, Essence polish, Zarniki exchange)

Risk: T2 (new currency sink, multi-currency debit, limits). Owner asked to do everything end to end (2026-10-14). `shop_catalog.json`, `designer_brief.md` and `designer_brief_ru.md` next to this file are the originals the owner pasted on 2026-10-14 (they replace an earlier reconstruction).

## Scope
- Sections: Keys (5 offers that already exist in `core.chests_v1.KEY_OFFERS`), Essence (Шлифовка), Exchange (2 routes of the existing `/wallet/exchange-zarniki`), Links (Season pass, VIP, Skins). Gifts: hidden until PR-C.
- New sink only: **Шлифовка** — 600 Mora + 1 💎 → 60 Essence, 2 per ISO week (UTC, Monday).
- Not sold: pet food, ×5 bundles, cosmetics/themes.

## Design
- `core/shop_v1.py` (pure): `SHOP_VERSION`, `POLISH = {price: {mora: 600, diamonds: 1}, essence: 60, limit: 2, window: week}`, section order, link targets. Key prices are **not** duplicated: key items are built from `KEY_OFFERS`; exchange items from `zarniki_exchange_v1.EXCHANGE_ROUTES` / `DAILY_ZARNIKI_CAP`. `catalog_payload()` + `catalog_digest()`.
- Flag `shop_v1` (default **off**, fail-closed in `system_flags._DEFAULT_ENABLED`). Flag off: `/shop-v1/*` answers 404-like "Магазин пока закрыт", no entry button. Key items additionally follow `pets_level_up_v1` (as on the chest screen).
- Polish purchase: one transaction under `lock_user` → replay by `(user_id, action_id)` (same request → same receipt; different → 409) → flag + catalog check → week window from one `CLOCK_TIMESTAMP()` → limit count → shortages for every currency (409 "Не хватает: …", nothing debited) → `economy_ledger.apply_balance_change({mora:-600, diamonds:-1}, reason_code="shop_essence_polish", idempotency_key="shop-polish:<id>")` → `skins_v3.essence_apply(+60, idempotency_key="shop-polish:<id>")` → append-only receipt row in new table `shop_purchases_v1(id, user_id, action_id UNIQUE per user, item_id CHECK, request_hash, shop_version, catalog_digest, price JSONB, gives JSONB, economy_operation_id, purchased_on, purchased_week CHECK Monday, created_at)` with append-only trigger.
- Key purchases go through `chests_v1.buy_offer` unchanged (same limits, receipts, idempotency). Exchange goes through the existing `zarniki_exchange_v1.exchange` (same daily cap, Idempotency-Key).
- API: `GET /shop-v1/me` (balances, sections, per item: price, gives, limit/used/remaining, `shortages`, `available`), `POST /shop-v1/buy {item_id, action_id, catalog_version, catalog_digest, amount?}` dispatching by item kind. 409 on any conflict.
- Wallet history label for `shop_essence_polish`. `audit_economy_mutations` classification for the new writer.
- Mini App: new page `pg-shop` (balance strip, sections, cards with all states from the brief, confirm sheet with before→after balances and «Покупка необратима», toast, retry keeps the same action id). Entry: «Магазин» button in the currency modal and on the profile hub, shown only when `shop_v1` is on (from `/shop-v1/me` 404 → hidden).
- «Что нового»: ships with the flag decision, not in this PR.

## From the designer brief (originals)
- Tabs **Ключи · Эссенция · Обменник · Подарки** (Подарки hidden until PR-C), link tiles at the bottom (Сезонный пропуск, VIP, Скины).
- Balance strip includes 🗝 keys per tier.
- One card for all items; Silver is one tile with a method switch (крафт / ✨). Button words «Купить» / «Скрафтить» / «Обменять». Limit line «Осталось N из M на этой неделе» or, for daily limits, «до сброса N ч».
- Missing currency highlighted, «Не хватает: 120 🪙»; API returns `missing` per currency and `affordable`.
- Odds hint above keys from data (89% / 97%).
- Exchange tab: amount field, «Лимит 50✨ в сутки, осталось N», «Обмен необратим».
- Item ids follow the catalog (`key_t3_mora`, `key_t4_craft`, `key_t4_zar`, `key_t6_dia`, `key_t6_zar`, `ess_polish`, `exchange_mora`, `exchange_dia`) and map onto existing `KEY_OFFERS` ids.

## Acceptance
- Tests: `test_shop_v1_rules` (catalog == KEY_OFFERS/exchange policy, price change = one constant, digest), `test_shop_v1_pg` (polish: shortage of Mora or 💎 → nothing debited and both named; replay; week limit with UTC boundary via fixed window; flag off refused; key purchase through the shop = chest offer receipt; exchange through the shop respects the 50 ✨ cap; concurrency 16 connections × 30 tasks never exceeds 2/week), `test_shop_v1_ui_contract`.
- Regression: chests/key tiers/pets/quests PG, audit_economy_mutations, whatsnew contract.
- Independent pre-implementation critique and post-implementation review (T2); owner card before merge.

## Implementation notes and decisions
- Files: `core/shop_v1.py` (catalogue), `infrastructure/repositories/shop_v1.py` (`shop_purchases_v1`, window, action owner), `services/shop_v1.py`, `FastAPI/routers/shop_v1.py`, `FastAPI/static/app.44.js` + `.shop-*` in `app.css`. Flag `shop_v1` in `system_flags._DEFAULTS` (off, fail-closed); `bot/core/database.py` seeds only tab/reconstruction flags, so nothing there (same as `pets_level_up_v1`). Table created by `bot/startup_schema.py` (production path) and FastAPI lifespan.
- One action id belongs to one store: the shop locks the player (same advisory key as chests and exchange) and refuses an action id already used by another kind (Polish receipt, chest offer receipt, exchange ledger operation). Inside one kind the store's own replay check decides (other key with the same id → chest request-hash conflict; other amount → ledger idempotency conflict). A replay is answered before the flag and catalogue checks, so a retry after the flag goes off still returns its receipt.
- Keys are on sale only while `pets_level_up_v1` **and** `content_chests_v1` are on (a key without the chest screen cannot be opened). Shop keys pass the chest catalogue version/digest to `buy_offer`; the shop digest includes the chest digest and `KEY_OFFERS`.
- Polish shortage text uses icons from the brief: «Не хватает: 600 🪙, 1 💎.». Polish limit is per user, independent of chest account epochs.
- Platinum stays two cards; only Silver is one tile with a switch (brief). The season pass tile is shown only while `season_pass_v1` is on; the tile is also hidden when its opener function is missing.
- `audit_economy_mutations`: no change needed — Polish writes balances only through `economy_ledger.apply_balance_change` and Essence through `skins_v3.essence_apply`; the guard reports no new direct writer.
- Exchange through the shop keeps the existing day boundary of the exchange repo (`CURRENT_DATE`), as `/wallet/exchange-zarniki`.

## Checks (branch claude/eco04-pr-b-shop, local PostgreSQL 16)
- New: `test_shop_v1_rules` (ids = owner catalogue minus gifts/links, keys = `KEY_OFFERS`, exchange = policy rates/cap, Polish constant, digest changes with Polish/key/exchange price, `math.ceil` shortages), `test_shop_v1_pg` (flag off refused; keys refused while `pets_level_up_v1` off; Polish shortage of Mora only / 💎 only / both debits nothing and names each; replay = same receipt; same action id on another item → 409; 2 per ISO week with a fixed window, Sunday same week, next Monday resets; replay after flag off; key via shop = chest offer receipt + tier-6 key, chest limit applies; exchange via shop: 30 + 20 ✨ ok, then refused, replay/other amount; `/me` left, missing, affordable, `resets_in_seconds`; 16 connections × 30 tasks → exactly 2 Polish purchases, balances exact), `test_shop_v1_ui_contract` (wiring, flag-gated entry, tabs/words/limit lines, confirm with before→after and irreversible lines, one action id until success, no copied prices, no pressure words, no Dark Mora/Echo Shards, 360px CSS, `node --check`).
- Green: chest_key_tiers rules/pg, chests_v1 rules/pg/mixed (with `pets_level_up_v1` off)/visual, chest_keys_multi_pg, quests_v1_pg, pets_v1_pg, whatsnew_v3_contract, release_whatsnew, startup_schema_contract, ui_smoke_screens_contract, shell_v3_contract, season_pass_ui_contract, inventory_v3_contract, trail_v3_contract, audit_economy_mutations; `node --check` on app.01/02/15/31/44.
- Start-up: `init_db` + `ensure_runtime_schema` and the FastAPI lifespan both create `shop_purchases_v1`; router answers 404 «Магазин пока закрыт» with the flag off and 409 «Не хватает: 600 🪙, 1 💎.» for an empty wallet.
- Visual: headless Chromium at 360px, all three tabs and both confirm sheets, `scrollWidth` = 360 (no horizontal scroll), no page errors.
- Not done here (per task): independent T2 review, owner card, «Что нового».
