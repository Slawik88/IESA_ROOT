-- Production gameplay/economy baseline for GAMEPLAY_ECONOMY_REBUILD_AUDIT.md.
--
-- Safety contract:
--   * no credentials in this file;
--   * one stable REPEATABLE READ snapshot;
--   * transaction is forced READ ONLY;
--   * output contains aggregates only, never player identifiers/usernames.
--
-- Run explicitly (never from the application startup path):
--   psql "$PROD_DATABASE_URL" -X -v ON_ERROR_STOP=1 \
--     -f tools/audit_production_gameplay_readonly.sql

\pset pager off
\set ON_ERROR_STOP on

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

\echo 'SNAPSHOT'
SELECT now() AS snapshot_at, current_setting('TimeZone') AS database_timezone;

\echo 'ACCOUNT PROGRESSION'
SELECT
  count(*) FILTER (WHERE deleted_at IS NULL) AS accounts,
  count(*) FILTER (WHERE deleted_at IS NULL AND onboarded) AS onboarded,
  count(*) FILTER (WHERE deleted_at IS NULL AND combat_tutorial_done) AS tutorial_done,
  count(*) FILTER (WHERE deleted_at IS NULL AND account_level >= 10) AS level_10_plus,
  count(*) FILTER (WHERE deleted_at IS NULL AND account_level >= 25) AS level_25_plus,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY account_level)::numeric, 1) AS median_level,
  max(account_level) AS max_level,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY combat_power)::numeric, 1) AS median_cached_cp,
  round(percentile_cont(0.9) WITHIN GROUP (ORDER BY combat_power)::numeric, 1) AS p90_cached_cp,
  max(combat_power) AS max_cached_cp
FROM predvestnik.users
WHERE deleted_at IS NULL;

\echo 'CURRENCY DISTRIBUTIONS'
SELECT metric,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY value)::numeric, 2) AS median,
       round(percentile_cont(0.9) WITHIN GROUP (ORDER BY value)::numeric, 2) AS p90,
       round(percentile_cont(0.99) WITHIN GROUP (ORDER BY value)::numeric, 2) AS p99,
       round(max(value)::numeric, 2) AS maximum,
       count(*) FILTER (WHERE value = 0) AS zero_accounts
FROM (
  SELECT 'mora' metric, user_balance_mora value FROM predvestnik.users WHERE deleted_at IS NULL
  UNION ALL SELECT 'diamonds', user_balance_diamonds FROM predvestnik.users WHERE deleted_at IS NULL
  UNION ALL SELECT 'dark_mora', user_balance_dark_mora FROM predvestnik.users WHERE deleted_at IS NULL
  UNION ALL SELECT 'crystals', user_balance_crystals FROM predvestnik.users WHERE deleted_at IS NULL
  UNION ALL SELECT 'zarniki', user_balance_zarniki FROM predvestnik.users WHERE deleted_at IS NULL
) currency
GROUP BY metric
ORDER BY metric;

WITH balances AS (
  SELECT greatest(user_balance_mora, 0) AS mora,
         greatest(user_balance_diamonds, 0) AS diamonds,
         greatest(user_balance_zarniki, 0) AS zarniki,
         ntile(10) OVER (ORDER BY user_balance_mora DESC) AS mora_decile,
         ntile(10) OVER (ORDER BY user_balance_diamonds DESC) AS diamond_decile,
         ntile(10) OVER (ORDER BY user_balance_zarniki DESC) AS zarniki_decile
  FROM predvestnik.users WHERE deleted_at IS NULL
)
SELECT
  round((100 * sum(mora) FILTER (WHERE mora_decile=1) / nullif(sum(mora),0))::numeric, 1)
    AS top_decile_mora_share_pct,
  round((100 * sum(diamonds) FILTER (WHERE diamond_decile=1) / nullif(sum(diamonds),0))::numeric, 1)
    AS top_decile_diamond_share_pct,
  round((100 * sum(zarniki) FILTER (WHERE zarniki_decile=1) / nullif(sum(zarniki),0))::numeric, 1)
    AS top_decile_zarniki_share_pct
