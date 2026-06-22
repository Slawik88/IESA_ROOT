"""bot/core/database.py — PostgreSQL schema initialisation."""
from loguru import logger
from infrastructure.database import get_pool

_SCHEMA = "predvestnik"


async def init_db():
    logger.info("Проверка и создание таблиц PostgreSQL...")
    pool = get_pool()
    async with pool.acquire() as db:
        # Create dedicated schema
        await db.execute(f"CREATE SCHEMA IF NOT EXISTS {_SCHEMA}")
        await db.execute(f"SET search_path TO {_SCHEMA}, public")
        # Permanently set search_path for this DB user so RESET ALL still
        # resolves to 'predvestnik' (asyncpg calls RESET ALL on pool release).
        try:
            await db.execute(
                f"ALTER ROLE CURRENT_USER SET search_path TO {_SCHEMA}, public"
            )
        except Exception:
            pass  # might fail without ALTER ROLE privilege; server_settings handles it

        # 1. Users
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_tg_id      BIGINT PRIMARY KEY,
                user_tg_username TEXT,
                user_balance_mora      FLOAT8 DEFAULT 0.0,
                user_balance_diamonds  FLOAT8 DEFAULT 0.0,
                user_balance_dark_mora FLOAT8 DEFAULT 0.0,
                user_balance_zarniki   FLOAT8 DEFAULT 0.0,
                global_rank     INTEGER DEFAULT 0,
                user_is_active  BOOLEAN DEFAULT TRUE,
                onboarded       BOOLEAN DEFAULT TRUE,
                active_theme    TEXT DEFAULT NULL,
                contrabanda_last_at      TIMESTAMP DEFAULT NULL,
                contrabanda_banned_until TIMESTAMP DEFAULT NULL,
                ritual_last_at           TIMESTAMP DEFAULT NULL
            )
        """)
        # NB: колонки ниже продублированы ALTER-ами для апгрейда СТАРЫХ БД
        # (созданных до того, как они попали в CREATE). На свежей БД ALTER —
        # no-op (IF NOT EXISTS). Не удалять ALTER, пока живы старые инсталляции.

        # 2. Chat stats
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_chat_stats (
                user_tg_id  BIGINT,
                chat_tg_id  BIGINT,
                user_level  INTEGER DEFAULT 1,
                user_xp     INTEGER DEFAULT 0,
                local_rank  INTEGER DEFAULT 0,
                user_messages_count_per_day         INTEGER DEFAULT 0,
                user_messages_count_per_week        INTEGER DEFAULT 0,
                user_messages_count_per_month       INTEGER DEFAULT 0,
                user_messages_count_all_time        INTEGER DEFAULT 0,
                user_messages_count_per_last_day    INTEGER DEFAULT 0,
                user_messages_count_per_last_week   INTEGER DEFAULT 0,
                user_messages_count_per_last_month  INTEGER DEFAULT 0,
                last_message_at  TIMESTAMP DEFAULT NOW(),
                is_left          BOOLEAN DEFAULT FALSE,
                joined_at        TIMESTAMP DEFAULT NOW(),
                immune_until     TIMESTAMP DEFAULT NULL,
                is_immune        BOOLEAN DEFAULT FALSE,
                warnings         INTEGER DEFAULT 0,
                PRIMARY KEY (user_tg_id, chat_tg_id)
            )
        """)

        # 3. Daily stats
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_user_stats (
                user_id  BIGINT,
                chat_id  BIGINT,
                date     TEXT,
                message_count INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, chat_id, date)
            )
        """)

        # 4. Chat settings
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id              BIGINT PRIMARY KEY,
                shield_duration_days INTEGER DEFAULT 0,
                max_warnings         INTEGER DEFAULT 3,
                is_purging           BOOLEAN DEFAULT FALSE,
                purge_min_rank       INTEGER DEFAULT 4,
                purge_action_rank    INTEGER DEFAULT 2,
                rank_chat_lock       INTEGER DEFAULT 4,
                chat_title           TEXT DEFAULT NULL,
                timezone_offset      INTEGER DEFAULT 0,
                last_chest_at        TIMESTAMP DEFAULT NULL,
                rank_warn            INTEGER DEFAULT 2,
                rank_mute            INTEGER DEFAULT 3,
                rank_kick            INTEGER DEFAULT 4,
                rank_ban             INTEGER DEFAULT 5,
                rank_shield          INTEGER DEFAULT 4,
                rank_immune          INTEGER DEFAULT 5,
                events_enabled       INTEGER DEFAULT 1,
                nsfw_warps_allowed   INTEGER DEFAULT 1,
                auction_min_rank     INTEGER DEFAULT 0,
                module_shop          INTEGER DEFAULT 1,
                module_gacha         INTEGER DEFAULT 1,
                module_expeditions   INTEGER DEFAULT 1,
                module_auction       INTEGER DEFAULT 1,
                module_games         INTEGER DEFAULT 1,
                module_exchange      INTEGER DEFAULT 1,
                module_quests        INTEGER DEFAULT 1,
                module_zoo           INTEGER DEFAULT 1,
                module_warps         INTEGER DEFAULT 1,
                module_daily_deal    INTEGER DEFAULT 1,
                rank_duel            INTEGER DEFAULT 0,
                rank_marriage        INTEGER DEFAULT 0,
                rank_give            INTEGER DEFAULT 0
            )
        """)
        # Migrations: add new columns to existing chat_settings rows
        for _col, _default in [
            ("rank_duel", 0), ("rank_marriage", 0), ("rank_give", 0),
            ("purge_action_rank", 2), ("rank_chat_lock", 4),
        ]:
            try:
                await db.execute(
                    f"ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS {_col} INTEGER DEFAULT {_default}"
                )
            except Exception:
                pass

        # Migrations: add dark mora columns to users
        for _stmt in [
            # Аудит «потерянных механик» п.4: legacy-дубль. Баланс Тёмной Моры живёт
            # в user_balance_dark_mora (FLOAT8); INTEGER-колонка dark_mora никогда не
            # читалась/писалась — убираем дубль (IF EXISTS — данные не теряются).
            "ALTER TABLE users DROP COLUMN IF EXISTS dark_mora",
            # Block 10: DEFAULT TRUE → существующие игроки уже «онбордингованы»
            # (стартовый набор не получат); новые вставляются с FALSE (update_user).
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarded BOOLEAN DEFAULT TRUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS contrabanda_last_at TIMESTAMP DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS contrabanda_banned_until TIMESTAMP DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ritual_last_at TIMESTAMP DEFAULT NULL",
        ]:
            try:
                await db.execute(_stmt)
            except Exception:
                pass

        # 5. Warnings history
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_warnings (
                id         SERIAL PRIMARY KEY,
                chat_id    BIGINT,
                user_id    BIGINT,
                admin_id   BIGINT,
                reason     TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # 6. Moderation logs
        await db.execute("""
            CREATE TABLE IF NOT EXISTS moderation_logs (
                id         SERIAL PRIMARY KEY,
                chat_id    BIGINT,
                user_id    BIGINT,
                admin_id   BIGINT,
                action     TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # 7. Marriages
        await db.execute("""
            CREATE TABLE IF NOT EXISTS marriages (
                id              SERIAL PRIMARY KEY,
                chat_id         BIGINT,
                user1_id        BIGINT,
                user1_name      TEXT,
                user2_id        BIGINT,
                user2_name      TEXT,
                family_balance           FLOAT8 DEFAULT 0.0,
                family_balance_diamonds  FLOAT8 DEFAULT 0.0,
                family_balance_dark_mora FLOAT8 DEFAULT 0.0,
                family_balance_zarniki   FLOAT8 DEFAULT 0.0,
                last_anniversary INTEGER DEFAULT 0,
                marriage_date   TIMESTAMP DEFAULT NOW()
            )
        """)

        # 8. Chat links
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_links (
                main_chat_id  BIGINT PRIMARY KEY,
                admin_chat_id BIGINT,
                added_at      TIMESTAMP DEFAULT NOW()
            )
        """)

        # 9. Chat bind tokens
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_bind_tokens (
                token           TEXT PRIMARY KEY,
                main_chat_id    BIGINT,
                main_chat_title TEXT,
                created_at      TIMESTAMP DEFAULT NOW()
            )
        """)

        # 10. Inventory
        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                user_id  BIGINT,
                item_id  TEXT,
                quantity INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, item_id)
            )
        """)

        # 11. Zoo stats
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_zoo_stats (
                user_id                BIGINT PRIMARY KEY,
                max_slots              INTEGER DEFAULT 3,
                wolf_cooldown_until    TIMESTAMP DEFAULT NULL,
                last_income_collection TIMESTAMP DEFAULT NULL
            )
        """)

        # 12. Pets
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                id          SERIAL PRIMARY KEY,
                owner_id    BIGINT,
                marriage_id INTEGER DEFAULT NULL,
                name        TEXT,
                species_id  TEXT,
                rarity      TEXT,
                placement   TEXT DEFAULT 'storage',
                fatigue     INTEGER DEFAULT 0,
                is_summoned BOOLEAN DEFAULT FALSE,
                buff_active_until       TIMESTAMP DEFAULT NULL,
                last_fatigue_update     TIMESTAMP DEFAULT NOW(),
                pet_level               INTEGER DEFAULT 1,
                duplicates_collected    INTEGER DEFAULT 0,
                copy_index              INTEGER DEFAULT 1,
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """)

        # 13. Expeditions
        await db.execute("""
            CREATE TABLE IF NOT EXISTS active_expeditions (
                pet_id         INTEGER PRIMARY KEY,
                chat_id        BIGINT,
                duration_hours INTEGER,
                cost_mora      FLOAT8,
                ends_at        TIMESTAMP
            )
        """)

        # 14. Daily login / streak
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_login (
                user_id                BIGINT,
                chat_id                BIGINT,
                streak                 INTEGER DEFAULT 0,
                last_login             TIMESTAMP DEFAULT NULL,
                last_notified          TIMESTAMP DEFAULT NULL,
                recovery_streak        INTEGER DEFAULT 0,
                recovery_missed_days   INTEGER DEFAULT 0,
                recovery_expires       TIMESTAMP DEFAULT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        # Migration: TEXT → TIMESTAMP for existing tables (safe, idempotent)
        for _col in ("last_login", "last_notified", "recovery_expires"):
            try:
                await db.execute(
                    f"ALTER TABLE daily_login ALTER COLUMN {_col} "
                    f"TYPE TIMESTAMP USING "
                    f"CASE WHEN {_col} IS NOT NULL AND {_col} != '' "
                    f"THEN {_col}::TIMESTAMP ELSE NULL END"
                )
            except Exception:
                pass  # already TIMESTAMP or migration failed (non-fatal)
        # Migration: ЕДИНЫЙ (глобальный) стрик на все чаты — засеять строку
        # chat_id=0 максимальным стриком пользователя из старых по-чатных строк.
        # Идемпотентно (ON CONFLICT DO NOTHING): после создания глобальной строки
        # её ведёт middleware, повторный засев ничего не делает.
        try:
            await db.execute("""
                INSERT INTO daily_login
                    (user_id, chat_id, streak, last_login, last_notified,
                     recovery_streak, recovery_missed_days, recovery_expires)
                SELECT user_id, 0, MAX(streak), MAX(last_login), MAX(last_notified), 0, 0, NULL
                FROM daily_login
                WHERE chat_id <> 0
                GROUP BY user_id
                ON CONFLICT (user_id, chat_id) DO NOTHING
            """)
        except Exception:
            pass  # non-fatal: глобальная строка будет создана при первом сообщении

        # 15. Pet milestones
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pet_milestones_received (
                pet_id      INTEGER,
                milestone   INTEGER,
                granted_at  TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (pet_id, milestone)
            )
        """)

        # 16. Daily deal
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_deal_current (
                slot           INTEGER PRIMARY KEY,
                item_id        TEXT NOT NULL,
                quantity       INTEGER NOT NULL,
                price_mora     FLOAT8 DEFAULT 0,
                price_diamonds FLOAT8 DEFAULT 0,
                generated_at   TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_deal_purchases (
                user_id       BIGINT,
                slot          INTEGER,
                purchase_date TEXT,
                PRIMARY KEY (user_id, slot, purchase_date)
            )
        """)

        # 17. Wallet log
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wallet_log (
                id                       SERIAL PRIMARY KEY,
                user_id                  BIGINT NOT NULL,
                chat_id                  BIGINT,
                delta_mora               FLOAT8 DEFAULT 0,
                delta_diamonds           FLOAT8 DEFAULT 0,
                balance_mora_after       FLOAT8 NOT NULL DEFAULT 0,
                balance_diamonds_after   FLOAT8 NOT NULL DEFAULT 0,
                source                   TEXT NOT NULL,
                target_id                BIGINT,
                note                     TEXT,
                created_at               TIMESTAMP DEFAULT NOW()
            )
        """)

        # 18. Achievements
        await db.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                id             SERIAL PRIMARY KEY,
                user_id        BIGINT NOT NULL,
                achievement_id TEXT NOT NULL,
                level          INTEGER DEFAULT 0,
                progress       FLOAT8 DEFAULT 0,
                updated_at     TIMESTAMP DEFAULT NOW(),
                UNIQUE (user_id, achievement_id)
            )
        """)

        # 19. Exchange events
        await db.execute("""
            CREATE TABLE IF NOT EXISTS exchange_events (
                id         SERIAL PRIMARY KEY,
                starts_at  TIMESTAMP NOT NULL,
                ends_at    TIMESTAMP NOT NULL,
                status     TEXT DEFAULT 'scheduled'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_exchange_quota (
                user_id              BIGINT,
                event_id             INTEGER,
                diamonds_converted   FLOAT8 DEFAULT 0,
                PRIMARY KEY (user_id, event_id)
            )
        """)

        # 20. Mini-games
        await db.execute("""
            CREATE TABLE IF NOT EXISTS gamble_cooldowns (
                user_id     BIGINT,
                game        TEXT,
                last_played TIMESTAMP,
                PRIMARY KEY (user_id, game)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS gamble_daily_winnings (
                user_id   BIGINT,
                date      TEXT,
                total_won FLOAT8 DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        """)

        # 21. NSFW consents
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_nsfw_consents (
                target_user_id BIGINT,
                chat_id        BIGINT,
                status         TEXT NOT NULL,
                set_at         TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (target_user_id, chat_id)
            )
        """)

        # 22. Gacha pity
        await db.execute("""
            CREATE TABLE IF NOT EXISTS gacha_pity (
                user_id   BIGINT,
                spin_type TEXT,
                count     INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, spin_type)
            )
        """)

        # 23. Gacha history
        await db.execute("""
            CREATE TABLE IF NOT EXISTS gacha_history (
                id          SERIAL PRIMARY KEY,
                user_id     BIGINT NOT NULL,
                spin_type   TEXT NOT NULL,
                reward_json TEXT NOT NULL,
                rolled_at   TIMESTAMP DEFAULT NOW()
            )
        """)

        # 24. Nicknames
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_nicknames (
                user_id   BIGINT,
                chat_id   BIGINT,
                nickname  TEXT NOT NULL,
                set_at    TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # 25. Duels
        await db.execute("""
            CREATE TABLE IF NOT EXISTS duels (
                id              SERIAL PRIMARY KEY,
                challenger_id   BIGINT NOT NULL,
                challenged_id   BIGINT NOT NULL,
                chat_id         BIGINT NOT NULL,
                stake           FLOAT8 NOT NULL,
                challenger_pet_id INTEGER,
                challenged_pet_id INTEGER,
                status          TEXT DEFAULT 'pending',
                winner_id       BIGINT,
                created_at      TIMESTAMP DEFAULT NOW(),
                resolved_at     TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS duel_cooldowns (
                user_a      BIGINT,
                user_b      BIGINT,
                last_duel   TIMESTAMP,
                PRIMARY KEY (user_a, user_b)
            )
        """)

        # 26. Auction
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auction_lots (
                id                SERIAL PRIMARY KEY,
                seller_id         BIGINT NOT NULL,
                category          TEXT NOT NULL,
                item_type         TEXT NOT NULL,
                item_id_or_pet_id BIGINT NOT NULL,
                quantity          INTEGER DEFAULT 1,
                item_name         TEXT,
                min_bid           FLOAT8 NOT NULL,
                buyout            FLOAT8,
                created_at        TIMESTAMP DEFAULT NOW(),
                ends_at           TIMESTAMP NOT NULL,
                status            TEXT DEFAULT 'active'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auction_bids (
                id        SERIAL PRIMARY KEY,
                lot_id    INTEGER NOT NULL,
                bidder_id BIGINT NOT NULL,
                amount    FLOAT8 NOT NULL,
                is_active INTEGER DEFAULT 1,
                placed_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_reserve (
                user_id       BIGINT PRIMARY KEY,
                reserved_mora FLOAT8 DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auction_weekly_count (
                user_id    BIGINT,
                week_start TEXT,
                count      INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, week_start)
            )
        """)

        # 27. Chest events
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chest_events (
                id         SERIAL PRIMARY KEY,
                chat_id    BIGINT NOT NULL,
                spawned_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL,
                status     TEXT DEFAULT 'active'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chest_claims (
                chest_id   INTEGER,
                user_id    BIGINT,
                position   INTEGER NOT NULL,
                claimed_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (chest_id, user_id)
            )
        """)

        # 28. Daily quests
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_quests (
                user_id   BIGINT,
                chat_id   BIGINT,
                date      TEXT,
                quest_id  TEXT,
                progress  FLOAT8 DEFAULT 0,
                completed INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id, date, quest_id)
            )
        """)

        # 29. Blacklists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_blacklist (
                chat_id  BIGINT,
                user_id  BIGINT,
                reason   TEXT,
                added_by BIGINT,
                added_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS global_blacklist (
                id          SERIAL PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id   BIGINT NOT NULL,
                reason      TEXT,
                added_at    TIMESTAMP DEFAULT NOW(),
                UNIQUE (entity_type, entity_id)
            )
        """)

        # 30. Global module toggles
        await db.execute("""
            CREATE TABLE IF NOT EXISTS global_module_toggles (
                module_key      TEXT PRIMARY KEY,
                enabled         INTEGER DEFAULT 1,
                disabled_reason TEXT,
                updated_at      TIMESTAMP DEFAULT NOW()
            )
        """)

        # 31. Promo codes
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promocodes (
                code               TEXT PRIMARY KEY,
                description        TEXT DEFAULT '',
                valid_from         TEXT DEFAULT NULL,
                valid_until        TEXT DEFAULT NULL,
                max_activations    INTEGER DEFAULT 0,
                activations_count  INTEGER DEFAULT 0,
                reward_mora        FLOAT8 DEFAULT 0,
                reward_diamonds    FLOAT8 DEFAULT 0,
                reward_items_json  TEXT DEFAULT '{}',
                is_active          INTEGER DEFAULT 1,
                created_by         BIGINT,
                created_at         TIMESTAMP DEFAULT NOW()
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promocode_redemptions (
                code       TEXT NOT NULL,
                user_id    BIGINT NOT NULL,
                chat_id    BIGINT,
                redeemed_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (code, user_id)
            )
        """)

        # 31b. Promo code extensions (user/chat whitelists + dark mora + zarniki rewards)
        for _col, _type, _def in [
            ("reward_dark_mora",   "FLOAT8", "0"),
            ("reward_zarniki",     "FLOAT8", "0"),
            ("allowed_users_json", "TEXT",   "''"),
            ("allowed_chats_json", "TEXT",   "''"),
        ]:
            try:
                await db.execute(
                    f"ALTER TABLE promocodes ADD COLUMN IF NOT EXISTS {_col} {_type} DEFAULT {_def}"
                )
            except Exception:
                pass
        # Rename old crystals column if it exists (migration from wrong name)
        try:
            await db.execute("ALTER TABLE promocodes RENAME COLUMN reward_crystals TO reward_zarniki")
        except Exception:
            pass

        # 32. Dark Mora balance & cooldowns
        await db.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS user_balance_dark_mora FLOAT8 DEFAULT 0.0
        """)
        # 32b. Zarniki (donate currency ✨) balance
        try:
            await db.execute("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS user_balance_zarniki FLOAT8 DEFAULT 0.0
            """)
        except Exception:
            pass
        # Rename old crystals column if it exists
        try:
            await db.execute("ALTER TABLE users RENAME COLUMN user_balance_crystals TO user_balance_zarniki")
        except Exception:
            pass
        await db.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS active_theme TEXT DEFAULT NULL
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS dark_mora_cooldowns (
                user_id        BIGINT,
                action         TEXT,
                available_from TIMESTAMP NOT NULL,
                PRIMARY KEY (user_id, action)
            )
        """)

        # 33. Player buffs (one-use or timed)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS player_buffs (
                user_id    BIGINT,
                buff_type  TEXT,
                uses_left  INTEGER DEFAULT 1,
                expires_at TIMESTAMP DEFAULT NULL,
                value      FLOAT8 DEFAULT 0.0,
                PRIMARY KEY (user_id, buff_type)
            )
        """)

        # 34. Profile themes ownership
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_themes (
                user_id     BIGINT,
                theme_id    TEXT,
                acquired_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (user_id, theme_id)
            )
        """)

        # 35. Artifact instances (limited-print)
        # M1 (аудит): artifact_instances/artifact_award_log/relic_instances/
        # relic_award_log — мёртвые таблицы (нигде в коде не используются; реликвии
        # Блока 13 живут в user_relics). Удаляем идемпотентно. Если когда-нибудь
        # понадобятся теневые реликвии/артефакты — заводить заново осознанно.
        for _dead in ("artifact_instances", "artifact_award_log",
                      "relic_instances", "relic_award_log"):
            try:
                await db.execute(f"DROP TABLE IF EXISTS {_dead}")
            except Exception:
                pass

        # 37. Shadow Merchant events (Теневой Торговец)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shadow_merchant_events (
                id         SERIAL PRIMARY KEY,
                chat_id    BIGINT NOT NULL,
                keyword    TEXT NOT NULL,
                posted_at  TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL,
                status     TEXT DEFAULT 'active'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shadow_merchant_winners (
                event_id  INTEGER NOT NULL,
                user_id   BIGINT NOT NULL,
                position  INTEGER NOT NULL,
                reward    FLOAT8 NOT NULL,
                won_at    TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (event_id, user_id)
            )
        """)

        # Migrations: wallet_log dark mora + zarniki columns
        for _col, _def in [
            ("delta_dark_mora",         "0"),
            ("balance_dark_mora_after", "0"),
            ("delta_zarniki",           "0"),
            ("balance_zarniki_after",   "0"),
        ]:
            try:
                await db.execute(
                    f"ALTER TABLE wallet_log ADD COLUMN IF NOT EXISTS {_col} FLOAT8 DEFAULT {_def}"
                )
            except Exception:
                pass
        # Rename old crystals columns if they exist
        for _old, _new in [
            ("delta_crystals",         "delta_zarniki"),
            ("balance_crystals_after", "balance_zarniki_after"),
        ]:
            try:
                await db.execute(f"ALTER TABLE wallet_log RENAME COLUMN {_old} TO {_new}")
            except Exception:
                pass

        # Marriage proposals
        await db.execute("""
            CREATE TABLE IF NOT EXISTS marriage_proposals (
                id          SERIAL PRIMARY KEY,
                chat_id     BIGINT,
                proposer_id BIGINT,
                target_id   BIGINT,
                proposed_at TIMESTAMP DEFAULT NOW(),
                expires_at  TIMESTAMP,
                status      TEXT DEFAULT 'pending'
            )
        """)

        # VIP subscriptions (Implementation Block 2.1)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS vip_subscriptions (
                user_id          BIGINT PRIMARY KEY REFERENCES users(user_tg_id),
                tier             TEXT NOT NULL,
                started_at       TIMESTAMP DEFAULT NOW(),
                expires_at       TIMESTAMP NOT NULL,
                last_probnik_at  TIMESTAMP DEFAULT NULL,
                expiry_notified  BOOLEAN DEFAULT FALSE
            )
        """)

        # Battle Pass progress (Implementation Block 5.1)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS battle_pass_progress (
                user_id              BIGINT NOT NULL REFERENCES users(user_tg_id),
                season_id            TEXT NOT NULL,
                xp                   INTEGER DEFAULT 0,
                level                INTEGER DEFAULT 1,
                claimed_free_levels  INTEGER[] DEFAULT '{}',
                claimed_paid_levels  INTEGER[] DEFAULT '{}',
                season_end_notified  BOOLEAN NOT NULL DEFAULT FALSE,
                PRIMARY KEY (user_id, season_id)
            )
        """)

        # Global moderation: sanctions + appeals (Implementation Block 6.1)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS global_sanctions (
                id            SERIAL PRIMARY KEY,
                target_type   TEXT NOT NULL,        -- 'user' | 'chat'
                target_id     BIGINT NOT NULL,
                sanction_type TEXT NOT NULL,        -- 'warn' | 'restrict' | 'ban'
                reason        TEXT,
                issued_by     BIGINT NOT NULL,
                created_at    TIMESTAMP DEFAULT NOW(),
                expires_at    TIMESTAMP NULL,       -- NULL = бессрочно
                revoked_at    TIMESTAMP NULL,
                revoked_by    BIGINT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sanction_appeals (
                id            SERIAL PRIMARY KEY,
                user_id       BIGINT NOT NULL,
                sanction_id   INTEGER NOT NULL REFERENCES global_sanctions(id),
                text          TEXT NOT NULL,
                created_at    TIMESTAMP DEFAULT NOW(),
                status        TEXT DEFAULT 'pending',  -- pending | accepted | rejected
                resolved_by   BIGINT NULL,
                resolved_at   TIMESTAMP NULL
            )
        """)

        # Battle Pass seasons, управляемые с сайта (Консоль разработчика).
        # Мерджатся с registry.BATTLE_PASS_SEASONS — DB перекрывает registry по id.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS battle_pass_seasons (
                id         TEXT PRIMARY KEY,
                label      TEXT NOT NULL,
                starts_at  TEXT NOT NULL,   -- YYYY-MM-DD (как в registry)
                ends_at    TEXT NOT NULL,
                max_level  INTEGER DEFAULT 50,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Battle Pass rewards — DB-переопределения registry.BATTLE_PASS_REWARDS
        # Формат items: JSON-массив [["item_id", qty], ...] (как в registry)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS battle_pass_reward_overrides (
                season_id  TEXT NOT NULL,
                level      INTEGER NOT NULL,
                track      TEXT NOT NULL,
                mora       INTEGER DEFAULT 0,
                diamonds   INTEGER DEFAULT 0,
                items      TEXT DEFAULT '[]',
                theme_id   TEXT DEFAULT NULL,
                reward_options TEXT DEFAULT NULL,
                PRIMARY KEY (season_id, level, track)
            )
        """)

        # Battle Pass XP-конструктор (B): оверрайды веса XP за действие.
        # БД перекрывает constants.BATTLE_PASS_XP_WEIGHTS / _DAILY_CAPS.
        # enabled=FALSE → действие не даёт XP. daily_cap=0 → без лимита.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bp_xp_weight_overrides (
                metric     TEXT PRIMARY KEY,
                weight     INTEGER NOT NULL DEFAULT 0,
                enabled    BOOLEAN NOT NULL DEFAULT TRUE,
                daily_cap  INTEGER NOT NULL DEFAULT 0,
                label      TEXT DEFAULT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Battle Pass дневной счётчик XP на действие (A, анти-абуз): сколько XP
        # игрок уже набрал сегодня по каждой метрике — для усечения по daily_cap.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bp_xp_daily (
                user_id  BIGINT NOT NULL,
                day      TEXT NOT NULL,
                metric   TEXT NOT NULL,
                xp_today INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, day, metric)
            )
        """)
        # Battle Pass глобальные настройки (key-value): weekend_boost_pct и т.п.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bp_settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # Косметика профиля (конструктор внешнего вида): владение + надетый сет.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_cosmetics (
                user_id     BIGINT NOT NULL,
                cosmetic_id TEXT NOT NULL,
                acquired_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (user_id, cosmetic_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_cosmetic_loadout (
                user_id     BIGINT NOT NULL,
                slot        TEXT NOT NULL,
                cosmetic_id TEXT NOT NULL,
                PRIMARY KEY (user_id, slot)
            )
        """)

        # Theme Lab — кастомные raw-шаблоны премиум-тем профиля (правки без деплоя)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS profile_theme_overrides (
                template_id TEXT PRIMARY KEY,
                raw_text    TEXT NOT NULL,
                updated_at  TIMESTAMP DEFAULT NOW(),
                updated_by  BIGINT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_relics (
                user_id    BIGINT NOT NULL,
                relic_id   TEXT NOT NULL,
                acquired_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (user_id, relic_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_notification_prefs (
                user_id  BIGINT NOT NULL,
                category TEXT NOT NULL,
                enabled  BOOLEAN DEFAULT TRUE,
                PRIMARY KEY (user_id, category)
            )
        """)
        # Отложенные веб-уведомления (Welcome Back, БЛОК 3.3): если игрок был
        # офлайн при событии (поход завершился) — сохраняем чек до входа на сайт.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS web_notifications (
                id          SERIAL PRIMARY KEY,
                user_id     BIGINT,
                payload     TEXT,
                seen        INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """)
        # Журнал действий разработчика (БЛОК 4.2): кто, кому, что выдал/забрал,
        # причина и баланс «до/после» — для подотчётности дев-консоли.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_grant_log (
                id          SERIAL PRIMARY KEY,
                admin_id    BIGINT,
                target_id   BIGINT,
                action      TEXT,
                detail      TEXT,
                amount      FLOAT8,
                reason      TEXT,
                before_val  FLOAT8,
                after_val   FLOAT8,
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS partner_gifts_log (
                id          SERIAL PRIMARY KEY,
                sender_id   BIGINT,
                receiver_id BIGINT,
                gift_id     TEXT,
                sent_at     TIMESTAMP DEFAULT NOW()
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS theme_metadata_overrides (
                theme_id       TEXT PRIMARY KEY,
                name           TEXT,
                rarity         TEXT,
                source         TEXT,
                price_mora     INTEGER,
                price_diamonds NUMERIC,
                price_zarniki  INTEGER,
                price_dark     INTEGER,
                obtainable_bp  INTEGER DEFAULT 0,
                description    TEXT
            )
        """)

        # Migrations: admin panel + moderation extras
        for _stmt in [
            "ALTER TABLE moderation_logs ADD COLUMN IF NOT EXISTS reason TEXT",
            "ALTER TABLE user_chat_stats ADD COLUMN IF NOT EXISTS muted_until TIMESTAMP DEFAULT NULL",
            "ALTER TABLE user_chat_stats ADD COLUMN IF NOT EXISTS nickname_changes_count INTEGER DEFAULT 0",
            "ALTER TABLE user_chat_stats ADD COLUMN IF NOT EXISTS nickname_changes_reset_at TIMESTAMP DEFAULT NOW()",
            # «Стаж VIP» — суммарно оплаченных дней за всё время
            "ALTER TABLE vip_subscriptions ADD COLUMN IF NOT EXISTS total_days INTEGER DEFAULT 0",
            # Прошлый деплой мог уже создать theme_metadata_overrides со старым именем колонки
            "ALTER TABLE theme_metadata_overrides RENAME COLUMN price_dark_mora TO price_dark",
            # Block 5: семейный кошелёк на все 4 валюты (family_balance = Мора, уже была)
            "ALTER TABLE marriages ADD COLUMN IF NOT EXISTS family_balance_diamonds FLOAT8 DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN IF NOT EXISTS family_balance_dark_mora FLOAT8 DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN IF NOT EXISTS family_balance_zarniki FLOAT8 DEFAULT 0",
            # Block 6: выбор между 2 наградами на уровне БП (JSON массив вариантов)
            "ALTER TABLE battle_pass_reward_overrides ADD COLUMN IF NOT EXISTS reward_options TEXT DEFAULT NULL",
            # Block 14: маркер последней отпразднованной годовщины брака (в днях)
            "ALTER TABLE marriages ADD COLUMN IF NOT EXISTS last_anniversary INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(_stmt)
            except Exception:
                pass

        # Block 2: slot_expander снят с продажи — рефанд оставшихся в инвентарях
        # по 15💎/шт + удаление. Идемпотентно: после DELETE строк не остаётся,
        # повторный прогон ничего не делает. Уже КУПЛЕННЫЕ слоты (max_slots) не трогаем.
        try:
            await db.execute(
                "UPDATE users u SET user_balance_diamonds = user_balance_diamonds + agg.refund "
                "FROM (SELECT user_id, SUM(quantity) * 15 AS refund FROM inventory "
                "      WHERE item_id = 'slot_expander' GROUP BY user_id) agg "
                "WHERE u.user_tg_id = agg.user_id"
            )
            await db.execute(
                "INSERT INTO wallet_log (user_id, delta_diamonds, balance_mora_after, "
                "       balance_diamonds_after, source, note) "
                "SELECT agg.user_id, agg.refund, u.user_balance_mora, u.user_balance_diamonds, "
                "       'slot_expander_refund', 'Block 2: расширитель снят с продажи' "
                "FROM (SELECT user_id, SUM(quantity) * 15 AS refund FROM inventory "
                "      WHERE item_id = 'slot_expander' GROUP BY user_id) agg "
                "JOIN users u ON u.user_tg_id = agg.user_id"
            )
            await db.execute("DELETE FROM inventory WHERE item_id = 'slot_expander'")
        except Exception:
            pass

        # Block 8: единая гача. 4 старых жетона (novice/standard/premium/diamond)
        # сливаются 1:1 в единый spin_token (бесплатный спин мора-режима).
        # Идемпотентно: после DELETE старых строк не остаётся, повторный прогон
        # ничего не суммирует. Старые pity-строки гачи безвредны (новые ключи —
        # mora/diamond), их не трогаем.
        try:
            await db.execute(
                "INSERT INTO inventory (user_id, item_id, quantity) "
                "SELECT user_id, 'spin_token', SUM(quantity) FROM inventory "
                "WHERE item_id IN ('spin_token_novice','spin_token_standard',"
                "                  'spin_token_premium','spin_token_diamond') AND quantity > 0 "
                "GROUP BY user_id "
                "ON CONFLICT (user_id, item_id) DO UPDATE SET "
                "  quantity = inventory.quantity + EXCLUDED.quantity"
            )
            await db.execute(
                "DELETE FROM inventory WHERE item_id IN "
                "('spin_token_novice','spin_token_standard','spin_token_premium','spin_token_diamond')"
            )
        except Exception:
            pass

        # ── Indexes ────────────────────────────────────────────────────────────
        # ── Indexes ────────────────────────────────────────────────────────────
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(user_tg_username)",
            "CREATE INDEX IF NOT EXISTS idx_stats_chat_xp ON user_chat_stats(chat_tg_id, user_xp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_mod_chat_action ON moderation_logs(chat_id, action)",
            "CREATE INDEX IF NOT EXISTS idx_marriages_chat ON marriages(chat_id, user1_id, user2_id)",
            "CREATE INDEX IF NOT EXISTS idx_daily_stats ON daily_user_stats(chat_id, date)",
            "CREATE INDEX IF NOT EXISTS idx_pets_owner ON pets(owner_id, placement)",
            "CREATE INDEX IF NOT EXISTS idx_daily_login ON daily_login(user_id, chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_wallet_log_user ON wallet_log(user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_achievements_user ON achievements(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_gacha_history ON gacha_history(user_id, rolled_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_auction_lots ON auction_lots(status, ends_at)",
            "CREATE INDEX IF NOT EXISTS idx_auction_bids ON auction_bids(lot_id, is_active)",
            "CREATE INDEX IF NOT EXISTS idx_chest_events ON chest_events(chat_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_daily_quests ON daily_quests(user_id, chat_id, date)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_nickname_unique ON user_nicknames(chat_id, LOWER(nickname))",
            "CREATE INDEX IF NOT EXISTS idx_promo_redemptions ON promocode_redemptions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_themes ON user_themes(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_shadow_events ON shadow_merchant_events(status, expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_player_buffs ON player_buffs(user_id, buff_type)",
            "CREATE INDEX IF NOT EXISTS idx_global_sanctions_target ON global_sanctions(target_type, target_id)",
            "CREATE INDEX IF NOT EXISTS idx_sanction_appeals_status ON sanction_appeals(status)",
            "CREATE INDEX IF NOT EXISTS idx_web_notif_unseen ON web_notifications(user_id, seen)",
        ]
        for idx_sql in indexes:
            await db.execute(idx_sql)

    logger.info("✅ Схема PostgreSQL готова!")
