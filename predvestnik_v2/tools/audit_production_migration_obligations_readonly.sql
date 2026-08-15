-- Reproducible aggregate-only audit for the migration-obligations report.
-- Run with psql against a production snapshot or the frozen cutover backup.
-- The script returns no Telegram IDs, usernames, messages, payment IDs, or other PII.

\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

\echo 'SNAPSHOT CLOCK'
SELECT statement_timestamp() AT TIME ZONE 'UTC' AS snapshot_utc,
       current_setting('transaction_isolation') AS isolation,
       current_setting('transaction_read_only') AS read_only;

\echo 'ACCOUNT WALLETS'
SELECT count(*) AS active_accounts,
       round(sum(user_balance_mora)::numeric, 2) AS mora,
       round(sum(user_balance_diamonds)::numeric, 2) AS diamonds,
       round(sum(user_balance_dark_mora)::numeric, 2) AS dark_mora,
       round(sum(user_balance_zarniki)::numeric, 2) AS zarniki,
       round(sum(user_balance_crystals)::numeric, 2) AS crystals
FROM predvestnik.users
WHERE deleted_at IS NULL;

\echo 'PETS'
SELECT count(*) AS pet_rows,
       count(DISTINCT owner_id) AS owners,
       count(DISTINCT owner_id) FILTER (WHERE pet_level >= 10) AS owners_with_level_10,
       sum(duplicates_collected) AS duplicates
FROM predvestnik.pets;

\echo 'UNITS AND TARGET SHARDS'
SELECT count(DISTINCT user_id) FILTER (WHERE level >= 1) AS owners,
       count(*) FILTER (WHERE level = 0 AND shards > 0) AS partial_unlock_rows,
       coalesce(sum(shards), 0) AS target_shards_total,
       coalesce(sum(shards) FILTER (WHERE level = 0), 0) AS shards_on_unowned_rows
FROM predvestnik.user_units;

\echo 'LEGACY GACHA TOKENS'
SELECT item_id,
       count(DISTINCT user_id) AS owners,
       sum(quantity) AS quantity,
       max(quantity) AS max_per_owner
FROM predvestnik.inventory
WHERE item_id IN ('spin_token', 'spin_token_diamond') AND quantity > 0
GROUP BY item_id
ORDER BY item_id;

\echo 'BROKEN DIAMOND PITY EVIDENCE'
SELECT (SELECT count(*) FROM predvestnik.gacha_history WHERE spin_type = 'diamond') AS diamond_spins,
       (SELECT count(DISTINCT user_id) FROM predvestnik.gacha_history WHERE spin_type = 'diamond') AS diamond_players,
       (SELECT count(*) FROM predvestnik.gacha_pity WHERE spin_type = 'diamond') AS tracked_pity_rows,
       (SELECT count(*) FROM predvestnik.gacha_pity WHERE spin_type = 'diamond' AND count = 0) AS zero_pity_rows;

\echo 'BATTLE PASS RIGHTS'
SELECT count(*) AS progress_rows,
       count(*) FILTER (WHERE coalesce(cardinality(claimed_free_levels), 0) > 0) AS free_claimers,
       count(*) FILTER (WHERE coalesce(cardinality(claimed_paid_levels), 0) > 0) AS paid_claimers,
       max(level) AS max_level
FROM predvestnik.battle_pass_progress;

\echo 'FAMILY ESCROW'
SELECT count(*) AS marriage_rows,
       round(sum(family_balance)::numeric, 2) AS mora,
       round(sum(family_balance_diamonds)::numeric, 2) AS diamonds,
       round(sum(family_balance_dark_mora)::numeric, 2) AS dark_mora,
       round(sum(family_balance_zarniki)::numeric, 2) AS zarniki
FROM predvestnik.marriages;

\echo 'VIP OBLIGATIONS'
SELECT count(*) FILTER (WHERE expires_at > statement_timestamp()) AS active_rows,
       sum(GREATEST(0, ceil(extract(epoch FROM (expires_at - statement_timestamp())) / 86400.0)))
         FILTER (WHERE expires_at > statement_timestamp()) AS remaining_paid_days,
       max(expires_at) FILTER (WHERE expires_at > statement_timestamp()) AS latest_expiry
FROM predvestnik.vip_subscriptions;

\echo 'AUCTION AND SHARED RESERVE'
SELECT (SELECT count(*) FROM predvestnik.auction_lots WHERE status = 'active') AS active_lots,
       (SELECT count(*)
          FROM predvestnik.auction_bids b
          JOIN predvestnik.auction_lots l ON l.id = b.lot_id
         WHERE l.status = 'active' AND b.is_active = 1) AS active_bids,
       (SELECT coalesce(sum(b.amount), 0)
          FROM predvestnik.auction_bids b
          JOIN predvestnik.auction_lots l ON l.id = b.lot_id
         WHERE l.status = 'active' AND b.is_active = 1) AS active_bid_mora,
       (SELECT count(*) FROM predvestnik.user_reserve WHERE reserved_mora <> 0) AS nonzero_reserve_rows,
       (SELECT round(coalesce(sum(reserved_mora), 0)::numeric, 2)
          FROM predvestnik.user_reserve WHERE reserved_mora <> 0) AS reserved_mora;

\echo 'ACTIVE EXPEDITIONS'
SELECT count(*) AS active_rows,
       round(coalesce(sum(cost_mora), 0)::numeric, 2) AS prepaid_mora
FROM predvestnik.active_expeditions;

\echo 'OPEN CRYPTO POSITIONS'
SELECT count(*) AS position_rows,
       count(DISTINCT user_id) AS owners,
       round(sum(amount * avg_buy_price)::numeric, 2) AS book_cost_reference
FROM predvestnik.crypto_holdings
WHERE amount > 0;

\echo 'COSMETIC OWNERSHIP'
SELECT 'cosmetics' AS asset, count(*) AS rows, count(DISTINCT user_id) AS owners
FROM predvestnik.user_cosmetics
UNION ALL
SELECT 'themes', count(*), count(DISTINCT user_id) FROM predvestnik.user_themes
UNION ALL
SELECT 'relics', count(*), count(DISTINCT user_id) FROM predvestnik.user_relics
UNION ALL
SELECT 'shadow_relics', count(*), count(DISTINCT user_id) FROM predvestnik.user_shadow_relics
ORDER BY asset;

\echo 'CLAN OBLIGATIONS'
SELECT (SELECT count(*) FROM predvestnik.clans) AS clans,
       (SELECT count(*) FROM predvestnik.clan_members) AS members,
       (SELECT round(coalesce(sum(treasury_shards), 0)::numeric, 2) FROM predvestnik.clans) AS treasury_shards,
       (SELECT round(coalesce(sum(treasury_mora), 0)::numeric, 2) FROM predvestnik.clans) AS treasury_mora,
       (SELECT coalesce(sum(clan_coins), 0) FROM predvestnik.clan_members) AS member_coins,
       (SELECT count(*) FROM predvestnik.clan_buildings) AS building_rows;

COMMIT;