FROM balances;

\echo 'MESSAGE ACTIVITY AND PROXY RETENTION'
WITH activity AS (
  SELECT user_id, date::date AS activity_day, sum(message_count)::bigint AS messages
  FROM predvestnik.daily_user_stats
  WHERE date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
  GROUP BY user_id, date::date
), anchor AS (
  SELECT min(activity_day) AS min_day, max(activity_day) AS max_day FROM activity
)
SELECT min_day, max_day,
       (SELECT count(DISTINCT user_id) FROM activity) AS ever_active_users,
       (SELECT count(DISTINCT user_id) FROM activity, anchor WHERE activity_day=max_day) AS dau,
       (SELECT count(DISTINCT user_id) FROM activity, anchor
        WHERE activity_day BETWEEN max_day-6 AND max_day) AS wau,
       (SELECT count(DISTINCT user_id) FROM activity, anchor
        WHERE activity_day BETWEEN max_day-29 AND max_day) AS mau,
       (SELECT sum(messages) FROM activity, anchor
        WHERE activity_day BETWEEN max_day-29 AND max_day) AS messages_30d
FROM anchor;

WITH activity AS (
  SELECT DISTINCT user_id, date::date AS activity_day
  FROM predvestnik.daily_user_stats
  WHERE date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
), firsts AS (
  SELECT user_id, min(activity_day) AS first_day FROM activity GROUP BY user_id
), anchor AS (
  SELECT max(activity_day) AS max_day FROM activity
)
SELECT horizon, eligible, retained,
       round(100.0 * retained / nullif(eligible,0), 1) AS retained_pct
FROM (
  SELECT 'D1_exact_message_proxy' AS horizon,
         count(*) FILTER (WHERE first_day <= max_day-1) AS eligible,
         count(*) FILTER (WHERE first_day <= max_day-1 AND EXISTS (
           SELECT 1 FROM activity a WHERE a.user_id=f.user_id AND a.activity_day=f.first_day+1
         )) AS retained
  FROM firsts f CROSS JOIN anchor
  UNION ALL
  SELECT 'D7_exact_message_proxy',
         count(*) FILTER (WHERE first_day <= max_day-7),
         count(*) FILTER (WHERE first_day <= max_day-7 AND EXISTS (
           SELECT 1 FROM activity a WHERE a.user_id=f.user_id AND a.activity_day=f.first_day+7
         ))
  FROM firsts f CROSS JOIN anchor
  UNION ALL
  SELECT 'D30_exact_message_proxy',
         count(*) FILTER (WHERE first_day <= max_day-30),
         count(*) FILTER (WHERE first_day <= max_day-30 AND EXISTS (
           SELECT 1 FROM activity a WHERE a.user_id=f.user_id AND a.activity_day=f.first_day+30
         ))
  FROM firsts f CROSS JOIN anchor
) retention;

\echo 'GAMEPLAY FUNNEL'
SELECT
  (SELECT count(*) FROM predvestnik.users WHERE deleted_at IS NULL) AS accounts,
  (SELECT count(DISTINCT owner_id) FROM predvestnik.pets) AS pet_owners,
  (SELECT count(DISTINCT user_id) FROM predvestnik.gacha_history) AS gacha_users,
  (SELECT count(DISTINCT user_id) FROM predvestnik.user_units WHERE level >= 1) AS unit_owners,
  (SELECT count(DISTINCT user_id) FROM predvestnik.user_squad) AS squad_owners,
  (SELECT count(DISTINCT user_id) FROM predvestnik.battles) AS battle_users,
  (SELECT count(DISTINCT user_id) FROM predvestnik.clan_members) AS clan_members;

\echo 'PETS AND UNITS'
SELECT rarity, count(*) AS pets, count(DISTINCT owner_id) AS owners,
       round(avg(pet_level)::numeric, 2) AS avg_level,
       max(pet_level) AS max_level,
       sum(duplicates_collected) AS duplicates
FROM predvestnik.pets
GROUP BY rarity ORDER BY pets DESC;

WITH owner_pets AS (
  SELECT owner_id, max(pet_level) AS max_level,
         sum(duplicates_collected) AS duplicates
  FROM predvestnik.pets GROUP BY owner_id
)
SELECT count(*) AS owners,
       count(*) FILTER (WHERE max_level>=10) AS owners_with_level10_pet,
       count(*) FILTER (WHERE duplicates>0) AS owners_with_duplicates
FROM owner_pets;

WITH owner_units AS (
  SELECT user_id,
         count(*) FILTER (WHERE level >= 1) AS owned_units,
         max(level) AS max_level
  FROM predvestnik.user_units GROUP BY user_id
)
SELECT count(*) FILTER (WHERE owned_units>0) AS owners,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY owned_units)
             FILTER (WHERE owned_units>0)::numeric, 1) AS median_units,
       max(owned_units) AS max_units,
       max(max_level) AS max_unit_level,
       count(*) FILTER (WHERE max_level >= 10) AS owners_with_level10_unit
FROM owner_units;

\echo 'BATTLE OUTCOMES'
SELECT mode, status, count(*) AS battles, count(DISTINCT user_id) AS users,
       min(created_at) AS first_battle, max(created_at) AS last_battle
FROM predvestnik.battles
GROUP BY mode,status ORDER BY battles DESC;

WITH tutorial_winners AS (
  SELECT DISTINCT user_id FROM predvestnik.battles
  WHERE mode='tutorial' AND status='won'
)
SELECT (SELECT count(*) FROM tutorial_winners) AS tutorial_winners,
       count(*) FILTER (WHERE u.combat_tutorial_done) AS winners_flagged_done,
       count(*) FILTER (WHERE NOT u.combat_tutorial_done) AS winners_missing_done_flag
FROM tutorial_winners t JOIN predvestnik.users u ON u.user_tg_id=t.user_id;

\echo 'FEATURE ADOPTION'
SELECT feature, users, events
FROM (
  SELECT 'quest_reward' feature, count(DISTINCT user_id) users, count(*) events
    FROM predvestnik.wallet_log WHERE source='quest_reward'
  UNION ALL SELECT 'gacha', count(DISTINCT user_id), count(*) FROM predvestnik.gacha_history
  UNION ALL SELECT 'expedition_reward', count(DISTINCT user_id), count(*)
    FROM predvestnik.wallet_log WHERE source='expedition'
  UNION ALL SELECT 'battle_pass_reward', count(DISTINCT user_id), count(*)
    FROM predvestnik.wallet_log WHERE source='battle_pass_reward'
  UNION ALL SELECT 'shop_purchase', count(DISTINCT user_id), count(*)
    FROM predvestnik.wallet_log WHERE source='shop_purchase'
  UNION ALL SELECT 'auction_participant', count(DISTINCT user_id), count(*) FROM (
    SELECT seller_id user_id FROM predvestnik.auction_lots
    UNION ALL SELECT bidder_id FROM predvestnik.auction_bids
  ) auction_users
  UNION ALL SELECT 'minigame', count(DISTINCT user_id), count(*) FROM predvestnik.minigame_sessions
  UNION ALL SELECT 'crypto', count(DISTINCT user_id), count(*) FROM predvestnik.crypto_trades
  UNION ALL SELECT 'duel_challenger', count(DISTINCT challenger_id), count(*) FROM predvestnik.duels
) adoption ORDER BY users DESC, feature;

SELECT duration_hours, count(*) AS active_expeditions,
       count(DISTINCT chat_id) AS users
FROM predvestnik.active_expeditions
GROUP BY duration_hours ORDER BY duration_hours;

SELECT status, count(*) AS lots, count(DISTINCT seller_id) AS sellers
FROM predvestnik.auction_lots
GROUP BY status ORDER BY lots DESC;

SELECT count(*) AS bids, count(DISTINCT bidder_id) AS bidders,
       count(DISTINCT lot_id) AS lots_with_bid
FROM predvestnik.auction_bids;

SELECT
  count(*) FILTER (WHERE traded_at>=now()-interval '30 days') AS trades_30d,
  count(DISTINCT user_id) FILTER (WHERE traded_at>=now()-interval '30 days') AS users_30d
FROM predvestnik.crypto_trades;

SELECT
  count(*) FILTER (WHERE created_at>=now()-interval '7 days') AS sessions_7d,
  count(DISTINCT user_id) FILTER (WHERE created_at>=now()-interval '7 days') AS users_7d,
  count(*) FILTER (WHERE created_at>=now()-interval '30 days') AS sessions_30d,
  count(DISTINCT user_id) FILTER (WHERE created_at>=now()-interval '30 days') AS users_30d
FROM predvestnik.minigame_sessions;

\echo 'WALLET FLOWS'
SELECT currency,
       count(*) FILTER (WHERE delta<>0) AS nonzero_entries,
       count(DISTINCT user_id) FILTER (WHERE delta<>0) AS users,
       round(sum(delta) FILTER (WHERE delta>0)::numeric, 2) AS total_in,
       round(abs(sum(delta) FILTER (WHERE delta<0))::numeric, 2) AS total_out,
       round(sum(delta)::numeric, 2) AS net
FROM (
  SELECT user_id, 'mora' currency, delta_mora delta FROM predvestnik.wallet_log
  UNION ALL SELECT user_id, 'diamonds', delta_diamonds FROM predvestnik.wallet_log
  UNION ALL SELECT user_id, 'dark_mora', delta_dark_mora FROM predvestnik.wallet_log
  UNION ALL SELECT user_id, 'crystals', delta_crystals FROM predvestnik.wallet_log
  UNION ALL SELECT user_id, 'zarniki', delta_zarniki FROM predvestnik.wallet_log
) flows
GROUP BY currency ORDER BY currency;

SELECT source, count(*) AS entries, count(DISTINCT user_id) AS users,
       round(sum(delta_mora)::numeric, 2) AS net_mora,
       round(sum(delta_diamonds)::numeric, 2) AS net_diamonds,
       round(sum(delta_zarniki)::numeric, 2) AS net_zarniki
FROM predvestnik.wallet_log
GROUP BY source ORDER BY entries DESC
LIMIT 20;

\echo 'GACHA'
WITH per_user AS (
  SELECT user_id, count(*) AS spins FROM predvestnik.gacha_history GROUP BY user_id
), ranked AS (
  SELECT spins, ntile(10) OVER (ORDER BY spins DESC) AS decile FROM per_user
)
SELECT sum(spins) AS spins,
       count(*) AS users,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY spins)::numeric,1) AS median_spins,
       round(percentile_cont(0.9) WITHIN GROUP (ORDER BY spins)::numeric,1) AS p90_spins,
       max(spins) AS max_spins,
       round((100.0*sum(spins) FILTER (WHERE decile=1)/sum(spins))::numeric,1)
         AS top_decile_share_pct
FROM ranked;

SELECT spin_type, count(*) AS spins, count(DISTINCT user_id) AS users
FROM predvestnik.gacha_history
GROUP BY spin_type ORDER BY spins DESC;

SELECT spin_type, count(*) AS tracked_users,
       round(avg(count)::numeric,1) AS avg_pity,
       max(count) AS max_pity
FROM predvestnik.gacha_pity
GROUP BY spin_type ORDER BY spin_type;

\echo 'QUESTS AND BATTLE PASS'
SELECT quest_id, count(*) AS assignments, count(DISTINCT user_id) AS users,
       count(*) FILTER (WHERE completed<>0) AS completed,
       round(100.0*count(*) FILTER (WHERE completed<>0)/nullif(count(*),0),1)
         AS completion_pct
FROM predvestnik.daily_quests
GROUP BY quest_id ORDER BY assignments DESC;

SELECT season_id, count(*) AS users,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY level)::numeric,1) AS median_level,
       max(level) AS max_level,
       count(*) FILTER (WHERE cardinality(claimed_free_levels)>0) AS free_claimers,
       count(*) FILTER (WHERE cardinality(claimed_paid_levels)>0) AS paid_claimers
FROM predvestnik.battle_pass_progress
GROUP BY season_id ORDER BY season_id;

SELECT
  count(*) FILTER (WHERE cardinality(claimed_paid_levels)>0) AS paid_claimers,
  count(*) FILTER (WHERE cardinality(claimed_paid_levels)>0 AND EXISTS (
    SELECT 1 FROM predvestnik.vip_subscriptions v
    WHERE v.user_id=bp.user_id AND v.expires_at>now()
  )) AS paid_claimers_with_active_vip
FROM predvestnik.battle_pass_progress bp;

\echo 'DATA QUALITY GATES'
SELECT check_name, failures
FROM (
  SELECT 'duplicate_users_pk' check_name, count(*)::bigint failures
    FROM (SELECT user_tg_id FROM predvestnik.users GROUP BY user_tg_id HAVING count(*)>1) d
  UNION ALL SELECT 'duplicate_daily_stats_grain', count(*) FROM (
    SELECT user_id,chat_id,date FROM predvestnik.daily_user_stats
    GROUP BY user_id,chat_id,date HAVING count(*)>1
  ) d
  UNION ALL SELECT 'pets_without_user', count(*) FROM predvestnik.pets p
    LEFT JOIN predvestnik.users u ON u.user_tg_id=p.owner_id WHERE u.user_tg_id IS NULL
  UNION ALL SELECT 'units_without_user', count(*) FROM predvestnik.user_units x
    LEFT JOIN predvestnik.users u ON u.user_tg_id=x.user_id WHERE u.user_tg_id IS NULL
  UNION ALL SELECT 'wallet_without_user', count(*) FROM predvestnik.wallet_log x
    LEFT JOIN predvestnik.users u ON u.user_tg_id=x.user_id WHERE u.user_tg_id IS NULL
  UNION ALL SELECT 'negative_user_balance', count(*) FROM predvestnik.users
    WHERE user_balance_mora<0 OR user_balance_diamonds<0 OR user_balance_dark_mora<0
       OR user_balance_crystals<0 OR user_balance_zarniki<0
  UNION ALL SELECT 'invalid_pet_level', count(*) FROM predvestnik.pets
    WHERE pet_level<1 OR pet_level>10
  UNION ALL SELECT 'invalid_unit_level', count(*) FROM predvestnik.user_units
    WHERE level<0 OR level>10
  UNION ALL SELECT 'wallet_zero_delta_rows', count(*) FROM predvestnik.wallet_log
    WHERE coalesce(delta_mora,0)=0 AND coalesce(delta_diamonds,0)=0
      AND coalesce(delta_dark_mora,0)=0 AND coalesce(delta_crystals,0)=0
      AND coalesce(delta_zarniki,0)=0
) checks ORDER BY failures DESC, check_name;

SELECT count(*) AS quest_rows,
       count(*) FILTER (WHERE date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$') AS daily_key_rows,
       count(*) FILTER (WHERE date ~ '^W[0-9]{4}-[0-9]{2}$') AS weekly_key_rows,
       count(*) FILTER (WHERE date !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                         AND date !~ '^W[0-9]{4}-[0-9]{2}$') AS other_key_rows
FROM predvestnik.daily_quests;

SELECT count(*) AS site_events,
       count(*) FILTER (WHERE duration_sec=0) AS zero_duration,
       round(100.0*count(*) FILTER (WHERE duration_sec=0)/nullif(count(*),0),1)
         AS zero_duration_pct,
       count(DISTINCT user_id) AS tracked_users
FROM predvestnik.site_analytics;

SELECT count(*) AS users,
       count(*) FILTER (WHERE combat_power=0) AS zero_cached_cp,
       count(*) FILTER (WHERE account_xp>0 AND combat_power=0) AS progressed_but_zero_cp
FROM predvestnik.users;

COMMIT;
