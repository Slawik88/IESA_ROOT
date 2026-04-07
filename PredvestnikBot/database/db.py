import asyncpg
import logging
import math
from datetime import datetime, timedelta, date, timezone

from database.postgres import connect as postgres_connect, ddl_connect, get_pg_pool

_log = logging.getLogger("db")


async def init_db():
    async with ddl_connect() as db:
        # PostgreSQL не нужен PRAGMA journal_mode

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username      TEXT    DEFAULT '',
                full_name     TEXT    DEFAULT '',
                rank          TEXT    DEFAULT 'user',
                message_count INTEGER DEFAULT 0,
                is_banned     INTEGER DEFAULT 0,
                ban_reason    TEXT    DEFAULT NULL,
                warns         INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id BIGINT PRIMARY KEY,
                welcome_text      TEXT    DEFAULT NULL,
                farewell_text     TEXT    DEFAULT NULL,
                rules_text        TEXT    DEFAULT NULL,
                antiflood_enabled INTEGER DEFAULT 0,
                antiflood_limit   INTEGER DEFAULT 5,
                antiflood_action  TEXT    DEFAULT 'mute',
                blacklist_enabled INTEGER DEFAULT 1,
                welcome_call      INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id BIGINT PRIMARY KEY,
                title     TEXT    DEFAULT '',
                username  TEXT    DEFAULT '',
                chat_type TEXT    DEFAULT 'private',
                is_active INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                name    TEXT    NOT NULL,
                content TEXT    NOT NULL,
                UNIQUE(chat_id, name)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_filters (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                keyword  TEXT    NOT NULL,
                response TEXT    NOT NULL,
                UNIQUE(chat_id, keyword)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                word    TEXT    NOT NULL,
                UNIQUE(chat_id, word)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS locks (
                chat_id BIGINT PRIMARY KEY,
                links    INTEGER DEFAULT 0,
                stickers INTEGER DEFAULT 0,
                gifs     INTEGER DEFAULT 0,
                forwards INTEGER DEFAULT 0,
                voice    INTEGER DEFAULT 0,
                video    INTEGER DEFAULT 0,
                photo    INTEGER DEFAULT 0,
                audio    INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS rep_log (
                id SERIAL PRIMARY KEY,
                from_uid  INTEGER NOT NULL,
                to_uid    INTEGER NOT NULL,
                chat_id BIGINT NOT NULL,
                amount    INTEGER NOT NULL DEFAULT 1,
                given_at  TIMESTAMPTZ NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS cleanup_counts (
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                count      INTEGER DEFAULT 0,
                week_count INTEGER DEFAULT 0,
                day_count  INTEGER DEFAULT 0,
                week_start TEXT    DEFAULT NULL,
                day_start  TEXT    DEFAULT NULL,
                PRIMARY KEY(chat_id, user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_quests (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                quest_date TIMESTAMPTZ NOT NULL,
                quest_type TEXT    NOT NULL,
                goal       INTEGER NOT NULL,
                progress   INTEGER DEFAULT 0,
                completed  INTEGER DEFAULT 0,
                rewarded   INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id, quest_date)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_achievements (
                user_id BIGINT NOT NULL,
                badge     TEXT    NOT NULL,
                earned_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (user_id, badge)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                question     TEXT    NOT NULL,
                options_json TEXT    NOT NULL,
                created_at   TIMESTAMPTZ NOT NULL,
                closed       INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS poll_votes (
                poll_id    INTEGER NOT NULL,
                user_id BIGINT NOT NULL,
                option_idx INTEGER NOT NULL,
                PRIMARY KEY (poll_id, user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                user_id BIGINT PRIMARY KEY,
                birthday TEXT    NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS marriages (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                partner_id BIGINT NOT NULL,
                married_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS anniversary_log (
                id       SERIAL PRIMARY KEY,
                user_id  BIGINT NOT NULL,
                chat_id  BIGINT NOT NULL,
                date_str TEXT   NOT NULL,
                UNIQUE (user_id, chat_id, date_str)
            )
        """)

        # Ожидающие импорты — применяются при первом сообщении юзера в чат
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_user_imports (
                username      TEXT    NOT NULL,
                chat_id BIGINT NOT NULL,
                message_count INTEGER DEFAULT 0,
                PRIMARY KEY (username, chat_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_marriage_imports (
                username1  TEXT    NOT NULL,
                username2  TEXT    NOT NULL,
                chat_id BIGINT NOT NULL,
                married_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (username1, chat_id)
            )
        """)

        # ─── Профили пользователей привязанные к конкретному чату ─────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                rank          TEXT    DEFAULT 'user',
                message_count INTEGER DEFAULT 0,
                xp            INTEGER DEFAULT 0,
                level         INTEGER DEFAULT 1,
                reputation   INTEGER DEFAULT 0,
                warns        INTEGER DEFAULT 0,
                bio          TEXT    DEFAULT NULL,
                custom_title TEXT    DEFAULT NULL,
                is_banned    INTEGER DEFAULT 0,
                ban_reason   TEXT    DEFAULT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # Добавляем новые колонки в users (для обновлений существующей БД)
        for col_def in [
            "reputation  INTEGER DEFAULT 0",
            "xp          INTEGER DEFAULT 0",
            "level       INTEGER DEFAULT 1",
            "bio         TEXT    DEFAULT NULL",
            "first_seen  TIMESTAMPTZ DEFAULT NULL",
            "custom_title TEXT   DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass  # колонка уже существует

        # Добавляем новые колонки в cleanup_counts (для обновлений существующей БД)
        for col_def in [
            "week_count      INTEGER DEFAULT 0",
            "day_count       INTEGER DEFAULT 0",
            "week_start      TEXT    DEFAULT NULL",
            "day_start       TEXT    DEFAULT NULL",
            "yesterday_count INTEGER DEFAULT 0",
            "last_week_count INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(f"ALTER TABLE cleanup_counts ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        # Добавляем новую колонку в chat_settings
        for col_def in [
            "cleanup_threshold INTEGER DEFAULT 10",
            "blacklist_enabled INTEGER DEFAULT 1",
            "welcome_call      INTEGER DEFAULT 0",
            "social_tiktok     TEXT    DEFAULT NULL",
            "social_youtube    TEXT    DEFAULT NULL",
            "social_instagram  TEXT    DEFAULT NULL",
            "cleanup_locked    INTEGER DEFAULT 0",
            "inactivity_warn_enabled INTEGER DEFAULT 0",
            "inactivity_warn_days    INTEGER DEFAULT 5",
            "next_cleanup_at         TIMESTAMPTZ DEFAULT NULL",
            "cleanup_reminder_sent   INTEGER DEFAULT 0",
            "antiflood_window  REAL    DEFAULT 2.0",
            "cleanup_message_norm INTEGER DEFAULT 70",
            "cleanup_warn_hours   INTEGER DEFAULT 48",
            # ── Feature Flags (1 = enabled / 0 = disabled) ──────────────
            "feat_website       INTEGER DEFAULT 1",
            "feat_antispam      INTEGER DEFAULT 1",
            "feat_marriages     INTEGER DEFAULT 1",
            "feat_pets          INTEGER DEFAULT 1",
            "feat_casino        INTEGER DEFAULT 1",
            "feat_random_events INTEGER DEFAULT 1",
        ]:
            try:
                await db.execute(
                    f"ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS {col_def}"
                )
            except Exception:
                pass

        # Миграция: добавить message_count в user_stats (для обновлений БД)
        for col_def in [
            "message_count       INTEGER DEFAULT 0",
            "first_active        TIMESTAMPTZ DEFAULT NULL",
            "last_active         TIMESTAMPTZ DEFAULT NULL",
            "inactivity_warned_at TIMESTAMPTZ DEFAULT NULL",
            "newbie_shield_until TIMESTAMPTZ DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        # Миграция: новые колонки user_mora (VIP, буст XP, рамка топа)
        for col_def in [
            "vip              INTEGER   DEFAULT 0",
            "vip_expires_at   TIMESTAMPTZ DEFAULT NULL",
            "xp_boost_until   TIMESTAMPTZ DEFAULT NULL",
            "top_frame        TEXT    DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_mora ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        # Таблица отдыхающих (защита от чистки)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rest_users (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                days       INTEGER NOT NULL DEFAULT 7,
                added_at   TIMESTAMPTZ NOT NULL,
                added_by   BIGINT NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # Таблица онлайн-статуса mini app
        await db.execute("""
            CREATE TABLE IF NOT EXISTS miniapp_online (
                user_id    BIGINT PRIMARY KEY,
                last_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # Таблица админ-групп (для системных уведомлений)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_groups (
                chat_id BIGINT PRIMARY KEY
            )
        """)

        # Таблица тестовых чатов (изоляция от основной экономики)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS test_chats (
                chat_id BIGINT PRIMARY KEY,
                set_by  BIGINT NOT NULL DEFAULT 0
            )
        """)

        # Привязка основного чата к конкретному чату-администрации
        # (уведомления из main_chat_id идут в admin_chat_id)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_admin_links (
                main_chat_id  BIGINT PRIMARY KEY,
                admin_chat_id BIGINT NOT NULL
            )
        """)

        # Таблица типов каналов (правила/основной/etc.)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_types (
                type     TEXT PRIMARY KEY,
                chat_id BIGINT NOT NULL
            )
        """)

        # Таблица ролей сообщества
        await db.execute("""
            CREATE TABLE IF NOT EXISTS community_roles (
                id SERIAL PRIMARY KEY,
                name        TEXT    NOT NULL UNIQUE,
                emoji       TEXT    NOT NULL DEFAULT '',
                description TEXT    NOT NULL DEFAULT '',
                created_at  TIMESTAMPTZ NOT NULL
            )
        """)

        # Таблица назначенных ролей пользователям
        # role_id UNIQUE гарантирует: одна роль — один человек (1:1)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                role_id INTEGER NOT NULL UNIQUE REFERENCES community_roles(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL
            )
        """)

        # Журнал добровольных выходов из чата
        await db.execute("""
            CREATE TABLE IF NOT EXISTS leave_log (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                full_name TEXT    DEFAULT '',
                username  TEXT    DEFAULT '',
                left_at   TIMESTAMPTZ NOT NULL
            )
        """)

        # Чёрный список пользователей по Telegram ID (per-chat)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_banlist (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                added_by  BIGINT DEFAULT 0,
                reason    TEXT    DEFAULT '',
                added_at  TIMESTAMPTZ NOT NULL,
                UNIQUE(chat_id, user_id)
            )
        """)

        # Ожидающие назначения ролей (до вступления в основной чат)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_roles (
                user_id BIGINT PRIMARY KEY,
                role_name   TEXT    NOT NULL,
                reserved_at TIMESTAMPTZ NOT NULL
            )
        """)

        # ─── Питомцы (разблокируются через брак) ───────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                pet_type   TEXT    NOT NULL,
                name       TEXT    DEFAULT NULL,
                adopted_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # Система экономики: валюта Мора
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_mora (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                balance        INTEGER DEFAULT 0,
                total_earned   INTEGER DEFAULT 0,
                streak_days    INTEGER DEFAULT 0,
                last_daily     TEXT    DEFAULT NULL,
                mora_public    INTEGER DEFAULT 1,
                vip            INTEGER DEFAULT 0,
                xp_boost_until TIMESTAMPTZ DEFAULT NULL,
                top_frame      TEXT    DEFAULT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # Казино: вызовы на дуэль (кубик)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS casino_duels (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                challenger_id INTEGER NOT NULL,
                target_id     BIGINT NOT NULL,
                bet           INTEGER NOT NULL,
                status        TEXT    DEFAULT 'pending',
                msg_id        INTEGER DEFAULT NULL,
                created_at    TIMESTAMPTZ NOT NULL
            )
        """)

        # Казино: лотерейные билеты (обновляются еженедельно)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS casino_lottery (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                week_key TEXT    NOT NULL,
                tickets  INTEGER DEFAULT 1,
                UNIQUE(chat_id, user_id, week_key)
            )
        """)

        # Семейный кошелёк (совместный баланс для пар)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS family_wallet (
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                balance   INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        # Журнал транзакций семейного кошелька (хранится 2 месяца)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS family_wallet_log (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                action      TEXT    NOT NULL,
                amount      INTEGER NOT NULL,
                description TEXT    DEFAULT '',
                created_at  TIMESTAMPTZ NOT NULL
            )
        """)
        
        # Миграция: исправляем тип поля created_at с TEXT на TIMESTAMPTZ
        try:
            await db.execute("""
                ALTER TABLE family_wallet_log 
                ALTER COLUMN created_at TYPE TIMESTAMPTZ 
                USING created_at::TIMESTAMPTZ
            """)
        except Exception:
            # Если миграция не удалась, пересоздаем таблицу
            await db.execute("DROP TABLE IF EXISTS family_wallet_log")
            await db.execute("""
                CREATE TABLE family_wallet_log (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    action      TEXT    NOT NULL,
                    amount      INTEGER NOT NULL,
                    description TEXT    DEFAULT '',
                    created_at  TIMESTAMPTZ NOT NULL
                )
            """)
        
        # Очищаем записи старше 2 месяцев при каждом старте
        await db.execute(
            "DELETE FROM family_wallet_log WHERE created_at < NOW() - INTERVAL '60 days'"
        )

        # Миграция: семейный кошелёк становится глобальным (chat_id=0).
        # Суммируем все per-chat вклады в глобальную строку chat_id=0.
        await db.execute("""
            INSERT INTO family_wallet (chat_id, user_id, balance)
            SELECT 0, user_id, SUM(balance)
            FROM family_wallet
            WHERE chat_id != 0
            GROUP BY user_id
            ON CONFLICT(chat_id, user_id) DO UPDATE
                SET balance = family_wallet.balance + EXCLUDED.balance
        """)
        await db.execute("DELETE FROM family_wallet WHERE chat_id != 0")
        await db.execute("""
            INSERT INTO family_wallet_log (chat_id, user_id, action, amount, description, created_at)
            SELECT 0, user_id, action, amount, description, created_at
            FROM family_wallet_log
            WHERE chat_id != 0
            ON CONFLICT DO NOTHING
        """)
        await db.execute("DELETE FROM family_wallet_log WHERE chat_id != 0")

        # Миграция: биржа (облигации) становится глобальной (chat_id=0).
        # Суммируем per-chat holdings в глобальную строку.
        await db.execute("""
            INSERT INTO bond_prices (bond_key, chat_id, price, updated_at)
            SELECT bond_key, 0, price, updated_at
            FROM bond_prices
            WHERE chat_id != 0
            ON CONFLICT(bond_key, chat_id) DO NOTHING
        """)
        await db.execute("DELETE FROM bond_prices WHERE chat_id != 0")
        await db.execute("""
            INSERT INTO market_state (chat_id, trend, ticks_left, updated_at)
            SELECT 0, trend, ticks_left, updated_at
            FROM market_state
            WHERE chat_id != 0
            ON CONFLICT(chat_id) DO NOTHING
        """)
        await db.execute("DELETE FROM market_state WHERE chat_id != 0")
        await db.execute("""
            INSERT INTO user_bonds (user_id, chat_id, bond_key, amount, invested)
            SELECT user_id, 0, bond_key, SUM(amount), SUM(invested)
            FROM user_bonds
            WHERE chat_id != 0
            GROUP BY user_id, bond_key
            ON CONFLICT(user_id, chat_id, bond_key) DO UPDATE
                SET amount   = user_bonds.amount   + EXCLUDED.amount,
                    invested = user_bonds.invested + EXCLUDED.invested
        """)
        await db.execute("DELETE FROM user_bonds WHERE chat_id != 0")
        await db.execute("""
            INSERT INTO user_bond_lots (user_id, chat_id, bond_key, quantity, price_per, bought_at)
            SELECT user_id, 0, bond_key, quantity, price_per, bought_at
            FROM user_bond_lots
            WHERE chat_id != 0
            ON CONFLICT DO NOTHING
        """)
        await db.execute("DELETE FROM user_bond_lots WHERE chat_id != 0")
        await db.execute("""
            INSERT INTO bond_price_history (chat_id, bond_key, price, recorded_at)
            SELECT 0, bond_key, price, recorded_at
            FROM bond_price_history
            WHERE chat_id != 0
            ON CONFLICT DO NOTHING
        """)
        await db.execute("DELETE FROM bond_price_history WHERE chat_id != 0")
        await db.commit()

        # Персональный ledger кошелька (зарплаты, админ-правки, доходы/расходы)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wallet_ledger (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                direction TEXT NOT NULL,
                amount INTEGER NOT NULL,
                source TEXT NOT NULL,
                description TEXT DEFAULT '',
                actor_id BIGINT DEFAULT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
        """)
        await db.execute(
            "DELETE FROM wallet_ledger WHERE created_at < NOW() - INTERVAL '60 days'"
        )

        # Журнал розыгрышей лотереи (персистентный guard, выживает перезапуск)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lottery_draws (
                week_key TEXT PRIMARY KEY
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS singles_bonus_log (
                week_key TEXT PRIMARY KEY
            )
        """)

        # Журнал выплат наград топ-10 по сообщениям (weekly)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS weekly_top_reward_log (
                chat_id  BIGINT  NOT NULL,
                week_key TEXT    NOT NULL,
                user_id  BIGINT  NOT NULL,
                place    INTEGER NOT NULL,
                amount   INTEGER NOT NULL,
                full_name TEXT   DEFAULT '',
                PRIMARY KEY (chat_id, week_key, user_id)
            )
        """)

        # ─── Новые таблицы (обновление v2: экспедиции, гача, банк, налоги, магазин, подарки, баффы) ────

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pet_expeditions (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                started_at  TIMESTAMPTZ NOT NULL,
                duration_h  INTEGER NOT NULL,
                reward_min  INTEGER NOT NULL,
                reward_max  INTEGER NOT NULL,
                finished    INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS gacha_inventory (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                item_key    TEXT    NOT NULL,
                item_name   TEXT    NOT NULL,
                rarity      TEXT    NOT NULL,
                obtained_at TIMESTAMPTZ NOT NULL,
                equipped    INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bank_deposits (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                amount      INTEGER NOT NULL,
                rate        REAL    NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL,
                matures_at  TIMESTAMPTZ NOT NULL,
                withdrawn   INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tax_events (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                message_id BIGINT,
                prize       INTEGER NOT NULL,
                penalty_pct REAL    DEFAULT 0.05,
                started_at  TIMESTAMPTZ NOT NULL,
                expires_at  TIMESTAMPTZ NOT NULL,
                finished    INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tax_event_clicks (
                event_id    INTEGER NOT NULL,
                user_id BIGINT NOT NULL,
                clicked_at  TIMESTAMPTZ NOT NULL,
                position    INTEGER NOT NULL,
                PRIMARY KEY (event_id, user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS shop_items (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                item_type    TEXT    NOT NULL,
                item_value   TEXT    NOT NULL,
                purchased_at TIMESTAMPTZ NOT NULL,
                active       INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS marriage_gifts (
                id SERIAL PRIMARY KEY,
                from_user   BIGINT NOT NULL,
                to_user     BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                gift_key    TEXT    NOT NULL,
                gift_name   TEXT    NOT NULL,
                gift_price  INTEGER NOT NULL,
                gifted_at   TIMESTAMPTZ NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS active_buffs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                buff_type   TEXT    NOT NULL,
                expires_at  TIMESTAMPTZ NOT NULL,
                source      TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS cleanup_passes (
                id SERIAL PRIMARY KEY,
                user_id    BIGINT NOT NULL,
                chat_id    BIGINT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'pending',
                price      INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                resolved_at TIMESTAMPTZ,
                resolved_by BIGINT
            )
        """)

        # ─── Миграция: новые колонки в user_mora ──────────────────────────
        for col_def in [
            "gacha_display TEXT DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_mora ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        # ─── Миграция: новые колонки в pets (косметика) ───────────────────
        for col_def in [
            "color_name   TEXT DEFAULT NULL",
            "emoji_status TEXT DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE pets ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        # ─── Темы профиля (какие куплены/получены и какая активна) ────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_themes (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                theme_key TEXT    NOT NULL,
                source    TEXT    NOT NULL DEFAULT 'shop',
                obtained_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (user_id, chat_id, theme_key)
            )
        """)

        # ─── Активная тема (у каждого юзера одна на чат) ──────────────────
        for col_def in [
            "active_theme TEXT DEFAULT 'default'",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_mora ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        # ─── Бейджи (значки) профиля ─────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_badges (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                badge_key TEXT    NOT NULL,
                obtained_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (user_id, chat_id, badge_key)
            )
        """)

        # ─── Личные приветствия ───────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_greetings (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                template_key TEXT    NOT NULL,
                source       TEXT    NOT NULL DEFAULT 'gacha',
                obtained_at  TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # ─── Богатый сундук (замена налогового ивента) ────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chest_events (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                message_id BIGINT,
                started_at  TIMESTAMPTZ NOT NULL,
                expires_at  TIMESTAMPTZ NOT NULL,
                finished    INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS chest_event_clicks (
                event_id    INTEGER NOT NULL,
                user_id BIGINT NOT NULL,
                clicked_at  TIMESTAMPTZ NOT NULL,
                position    INTEGER NOT NULL,
                reward      INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (event_id, user_id)
            )
        """)

        # ─── Трекинг для бейджей ─────────────────────────────────────────
        for col_def in [
            "expeditions_sent INTEGER DEFAULT 0",
            "chests_opened    INTEGER DEFAULT 0",
            "casino_wins      INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_mora ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        # ─── Рулетка: счётчик поражений подряд (пити-система) ────────────
        for col_def in [
            "roulette_losses INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_mora ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        # ─── Трекинг: юзер видел приветствие сегодня ──────────────────────
        for col_def in [
            "last_greeting_date TEXT DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        # ─── Ограничения пользователей (муты/ограниченные) ────────────────
        for col_def in [
            "restrict_until TIMESTAMPTZ DEFAULT NULL",
            "restrict_type  TEXT        DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        # Миграция: сделать баланс Моры видимым по умолчанию для всех
        await db.execute("UPDATE user_mora SET mora_public = 1 WHERE mora_public = 0")

        # ─── Переводы и долги ─────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS mora_loans (
                id SERIAL PRIMARY KEY,
                lender_id    BIGINT NOT NULL,
                borrower_id  BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                amount       INTEGER NOT NULL,
                loaned_at    TIMESTAMPTZ NOT NULL,
                repaid_at    TIMESTAMPTZ DEFAULT NULL
            )
        """)

        # ─── Облигации ────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bond_prices (
                bond_key     TEXT    NOT NULL,
                chat_id BIGINT NOT NULL DEFAULT 0,
                price        INTEGER NOT NULL,
                updated_at   TEXT    NOT NULL,
                PRIMARY KEY (bond_key, chat_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_bonds (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                bond_key     TEXT    NOT NULL,
                amount       INTEGER NOT NULL DEFAULT 0,
                invested     INTEGER NOT NULL DEFAULT 0,
                UNIQUE (user_id, chat_id, bond_key)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_bond_lots (
                id        SERIAL PRIMARY KEY,
                user_id   BIGINT NOT NULL,
                chat_id   BIGINT NOT NULL,
                bond_key  TEXT   NOT NULL,
                quantity  INTEGER NOT NULL,
                price_per INTEGER NOT NULL,
                bought_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ─── Лог шпионажа ─────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS espionage_log (
                id SERIAL PRIMARY KEY,
                spy_id       BIGINT NOT NULL,
                target_id    BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                success      INTEGER NOT NULL,
                attempted_at TIMESTAMPTZ NOT NULL
            )
        """)

        # ─── Казна чата ───────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_treasury (
                chat_id BIGINT PRIMARY KEY,
                balance   INTEGER DEFAULT 0
            )
        """)

        # ─── НДС-лог казны ────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS treasury_log (
                id         BIGSERIAL PRIMARY KEY,
                chat_id    BIGINT NOT NULL,
                user_id    BIGINT NOT NULL DEFAULT 0,
                amount     INTEGER NOT NULL,
                source     TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ─── Ежедневный чекин (стрики и чекпоинты) ───────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_checkin (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                streak       INTEGER DEFAULT 0,
                total_days   INTEGER DEFAULT 0,
                last_checkin TEXT    DEFAULT NULL,
                checkpoint   INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # ─── Урон по Боссу (лог + лидерборд) ────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS boss_damage_log (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                damage       INTEGER NOT NULL,
                session_date TEXT    NOT NULL
            )
        """)
        
        # ─── Парные Боссы (для пар в браке) ─────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS couple_boss_sessions (
                id SERIAL PRIMARY KEY,
                user_a_id      BIGINT NOT NULL,
                user_b_id      BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                boss_level     INTEGER DEFAULT 1,
                boss_max_hp    INTEGER NOT NULL,
                boss_current_hp INTEGER NOT NULL,
                user_a_damage  INTEGER DEFAULT 0,
                user_b_damage  INTEGER DEFAULT 0,
                user_a_hits    INTEGER DEFAULT 0,
                user_b_hits    INTEGER DEFAULT 0,
                user_a_aggro   INTEGER DEFAULT 0,
                user_b_aggro   INTEGER DEFAULT 0,
                is_completed   INTEGER DEFAULT 0,
                is_repeat      INTEGER DEFAULT 0,
                session_date   TEXT    NOT NULL,
                completed_at   TIMESTAMPTZ DEFAULT NULL,
                UNIQUE(user_a_id, user_b_id, chat_id, session_date)
            )
        """)
        
        # ─── Прогресс парных боссов (максимальный пройденный уровень) ─
        await db.execute("""
            CREATE TABLE IF NOT EXISTS couple_boss_progress (
                user_a_id      BIGINT NOT NULL,
                user_b_id      BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                max_level      INTEGER DEFAULT 0,
                last_completed TEXT    DEFAULT NULL,
                PRIMARY KEY (user_a_id, user_b_id, chat_id)
            )
        """)

        # ─── Предложения руки и сердца ────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS marriage_proposals (
                id           SERIAL PRIMARY KEY,
                from_user_id BIGINT NOT NULL,
                to_user_id   BIGINT NOT NULL,
                chat_id      BIGINT NOT NULL,
                status       TEXT   DEFAULT 'pending',
                created_at   TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(from_user_id, to_user_id, chat_id)
            )
        """)

        # ─── Одиночные боссы ─────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS solo_boss_sessions (
                id              SERIAL PRIMARY KEY,
                user_id         BIGINT NOT NULL,
                chat_id         BIGINT NOT NULL,
                boss_level      INTEGER DEFAULT 1,
                boss_max_hp     INTEGER NOT NULL,
                boss_current_hp INTEGER NOT NULL,
                user_damage     INTEGER DEFAULT 0,
                user_hits       INTEGER DEFAULT 0,
                is_completed    INTEGER DEFAULT 0,
                is_repeat       INTEGER DEFAULT 0,
                session_date    TEXT    NOT NULL,
                completed_at    TIMESTAMPTZ DEFAULT NULL,
                UNIQUE(user_id, chat_id, session_date)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS solo_boss_progress (
                user_id        BIGINT NOT NULL,
                chat_id        BIGINT NOT NULL,
                max_level      INTEGER DEFAULT 0,
                last_completed TEXT    DEFAULT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bond_price_history (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                bond_key    TEXT    NOT NULL,
                price       INTEGER NOT NULL,
                recorded_at TIMESTAMPTZ NOT NULL
            )
        """)

        # Market-wide trend state persisted across bot restarts
        await db.execute("""
            CREATE TABLE IF NOT EXISTS market_state (
                chat_id     BIGINT  PRIMARY KEY,
                trend       TEXT    NOT NULL DEFAULT 'neutral',
                ticks_left  INTEGER NOT NULL DEFAULT 0,
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_rpg_stats (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                base_hp     INTEGER DEFAULT 150,  -- РЕБАЛАНС: было 100
                base_atk    INTEGER DEFAULT 75,   -- РЕБАЛАНС: было 50
                base_def    INTEGER DEFAULT 30,   -- РЕБАЛАНС: было 20
                base_crit   REAL    DEFAULT 0.08, -- РЕБАЛАНС: было 0.05
                weapon_id   INTEGER DEFAULT NULL,
                armor_id    INTEGER DEFAULT NULL,
                artifact_id INTEGER DEFAULT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # ─── Миграция: РПГ-статы гача-предметов ──────────────────────────
        for col_def in [
            "atk       INTEGER DEFAULT 0",
            "def_val   INTEGER DEFAULT 0",
            "hp        INTEGER DEFAULT 0",
            "crit_rate REAL    DEFAULT 0.0",
            "slot      TEXT    DEFAULT NULL",
            "description TEXT  DEFAULT NULL",
            "enhancement_level INTEGER DEFAULT 0",
            "stack_count INTEGER DEFAULT 1",
        ]:
            try:
                await db.execute(f"ALTER TABLE gacha_inventory ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        # ─── Миграция: usталость питомца + время прогулки ──────────────────
        for col_def in ["fatigue INTEGER DEFAULT 0", "last_walked TIMESTAMPTZ DEFAULT NULL", "walk_end_at TIMESTAMPTZ DEFAULT NULL"]:
            try:
                await db.execute(f"ALTER TABLE pets ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        # ─── Миграция: исправить тип obtained_at если он был создан как TEXT ──
        try:
            await db.execute("""
                ALTER TABLE gacha_inventory
                ALTER COLUMN obtained_at TYPE TIMESTAMPTZ
                USING CASE
                    WHEN obtained_at ~ '^\\d{4}-\\d{2}-\\d{2}' THEN obtained_at::TIMESTAMPTZ
                    ELSE NOW()
                END
            """)
        except Exception:
            pass

        # ─── Миграция: исправить тип started_at в pet_expeditions если TEXT ──
        try:
            await db.execute("""
                ALTER TABLE pet_expeditions
                ALTER COLUMN started_at TYPE TIMESTAMPTZ
                USING CASE
                    WHEN started_at::text ~ '^\\d{4}-\\d{2}-\\d{2}' THEN started_at::text::TIMESTAMPTZ
                    ELSE NOW()
                END
            """)
        except Exception:
            pass

        # ─── Донаты в казну ───────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS treasury_donations (
                id         SERIAL PRIMARY KEY,
                user_id    BIGINT      NOT NULL,
                chat_id    BIGINT      NOT NULL,
                amount     INTEGER     NOT NULL,
                donated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ─── Глобальные бафы чата ─────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_global_buffs (
                id           SERIAL PRIMARY KEY,
                chat_id      BIGINT      NOT NULL,
                buff_type    TEXT        NOT NULL,
                activated_by BIGINT      NOT NULL,
                activated_at TIMESTAMPTZ NOT NULL,
                expires_at   TIMESTAMPTZ NOT NULL,
                UNIQUE (chat_id, buff_type)
            )
        """)

        # ─── Лог чат-пиров (анти-абуз: 1 пир в 12 часов) ─────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS feast_log (
                id           SERIAL PRIMARY KEY,
                chat_id      BIGINT      NOT NULL,
                triggered_by BIGINT      NOT NULL,
                cost         INTEGER     NOT NULL,
                recipients   INTEGER     NOT NULL,
                total_given  INTEGER     NOT NULL,
                triggered_at TIMESTAMPTZ NOT NULL
            )
        """)

        # Персистентное состояние планировщика (переживает перезапуски)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_state (
                task_key   TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ─── Аукцион ──────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auctions (
                id                SERIAL PRIMARY KEY,
                chat_id           BIGINT NOT NULL,
                seller_id         BIGINT NOT NULL,
                item_id           INTEGER NOT NULL,
                item_key          TEXT NOT NULL,
                item_name         TEXT NOT NULL,
                item_rarity       TEXT NOT NULL DEFAULT 'common',
                item_emoji        TEXT NOT NULL DEFAULT '🎴',
                start_price       INTEGER NOT NULL,
                current_price     INTEGER NOT NULL,
                buyout_price      INTEGER DEFAULT NULL,
                highest_bidder_id BIGINT DEFAULT NULL,
                bid_count         INTEGER DEFAULT 0,
                status            TEXT NOT NULL DEFAULT 'active',
                created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ends_at           TIMESTAMPTZ NOT NULL,
                finished_at       TIMESTAMPTZ DEFAULT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auction_bids (
                id          SERIAL PRIMARY KEY,
                auction_id  INTEGER NOT NULL,
                bidder_id   BIGINT NOT NULL,
                chat_id     BIGINT NOT NULL,
                amount      INTEGER NOT NULL,
                bid_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_auctions_status ON auctions(status, ends_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_auctions_seller ON auctions(seller_id, chat_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_auction_bids_aid ON auction_bids(auction_id)")

        # ─── Счётчики для системы достижений ──────────────────────────────
        for col_def in [
            "total_gacha_rolls INTEGER DEFAULT 0",
            "total_coinflip    INTEGER DEFAULT 0",
            "rep_given_count   INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_mora ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass

        # ─── Премиум-валюта Кристаллы (покупается за Telegram Stars) ────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_crystals (
                user_id         BIGINT  NOT NULL,
                balance         INTEGER NOT NULL DEFAULT 0,
                total_purchased INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id)
            )
        """)

        # ─── Конфигурация бота для каждого чата (multi-tenant) ───────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_configs (
                chat_id       BIGINT  PRIMARY KEY,
                display_name  TEXT    NOT NULL DEFAULT 'Предвестник',
                theme_pack    TEXT    NOT NULL DEFAULT 'default',
                currency_name TEXT    NOT NULL DEFAULT 'Мора',
                currency_emoji TEXT   NOT NULL DEFAULT '🪙',
                gacha_enabled INTEGER NOT NULL DEFAULT 1,
                casino_enabled INTEGER NOT NULL DEFAULT 1,
                boss_enabled   INTEGER NOT NULL DEFAULT 1,
                custom_config  TEXT    NOT NULL DEFAULT '{}',
                owner_user_id  BIGINT  DEFAULT NULL,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ─── Block 3: кастомные роли в чате за кристаллы ─────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS crystal_chat_roles (
                user_id     BIGINT NOT NULL,
                chat_id     BIGINT NOT NULL,
                role_text   TEXT   NOT NULL DEFAULT '',
                purchased_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # ─── Block 3: пропуска на аукционный перенос ──────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS crystal_transfer_passes (
                user_id  BIGINT NOT NULL PRIMARY KEY,
                passes   INTEGER NOT NULL DEFAULT 0
            )
        """)

        # ─── Block 3: свитки гаранта (×10 гача → guaranteed rare+) ────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS crystal_guarantee_scrolls (
                user_id  BIGINT NOT NULL PRIMARY KEY,
                scrolls  INTEGER NOT NULL DEFAULT 0
            )
        """)

        # ─── Block 3: камни улучшения за кристаллы ────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS crystal_enhancement_stones (
                user_id  BIGINT NOT NULL PRIMARY KEY,
                stones   INTEGER NOT NULL DEFAULT 0
            )
        """)

        # ─── Block 3: разблокированные аватары ────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS crystal_avatar_unlocks (
                user_id      BIGINT NOT NULL PRIMARY KEY,
                avatar_path  TEXT   DEFAULT NULL,
                unlocked_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ─── Block 4: Season Pass (Боевой Пропуск) ─────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seasons (
                id         SERIAL PRIMARY KEY,
                name       TEXT NOT NULL,
                start_date TIMESTAMPTZ NOT NULL,
                end_date   TIMESTAMPTZ NOT NULL,
                active     BOOLEAN DEFAULT TRUE
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS season_progress (
                user_id      BIGINT NOT NULL,
                season_id    INTEGER NOT NULL,
                season_xp    INTEGER NOT NULL DEFAULT 0,
                level        INTEGER NOT NULL DEFAULT 0,
                claimed_levels TEXT NOT NULL DEFAULT '[]',  -- JSON array of claimed level numbers
                premium_purchased BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (user_id, season_id),
                FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS season_rewards (
                season_id   INTEGER NOT NULL,
                level       INTEGER NOT NULL,
                is_premium  BOOLEAN NOT NULL DEFAULT FALSE,
                reward_type TEXT NOT NULL,  -- 'mora', 'crystals', 'item', 'title'
                reward_data TEXT NOT NULL,  -- amount or item_key or title text
                PRIMARY KEY (season_id, level, is_premium),
                FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
            )
        """)

        # ─── История покупок кристаллов за Stars ──────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stars_purchases (
                id              SERIAL PRIMARY KEY,
                user_id         BIGINT NOT NULL,
                stars_amount    INTEGER NOT NULL,
                crystals_amount INTEGER NOT NULL,
                pack_key        TEXT NOT NULL,
                telegram_charge_id TEXT DEFAULT NULL,
                purchased_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS app_error_logs (
                id          SERIAL PRIMARY KEY,
                source      TEXT NOT NULL DEFAULT 'backend',
                context     TEXT NOT NULL DEFAULT '',
                error_msg   TEXT NOT NULL DEFAULT '',
                traceback   TEXT NOT NULL DEFAULT '',
                user_id     BIGINT DEFAULT NULL,
                chat_id     BIGINT DEFAULT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ─── Динамическая конфигурация AF2 (настраивается через мини апп) ──────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS af2_config (
                chat_id BIGINT  NOT NULL DEFAULT 0,
                key     TEXT    NOT NULL,
                value   REAL    NOT NULL,
                PRIMARY KEY (chat_id, key)
            )
        """)

        # DDL соединение не поддерживает транзакции - commit() не нужен

    # PostgreSQL: widen all Telegram ID columns from int32 (INTEGER) → int64 (BIGINT).
    # Telegram supergroup/channel IDs like -1003xxxxxxxxx exceed int32 range.
    # Each ALTER runs in its own transaction so one failure doesn't abort the rest.
    from config import DATABASE_PATH
    # Всегда выполняем миграции для PostgreSQL (теперь единственная СУБД)
    _bigint_migrations = [
        ("users",             "user_id"),
        ("chat_settings",     "chat_id"),
        ("chats",             "chat_id"),
        ("notes",             "chat_id"),
        ("chat_filters",      "chat_id"),
        ("blacklist",         "chat_id"),
        ("locks",             "chat_id"),
        ("rep_log",           "from_uid"),
        ("rep_log",           "to_uid"),
        ("rep_log",           "chat_id"),
        ("cleanup_counts",    "chat_id"),
        ("cleanup_counts",    "user_id"),
        ("user_quests",       "user_id"),
        ("user_quests",       "chat_id"),
        ("user_achievements", "user_id"),
        ("polls",             "chat_id"),
        ("polls",             "message_id"),
        ("poll_votes",        "user_id"),
        ("birthdays",         "user_id"),
        ("marriages",         "user_id"),
        ("marriages",         "chat_id"),
        ("marriages",         "partner_id"),
        ("user_stats",        "user_id"),
        ("user_stats",        "chat_id"),
        ("rest_users",        "user_id"),
        ("rest_users",        "chat_id"),
        ("rest_users",        "added_by"),
        ("admin_groups",      "chat_id"),
        ("channel_types",     "chat_id"),
        ("user_roles",        "user_id"),
        ("leave_log",         "chat_id"),
        ("leave_log",         "user_id"),
        ("user_banlist",      "chat_id"),
        ("user_banlist",      "user_id"),
        ("user_banlist",      "added_by"),
        ("pending_roles",           "user_id"),
        ("pending_user_imports",   "chat_id"),
        ("pending_marriage_imports", "chat_id"),
        ("pets",              "user_id"),
        ("pets",              "chat_id"),
        ("user_mora",         "user_id"),
        ("user_mora",         "chat_id"),
        # Новые таблицы v2
        ("pet_expeditions",    "user_id"),
        ("pet_expeditions",    "chat_id"),
        ("gacha_inventory",    "user_id"),
        ("gacha_inventory",    "chat_id"),
        ("bank_deposits",      "user_id"),
        ("bank_deposits",      "chat_id"),
        ("tax_events",         "chat_id"),
        ("tax_events",         "message_id"),
        ("tax_event_clicks",   "user_id"),
        ("shop_items",         "user_id"),
        ("shop_items",         "chat_id"),
        ("marriage_gifts",     "from_user"),
        ("marriage_gifts",     "to_user"),
        ("marriage_gifts",     "chat_id"),
        ("active_buffs",       "user_id"),
        ("active_buffs",       "chat_id"),
        ("daily_checkin",      "user_id"),
        ("daily_checkin",      "chat_id"),
        ("boss_damage_log",    "user_id"),
        ("boss_damage_log",    "chat_id"),
        ("couple_boss_sessions", "user_a_id"),
        ("couple_boss_sessions", "user_b_id"),
        ("couple_boss_sessions", "chat_id"),
        ("couple_boss_progress", "user_a_id"),
        ("couple_boss_progress", "user_b_id"),
        ("couple_boss_progress", "chat_id"),
    ]
    for _tbl, _col in _bigint_migrations:
        try:
            async with postgres_connect() as db:
                await db.execute(
                    f"ALTER TABLE {_tbl} ALTER COLUMN {_col} TYPE BIGINT"
                )
        except Exception:
            pass

    # АF2: migrate af2_config to per-chat storage (add chat_id column + update PK)
    try:
        async with postgres_connect() as db:
            await db.execute("ALTER TABLE af2_config ADD COLUMN IF NOT EXISTS chat_id BIGINT DEFAULT 0")
            await db.commit()
    except Exception:
        pass
    try:
        async with postgres_connect() as db:
            await db.execute("UPDATE af2_config SET chat_id = 0 WHERE chat_id IS NULL")
            await db.commit()
    except Exception:
        pass
    try:
        async with postgres_connect() as db:
            await db.execute("ALTER TABLE af2_config DROP CONSTRAINT IF EXISTS af2_config_pkey")
            await db.execute("ALTER TABLE af2_config ADD PRIMARY KEY (chat_id, key)")
            await db.commit()
    except Exception:
        pass

    # Load isolation caches into memory
    await load_admin_groups()
    await load_test_chats()
    await load_chat_admin_links()
    
    # ═══════════════════════════════════════════════════════════════════════════════
    #  🔄 PostgreSQL TIMESTAMPTZ миграции для TEXT полей дат
    # ═══════════════════════════════════════════════════════════════════════════════
    
    _timestamptz_migrations = [
        # Round 1 (original)
        ("users",               "first_seen"),
        ("user_stats",          "first_active"),
        ("user_stats",          "last_active"),
        ("user_stats",          "inactivity_warned_at"),
        ("shop_items",          "purchased_at"),
        ("marriage_gifts",      "gifted_at"),
        ("user_themes",         "obtained_at"),
        ("user_badges",         "obtained_at"),
        ("bond_prices",         "updated_at"),
        ("couple_boss_sessions","completed_at"),
        ("bond_price_history",  "recorded_at"),
        ("mora_loans",          "loaned_at"),
        ("mora_loans",          "repaid_at"),
        ("pets",                "last_walked"),
        ("pets",                "walk_end_at"),
        # Round 2 — global audit: every table where datetime is passed as query param
        ("marriages_global",    "married_at"),
        ("rest_users",          "added_at"),
        ("user_achievements",   "earned_at"),
        ("rep_log",             "given_at"),
        ("community_roles",     "created_at"),
        ("leave_log",           "left_at"),
        ("user_banlist",        "added_at"),
        ("pending_roles",       "reserved_at"),
        ("chest_events",        "started_at"),
        ("chest_events",        "expires_at"),
        ("chest_event_clicks",  "clicked_at"),
        ("espionage_log",       "attempted_at"),
        ("active_buffs",        "expires_at"),
    ]
    
    for table, column in _timestamptz_migrations:
        try:
            async with postgres_connect() as db:
                await db.execute(f"""
                    ALTER TABLE {table} 
                    ALTER COLUMN {column} TYPE TIMESTAMPTZ 
                    USING CASE 
                        WHEN {column} IS NULL THEN NULL
                        ELSE {column}::TIMESTAMPTZ 
                    END
                """)
                await db.commit()
        except Exception as e:
            # Игнорируем ошибки миграций (колонка уже правильного типа, таблица не существует и т.д.)
            pass
    
    # Add status column to mora_loans if not present (pending/accepted/rejected flow)
    try:
        async with postgres_connect() as db:
            await db.execute(
                "ALTER TABLE mora_loans ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'accepted'"
            )
            await db.commit()
    except Exception:
        pass

    # ─── Блок 2: Глобальный инвентарь ─────────────────────────────────────────
    # Добавляем колонку acquired_at в gacha_inventory для 3-дневного правила аукциона
    # DEFAULT NOW() - INTERVAL '10 days' чтобы старые предметы сразу считались "достаточно старыми"
    try:
        async with postgres_connect() as db:
            await db.execute(
                "ALTER TABLE gacha_inventory ADD COLUMN IF NOT EXISTS "
                "acquired_at TIMESTAMPTZ DEFAULT NOW() - INTERVAL '10 days'"
            )
            # Для новых вставок acquired_at = obtained_at (они синонимы)
            await db.execute(
                "UPDATE gacha_inventory SET acquired_at = obtained_at WHERE acquired_at IS NULL OR acquired_at < NOW() - INTERVAL '11 days'"
            )
            await db.commit()
    except Exception:
        pass

    # ─── Блок 1: Глобальная архитектура (мора, брак, питомец) ─────────────────
    # Добавляем колонки глобального баланса в таблицу users
    for _col_def in ["balance BIGINT DEFAULT 0", "total_earned BIGINT DEFAULT 0"]:
        try:
            async with postgres_connect() as db:
                await db.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {_col_def}")
                await db.commit()
        except Exception:
            pass  # Колонка уже существует

    # Глобальный брак (1 на пользователя, не привязан к чату)
    try:
        async with postgres_connect() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS marriages_global (
                    user_id    BIGINT PRIMARY KEY,
                    partner_id BIGINT NOT NULL,
                    married_at TIMESTAMPTZ NOT NULL
                )
            """)
            await db.commit()
    except Exception:
        pass

    # Глобальный питомец (1 на пользователя, не привязан к чату)
    try:
        async with postgres_connect() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pets_global (
                    user_id      BIGINT PRIMARY KEY,
                    pet_type     TEXT    NOT NULL,
                    name         TEXT    DEFAULT NULL,
                    color_name   TEXT    DEFAULT NULL,
                    emoji_status TEXT    DEFAULT NULL,
                    fatigue      INTEGER DEFAULT 0,
                    walk_end_at  TIMESTAMPTZ DEFAULT NULL,
                    last_walked  TIMESTAMPTZ DEFAULT NULL,
                    adopted_at   TIMESTAMPTZ NOT NULL
                )
            """)
            await db.commit()
    except Exception:
        pass

    # Миграция: браки → marriages_global (idempotent, ON CONFLICT DO NOTHING)
    try:
        async with postgres_connect() as _db:
            await _db.execute("""
                INSERT INTO marriages_global (user_id, partner_id, married_at)
                SELECT DISTINCT ON (user_id) user_id, partner_id,
                       NULLIF(married_at, '')::TIMESTAMPTZ
                FROM marriages ORDER BY user_id, married_at DESC
                ON CONFLICT DO NOTHING
            """)
            await _db.commit()
    except Exception:
        pass

    # Миграция: питомцы → pets_global (idempotent, ON CONFLICT DO NOTHING)
    try:
        async with postgres_connect() as _db:
            await _db.execute("""
                INSERT INTO pets_global (user_id, pet_type, name, color_name, emoji_status,
                                         fatigue, walk_end_at, last_walked, adopted_at)
                SELECT DISTINCT ON (user_id)
                       user_id, pet_type, name, color_name, emoji_status,
                       COALESCE(fatigue, 0), walk_end_at, last_walked,
                       NULLIF(adopted_at, '')::TIMESTAMPTZ
                FROM pets ORDER BY user_id, adopted_at DESC
                ON CONFLICT DO NOTHING
            """)
            await _db.commit()
    except Exception:
        pass

    # Миграция: баланс моры user_mora → users.balance
    # Idempotent: только для юзеров у которых users.balance = 0 но есть мора в user_mora
    try:
        async with postgres_connect() as _db:
            await _db.execute("""
                UPDATE users SET
                    balance      = subq.total_balance,
                    total_earned = subq.total_earned
                FROM (
                    SELECT user_id,
                           SUM(balance)      AS total_balance,
                           SUM(total_earned) AS total_earned
                    FROM user_mora
                    GROUP BY user_id
                ) subq
                WHERE users.user_id = subq.user_id
                  AND COALESCE(users.balance, 0) = 0
                  AND subq.total_balance > 0
            """)
            await _db.commit()
    except Exception:
        pass

    # ─── Очередь событий от Mini App к боту ───────────────────────────────────
    try:
        async with postgres_connect() as _db:
            await _db.execute("""
                CREATE TABLE IF NOT EXISTS dev_event_queue (
                    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    chat_id      BIGINT NOT NULL,
                    event_type   TEXT NOT NULL,
                    requested_by BIGINT NOT NULL,
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    processed    INTEGER DEFAULT 0
                )
            """)
            await _db.commit()
    except Exception:
        pass

    # ─── 🅱️ Block 4: Season Pass seed data ──────────────────────────────────
    await seed_first_season()

    await enforce_rank_invariants()


async def enforce_rank_invariants():
    """Normalize rank data invariants:
    - developer: only DEVELOPER_ID (global)
    - owner: only one per chat (others downgraded to co_owner)
    """
    from config import DEVELOPER_ID

    async with postgres_connect() as db:
        if DEVELOPER_ID:
            await db.execute(
                "UPDATE user_stats SET rank = 'owner' WHERE rank = 'developer' AND user_id <> ?",
                (DEVELOPER_ID,),
            )
        else:
            await db.execute("UPDATE user_stats SET rank = 'owner' WHERE rank = 'developer'")

        async with db.execute(
            "SELECT chat_id, user_id FROM user_stats WHERE rank = 'owner' ORDER BY chat_id, user_id"
        ) as c:
            rows = await c.fetchall()

        seen_chat: set[int] = set()
        for row in rows:
            chat_id = row[0]
            user_id = row[1]
            if chat_id in seen_chat:
                await db.execute(
                    "UPDATE user_stats SET rank = 'co_owner' WHERE chat_id = ? AND user_id = ? AND rank = 'owner'",
                    (chat_id, user_id),
                )
            else:
                seen_chat.add(chat_id)

        await db.commit()


# ─── Admin groups (группы администрации) ──────────────────────────────────────

_admin_groups: set[int] = set()


async def load_admin_groups():
    global _admin_groups
    async with postgres_connect() as db:
        async with db.execute("SELECT chat_id FROM admin_groups") as c:
            rows = await c.fetchall()
    _admin_groups = {r[0] for r in rows}


async def get_admin_groups() -> list[int]:
    async with postgres_connect() as db:
        async with db.execute("SELECT chat_id FROM admin_groups") as c:
            return [r[0] for r in await c.fetchall()]


async def add_admin_group(chat_id: int):
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO admin_groups (chat_id) VALUES (?) ON CONFLICT (chat_id) DO NOTHING",
            (chat_id,),
        )
        await db.commit()
    _admin_groups.add(chat_id)


async def remove_admin_group(chat_id: int):
    async with postgres_connect() as db:
        await db.execute(
            "DELETE FROM admin_groups WHERE chat_id = ?", (chat_id,),
        )
        await db.commit()
    _admin_groups.discard(chat_id)


def get_admin_group_ids() -> set[int]:
    return _admin_groups


# ─── Test chats (тестовые чаты — изоляция от основной экономики) ──────────────
# Только DEVELOPER может назначать тестовые чаты.
# В тестовых чатах и в admin_groups полностью блокируются все экономические/игровые команды.

_test_chats: set[int] = set()


async def load_test_chats():
    """Load test chat ids from DB into the in-memory cache."""
    global _test_chats
    async with postgres_connect() as db:
        async with db.execute("SELECT chat_id FROM test_chats") as c:
            rows = await c.fetchall()
    _test_chats = {r[0] for r in rows}


def is_test_chat(chat_id: int) -> bool:
    """Sync check — True if this chat is marked as a test chat."""
    return chat_id in _test_chats


def get_test_chat_ids() -> set[int]:
    return _test_chats


async def add_test_chat(chat_id: int, set_by: int):
    """Mark a chat as a test chat (developer-only). Updates DB + cache."""
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO test_chats (chat_id, set_by) VALUES (?, ?) ON CONFLICT (chat_id) DO UPDATE SET set_by = EXCLUDED.set_by",
            (chat_id, set_by),
        )
        await db.commit()
    _test_chats.add(chat_id)


async def remove_test_chat(chat_id: int):
    """Unmark a test chat. Updates DB + cache."""
    async with postgres_connect() as db:
        await db.execute("DELETE FROM test_chats WHERE chat_id = ?", (chat_id,))
        await db.commit()
    _test_chats.discard(chat_id)


def is_isolated_chat(chat_id: int) -> bool:
    """Returns True if this chat is isolated from main economy.
    Includes admin_groups, test_chats, and community admin chats (via chat_admin_links)."""
    return chat_id in _admin_groups or chat_id in _test_chats or chat_id in _admin_chat_ids


async def is_isolated_chat_db(chat_id: int) -> bool:
    """DB-level check: True if chat is admin_group, test_chat, or community admin chat.

    Unlike ``is_isolated_chat`` this does NOT rely on in-memory caches
    and is safe to call from processes that never ran ``load_admin_groups``
    (e.g. the Django miniapp server).
    """
    if not chat_id:
        return False
    # Fast path: if caches were loaded, trust them
    if _admin_groups or _test_chats or _admin_chat_ids:
        return chat_id in _admin_groups or chat_id in _test_chats or chat_id in _admin_chat_ids
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT 1 FROM admin_groups WHERE chat_id=? "
            "UNION ALL "
            "SELECT 1 FROM test_chats WHERE chat_id=? "
            "UNION ALL "
            "SELECT 1 FROM chat_admin_links WHERE admin_chat_id=?",
            (chat_id, chat_id, chat_id),
        ) as c:
            return await c.fetchone() is not None


def get_chat_isolation_mode(chat_id: int) -> str | None:
    """Returns 'admin', 'community_admin', 'test', or None (= main chat)."""
    if chat_id in _test_chats:
        return "test"
    if chat_id in _admin_groups:
        return "admin"
    if chat_id in _admin_chat_ids:
        return "community_admin"
    return None


# ─── Chat → Admin-chat links (привязка чата к его чату-администрации) ─────────
# Уведомления из конкретного основного чата идут только в СВОЙ админ-чат.
# Если привязка не задана — используются глобальные admin_groups.

_chat_admin_links: dict[int, int] = {}  # main_chat_id -> admin_chat_id
_admin_chat_ids: set[int] = set()       # admin_chat_id values (community admin groups)


async def load_chat_admin_links():
    """Load chat→admin bindings from DB into memory cache."""
    global _chat_admin_links, _admin_chat_ids
    async with postgres_connect() as db:
        async with db.execute("SELECT main_chat_id, admin_chat_id FROM chat_admin_links") as c:
            rows = await c.fetchall()
    _chat_admin_links = {r[0]: r[1] for r in rows}
    _admin_chat_ids = set(_chat_admin_links.values())


async def set_chat_admin_link(main_chat_id: int, admin_chat_id: int):
    """Link a main chat to its admin chat. Upserts."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO chat_admin_links (main_chat_id, admin_chat_id)
               VALUES (?, ?)
               ON CONFLICT (main_chat_id) DO UPDATE SET admin_chat_id = EXCLUDED.admin_chat_id""",
            (main_chat_id, admin_chat_id),
        )
        await db.commit()
    _chat_admin_links[main_chat_id] = admin_chat_id
    _admin_chat_ids.add(admin_chat_id)


async def remove_chat_admin_link(main_chat_id: int):
    """Remove the admin-chat link for a main chat."""
    async with postgres_connect() as db:
        await db.execute(
            "DELETE FROM chat_admin_links WHERE main_chat_id = ?", (main_chat_id,)
        )
        await db.commit()
    _chat_admin_links.pop(main_chat_id, None)
    _admin_chat_ids.clear()
    _admin_chat_ids.update(_chat_admin_links.values())


def get_admin_chat_for(main_chat_id: int) -> int | None:
    """Sync lookup: returns admin_chat_id for a main chat, or None if not linked."""
    return _chat_admin_links.get(main_chat_id)


def get_all_chat_admin_links() -> dict[int, int]:
    """Returns a copy of all main→admin chat links."""
    return dict(_chat_admin_links)


def get_admin_chat_ids() -> set[int]:
    """Returns the set of all admin_chat_id values (community admin groups)."""
    return _admin_chat_ids


def get_main_chat_for(admin_chat_id: int) -> int | None:
    """Sync reverse lookup: returns main_chat_id for an admin chat, or None if not linked."""
    for main_id, adm_id in _chat_admin_links.items():
        if adm_id == admin_chat_id:
            return main_id
    return None


def is_community_admin_chat(chat_id: int) -> bool:
    """True if this chat is an admin group for some linked community."""
    return chat_id in _admin_chat_ids


# ─── Rest users (отдыхающие — защита от чистки) ──────────────────────────────

async def add_rest_user(user_id: int, chat_id: int, days: int, added_by: int):
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO rest_users (user_id, chat_id, days, added_at, added_by)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE
               SET days = excluded.days, added_at = excluded.added_at, added_by = excluded.added_by""",
            (user_id, chat_id, days, now, added_by),
        )
        await db.commit()


async def remove_rest_user(user_id: int, chat_id: int):
    async with postgres_connect() as db:
        await db.execute(
            "DELETE FROM rest_users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        await db.commit()


async def get_rest_users(chat_id: int):
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT r.user_id, r.days, r.added_at, r.added_by,
                      u.full_name, u.username
               FROM rest_users r
               JOIN users u ON u.user_id = r.user_id
               WHERE r.chat_id = ?""",
            (chat_id,),
        ) as c:
            return await c.fetchall()


async def is_on_rest(user_id: int, chat_id: int) -> bool:
    """Check if user is on rest and rest hasn't expired."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT days, added_at FROM rest_users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
    if not row:
        return False
    added = row["added_at"]
    if isinstance(added, str):
        added = datetime.fromisoformat(added)
    if added.tzinfo is None:
        added = added.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - added).days < row["days"]


async def get_resting_user_ids(chat_id: int) -> set[int]:
    """Return set of user_ids currently on active rest in this chat."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT user_id, days, added_at FROM rest_users WHERE chat_id = ?",
            (chat_id,),
        ) as c:
            rows = await c.fetchall()
    result: set[int] = set()
    now = datetime.now(timezone.utc)
    for r in rows:
        added = r["added_at"]
        if isinstance(added, str):
            added = datetime.fromisoformat(added)
        if added.tzinfo is None:
            added = added.replace(tzinfo=timezone.utc)
        if (now - added).days < r["days"]:
            result.add(r["user_id"])
    return result


async def get_rest_info_map(chat_id: int) -> dict[int, dict]:
    """Return {user_id: {'days': N, 'days_left': N, 'expires': datetime}} for active rest users."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT user_id, days, added_at FROM rest_users WHERE chat_id = ?",
            (chat_id,),
        ) as c:
            rows = await c.fetchall()
    result: dict[int, dict] = {}
    now = datetime.now(timezone.utc)
    for r in rows:
        added = r["added_at"]
        if isinstance(added, str):
            added = datetime.fromisoformat(added)
        if added.tzinfo is None:
            added = added.replace(tzinfo=timezone.utc)
        elapsed = (now - added).days
        if elapsed < r["days"]:
            expires = added + timedelta(days=r["days"])
            result[r["user_id"]] = {
                "days": r["days"],
                "days_left": r["days"] - elapsed,
                "expires": expires,
            }
    return result


async def set_newbie_shield(user_id: int, chat_id: int, days: int = 3) -> None:
    """Set newbie_shield_until = now + days IF it has not been set yet (idempotent)."""
    until = datetime.now(timezone.utc) + timedelta(days=days)
    async with postgres_connect() as db:
        await db.execute(
            """UPDATE user_stats
               SET newbie_shield_until = ?
               WHERE user_id = ? AND chat_id = ?
                 AND newbie_shield_until IS NULL""",
            (until, user_id, chat_id),
        )
        await db.commit()


async def get_shield_map(chat_id: int) -> dict[int, object]:
    """Return {user_id: newbie_shield_until} for all users whose shield is still active."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT user_id, newbie_shield_until
               FROM user_stats
               WHERE chat_id = ?
                 AND newbie_shield_until IS NOT NULL
                 AND newbie_shield_until > ?""",
            (chat_id, now),
        ) as c:
            rows = await c.fetchall()
    return {r["user_id"]: r["newbie_shield_until"] for r in rows}


# ─── Users ────────────────────────────────────────────────────────────────────

async def get_user(user_id: int):
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            return await cursor.fetchone()


async def get_user_by_username(username: str):
    uname = (username or "").strip().lstrip("@").lower()
    if not uname:
        return None
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM users WHERE LOWER(username) IN (?, ?)",
            (uname, f"@{uname}"),
        ) as cursor:
            return await cursor.fetchone()


async def upsert_user(user_id: int, username: str, full_name: str):
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, full_name, first_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username  = CASE WHEN excluded.username  != '' THEN excluded.username  ELSE users.username  END,
                full_name = CASE WHEN excluded.full_name != '' THEN excluded.full_name ELSE users.full_name END
            """,
            (user_id, username, full_name, now),
        )
        await db.commit()


async def import_users_bulk(records: list[dict], chat_id: int) -> dict:
    """
    Импортирует список пользователей в БД. Поддерживаемые форматы записей:
      • {user_id: int, message_count/messages: int, full_name?, username?}  → прямая запись
      • {username: "@foo", messages/message_count: int}                     → pending (применится при первом сообщении)
    Поддерживает также week_count, day_count, yesterday_count, last_week_count для cleanup_counts.
    Возвращает {'ok_direct': int, 'ok_pending': int, 'errors': list[str]}
    """
    now = datetime.now(timezone.utc)
    ok_direct = 0
    errors: list[str] = []
    pending_records: list[dict] = []

    # Pre-compute date keys for cleanup_counts period import
    from utils.helpers import bot_today as _bot_today
    from zoneinfo import ZoneInfo as _ZI
    _today    = _bot_today()
    _iso_wk   = datetime.now(_ZI("Europe/Zurich")).isocalendar()
    _week_key = f"{_iso_wk.year}-W{_iso_wk.week:02d}"

    async with postgres_connect() as db:
        for idx, rec in enumerate(records, 1):
            uid       = rec.get("user_id")
            uname_raw = (rec.get("username") or "").strip()
            msg_count = int(rec.get("message_count") or rec.get("messages") or 0)
            full_name = (rec.get("full_name") or "").strip()
            username  = uname_raw.lstrip("@")

            if uid and isinstance(uid, int):
                # Есть числовой user_id — пишем напрямую
                try:
                    await db.execute(
                        """
                        INSERT INTO users (user_id, username, full_name, first_seen)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET
                            username  = CASE WHEN excluded.username  != '' THEN excluded.username  ELSE users.username  END,
                            full_name = CASE WHEN excluded.full_name != '' THEN excluded.full_name ELSE users.full_name END
                        """,
                        (uid, username, full_name, now),
                    )
                    await db.execute(
                        """
                        INSERT INTO user_stats (user_id, chat_id, message_count)
                        VALUES (?, ?, ?)
                        ON CONFLICT(user_id, chat_id) DO UPDATE SET
                            message_count = GREATEST(user_stats.message_count, excluded.message_count)
                        """,
                        (uid, chat_id, msg_count),
                    )
                    # Also populate cleanup_counts with per-period counts from the JSON parser
                    _w  = int(rec.get("week_count")      or 0)
                    _d  = int(rec.get("day_count")        or 0)
                    _yd = int(rec.get("yesterday_count")  or 0)
                    _lw = int(rec.get("last_week_count")  or 0)
                    await db.execute(
                        """
                        INSERT INTO cleanup_counts
                            (chat_id, user_id, count, week_count, day_count,
                             week_start, day_start, last_week_count, yesterday_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(chat_id, user_id) DO UPDATE SET
                            count           = GREATEST(cleanup_counts.count, excluded.count),
                            week_count      = CASE WHEN ? > 0
                                                  THEN GREATEST(cleanup_counts.week_count, excluded.week_count)
                                                  ELSE cleanup_counts.week_count END,
                            week_start      = CASE WHEN ? > 0 THEN excluded.week_start
                                                  ELSE cleanup_counts.week_start END,
                            day_count       = CASE WHEN ? > 0
                                                  THEN GREATEST(cleanup_counts.day_count, excluded.day_count)
                                                  ELSE cleanup_counts.day_count END,
                            day_start       = CASE WHEN ? > 0 THEN excluded.day_start
                                                  ELSE cleanup_counts.day_start END,
                            last_week_count = CASE WHEN ? > 0
                                                  THEN GREATEST(cleanup_counts.last_week_count, excluded.last_week_count)
                                                  ELSE cleanup_counts.last_week_count END,
                            yesterday_count = CASE WHEN ? > 0
                                                  THEN GREATEST(cleanup_counts.yesterday_count, excluded.yesterday_count)
                                                  ELSE cleanup_counts.yesterday_count END
                        """,
                        (chat_id, uid, msg_count, _w, _d, _week_key, _today, _lw, _yd,
                         _w, _w, _d, _d, _lw, _yd),
                    )
                    ok_direct += 1
                except Exception as exc:
                    errors.append(f"#{idx} uid={uid}: {exc}")
            elif username:
                # Только username — откладываем до первого сообщения
                pending_records.append({"username": username, "messages": msg_count})
            else:
                errors.append(f"#{idx}: нет user_id и нет username")
        await db.commit()

    ok_pending = 0
    if pending_records:
        result = await store_pending_users(pending_records, chat_id)
        ok_pending = result["ok"]
        errors.extend(result["errors"])

    return {"ok_direct": ok_direct, "ok_pending": ok_pending, "errors": errors}


async def increment_message_count(user_id: int):
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE users SET message_count = message_count + 1 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


# ─── Pending imports ───────────────────────────────────────────────────────────────────────

async def store_pending_users(records: list[dict], chat_id: int) -> dict:
    """Хранит username-ключевые пендинг-записи для применения при первом сообщении."""
    ok_count = 0
    errors: list[str] = []
    async with postgres_connect() as db:
        for idx, rec in enumerate(records, 1):
            uname = (rec.get("username") or "").strip().lstrip("@").lower()
            if not uname:
                errors.append(f"#{idx}: нет username")
                continue
            msg_count = int(rec.get("messages") or rec.get("message_count") or 0)
            try:
                await db.execute(
                    """
                    INSERT INTO pending_user_imports (username, chat_id, message_count)
                    VALUES (?, ?, ?)
                    ON CONFLICT(username, chat_id) DO UPDATE SET
                        message_count = GREATEST(pending_user_imports.message_count, excluded.message_count)
                    """,
                    (uname, chat_id, msg_count),
                )
                ok_count += 1
            except Exception as exc:
                errors.append(f"#{idx} @{uname}: {exc}")
        await db.commit()
    return {"ok": ok_count, "errors": errors}


async def apply_pending_import(username: str, user_id: int, chat_id: int) -> bool:
    """Применяет pending message_count при первом сообщении юзера. Возвращает True если данные были применены."""
    uname_lower = username.strip().lstrip("@").lower()
    if not uname_lower:
        return False
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT message_count FROM pending_user_imports WHERE username=? AND chat_id=?",
            (uname_lower, chat_id),
        ) as c:
            row = await c.fetchone()
        if not row:
            return False
        pending_count = row[0] or 0
        # Записываем MAX(существующий, pending), чтобы не сбросить уже накопленные сообщения
        await db.execute(
            """
            INSERT INTO user_stats (user_id, chat_id, message_count)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
                message_count = GREATEST(user_stats.message_count, excluded.message_count)
            """,
            (user_id, chat_id, pending_count),
        )
        await db.execute(
            "DELETE FROM pending_user_imports WHERE username=? AND chat_id=?",
            (uname_lower, chat_id),
        )
        await db.commit()
    return True


async def store_pending_marriages(username1: str, username2: str, chat_id: int, married_at: str):
    """Хранит оба направления ожидающего брака (по username)."""
    u1 = username1.strip().lstrip("@").lower()
    u2 = username2.strip().lstrip("@").lower()
    async with postgres_connect() as db:
        for a, b in [(u1, u2), (u2, u1)]:
            await db.execute(
                """
                INSERT INTO pending_marriage_imports (username1, username2, chat_id, married_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(username1, chat_id) DO UPDATE SET
                    username2  = excluded.username2,
                    married_at = excluded.married_at
                """,
                (a, b, chat_id, married_at),
            )
        await db.commit()


async def apply_pending_marriages(username: str, user_id: int, chat_id: int):
    """Пытается создать ожидающие браки при первом сообщении юзера."""
    uname_lower = username.strip().lstrip("@").lower()
    if not uname_lower:
        return
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT username2, married_at FROM pending_marriage_imports WHERE username1=? AND chat_id=?",
            (uname_lower, chat_id),
        ) as c:
            rows = await c.fetchall()
        if not rows:
            return
        for row in rows:
            partner_uname = row["username2"]
            married_at    = row["married_at"]
            # Ищем партнёра в таблице users по username (регистрируется при первом сообщении)
            async with db.execute(
                "SELECT user_id FROM users WHERE LOWER(username)=?",
                (partner_uname,),
            ) as c2:
                partner_row = await c2.fetchone()
            if partner_row:
                partner_id = partner_row["user_id"]
                await db.execute(
                    "DELETE FROM marriages_global WHERE user_id=? OR user_id=?",
                    (user_id, partner_id),
                )
                await db.execute(
                    "INSERT INTO marriages_global (user_id, partner_id, married_at) VALUES (?,?,?) ON CONFLICT (user_id) DO NOTHING",
                    (user_id, partner_id, married_at),
                )
                await db.execute(
                    "INSERT INTO marriages_global (user_id, partner_id, married_at) VALUES (?,?,?) ON CONFLICT (user_id) DO NOTHING",
                    (partner_id, user_id, married_at),
                )
                for u in [uname_lower, partner_uname]:
                    await db.execute(
                        "DELETE FROM pending_marriage_imports WHERE chat_id=? AND username1=?",
                        (chat_id, u),
                    )
        await db.commit()


# ─── Chat Settings ────────────────────────────────────────────────────────────

async def upsert_chat(
    chat_id: int,
    title: str = "",
    username: str = "",
    chat_type: str = "private",
    is_active: int = 1,
):
    async with postgres_connect() as db:
        await db.execute(
            """
            INSERT INTO chats (chat_id, title, username, chat_type, is_active)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = excluded.title,
                username = excluded.username,
                chat_type = excluded.chat_type,
                is_active = excluded.is_active
            """,
            (chat_id, title or "", username or "", chat_type or "private", is_active),
        )
        await db.commit()


async def set_chat_active(chat_id: int, is_active: int):
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO chats (chat_id, is_active) VALUES (?, ?) ON CONFLICT (chat_id) DO NOTHING",
            (chat_id, is_active),
        )
        await db.execute(
            "UPDATE chats SET is_active = ? WHERE chat_id = ?",
            (is_active, chat_id),
        )
        await db.commit()


async def get_active_chats():
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM chats WHERE is_active = 1"
        ) as cursor:
            return await cursor.fetchall()


# ─── Simple TTL cache for chat_settings ──────────────────────────────────────
# Called on every Telegram message in the middleware — one DB round-trip per
# message was expensive.  We keep a 60-second in-memory cache per chat_id.
import time as _time
_chat_settings_cache: dict[int, tuple[float, object]] = {}
_CHAT_SETTINGS_TTL = 60.0  # seconds


def _invalidate_chat_settings(chat_id: int) -> None:
    """Drop the cached entry so the next read hits the DB."""
    _chat_settings_cache.pop(chat_id, None)


async def get_chat_settings(chat_id: int):
    now = _time.monotonic()
    cached = _chat_settings_cache.get(chat_id)
    if cached and now - cached[0] < _CHAT_SETTINGS_TTL:
        return cached[1]
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM chat_settings WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
    _chat_settings_cache[chat_id] = (now, row)
    return row


# ─── Допустимые колонки для защиты от SQL-инъекции ───────────────────────────
_ALLOWED_CHAT_SETTING_KEYS = {
    "welcome_text", "farewell_text", "rules_text",
    "antiflood_enabled", "antiflood_limit", "antiflood_action", "antiflood_window",
    "cleanup_threshold", "blacklist_enabled", "welcome_call",
    "social_tiktok", "social_youtube", "social_instagram",
    "cleanup_locked",
    "inactivity_warn_enabled", "inactivity_warn_days",
    "next_cleanup_at", "cleanup_reminder_sent",
    "cleanup_message_norm", "cleanup_warn_hours",
    # Feature Flags
    "feat_website", "feat_antispam", "feat_marriages",
    "feat_pets", "feat_casino", "feat_random_events",
}
_ALLOWED_LOCK_TYPES = {"links", "stickers", "gifs", "forwards", "voice", "video", "photo", "audio"}


async def set_chat_setting(chat_id: int, key: str, value):
    if key not in _ALLOWED_CHAT_SETTING_KEYS:
        raise ValueError(f"Invalid chat setting key: {key!r}")
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO chat_settings (chat_id) VALUES (?) ON CONFLICT (chat_id) DO NOTHING", (chat_id,)
        )
        await db.execute(
            f"UPDATE chat_settings SET {key} = ? WHERE chat_id = ?", (value, chat_id)
        )
        await db.commit()
    _invalidate_chat_settings(chat_id)


async def get_locked_chats() -> list[int]:
    """Return chat_ids where cleanup_locked=1 (чаты заблокированные чисткой)."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT chat_id FROM chat_settings WHERE cleanup_locked = 1"
        ) as c:
            return [r[0] for r in await c.fetchall()]


# ─── Notes ────────────────────────────────────────────────────────────────────

async def save_note(chat_id: int, name: str, content: str):
    async with postgres_connect() as db:
        await db.execute(
            """
            INSERT INTO notes (chat_id, name, content) VALUES (?, ?, ?)
            ON CONFLICT(chat_id, name) DO UPDATE SET content = excluded.content
            """,
            (chat_id, name.lower(), content),
        )
        await db.commit()


async def get_note(chat_id: int, name: str):
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM notes WHERE chat_id = ? AND name = ?",
            (chat_id, name.lower()),
        ) as cursor:
            return await cursor.fetchone()


async def list_notes(chat_id: int):
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT name FROM notes WHERE chat_id = ? ORDER BY name", (chat_id,)
        ) as cursor:
            return await cursor.fetchall()


async def delete_note(chat_id: int, name: str) -> bool:
    async with postgres_connect() as db:
        cursor = await db.execute(
            "DELETE FROM notes WHERE chat_id = ? AND name = ?",
            (chat_id, name.lower()),
        )
        await db.commit()
        return cursor.rowcount > 0


# ─── Filters ──────────────────────────────────────────────────────────────────

async def add_filter(chat_id: int, keyword: str, response: str):
    async with postgres_connect() as db:
        await db.execute(
            """
            INSERT INTO chat_filters (chat_id, keyword, response) VALUES (?, ?, ?)
            ON CONFLICT(chat_id, keyword) DO UPDATE SET response = excluded.response
            """,
            (chat_id, keyword.lower(), response),
        )
        await db.commit()


async def get_filters(chat_id: int):
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM chat_filters WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            return await cursor.fetchall()


async def delete_filter(chat_id: int, keyword: str) -> bool:
    async with postgres_connect() as db:
        cursor = await db.execute(
            "DELETE FROM chat_filters WHERE chat_id = ? AND keyword = ?",
            (chat_id, keyword.lower()),
        )
        await db.commit()
        return cursor.rowcount > 0


# ─── Blacklist ────────────────────────────────────────────────────────────────

async def add_blacklist_word(chat_id: int, word: str) -> bool:
    async with postgres_connect() as db:
        try:
            await db.execute(
                "INSERT INTO blacklist (chat_id, word) VALUES (?, ?)",
                (chat_id, word.lower()),
            )
            await db.commit()
            return True
        except asyncpg.UniqueViolationError:
            return False


async def remove_blacklist_word(chat_id: int, word: str) -> bool:
    async with postgres_connect() as db:
        cursor = await db.execute(
            "DELETE FROM blacklist WHERE chat_id = ? AND word = ?",
            (chat_id, word.lower()),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_blacklist(chat_id: int):
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT word FROM blacklist WHERE chat_id = ? ORDER BY word", (chat_id,)
        ) as cursor:
            return await cursor.fetchall()


# ─── Locks ────────────────────────────────────────────────────────────────────

async def get_locks(chat_id: int):
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM locks WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            return await cursor.fetchone()


async def set_lock(chat_id: int, lock_type: str, value: int):
    if lock_type not in _ALLOWED_LOCK_TYPES:
        raise ValueError(f"Invalid lock type: {lock_type!r}")
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO locks (chat_id) VALUES (?) ON CONFLICT (chat_id) DO NOTHING", (chat_id,)
        )
        await db.execute(
            f"UPDATE locks SET {lock_type} = ? WHERE chat_id = ?", (value, chat_id)
        )
        await db.commit()


# ─── Reputation ───────────────────────────────────────────────────────────────

async def get_rep_count_today(from_uid: int, to_uid: int, chat_id: int) -> int:
    """Сколько раз from_uid давал репутацию to_uid в чате за сегодня (UTC)."""
    today = datetime.now(timezone.utc).date().isoformat()  # "YYYY-MM-DD"
    cutoff = today + "T00:00:00"
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM rep_log WHERE from_uid=? AND to_uid=? AND chat_id=? AND given_at>=?",
            (from_uid, to_uid, chat_id, cutoff),
        ) as c:
            row = await c.fetchone()
            return row[0] if row else 0


async def can_give_rep(from_uid: int, to_uid: int, chat_id: int) -> bool:
    """Обратная совместимость: проверяет 2-часовой кулдаун (устарела, используй get_rep_count_today)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM rep_log WHERE from_uid=? AND to_uid=? AND chat_id=? AND given_at>?",
            (from_uid, to_uid, chat_id, cutoff),
        ) as c:
            row = await c.fetchone()
            return row[0] == 0




# ─── XP / Levels ──────────────────────────────────────────────────────────────

def xp_for_level(level: int) -> int:
    """Сколько XP нужно чтобы ДОСТИЧЬ этого уровня."""
    return level * (level - 1) * 100  # lv2=200, lv3=600, lv4=1200, lv5=2000...


def level_for_xp(xp: int) -> int:
    if xp < 0:
        xp = 0
    if xp < 200:
        return 1
    return max(1, int((1 + math.sqrt(1 + xp / 25)) / 2))


# Допустимые поля для developer-редактора (защита от SQL-инъекций)
_EDITABLE_USER_FIELDS = {
    "message_count", "xp", "level", "reputation", "warns",
    "bio", "custom_title", "is_banned",
}


async def set_user_stat(user_id: int, field: str, value) -> bool:
    """Developer-only: set any editable field on a user. Returns False if field not allowed."""
    if field not in _EDITABLE_USER_FIELDS:
        return False
    async with postgres_connect() as db:
        await db.execute(
            f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id)
        )
        await db.commit()
    return True


# ─── Cleanup counts ───────────────────────────────────────────────────────────

async def increment_cleanup_count(chat_id: int, user_id: int):
    from utils.helpers import bot_today as _bot_today
    from zoneinfo import ZoneInfo
    from datetime import datetime as _dt
    _ZURICH = ZoneInfo("Europe/Zurich")
    today    = _bot_today()
    iso      = _dt.now(_ZURICH).isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"

    async with postgres_connect() as db:
        # Single atomic upsert — eliminates the read-modify-write race condition
        # that caused ~42% message count loss under concurrent asyncio tasks.
        await db.execute(
            """
            INSERT INTO cleanup_counts
                (chat_id, user_id, count, week_count, day_count,
                 week_start, day_start, last_week_count, yesterday_count)
            VALUES (?, ?, 1, 1, 1, ?, ?, 0, 0)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                count           = cleanup_counts.count + 1,
                last_week_count = CASE WHEN cleanup_counts.week_start != ?
                                       THEN cleanup_counts.week_count
                                       ELSE cleanup_counts.last_week_count END,
                week_count      = CASE WHEN cleanup_counts.week_start != ?
                                       THEN 1
                                       ELSE cleanup_counts.week_count + 1 END,
                week_start      = CASE WHEN cleanup_counts.week_start != ?
                                       THEN ?
                                       ELSE cleanup_counts.week_start END,
                yesterday_count = CASE WHEN cleanup_counts.day_start != ?
                                       THEN cleanup_counts.day_count
                                       ELSE cleanup_counts.yesterday_count END,
                day_count       = CASE WHEN cleanup_counts.day_start != ?
                                       THEN 1
                                       ELSE cleanup_counts.day_count + 1 END,
                day_start       = CASE WHEN cleanup_counts.day_start != ?
                                       THEN ?
                                       ELSE cleanup_counts.day_start END
            """,
            (
                chat_id, user_id, week_key, today,
                # CASE params for week rollover (×3 uses of week_key + literal)
                week_key, week_key, week_key, week_key,
                # CASE params for day rollover (×3 uses of today + literal)
                today, today, today, today,
            ),
        )
        await db.commit()


async def get_activity_report(chat_id: int):
    """Все отслеживаемые участники чата с их счётчиками (всего / за неделю / за день)."""
    today    = date.today().isoformat()
    iso      = date.today().isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"

    async with postgres_connect() as db:
        async with db.execute(
            """
            SELECT u.user_id, u.full_name, u.username, COALESCE(us.rank, u.rank) AS rank,
                   COALESCE(cc.count, 0) AS total_count,
                   CASE WHEN cc.week_start = ? THEN COALESCE(cc.week_count, 0) ELSE 0 END AS week_count,
                   CASE WHEN cc.day_start  = ? THEN COALESCE(cc.day_count,  0) ELSE 0 END AS day_count,
                   us.first_active, us.last_active
            FROM cleanup_counts cc
            JOIN users u ON u.user_id = cc.user_id
            LEFT JOIN user_stats us ON us.user_id = cc.user_id AND us.chat_id = cc.chat_id
            WHERE cc.chat_id = ? AND COALESCE(us.is_banned, 0) = 0
            ORDER BY week_count DESC
            """,
            (week_key, today, chat_id),
        ) as c:
            return await c.fetchall()


async def get_inactive_users(chat_id: int, min_msgs: int):
    """Возвращает пользователей с кол-вом сообщений < min_msgs с момента последнего сброса."""
    async with postgres_connect() as db:
        async with db.execute(
            """
            SELECT u.user_id, u.full_name, u.username, COALESCE(us.rank, u.rank) AS rank, COALESCE(us.warns, u.warns) AS warns,
                   COALESCE(cc.count, 0) AS chat_count
            FROM cleanup_counts cc
            JOIN users u ON u.user_id = cc.user_id
            LEFT JOIN user_stats us ON us.user_id = cc.user_id AND us.chat_id = cc.chat_id
            WHERE cc.chat_id = ? AND cc.count < ?
              AND COALESCE(us.is_banned, 0) = 0
              AND COALESCE(us.rank, u.rank) NOT IN ('moderator','admin_junior','admin_senior','co_owner','owner','developer','helper','admin')
            ORDER BY cc.count ASC
            """,
            (chat_id, min_msgs),
        ) as c:
            return await c.fetchall()


async def reset_cleanup_counts(chat_id: int):
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE cleanup_counts SET count = 0 WHERE chat_id = ?", (chat_id,)
        )
        await db.commit()


# ─── Пропуск чистки ──────────────────────────────────────────────────────────

async def buy_cleanup_pass(user_id: int, chat_id: int, price: int) -> int:
    """Создать заявку на пропуск чистки. Возвращает id заявки."""
    from shared_prices import CLEANUP_PASS_COOLDOWN_DAYS
    now = datetime.now(timezone.utc)
    cooldown_cutoff = now - timedelta(days=CLEANUP_PASS_COOLDOWN_DAYS)
    async with postgres_connect() as db:
        # Проверяем, нет ли уже активного или pending пропуска
        async with db.execute(
            "SELECT id FROM cleanup_passes WHERE user_id=? AND chat_id=? AND status IN ('pending','approved')",
            (user_id, chat_id),
        ) as c:
            existing = await c.fetchone()
        if existing:
            raise ValueError("У тебя уже есть активный пропуск чистки")
        # Проверяем КД: любая покупка в этом чате за последние 12 дней
        async with db.execute(
            "SELECT created_at FROM cleanup_passes WHERE user_id=? AND chat_id=? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, chat_id),
        ) as c:
            last_row = await c.fetchone()
        if last_row:
            last_dt = last_row[0]
            if isinstance(last_dt, str):
                from datetime import datetime as _dt
                last_dt = _dt.fromisoformat(last_dt.replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            if last_dt >= cooldown_cutoff:
                remaining = last_dt + timedelta(days=CLEANUP_PASS_COOLDOWN_DAYS) - now
                remaining_days = max(1, remaining.days + (1 if remaining.seconds > 0 else 0))
                raise ValueError(
                    f"Пропуск чистки на кулдауне: следующая покупка доступна через {remaining_days} дн."
                )
        cursor = await db.execute(
            "INSERT INTO cleanup_passes (user_id, chat_id, status, price, created_at) "
            "VALUES (?,?,'pending',?,?) RETURNING id",
            (user_id, chat_id, price, now),
        )
        row = await cursor.fetchone()
        await db.commit()
        return row[0]


async def resolve_cleanup_pass(pass_id: int, action: str, resolved_by: int) -> dict | None:
    """Одобрить или отклонить заявку. Возвращает данные заявки или None."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM cleanup_passes WHERE id=? AND status='pending'",
            (pass_id,),
        ) as c:
            row = await c.fetchone()
        if not row:
            return None
        new_status = "approved" if action == "approve" else "rejected"
        await db.execute(
            "UPDATE cleanup_passes SET status=?, resolved_at=?, resolved_by=? WHERE id=?",
            (new_status, now, resolved_by, pass_id),
        )
        await db.commit()
        return dict(row)


async def has_cleanup_pass(user_id: int, chat_id: int) -> bool:
    """Есть ли у пользователя одобренный пропуск чистки."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT 1 FROM cleanup_passes WHERE user_id=? AND chat_id=? AND status='approved'",
            (user_id, chat_id),
        ) as c:
            return bool(await c.fetchone())


async def use_cleanup_pass(user_id: int, chat_id: int) -> bool:
    """Использовать пропуск (пометить как used). Возвращает True если был пропуск."""
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE cleanup_passes SET status='used' WHERE user_id=? AND chat_id=? AND status='approved'",
            (user_id, chat_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_pending_cleanup_passes(chat_id: int) -> list:
    """Все заявки со статусом pending в чате."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT cp.*, u.full_name FROM cleanup_passes cp "
            "LEFT JOIN users u ON u.user_id = cp.user_id "
            "WHERE cp.chat_id=? AND cp.status='pending' ORDER BY cp.created_at",
            (chat_id,),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


# ─── Quests ───────────────────────────────────────────────────────────────────

DAILY_QUESTS: list[dict] = [
    # messages
    {"type": "messages", "goal": 10, "xp": 30,  "mora": 3, "desc": "✍️ Написать 10 сообщений в чате"},
    {"type": "messages", "goal": 20, "xp": 50,  "mora": 5, "desc": "✍️ Написать 20 сообщений в чате"},
    {"type": "messages", "goal": 30, "xp": 70,  "mora": 7, "desc": "✍️ Написать 30 сообщений в чате"},
    {"type": "messages", "goal": 50, "xp": 120, "mora": 12, "desc": "✍️ Написать 50 сообщений в чате"},
    # rep
    {"type": "rep",      "goal": 2,  "xp": 60,  "mora": 5, "desc": "⭐ Выдать репутацию 2 раза"},
    {"type": "rep",      "goal": 3,  "xp": 75,  "mora": 7, "desc": "⭐ Выдать репутацию 3 раза"},
    {"type": "rep",      "goal": 5,  "xp": 100, "mora": 10, "desc": "⭐ Выдать репутацию 5 раз"},
    # coinflip
    {"type": "coinflip", "goal": 2,  "xp": 40,  "mora": 4, "desc": "🪙 Сыграть в монетку 2 раза"},
    {"type": "coinflip", "goal": 3,  "xp": 55,  "mora": 6, "desc": "🪙 Сыграть в монетку 3 раза"},
    {"type": "coinflip", "goal": 5,  "xp": 80,  "mora": 8, "desc": "🪙 Сыграть в монетку 5 раз"},
    # expedition
    {"type": "expedition", "goal": 1, "xp": 50, "mora": 5, "desc": "🗺 Отправить питомца в экспедицию"},
    {"type": "expedition", "goal": 2, "xp": 80, "mora": 8, "desc": "🗺 Отправить питомца в 2 экспедиции"},
    # gacha
    {"type": "gacha",   "goal": 1,  "xp": 45,  "mora": 4, "desc": "🎰 Крутануть гачу 1 раз"},
    {"type": "gacha",   "goal": 3,  "xp": 90,  "mora": 9, "desc": "🎰 Крутануть гачу 3 раза"},
    # gift
    {"type": "gift",    "goal": 1,  "xp": 60,  "mora": 6, "desc": "🎁 Отправить подарок"},
    {"type": "gift",    "goal": 2,  "xp": 90,  "mora": 9, "desc": "🎁 Отправить 2 подарка"},
    # mixed variety
    {"type": "messages", "goal": 40, "xp": 90,  "mora": 9, "desc": "✍️ Написать 40 сообщений в чате"},
    {"type": "rep",      "goal": 1,  "xp": 35,  "mora": 3, "desc": "⭐ Выдать репутацию 1 раз"},
]


def get_todays_quest(today_str: str | None = None) -> dict:
    """Возвращает задание для указанного дня (YYYY-MM-DD) или для сегодня по таймзоне бота."""
    if today_str is None:
        from utils.helpers import bot_today
        today_str = bot_today()
    d = date.fromisoformat(today_str)
    idx = d.toordinal() % len(DAILY_QUESTS)
    return DAILY_QUESTS[idx]


async def get_user_quest(user_id: int, chat_id: int, today_str: str) -> dict:
    """Return the user's actual quest for today (randomly assigned on first look, persisted)."""
    import random
    row = await get_quest_progress(user_id, chat_id, today_str)
    if row and row["quest_type"]:
        # Find matching quest in DAILY_QUESTS by type+goal
        for q in DAILY_QUESTS:
            if q["type"] == row["quest_type"] and q["goal"] == row["goal"]:
                return q
        # Fallback: build from stored data
        return {"type": row["quest_type"], "goal": row["goal"],
                "xp": 50, "mora": 5, "desc": f"Задание: {row['quest_type']}"}
    # No quest for today — assign a random one and persist it
    # Filter out marriage-only quests for single users
    from database.db import get_marriage
    marriage = await get_marriage(user_id, chat_id)
    MARRIAGE_QUEST_TYPES = {"gift", "expedition"}
    pool = [q for q in DAILY_QUESTS if marriage or q["type"] not in MARRIAGE_QUEST_TYPES]
    if not pool:
        pool = [q for q in DAILY_QUESTS if q["type"] == "messages"]
    new_quest = random.choice(pool)
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_quests
               (user_id, chat_id, quest_date, quest_type, goal, progress, completed, rewarded)
               VALUES (?,?,?,?,?,0,0,0)
               ON CONFLICT(user_id, chat_id, quest_date) DO NOTHING""",
            (user_id, chat_id, today_str, new_quest["type"], new_quest["goal"]),
        )
        await db.commit()
    return new_quest


async def reroll_user_quest(user_id: int, chat_id: int, quest_date: str) -> dict:
    """Delete old progress and assign a random DIFFERENT quest. Returns the new quest."""
    import random
    old_quest = await get_user_quest(user_id, chat_id, quest_date)
    # Filter out marriage-only quests for single users
    marriage = await get_marriage(user_id, chat_id)
    MARRIAGE_QUEST_TYPES = {"gift", "expedition"}
    candidates = [q for q in DAILY_QUESTS
                  if (q["type"] != old_quest["type"] or q["goal"] != old_quest["goal"])
                  and (marriage or q["type"] not in MARRIAGE_QUEST_TYPES)]
    if not candidates:
        candidates = [q for q in DAILY_QUESTS if q["type"] == "messages"]
    new_quest = random.choice(candidates)
    async with postgres_connect() as db:
        await db.execute(
            "DELETE FROM user_quests WHERE user_id=? AND chat_id=? AND quest_date=?",
            (user_id, chat_id, quest_date),
        )
        # Create fresh row with the new quest type/goal so it persists
        await db.execute(
            """INSERT INTO user_quests
               (user_id, chat_id, quest_date, quest_type, goal, progress, completed, rewarded)
               VALUES (?,?,?,?,?,0,0,0)""",
            (user_id, chat_id, quest_date, new_quest["type"], new_quest["goal"]),
        )
        await db.commit()
    return new_quest


async def get_quest_progress(user_id: int, chat_id: int, quest_date: str):
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM user_quests WHERE user_id=? AND chat_id=? AND quest_date=?",
            (user_id, chat_id, quest_date),
        ) as c:
            return await c.fetchone()


async def quest_tick(user_id: int, chat_id: int, quest_date: str, quest_type: str, goal: int) -> tuple[int, int, bool]:
    """Ticks progress +1. Returns (new_progress, goal, just_completed). Creates row on first call."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT progress, goal, completed FROM user_quests WHERE user_id=? AND chat_id=? AND quest_date=?",
            (user_id, chat_id, quest_date),
        ) as c:
            row = await c.fetchone()

        if row is None:
            new_progress = 1
            just_completed = new_progress >= goal
            await db.execute(
                """INSERT INTO user_quests (user_id, chat_id, quest_date, quest_type, goal, progress, completed) VALUES (?,?,?,?,?,?,?) ON CONFLICT DO NOTHING""",
                (user_id, chat_id, quest_date, quest_type, goal, new_progress, 1 if just_completed else 0),
            )
            await db.commit()
            return new_progress, goal, just_completed

        if row["completed"]:
            return row["progress"], row["goal"], False

        new_progress = row["progress"] + 1
        just_completed = new_progress >= row["goal"]
        await db.execute(
            "UPDATE user_quests SET progress=?, completed=? WHERE user_id=? AND chat_id=? AND quest_date=?",
            (new_progress, 1 if just_completed else 0, user_id, chat_id, quest_date),
        )
        await db.commit()
        return new_progress, row["goal"], just_completed


async def mark_quest_rewarded(user_id: int, chat_id: int, quest_date: str):
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE user_quests SET rewarded=1 WHERE user_id=? AND chat_id=? AND quest_date=?",
            (user_id, chat_id, quest_date),
        )
        await db.commit()

    # Block 4: Add season XP for quest completion
    try:
        season_result = await add_season_xp(user_id, 20)  # +20 season XP
        return season_result  # Return for potential level-up notification
    except Exception:
        return {"level_up": False, "new_level": 0}


# ─── Achievements ─────────────────────────────────────────────────────────────

async def get_achievements(user_id: int) -> list:
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT badge, earned_at FROM user_achievements WHERE user_id=? ORDER BY earned_at",
            (user_id,),
        ) as c:
            return await c.fetchall()


async def award_achievement(user_id: int, badge: str) -> bool:
    """Awards achievement. Returns True if newly awarded."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        try:
            await db.execute(
                "INSERT INTO user_achievements (user_id, badge, earned_at) VALUES (?,?,?)",
                (user_id, badge, now),
            )
            await db.commit()
            return True
        except asyncpg.UniqueViolationError:
            return False


# ─── Weekly / Daily top ───────────────────────────────────────────────────────

async def get_weekly_top(chat_id: int, limit: int = 10) -> list:
    from zoneinfo import ZoneInfo
    from datetime import datetime as _dt
    iso = _dt.now(ZoneInfo("Europe/Zurich")).isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT u.user_id, u.full_name, u.username,
                      CASE WHEN cc.week_start=? THEN COALESCE(cc.week_count,0) ELSE 0 END AS wc
               FROM cleanup_counts cc
               JOIN users u ON u.user_id=cc.user_id
               LEFT JOIN user_stats us ON us.user_id=cc.user_id AND us.chat_id=cc.chat_id
               WHERE cc.chat_id=? AND COALESCE(us.is_banned,0)=0
                 AND CASE WHEN cc.week_start=? THEN COALESCE(cc.week_count,0) ELSE 0 END >= 1
               ORDER BY wc DESC LIMIT ?""",
            (week_key, chat_id, week_key, limit),
        ) as c:
            return await c.fetchall()


async def get_daily_top(chat_id: int, limit: int = 10) -> list:
    from utils.helpers import bot_today as _bot_today
    today = _bot_today()
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT u.user_id, u.full_name, u.username,
                      CASE WHEN cc.day_start=? THEN COALESCE(cc.day_count,0) ELSE 0 END AS dc
               FROM cleanup_counts cc
               JOIN users u ON u.user_id=cc.user_id
               LEFT JOIN user_stats us ON us.user_id=cc.user_id AND us.chat_id=cc.chat_id
               WHERE cc.chat_id=? AND COALESCE(us.is_banned,0)=0
                 AND CASE WHEN cc.day_start=? THEN COALESCE(cc.day_count,0) ELSE 0 END >= 1
               ORDER BY dc DESC LIMIT ?""",
            (today, chat_id, today, limit),
        ) as c:
            return await c.fetchall()


async def get_prev_weekly_top(chat_id: int, limit: int = 10) -> list:
    """Top users for the previous calendar week.

    Uses snapshot columns (last_week_count / week_count) so that
    people who already wrote this week still appear correctly.
    """
    from zoneinfo import ZoneInfo
    from datetime import datetime as _dt
    _now = _dt.now(ZoneInfo("Europe/Zurich"))
    this_iso = _now.isocalendar()
    this_week_key = f"{this_iso.year}-W{this_iso.week:02d}"
    prev_iso  = (_now - timedelta(days=7)).isocalendar()
    prev_week_key = f"{prev_iso.year}-W{prev_iso.week:02d}"
    async with postgres_connect() as db:
        async with db.execute(
            # If the user already wrote THIS week → their last_week_count holds prev week
            # If the user hasn't written this week yet → week_start=prev_week, week_count is prev
            """SELECT u.user_id, u.full_name, u.username,
                      CASE
                        WHEN cc.week_start=? THEN COALESCE(cc.last_week_count,0)
                        WHEN cc.week_start=? THEN COALESCE(cc.week_count,0)
                        ELSE 0
                      END AS wc
               FROM cleanup_counts cc
               JOIN users u ON u.user_id=cc.user_id
               LEFT JOIN user_stats us ON us.user_id=cc.user_id AND us.chat_id=cc.chat_id
               WHERE cc.chat_id=? AND COALESCE(us.is_banned,0)=0
                 AND CASE
                       WHEN cc.week_start=? THEN COALESCE(cc.last_week_count,0)
                       WHEN cc.week_start=? THEN COALESCE(cc.week_count,0)
                       ELSE 0
                     END >= 1
               ORDER BY wc DESC LIMIT ?""",
            (this_week_key, prev_week_key, chat_id,
             this_week_key, prev_week_key, limit),
        ) as c:
            return await c.fetchall()


async def get_yesterday_top(chat_id: int, limit: int = 10) -> list:
    """Top users for yesterday.

    Uses snapshot columns so that people who already wrote TODAY still
    appear with their YESTERDAY count (stored in yesterday_count on rollover).
    """
    from utils.helpers import bot_today as _bot_today
    today     = _bot_today()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    async with postgres_connect() as db:
        async with db.execute(
            # If user wrote today → their yesterday_count is the snapshot from yesterday
            # If user hasn't written today → day_start=yesterday, day_count is yesterday's value
            """SELECT u.user_id, u.full_name, u.username,
                      CASE
                        WHEN cc.day_start=? THEN COALESCE(cc.yesterday_count,0)
                        WHEN cc.day_start=? THEN COALESCE(cc.day_count,0)
                        ELSE 0
                      END AS dc
               FROM cleanup_counts cc
               JOIN users u ON u.user_id=cc.user_id
               LEFT JOIN user_stats us ON us.user_id=cc.user_id AND us.chat_id=cc.chat_id
               WHERE cc.chat_id=? AND COALESCE(us.is_banned,0)=0
                 AND CASE
                       WHEN cc.day_start=? THEN COALESCE(cc.yesterday_count,0)
                       WHEN cc.day_start=? THEN COALESCE(cc.day_count,0)
                       ELSE 0
                     END >= 1
               ORDER BY dc DESC LIMIT ?""",
            (today, yesterday, chat_id, today, yesterday, limit),
        ) as c:
            return await c.fetchall()


async def get_user_activity(user_id: int, chat_id: int) -> dict:
    """Return per-user message counts: today, this week, all-time.

    'total' uses GREATEST(cleanup_counts.count, user_stats.message_count) so
    that historically-imported data in user_stats is not hidden.
    """
    from utils.helpers import bot_today as _bot_today
    from zoneinfo import ZoneInfo
    from datetime import datetime as _dt
    today = _bot_today()
    iso = _dt.now(ZoneInfo("Europe/Zurich")).isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT GREATEST(COALESCE(cc.count, 0),
                               COALESCE(us.message_count, 0)) AS total,
                      CASE WHEN cc.day_start=? THEN COALESCE(cc.day_count,0) ELSE 0 END AS today,
                      CASE WHEN cc.week_start=? THEN COALESCE(cc.week_count,0) ELSE 0 END AS week
               FROM cleanup_counts cc
               LEFT JOIN user_stats us ON us.user_id=cc.user_id AND us.chat_id=cc.chat_id
               WHERE cc.chat_id=? AND cc.user_id=?""",
            (today, week_key, chat_id, user_id),
        ) as c:
            row = await c.fetchone()
    if row:
        return {"today": row["today"], "week": row["week"], "total": row["total"]}
    # Fallback: no cleanup_counts row yet — try user_stats directly
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COALESCE(message_count,0) AS total FROM user_stats WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row2 = await c.fetchone()
    if row2:
        return {"today": 0, "week": 0, "total": row2["total"]}
    return {"today": 0, "week": 0, "total": 0}


async def get_chat_members(chat_id: int, ranks: list[str] | None = None) -> list:
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT DISTINCT u.user_id, u.full_name, u.username, COALESCE(us.rank, u.rank) AS rank
               FROM cleanup_counts cc
               JOIN users u ON u.user_id = cc.user_id
               LEFT JOIN user_stats us ON us.user_id = cc.user_id AND us.chat_id = cc.chat_id
               WHERE cc.chat_id = ? AND COALESCE(us.is_banned, 0) = 0
               ORDER BY u.full_name""",
            (chat_id,),
        ) as c:
            rows = await c.fetchall()
    if ranks is not None:
        rows = [r for r in rows if r["rank"] in ranks]
    return rows


# ─── Marriages ──────────────────────────────────────────────────────────────

async def get_marriage(user_id: int, chat_id: int):
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM marriages_global WHERE user_id=?",
            (user_id,),
        ) as c:
            return await c.fetchone()


async def create_marriage(user_a: int, user_b: int, chat_id: int):
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        await db.execute(
            "DELETE FROM marriages_global WHERE user_id=? OR user_id=?",
            (user_a, user_b),
        )
        await db.execute(
            "INSERT INTO marriages_global (user_id, partner_id, married_at) VALUES (?,?,?)",
            (user_a, user_b, now.isoformat()),
        )
        await db.execute(
            "INSERT INTO marriages_global (user_id, partner_id, married_at) VALUES (?,?,?)",
            (user_b, user_a, now.isoformat()),
        )
        await db.commit()
    # Marriage achievement for both partners (fire-and-forget)
    try:
        from api.achievements import check_and_award as _ach
        await _ach(user_a, chat_id, "married", 1)
        await _ach(user_b, chat_id, "married", 1)
    except Exception:
        pass


async def delete_marriage(user_id: int, chat_id: int):
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT partner_id FROM marriages_global WHERE user_id=?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        if row:
            partner_id = row[0]
            await db.execute(
                "DELETE FROM marriages_global WHERE user_id=? OR user_id=?",
                (user_id, partner_id),
            )
            await db.commit()


async def import_marriage_with_date(user_a: int, user_b: int, chat_id: int, married_at: str):
    """Создаёт/обновляет брак с указанной датой (для импорта из JSON)."""
    async with postgres_connect() as db:
        await db.execute(
            "DELETE FROM marriages_global WHERE user_id=? OR user_id=?",
            (user_a, user_b),
        )
        await db.execute(
            "INSERT INTO marriages_global (user_id, partner_id, married_at) VALUES (?,?,?)",
            (user_a, user_b, married_at),
        )
        await db.execute(
            "INSERT INTO marriages_global (user_id, partner_id, married_at) VALUES (?,?,?)",
            (user_b, user_a, married_at),
        )
        await db.commit()


async def get_migration_stats(chat_id: int) -> dict:
    """Возвращает статистику по данным в БД для данного чата (для команды бот скан)."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COUNT(*) AS cnt FROM user_stats WHERE chat_id=?", (chat_id,)
        ) as c:
            row = await c.fetchone()
            users_total = row["cnt"] if row else 0

        async with db.execute(
            "SELECT COUNT(*) AS cnt FROM user_stats WHERE chat_id=? AND message_count > 0",
            (chat_id,),
        ) as c:
            row = await c.fetchone()
            users_with_msgs = row["cnt"] if row else 0

        async with db.execute(
            "SELECT COALESCE(SUM(message_count), 0) AS total FROM user_stats WHERE chat_id=?",
            (chat_id,),
        ) as c:
            row = await c.fetchone()
            total_messages = row["total"] if row else 0

        async with db.execute(
            """SELECT COUNT(*) AS cnt FROM marriages_global mg
               WHERE mg.user_id IN (SELECT user_id FROM user_stats WHERE chat_id=?)""",
            (chat_id,)
        ) as c:
            row = await c.fetchone()
            marriages_rows = row["cnt"] if row else 0

        async with db.execute(
            """SELECT us.user_id, u.full_name, u.username, us.message_count
               FROM user_stats us
               LEFT JOIN users u ON u.user_id = us.user_id
               WHERE us.chat_id=? AND us.message_count > 0
               ORDER BY us.message_count DESC LIMIT 5""",
            (chat_id,),
        ) as c:
            top5 = await c.fetchall()

    return {
        "users_total": users_total,
        "users_with_msgs": users_with_msgs,
        "total_messages": total_messages,
        "marriages_pairs": marriages_rows // 2,
        "top5": [dict(r) for r in top5],
    }


# ─── Per-chat user stats ─────────────────────────────────────────────────────

async def get_user_stats(user_id: int, chat_id: int):
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM user_stats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ) as cursor:
            return await cursor.fetchone()


async def upsert_user_stats(user_id: int, chat_id: int):
    """Ensure a row exists in user_stats for this user+chat."""
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO user_stats (user_id, chat_id) VALUES (?, ?) ON CONFLICT (user_id, chat_id) DO NOTHING",
            (user_id, chat_id),
        )
        await db.commit()


async def increment_message_count_chat(user_id: int, chat_id: int) -> int:
    """Increment message count and return the new value."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_stats (user_id, chat_id, message_count, first_active, last_active)
               VALUES (?, ?, 1, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                   message_count = user_stats.message_count + 1,
                   first_active = COALESCE(user_stats.first_active, EXCLUDED.first_active),
                   last_active = EXCLUDED.last_active""",
            (user_id, chat_id, now, now),
        )
        await db.commit()
        async with db.execute(
            "SELECT message_count FROM user_stats WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
            return row[0] if row else 1


async def batch_increment_message_counts(counts: dict) -> None:
    """Batch-update message_count for multiple (user_id, chat_id) pairs.

    Uses PostgreSQL unnest() to perform a single UPDATE round-trip instead of
    one query per message — the core of the Phase-2 batch-write optimisation.

    counts: dict[(user_id, chat_id) → delta]
    """
    if not counts:
        return
    now = datetime.now(timezone.utc)
    user_ids: list[int] = []
    chat_ids: list[int] = []
    deltas: list[int]   = []
    for (uid, cid), delta in counts.items():
        user_ids.append(uid)
        chat_ids.append(cid)
        deltas.append(delta)
    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE user_stats
                  SET message_count = message_count + v.delta,
                      last_active   = $4::TIMESTAMPTZ
               FROM (SELECT unnest($1::bigint[])  AS user_id,
                            unnest($2::bigint[])  AS chat_id,
                            unnest($3::integer[]) AS delta) AS v
               WHERE user_stats.user_id = v.user_id
                 AND user_stats.chat_id = v.chat_id""",
            user_ids, chat_ids, deltas, now,
        )


async def set_rank_in_chat(user_id: int, chat_id: int, rank: str):
    from config import DEVELOPER_ID

    async with postgres_connect() as db:
        if rank == "developer":
            if not DEVELOPER_ID or user_id != DEVELOPER_ID:
                raise ValueError("Только указанный DEVELOPER_ID может иметь ранг developer.")
            await db.execute(
                "UPDATE user_stats SET rank = 'owner' WHERE rank = 'developer' AND user_id <> ?",
                (user_id,),
            )

        if rank == "owner":
            await db.execute(
                "UPDATE user_stats SET rank = 'co_owner' WHERE chat_id = ? AND rank = 'owner' AND user_id <> ?",
                (chat_id, user_id),
            )

        await db.execute(
            """INSERT INTO user_stats (user_id, chat_id, rank) VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET rank = excluded.rank""",
            (user_id, chat_id, rank),
        )
        await db.commit()


async def ban_user_in_chat(user_id: int, chat_id: int, reason: str = None):
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_stats (user_id, chat_id, is_banned, ban_reason) VALUES (?, ?, 1, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET is_banned = 1, ban_reason = excluded.ban_reason""",
            (user_id, chat_id, reason),
        )
        await db.commit()


async def unban_user_in_chat(user_id: int, chat_id: int):
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE user_stats SET is_banned = 0, ban_reason = NULL WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        await db.commit()


async def add_warn_in_chat(user_id: int, chat_id: int) -> int:
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_stats (user_id, chat_id, warns) VALUES (?, ?, 1)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET warns = user_stats.warns + 1""",
            (user_id, chat_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT warns FROM user_stats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def remove_warn_in_chat(user_id: int, chat_id: int) -> int:
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE user_stats SET warns = GREATEST(0, warns - 1) WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT warns FROM user_stats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_warned_users(chat_id: int) -> list[dict]:
    """Return all users with warns > 0 in the given chat."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT us.user_id, COALESCE(u.full_name, CAST(us.user_id AS TEXT)) AS full_name,
                      u.username, us.warns
               FROM user_stats us
               LEFT JOIN users u ON u.user_id = us.user_id
               WHERE us.chat_id = ? AND us.warns > 0
               ORDER BY us.warns DESC, us.user_id""",
            (chat_id,),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_staff_in_chat(chat_id: int):
    async with postgres_connect() as db:
        async with db.execute(
            """
            SELECT us.*, u.username, u.full_name
            FROM user_stats us
            JOIN users u ON u.user_id = us.user_id
            WHERE us.chat_id = ? AND us.rank NOT IN ('user', 'vip', 'helper')
            ORDER BY CASE us.rank
                WHEN 'developer'    THEN 6
                WHEN 'owner'        THEN 5
                WHEN 'co_owner'     THEN 4
                WHEN 'admin_senior' THEN 3
                WHEN 'admin_junior' THEN 2
                WHEN 'admin'        THEN 2
                WHEN 'moderator'    THEN 1
                WHEN 'helper'       THEN 1
                ELSE 0
            END DESC
            """,
            (chat_id,),
        ) as cursor:
            return await cursor.fetchall()


async def add_xp_in_chat(user_id: int, chat_id: int, amount: int) -> tuple[int, int, bool]:
    """Add XP in a specific chat. Returns (new_xp, new_level, leveled_up).

    Guard: if chat_id is an isolated chat, silently skip.
    """
    if is_isolated_chat(chat_id):
        _log.debug("add_xp_in_chat BLOCKED uid=%s chat=%s amount=%s (isolated)", user_id, chat_id, amount)
        # Return current values without modifying anything
        async with postgres_connect() as db:
            async with db.execute(
                "SELECT COALESCE(xp, 0), COALESCE(level, 1) FROM user_stats WHERE user_id=? AND chat_id=?",
                (user_id, chat_id),
            ) as c:
                row = await c.fetchone()
                return (row[0], row[1], False) if row else (0, 1, False)
    _log.debug("add_xp_in_chat uid=%s chat=%s amount=%+d", user_id, chat_id, amount)
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO user_stats (user_id, chat_id) VALUES (?, ?) ON CONFLICT (user_id, chat_id) DO NOTHING",
            (user_id, chat_id),
        )
        async with db.execute(
            "SELECT xp, level FROM user_stats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
        new_xp = (row[0] or 0) + amount
        old_level = row[1] or 1
        new_level = level_for_xp(new_xp)
        leveled_up = new_level > old_level
        await db.execute(
            "UPDATE user_stats SET xp = ?, level = ? WHERE user_id = ? AND chat_id = ?",
            (new_xp, new_level, user_id, chat_id),
        )
        await db.commit()
    _log.debug("add_xp_in_chat uid=%s chat=%s → xp=%d level=%d leveled_up=%s",
               user_id, chat_id, new_xp, new_level, leveled_up)
    return new_xp, new_level, leveled_up


# ─── Мора (внутричатовая валюта) ──────────────────────────────────────────────

async def get_mora(user_id: int, chat_id: int):
    """Returns mora info: global balance (users.balance) + per-chat fields (user_mora)."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT u.user_id, COALESCE(u.balance, 0) AS balance,
                      COALESCE(u.total_earned, 0) AS total_earned,
                      COALESCE(um.mora_public, 1) AS mora_public,
                      COALESCE(um.vip, 0) AS vip,
                      um.vip_expires_at, um.xp_boost_until, um.top_frame,
                      COALESCE(um.streak_days, 0) AS streak_days,
                      um.last_daily,
                      COALESCE(um.rep_given_count, 0) AS rep_given_count,
                      um.active_theme, um.gacha_display
               FROM users u
               LEFT JOIN user_mora um ON um.user_id = u.user_id AND um.chat_id = ?
               WHERE u.user_id = ?""",
            (chat_id, user_id),
        ) as c:
            return await c.fetchone()


async def get_mora_batch(user_ids: list[int], chat_id: int) -> dict[int, dict]:
    """Fetch global mora + per-chat data for multiple users. Returns dict user_id → dict."""
    if not user_ids:
        return {}
    placeholders = ",".join("?" * len(user_ids))
    async with postgres_connect() as db:
        async with db.execute(
            f"""SELECT u.user_id, COALESCE(u.balance, 0) AS balance,
                        COALESCE(u.total_earned, 0) AS total_earned,
                        COALESCE(um.mora_public, 1) AS mora_public,
                        COALESCE(um.vip, 0) AS vip,
                        um.vip_expires_at, um.xp_boost_until, um.top_frame,
                        COALESCE(um.streak_days, 0) AS streak_days,
                        um.last_daily,
                        COALESCE(um.rep_given_count, 0) AS rep_given_count
                FROM users u
                LEFT JOIN user_mora um ON um.user_id = u.user_id AND um.chat_id = ?
                WHERE u.user_id IN ({placeholders})""",
            (chat_id, *user_ids),
        ) as c:
            rows = await c.fetchall()
    return {row["user_id"]: dict(row) for row in rows}


async def add_mora(user_id: int, chat_id: int, amount: int) -> int:
    """Add (or subtract) Мора globally. Balance never goes below 0. Returns new balance.

    Guard: if chat_id is an isolated chat (admin group / test chat), this is a no-op.
    This is the final safety net — no code path can bypass it.
    Pass chat_id=0 for purely global rewards (e.g. season rewards).
    """
    if chat_id and is_isolated_chat(chat_id):
        # Silently skip — return current balance without modifying it
        _log.debug("add_mora BLOCKED uid=%s chat=%s amount=%s (isolated)", user_id, chat_id, amount)
        async with postgres_connect() as db:
            async with db.execute(
                "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?", (user_id,)
            ) as c:
                row = await c.fetchone()
                return row[0] if row else 0
    _log.debug("add_mora uid=%s chat=%s amount=%+d", user_id, chat_id, amount)
    async with postgres_connect() as db:
        await db.execute(
            """UPDATE users SET
                   balance      = GREATEST(0, COALESCE(balance, 0) + ?),
                   total_earned = COALESCE(total_earned, 0) + CASE WHEN ? > 0 THEN ? ELSE 0 END
               WHERE user_id = ?""",
            (amount, amount, amount, user_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
            new_bal = row[0] if row else 0
    _log.debug("add_mora uid=%s → balance=%d", user_id, new_bal)
    return new_bal


async def check_daily_mora(user_id: int, chat_id: int) -> tuple[bool, int, bool]:
    """
    Check if this is the first message today for Мора purposes.
    Updates streak and last_daily. Returns (is_first_daily, new_streak, streak_7day_bonus).
    """
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT last_daily, streak_days FROM user_mora WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()

        if row is None:
            await db.execute(
                """INSERT INTO user_mora (user_id, chat_id, last_daily, streak_days) VALUES (?, ?, ?, 1) ON CONFLICT DO NOTHING""",
                (user_id, chat_id, today),
            )
            await db.commit()
            return True, 1, False

        last_daily = row["last_daily"]
        streak = row["streak_days"] or 0

        if last_daily == today:
            return False, streak, False

        if last_daily == yesterday:
            new_streak = streak + 1
        else:
            new_streak = 1  # Streak broken

        streak_bonus = (new_streak == 7)
        if new_streak > 7:
            new_streak = 0  # Reset after claiming 7-day bonus

        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, last_daily, streak_days)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                   last_daily  = excluded.last_daily,
                   streak_days = excluded.streak_days""",
            (user_id, chat_id, today, new_streak),
        )
        await db.commit()
        return True, new_streak, streak_bonus


async def set_mora_public(user_id: int, chat_id: int, public: int):
    """Set whether this user's Мора balance is visible to others in this chat."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, mora_public)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET mora_public = excluded.mora_public""",
            (user_id, chat_id, public),
        )
        await db.commit()


async def deduct_mora(user_id: int, chat_id: int, amount: int) -> tuple[bool, int]:
    """Deduct Мора globally if balance is sufficient. Atomic UPDATE prevents race conditions."""
    async with postgres_connect() as db:
        cursor = await db.execute(
            """UPDATE users
               SET balance = balance - ?
               WHERE user_id = ? AND COALESCE(balance, 0) >= ?""",
            (amount, user_id, amount),
        )
        if cursor.rowcount == 0:
            async with db.execute(
                "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            return False, (row[0] if row else 0)
        await db.commit()
        async with db.execute(
            "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        return True, (row[0] if row else 0)


async def get_vip(user_id: int, chat_id: int) -> int:
    """Returns 1 if user has active (non-expired) VIP in this chat, else 0."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT vip, vip_expires_at FROM user_mora WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
    if not row or not (row["vip"] or 0):
        return 0
    exp = row["vip_expires_at"]
    if exp is not None and exp < datetime.now(timezone.utc):
        return 0  # expired  but not yet cleaned up
    return 1


async def set_vip(user_id: int, chat_id: int, value: int):
    """Set VIP status for user in chat. Enabling VIP sets a 30-day expiry."""
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)) if value else None
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, vip, vip_expires_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE
               SET vip = excluded.vip, vip_expires_at = excluded.vip_expires_at""",
            (user_id, chat_id, value, expires_at),
        )
        await db.commit()


async def get_xp_boost_active(user_id: int, chat_id: int) -> bool:
    """Returns True if user has an active XP boost right now."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT xp_boost_until FROM user_mora WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
    if not row or not row["xp_boost_until"]:
        return False
    try:
        until = row["xp_boost_until"]
        if isinstance(until, str):
            until = datetime.fromisoformat(until)
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < until
    except Exception:
        return False


async def set_xp_boost(user_id: int, chat_id: int, until_iso: str):
    """Set XP boost expiry for user."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, xp_boost_until) VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET xp_boost_until = excluded.xp_boost_until""",
            (user_id, chat_id, until_iso),
        )
        await db.commit()


async def get_top_frame(user_id: int, chat_id: int) -> str | None:
    """Returns the active top frame key for user, or None."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT top_frame FROM user_mora WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
    return row["top_frame"] if row else None


async def set_top_frame(user_id: int, chat_id: int, frame: str | None):
    """Set top frame for user."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, top_frame) VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET top_frame = excluded.top_frame""",
            (user_id, chat_id, frame),
        )
        await db.commit()


# ─── Казино ───────────────────────────────────────────────────────────────────

async def create_duel(chat_id: int, challenger_id: int, target_id: int, bet: int, msg_id: int) -> int:
    """Create a pending dice duel. Returns duel id."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        cursor = await db.execute(
            """INSERT INTO casino_duels (chat_id, challenger_id, target_id, bet, status, msg_id, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?, ?) RETURNING id""",
            (chat_id, challenger_id, target_id, bet, msg_id, now),
        )
        row = await cursor.fetchone()
        await db.commit()
        return row[0] if row else cursor.lastrowid


async def get_duel(duel_id: int):
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM casino_duels WHERE id=?", (duel_id,)
        ) as c:
            return await c.fetchone()


async def set_duel_status(duel_id: int, status: str):
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE casino_duels SET status=? WHERE id=?",
            (status, duel_id),
        )
        await db.commit()


async def cancel_expired_duels():
    """Cancel duels older than 5 minutes that are still pending."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE casino_duels SET status='expired' WHERE status='pending' AND created_at < ?",
            (cutoff,),
        )
        await db.commit()


async def get_pending_duels_for_chat(chat_id: int, challenger_id: int) -> list:
    """Return pending duels by this challenger in this chat (to prevent spam)."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM casino_duels WHERE chat_id=? AND challenger_id=? AND status='pending'",
            (chat_id, challenger_id),
        ) as c:
            return await c.fetchall()


async def buy_lottery_ticket(chat_id: int, user_id: int, week_key: str):
    """Buy one lottery ticket for this week. Returns new ticket count."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO casino_lottery (chat_id, user_id, week_key, tickets)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(chat_id, user_id, week_key) DO UPDATE SET
                   tickets = casino_lottery.tickets + 1""",
            (chat_id, user_id, week_key),
        )
        await db.commit()
        async with db.execute(
            "SELECT tickets FROM casino_lottery WHERE chat_id=? AND user_id=? AND week_key=?",
            (chat_id, user_id, week_key),
        ) as c:
            row = await c.fetchone()
        return row["tickets"] if row else 1


async def get_lottery_tickets(chat_id: int, user_id: int, week_key: str) -> int:
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT tickets FROM casino_lottery WHERE chat_id=? AND user_id=? AND week_key=?",
            (chat_id, user_id, week_key),
        ) as c:
            row = await c.fetchone()
    return (row["tickets"] or 0) if row else 0


async def get_all_lottery_participants(chat_id: int, week_key: str) -> list:
    """Return all (user_id, tickets) rows for this chat and week."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT user_id, tickets FROM casino_lottery WHERE chat_id=? AND week_key=?",
            (chat_id, week_key),
        ) as c:
            return await c.fetchall()


async def get_all_lottery_chats_week(week_key: str) -> list[int]:
    """Return distinct chat_ids that have tickets for this week."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT DISTINCT chat_id FROM casino_lottery WHERE week_key=?",
            (week_key,),
        ) as c:
            return [r[0] for r in await c.fetchall()]


# ─── Семейный кошелёк ─────────────────────────────────────────────────────────

async def get_family_wallet(chat_id: int, user_id: int) -> int:
    """Returns the shared family wallet balance, or 0 if not found.
    Семейный кошелёк ГЛОБАЛЕН (брак един на все чаты) — chat_id игнорируется."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT balance FROM family_wallet WHERE chat_id=0 AND user_id=?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
    return (row["balance"] or 0) if row else 0


async def add_to_family_wallet(chat_id: int, user_id: int, amount: int) -> int:
    """Add or subtract from family wallet. Returns new balance.
    Семейный кошелёк ГЛОБАЛЕН (брак един на все чаты) — chat_id игнорируется."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO family_wallet (chat_id, user_id, balance)
               VALUES (0, ?, GREATEST(0, ?))
               ON CONFLICT(chat_id, user_id) DO UPDATE SET
                   balance = GREATEST(0, family_wallet.balance + ?)""",
            (user_id, amount, amount),
        )
        await db.commit()
        async with db.execute(
            "SELECT balance FROM family_wallet WHERE chat_id=0 AND user_id=?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        return (row["balance"] or 0) if row else 0


# ──────────────────────────────────────────────────────────────────────────────
# ЕДИНЫЙ СЕРВИСНЫЙ СЛОЙ — СЕМЕЙНЫЙ КОШЕЛЁК
# Брак — это ОБЩИЕ деньги. Каждый член пары может тратить ВЕСЬ семейный баланс.
# ──────────────────────────────────────────────────────────────────────────────

async def get_total_family_balance(chat_id: int, user_id: int) -> tuple[int, int, int | None]:
    """Returns (total_balance, my_balance, partner_id).
    total_balance = сумма вкладов обоих партнёров.
    partner_id = None если брак не найден.
    Семейный кошелёк ГЛОБАЛЕН — chat_id игнорируется."""
    async with postgres_connect() as db:
        # Получаем partner_id из глобальной таблицы браков
        async with db.execute(
            "SELECT partner_id FROM marriages_global WHERE user_id=?",
            (user_id,),
        ) as c:
            marriage = await c.fetchone()

        partner_id: int | None = marriage["partner_id"] if marriage else None

        async with db.execute(
            "SELECT balance FROM family_wallet WHERE chat_id=0 AND user_id=?",
            (user_id,),
        ) as c:
            my_row = await c.fetchone()
        my_balance = (my_row["balance"] or 0) if my_row else 0

        partner_balance = 0
        if partner_id:
            async with db.execute(
                "SELECT balance FROM family_wallet WHERE chat_id=0 AND user_id=?",
                (partner_id,),
            ) as c:
                p_row = await c.fetchone()
            partner_balance = (p_row["balance"] or 0) if p_row else 0

    return my_balance + partner_balance, my_balance, partner_id


async def deduct_family_pool(
    chat_id: int, user_id: int, partner_id: int | None, amount: int
) -> int:
    """Списать amount из семейного пула (вклад обоих партнёров).
    Сначала списывает с вклада user_id, затем — с вклада partner_id.
    Возвращает новый суммарный баланс.
    Атомарная операция: FOR UPDATE блокирует строки на время транзакции.
    Семейный кошелёк ГЛОБАЛЕН — chat_id игнорируется."""
    async with postgres_connect() as db:

        # Блокируем строки обоих партнёров FOR UPDATE — защита от параллельных снятий
        uids = [user_id] + ([partner_id] if partner_id else [])
        placeholders = ",".join("?" for _ in uids)
        async with db.execute(
            f"SELECT user_id, balance FROM family_wallet "
            f"WHERE chat_id=0 AND user_id IN ({placeholders}) FOR UPDATE",
            (*uids,),
        ) as c:
            rows = await c.fetchall()

        bal_map = {r["user_id"]: (r["balance"] or 0) for r in rows}
        my_bal = bal_map.get(user_id, 0)
        total_available = sum(bal_map.values())

        if total_available < amount:
            raise ValueError(f"В семейном кошельке {total_available} 🪙 (нужно {amount})")

        if my_bal >= amount:
            # Всё списывается с моего вклада
            await db.execute(
                "UPDATE family_wallet SET balance=balance-? WHERE chat_id=0 AND user_id=?",
                (amount, user_id),
            )
        elif partner_id:
            # Списываем полностью мой вклад, остаток — с партнёра
            rest = amount - my_bal
            await db.execute(
                "UPDATE family_wallet SET balance=0 WHERE chat_id=0 AND user_id=?",
                (user_id,),
            )
            await db.execute(
                "UPDATE family_wallet SET balance=GREATEST(0,balance-?) WHERE chat_id=0 AND user_id=?",
                (rest, partner_id),
            )

        await db.commit()

        # Суммируем оба остатка
        total = 0
        for uid_check in uids:
            async with db.execute(
                "SELECT balance FROM family_wallet WHERE chat_id=0 AND user_id=?",
                (uid_check,),
            ) as c:
                row = await c.fetchone()
            total += (row["balance"] or 0) if row else 0

    return total


async def log_family_transaction(
    chat_id: int, user_id: int, action: str, amount: int, description: str = ""
) -> None:
    """Записать транзакцию в журнал семейного кошелька.
    action: 'deposit' | 'withdraw' | 'purchase'
    Семейный кошелёк ГЛОБАЛЕН — chat_id игнорируется (хранится как 0)."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO family_wallet_log (chat_id, user_id, action, amount, description, created_at) "
            "VALUES (0,?,?,?,?,?)",
            (user_id, action, amount, description, now),
        )
        await db.commit()


async def get_family_wallet_log(chat_id: int, uid: int, partner_id: int | None, limit: int = 30) -> list:
    """Последние транзакции семейного кошелька для конкретной пары (uid + partner_id).
    Семейный кошелёк ГЛОБАЛЕН — chat_id игнорируется."""
    async with postgres_connect() as db:
        if partner_id and partner_id != uid:
            async with db.execute(
                "SELECT fw.*, u.full_name "
                "FROM family_wallet_log fw "
                "LEFT JOIN users u ON u.user_id = fw.user_id "
                "WHERE fw.chat_id=0 AND fw.user_id IN (?,?) "
                "ORDER BY fw.created_at DESC LIMIT ?",
                (uid, partner_id, limit),
            ) as c:
                rows = await c.fetchall()
        else:
            async with db.execute(
                "SELECT fw.*, u.full_name "
                "FROM family_wallet_log fw "
                "LEFT JOIN users u ON u.user_id = fw.user_id "
                "WHERE fw.chat_id=0 AND fw.user_id=? "
                "ORDER BY fw.created_at DESC LIMIT ?",
                (uid, limit),
            ) as c:
                rows = await c.fetchall()
    return [dict(r) for r in rows]


async def get_all_marriages_for_anniversary() -> list:
    """Return all marriages for anniversary check.

    Includes a representative shared chat_id (from user_stats) so the
    scheduler can send the anniversary notification somewhere meaningful.
    chat_id may be NULL when both users share no common chat.
    """
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT mg.user_id, mg.partner_id, mg.married_at,
                      (
                          SELECT us.chat_id
                          FROM user_stats us
                          JOIN user_stats us2
                               ON us2.user_id = mg.partner_id
                              AND us2.chat_id  = us.chat_id
                          WHERE us.user_id = mg.user_id
                          ORDER BY us.chat_id
                          LIMIT 1
                      ) AS chat_id
               FROM marriages_global mg"""
        ) as c:
            return await c.fetchall()


async def is_anniversary_awarded(user_id: int, chat_id: int, date_str: str) -> bool:
    """True если юбилейная Мора уже была начислена этому пользователю сегодня."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT 1 FROM anniversary_log WHERE user_id=? AND chat_id=? AND date_str=?",
            (user_id, chat_id, date_str),
        ) as c:
            return (await c.fetchone()) is not None


async def mark_anniversary_awarded(user_id: int, chat_id: int, date_str: str):
    """Записать факт начисления юбилейной Моры."""
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO anniversary_log (user_id, chat_id, date_str) VALUES (?,?,?) ON CONFLICT DO NOTHING",
            (user_id, chat_id, date_str),
        )
        await db.commit()
        # Автоочистка: удаляем записи старше 90 дней
        cutoff = (datetime.now(timezone.utc).date().isoformat()[:7])  # "YYYY-MM"
        await db.execute(
            "DELETE FROM anniversary_log WHERE date_str < ?",
            (cutoff + "-01",),
        )
        await db.commit()


# ─── Singles weekly bonus log (persistent guard) ─────────────────────────────

async def is_singles_bonus_awarded(week_key: str) -> bool:
    """Check if singles bonus has been awarded for this week."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT 1 FROM singles_bonus_log WHERE week_key=?", (week_key,)
        ) as c:
            return bool(await c.fetchone())


async def mark_singles_bonus_awarded(week_key: str):
    """Mark singles bonus as awarded for this week and cleanup old records."""
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO singles_bonus_log (week_key) VALUES (?) ON CONFLICT DO NOTHING", (week_key,)
        )
        
        # Auto-cleanup: remove records older than 12 weeks
        cutoff_year = datetime.now(timezone.utc).year
        if week_key.startswith(str(cutoff_year)) and int(week_key[-2:]) <= 12:
            cutoff_year -= 1
        await db.execute(
            "DELETE FROM singles_bonus_log WHERE week_key < ?", (f"{cutoff_year}-W01",)
        )
        await db.commit()


async def get_all_singles_for_weekly_bonus():
    """Get all single (unmarried) users who are active."""
    async with postgres_connect() as db:
        async with db.execute("""
            SELECT us.user_id, us.chat_id
            FROM user_stats us
            WHERE us.is_banned = 0
              AND us.message_count > 10
              AND NOT EXISTS (
                  SELECT 1 FROM marriages_global mg
                  WHERE mg.user_id = us.user_id
              )
        """) as c:
            return await c.fetchall()


# ─── Lottery draw log (persistent guard) ─────────────────────────────────────

async def is_lottery_drawn(week_key: str) -> bool:
    """True если розыгрыш лотереи уже был проведён на этой неделе (выживает перезапуск)."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT 1 FROM lottery_draws WHERE week_key=?", (week_key,)
        ) as c:
            return (await c.fetchone()) is not None


async def mark_lottery_drawn(week_key: str):
    """Записать факт проведения розыгрыша лотереи на этой неделе."""
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO lottery_draws (week_key) VALUES (?) ON CONFLICT DO NOTHING", (week_key,)
        )
        await db.commit()
        # Автоочистка: удаляем записи старше 12 недель
        cutoff_year = datetime.now(timezone.utc).year - 1
        await db.execute(
            "DELETE FROM lottery_draws WHERE week_key < ?", (f"{cutoff_year}-W01",)
        )
        await db.commit()


# ─── Mora balance management ──────────────────────────────────────────────────

async def set_mora_balance(user_id: int, chat_id: int, new_balance: int):
    """Устанавливает глобальный баланс Моры напрямую (для developer-команд)."""
    new_balance = max(0, new_balance)
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (new_balance, user_id),
        )
        await db.commit()


# ─── Переводы Моры ────────────────────────────────────────────────────────────

async def transfer_mora(from_uid: int, to_uid: int, chat_id: int, amount: int) -> tuple[bool, int, int]:
    """Атомарный перевод Моры (глобально). Возвращает (ok, from_new_bal, to_new_bal)."""
    async with postgres_connect() as db:
        # Atomic deduction with balance guard
        cursor = await db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id=? AND COALESCE(balance, 0) >= ?",
            (amount, from_uid, amount),
        )
        if cursor.rowcount == 0:
            async with db.execute(
                "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?",
                (from_uid,),
            ) as c:
                row = await c.fetchone()
            return False, (row[0] if row else 0), 0

        await db.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + ?,"
            " total_earned = COALESCE(total_earned, 0) + ? WHERE user_id=?",
            (amount, amount, to_uid),
        )
        await db.commit()

        async with db.execute(
            "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?", (from_uid,)
        ) as c:
            row = await c.fetchone()
        from_new_bal = row[0] if row else 0
        async with db.execute(
            "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?", (to_uid,)
        ) as c:
            row = await c.fetchone()
        to_new_bal = row[0] if row else 0
        return True, from_new_bal, to_new_bal


# ─── Долги (займы) ────────────────────────────────────────────────────────────

async def create_loan(lender_id: int, borrower_id: int, chat_id: int, amount: int) -> tuple[bool, int, int]:
    """Создаёт заём: списывает с кредитора (глобально), зачисляет заёмщику.
    Возвращает (ok, lender_new_bal, loan_id)."""
    async with postgres_connect() as db:
        now = datetime.now(timezone.utc)

        # Atomic deduction with balance guard
        cursor = await db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id=? AND COALESCE(balance, 0) >= ?",
            (amount, lender_id, amount),
        )
        if cursor.rowcount == 0:
            async with db.execute(
                "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?",
                (lender_id,),
            ) as c:
                row = await c.fetchone()
            return False, (row[0] if row else 0), 0

        await db.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + ?,"
            " total_earned = COALESCE(total_earned, 0) + ? WHERE user_id=?",
            (amount, amount, borrower_id),
        )
        cursor = await db.execute(
            "INSERT INTO mora_loans (lender_id, borrower_id, chat_id, amount, loaned_at) VALUES (?,?,?,?,?) RETURNING id",
            (lender_id, borrower_id, chat_id, amount, now),
        )
        row = await cursor.fetchone()
        loan_id = row[0] if row else cursor.lastrowid
        await db.commit()

        async with db.execute(
            "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?",
            (lender_id,),
        ) as c:
            row = await c.fetchone()
        lender_new_bal = row[0] if row else 0
        return True, lender_new_bal, loan_id


async def get_active_loans_as_lender(user_id: int, chat_id: int) -> list:
    """Займы, выданные пользователем (не погашенные)."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT * FROM mora_loans
               WHERE lender_id=? AND chat_id=? AND repaid_at IS NULL
               ORDER BY loaned_at ASC""",
            (user_id, chat_id),
        ) as c:
            return list(await c.fetchall())


async def get_active_loans_as_borrower(user_id: int, chat_id: int) -> list:
    """Займы, которые пользователь должен вернуть."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT * FROM mora_loans
               WHERE borrower_id=? AND chat_id=? AND repaid_at IS NULL
               ORDER BY loaned_at ASC""",
            (user_id, chat_id),
        ) as c:
            return list(await c.fetchall())


async def repay_loan(loan_id: int, borrower_id: int, chat_id: int) -> tuple[bool, int]:
    """Полностью погашает заём (глобальный баланс). Возвращает (ok, borrower_new_bal)."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM mora_loans WHERE id=? AND chat_id=? AND borrower_id=? AND repaid_at IS NULL AND COALESCE(status,'accepted')='accepted'",
            (loan_id, chat_id, borrower_id),
        ) as c:
            loan = await c.fetchone()
        if not loan:
            return False, 0

        amount = loan["amount"]
        lender_id = loan["lender_id"]

        now = datetime.now(timezone.utc)

        # Atomic deduction with balance guard
        cursor = await db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id=? AND COALESCE(balance, 0) >= ?",
            (amount, borrower_id, amount),
        )
        if cursor.rowcount == 0:
            async with db.execute(
                "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?",
                (borrower_id,),
            ) as c:
                row = await c.fetchone()
            return False, (row[0] if row else 0)

        await db.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE user_id=?",
            (amount, lender_id),
        )
        await db.execute(
            "UPDATE mora_loans SET repaid_at=? WHERE id=?",
            (now, loan_id),
        )
        await db.commit()

        async with db.execute(
            "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?",
            (borrower_id,),
        ) as c:
            row = await c.fetchone()
        return True, (row[0] if row else 0)


# ─── Смена вида питомца ───────────────────────────────────────────────────────

async def change_pet_type(user_id: int, chat_id: int, new_type: str) -> bool:
    """Меняет вид глобального питомца (user + партнёр). Возвращает True если питомец найден."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT 1 FROM pets_global WHERE user_id=?",
            (user_id,),
        ) as c:
            if not await c.fetchone():
                return False
        await db.execute(
            "UPDATE pets_global SET pet_type=? WHERE user_id=?",
            (new_type, user_id),
        )
        async with db.execute(
            "SELECT partner_id FROM marriages_global WHERE user_id=?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        if row:
            await db.execute(
                "UPDATE pets_global SET pet_type=? WHERE user_id=?",
                (new_type, row[0]),
            )
        await db.commit()
        return True


async def reset_user_quest(user_id: int, chat_id: int, quest_date: str):
    """Delete today's quest progress so it will be re-assigned fresh."""
    async with postgres_connect() as db:
        await db.execute(
            "DELETE FROM user_quests WHERE user_id=? AND chat_id=? AND quest_date=?",
            (user_id, chat_id, quest_date),
        )
        await db.commit()


async def add_reputation_in_chat(from_uid: int, to_uid: int, chat_id: int, amount: int = 1) -> int:
    """Add reputation in chat. Returns new rep value."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO rep_log (from_uid, to_uid, chat_id, amount, given_at) VALUES (?,?,?,?,?)",
            (from_uid, to_uid, chat_id, amount, now),
        )
        await db.execute(
            "INSERT INTO user_stats (user_id, chat_id) VALUES (?, ?) ON CONFLICT (user_id, chat_id) DO NOTHING",
            (to_uid, chat_id),
        )
        await db.execute(
            "UPDATE user_stats SET reputation = reputation + ? WHERE user_id = ? AND chat_id = ?",
            (amount, to_uid, chat_id),
        )
        # Increment rep_given counter for the giver
        await db.execute(
            "UPDATE user_mora SET rep_given_count = COALESCE(rep_given_count,0) + 1 WHERE user_id=? AND chat_id=?",
            (from_uid, chat_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT reputation FROM user_stats WHERE user_id = ? AND chat_id = ?",
            (to_uid, chat_id),
        ) as c:
            row = await c.fetchone()
            rep_new = row[0] if row else 0
        async with db.execute(
            "SELECT rep_given_count FROM user_mora WHERE user_id=? AND chat_id=?",
            (from_uid, chat_id),
        ) as c:
            row2 = await c.fetchone()
            rgc = row2[0] if row2 else 0

    # Check rep_given achievements (fire-and-forget)
    try:
        from api.achievements import check_and_award as _ach
        await _ach(from_uid, chat_id, "rep_given", rgc)
    except Exception:
        pass

    return rep_new


async def get_banned_in_chat(chat_id: int):
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT us.user_id, us.ban_reason, u.full_name, u.username
               FROM user_stats us
               JOIN users u ON u.user_id = us.user_id
               WHERE us.chat_id = ? AND us.is_banned = 1""",
            (chat_id,),
        ) as c:
            return await c.fetchall()


async def get_top_by_messages_in_chat(
    chat_id: int,
    limit: int = 10,
    pending: "dict | None" = None,
):
    """Return top users sorted by message_count.

    If *pending* is provided (a snapshot from services.message_buffer.get_all_pending()),
    unsaved in-memory counts are merged before sorting so the top is always up-to-date.
    """
    pending_for_chat = {
        uid: delta
        for (uid, cid), delta in (pending or {}).items()
        if cid == chat_id and delta > 0
    }

    async with postgres_connect() as db:
        if not pending_for_chat:
            async with db.execute(
                """SELECT us.*, u.full_name, u.username
                   FROM user_stats us
                   JOIN users u ON u.user_id = us.user_id
                   WHERE us.chat_id = ? AND us.is_banned = 0 AND us.message_count >= 1
                   ORDER BY us.message_count DESC LIMIT ?""",
                (chat_id, limit),
            ) as c:
                return await c.fetchall()

        pending_user_ids = list(pending_for_chat.keys())
        placeholders = ", ".join("?" for _ in pending_user_ids)
        async with db.execute(
            f"""SELECT us.*, u.full_name, u.username
                  FROM user_stats us
                  JOIN users u ON u.user_id = us.user_id
                  WHERE us.chat_id = ? AND us.is_banned = 0
                    AND (us.message_count >= 1 OR us.user_id IN ({placeholders}))""",
            (chat_id, *pending_user_ids),
        ) as c:
            rows = await c.fetchall()

    mutable: dict[int, dict] = {row["user_id"]: dict(row) for row in rows}
    for uid, delta in pending_for_chat.items():
        row = mutable.get(uid)
        if not row:
            continue
        row["message_count"] = (row.get("message_count") or 0) + delta

    merged = [row for row in mutable.values() if (row.get("message_count") or 0) >= 1]
    merged.sort(key=lambda r: ((r.get("message_count") or 0), (r.get("xp") or 0)), reverse=True)
    return merged[:limit]


async def get_top_by_xp_in_chat(chat_id: int, limit: int = 10):
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT us.*, u.full_name, u.username
               FROM user_stats us
               JOIN users u ON u.user_id = us.user_id
               WHERE us.chat_id = ? AND us.is_banned = 0
               ORDER BY us.xp DESC LIMIT ?""",
            (chat_id, limit),
        ) as c:
            return await c.fetchall()


async def get_top_reputation_in_chat(chat_id: int, limit: int = 10):
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT us.*, u.full_name, u.username
               FROM user_stats us
               JOIN users u ON u.user_id = us.user_id
               WHERE us.chat_id = ? AND us.is_banned = 0
               ORDER BY us.reputation DESC LIMIT ?""",
            (chat_id, limit),
        ) as c:
            return await c.fetchall()


async def get_chat_stats_for_chat(chat_id: int):
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM user_stats WHERE chat_id = ?", (chat_id,)
        ) as c:
            total = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM user_stats WHERE chat_id = ? AND is_banned = 1", (chat_id,)
        ) as c:
            banned = (await c.fetchone())[0]
        async with db.execute(
            "SELECT SUM(message_count) FROM user_stats WHERE chat_id = ?", (chat_id,)
        ) as c:
            messages = (await c.fetchone())[0] or 0
        async with db.execute(
            "SELECT COUNT(*) FROM user_stats WHERE chat_id = ? AND rank NOT IN ('user', 'vip')",
            (chat_id,),
        ) as c:
            staff = (await c.fetchone())[0]
    return {"total": total, "banned": banned, "messages": messages, "staff": staff}


async def set_bio_in_chat(user_id: int, chat_id: int, bio: str | None):
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_stats (user_id, chat_id, bio) VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET bio = excluded.bio""",
            (user_id, chat_id, bio),
        )
        await db.commit()


async def get_rep_last_time(from_uid: int, to_uid: int, chat_id: int) -> str | None:
    """Get ISO timestamp of last rep given from_uid to to_uid in chat."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT given_at FROM rep_log WHERE from_uid=? AND to_uid=? AND chat_id=? ORDER BY given_at DESC LIMIT 1",
            (from_uid, to_uid, chat_id),
        ) as c:
            row = await c.fetchone()
            return row[0] if row else None


_EDITABLE_STATS_FIELDS = {
    "message_count", "xp", "level", "reputation", "warns",
    "bio", "custom_title", "is_banned",
}


async def set_user_stat_in_chat(user_id: int, chat_id: int, field: str, value) -> bool:
    if field not in _EDITABLE_STATS_FIELDS:
        return False
    async with postgres_connect() as db:
        await db.execute(
            f"UPDATE user_stats SET {field} = ? WHERE user_id = ? AND chat_id = ?",
            (value, user_id, chat_id),
        )
        await db.commit()
    return True


# ─── Channel types (типы каналов) ─────────────────────────────────────────────
# type values: "rules"  = канал правил/ролей (куда ведёт TikTok-ссылка)
#              "main"   = основной чат для общения
# "admin" groups managed separately via admin_groups table

async def set_channel_type(type_name: str, chat_id: int):
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO channel_types (type, chat_id) VALUES (?, ?) "
            "ON CONFLICT (type) DO UPDATE SET chat_id = EXCLUDED.chat_id",
            (type_name, chat_id),
        )
        await db.commit()


async def remove_channel_type(type_name: str):
    async with postgres_connect() as db:
        await db.execute("DELETE FROM channel_types WHERE type = ?", (type_name,))
        await db.commit()


async def get_channel_type(type_name: str) -> int | None:
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT chat_id FROM channel_types WHERE type = ?", (type_name,)
        ) as c:
            row = await c.fetchone()
            return row[0] if row else None


async def get_all_channel_types() -> list[dict]:
    async with postgres_connect() as db:
        async with db.execute("SELECT type, chat_id FROM channel_types ORDER BY type") as c:
            return [dict(r) for r in await c.fetchall()]


# ─── Community roles (роли сообщества) ────────────────────────────────────────

async def add_community_role(name: str, emoji: str = "", description: str = "") -> bool:
    """Add a new community role. Returns False if name already exists."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        try:
            await db.execute(
                "INSERT INTO community_roles (name, emoji, description, created_at) VALUES (?, ?, ?, ?)",
                (name, emoji, description, now),
            )
            await db.commit()
            return True
        except asyncpg.UniqueViolationError:
            return False


async def remove_community_role(name: str) -> bool:
    """Remove a community role by name. Returns False if not found."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT id FROM community_roles WHERE name = ?", (name,)
        ) as c:
            row = await c.fetchone()
        if not row:
            return False
        await db.execute("DELETE FROM community_roles WHERE id = ?", (row[0],))
        await db.commit()
        return True


async def get_community_roles() -> list[dict]:
    """Return all roles with their holder count."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT r.id, r.name, r.emoji, r.description,
                      COUNT(ur.user_id) AS holder_count
               FROM community_roles r
               LEFT JOIN user_roles ur ON ur.role_id = r.id
               GROUP BY r.id
               ORDER BY r.name""",
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def get_user_community_roles(user_id: int) -> list[dict]:
    """Get all community roles assigned to a user."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT r.name, r.emoji, r.description
               FROM user_roles ur
               JOIN community_roles r ON r.id = ur.role_id
               WHERE ur.user_id = ?
               ORDER BY r.name""",
            (user_id,),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def assign_community_role(user_id: int, role_name: str) -> str:
    """Assign a role to a user.

    Returns:
        'ok'        – role assigned successfully
        'already'   – this user already has this role
        'taken'     – role is held by a different user
        'not_found' – no role with that name exists

    Enforces 1-role-1-person: a role can belong to only one person at a time.
    """
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT id FROM community_roles WHERE name = ?", (role_name,)
        ) as c:
            row = await c.fetchone()
        if not row:
            return "not_found"
        role_id = row[0]

        # Check if the role is already assigned to anyone
        async with db.execute(
            "SELECT user_id FROM user_roles WHERE role_id = ?", (role_id,)
        ) as c:
            existing = await c.fetchone()

        if existing:
            holder_id = existing["user_id"] if hasattr(existing, '__getitem__') else existing[0]
            if holder_id == user_id:
                return "already"
            return "taken"

        await db.execute(
            "INSERT INTO user_roles (role_id, user_id) VALUES (?, ?)",
            (role_id, user_id),
        )
        await db.commit()
        return "ok"


async def revoke_community_role(user_id: int, role_name: str) -> bool:
    """Remove a role from a user. Returns False if user didn't have it."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT id FROM community_roles WHERE name = ?", (role_name,)
        ) as c:
            row = await c.fetchone()
        if not row:
            return False
        result = await db.execute(
            "DELETE FROM user_roles WHERE role_id = ? AND user_id = ?",
            (row[0], user_id),
        )
        await db.commit()
        return result.rowcount > 0


async def get_role_holders(role_name: str) -> list[dict]:
    """Get all users who have a specific role."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT u.user_id, u.full_name, u.username
               FROM user_roles ur
               JOIN community_roles r ON r.id = ur.role_id
               JOIN users u ON u.user_id = ur.user_id
               WHERE r.name = ?
               ORDER BY u.full_name""",
            (role_name,),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def force_assign_community_role(user_id: int, role_name: str) -> tuple[str, int | None]:
    """Force-assign a role, evicting any current holder.

    Returns:
        ('ok', None)         – assigned, role was free
        ('ok', evicted_id)   – assigned, previous holder evicted
        ('not_found', None)  – role doesn't exist
        ('already', None)    – user already has this role
    """
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT id FROM community_roles WHERE name = ?", (role_name,)
        ) as c:
            row = await c.fetchone()
        if not row:
            return ("not_found", None)
        role_id = row[0]

        async with db.execute(
            "SELECT user_id FROM user_roles WHERE role_id = ?", (role_id,)
        ) as c:
            existing = await c.fetchone()

        evicted_id: int | None = None
        if existing:
            holder_id = existing[0]
            if holder_id == user_id:
                return ("already", None)
            await db.execute("DELETE FROM user_roles WHERE role_id = ?", (role_id,))
            evicted_id = holder_id

        await db.execute(
            "INSERT INTO user_roles (role_id, user_id) VALUES (?, ?)",
            (role_id, user_id),
        )
        await db.commit()
        return ("ok", evicted_id)


async def log_voluntary_leave(chat_id: int, user_id: int, full_name: str, username: str) -> None:
    """Log a user who voluntarily left a chat."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO leave_log (chat_id, user_id, full_name, username, left_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, full_name, username, now),
        )
        await db.commit()


async def clear_leave_log(chat_id: int, user_id: int) -> None:
    """Remove leave_log entries for a user who has rejoined the chat."""
    async with postgres_connect() as db:
        await db.execute(
            "DELETE FROM leave_log WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        await db.commit()


async def get_voluntary_leaves(chat_id: int, limit: int = 20) -> list[dict]:
    """Return recent voluntary leaves for a chat, newest first."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT user_id, full_name, username, left_at
               FROM leave_log WHERE chat_id = ?
               ORDER BY left_at DESC LIMIT ?""",
            (chat_id, limit),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def cleanup_left_inactive_users(cutoff_days: int = 7) -> int:
    """Delete per-chat data for users who left > cutoff_days ago.

    Only removes user_stats and user_mora rows for the specific chat the
    user left. The global users record and leave_log entry are kept.
    Returns the number of (user_id, chat_id) pairs cleaned up.
    """
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
    cleaned = 0
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT DISTINCT user_id, chat_id FROM leave_log WHERE left_at < ?",
            (cutoff,),
        ) as c:
            rows = await c.fetchall()
        for row in rows:
            uid, cid = row["user_id"], row["chat_id"]
            # Remove per-chat economy and stats rows only
            await db.execute(
                "DELETE FROM user_stats WHERE user_id = ? AND chat_id = ?", (uid, cid)
            )
            await db.execute(
                "DELETE FROM user_mora WHERE user_id = ? AND chat_id = ?", (uid, cid)
            )
            cleaned += 1
        if cleaned:
            await db.commit()
    return cleaned


# ─── User Banlist (ID-based, per-chat) ────────────────────────────────────────

async def add_user_to_banlist(
    chat_id: int, user_id: int, added_by: int = 0, reason: str = ""
) -> bool:
    """Add a user to the chat banlist. Returns False if already banned."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        try:
            await db.execute(
                "INSERT INTO user_banlist (chat_id, user_id, added_by, reason, added_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (chat_id, user_id, added_by, reason, now),
            )
            await db.commit()
            return True
        except Exception:
            return False


async def remove_user_from_banlist(chat_id: int, user_id: int) -> bool:
    """Remove a user from the chat banlist. Returns True if removed."""
    async with postgres_connect() as db:
        result = await db.execute(
            "DELETE FROM user_banlist WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        await db.commit()
        return result.rowcount > 0


async def is_user_in_banlist(chat_id: int, user_id: int) -> bool:
    """Check if a user is in the chat banlist."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT 1 FROM user_banlist WHERE chat_id = ? AND user_id = ? LIMIT 1",
            (chat_id, user_id),
        ) as c:
            return (await c.fetchone()) is not None


async def get_chat_banlist_users(chat_id: int, limit: int = 50) -> list[dict]:
    """Return user banlist for a chat."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT ub.user_id, ub.added_by, ub.reason, ub.added_at,
                      u.full_name, u.username
               FROM user_banlist ub
               LEFT JOIN users u ON u.user_id = ub.user_id
               WHERE ub.chat_id = ?
               ORDER BY ub.added_at DESC LIMIT ?""",
            (chat_id, limit),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def get_senior_users_in_chat(chat_id: int) -> list[dict]:
    """Return users with rank co_owner, owner, or developer in a chat."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT us.user_id, u.full_name, u.username
               FROM user_stats us
               JOIN users u ON u.user_id = us.user_id
               WHERE us.chat_id = ? AND us.rank IN ('co_owner', 'owner', 'developer')
               ORDER BY CASE us.rank
                   WHEN 'developer' THEN 3
                   WHEN 'owner'     THEN 2
                   WHEN 'co_owner'  THEN 1
               END DESC""",
            (chat_id,),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


# ─── Pending role assignments (waiting for main chat join) ────────────────────

async def set_pending_role(user_id: int, role_name: str) -> None:
    """Reserve a role in DM; it becomes active once the user joins the main chat."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO pending_roles (user_id, role_name, reserved_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   role_name   = excluded.role_name,
                   reserved_at = excluded.reserved_at""",
            (user_id, role_name, now),
        )
        await db.commit()


async def get_pending_role(user_id: int) -> str | None:
    """Return the pending role name for a user, or None."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT role_name FROM pending_roles WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        return row[0] if row else None


async def clear_pending_role(user_id: int) -> None:
    """Remove any pending role for a user."""
    async with postgres_connect() as db:
        await db.execute("DELETE FROM pending_roles WHERE user_id = ?", (user_id,))
        await db.commit()


# ─── Авто-варн за неактив ─────────────────────────────────────────────────────

async def get_chats_with_inactivity_warn() -> list[dict]:
    """Return all chats where inactivity_warn_enabled=1."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT chat_id, inactivity_warn_days FROM chat_settings WHERE inactivity_warn_enabled = 1"
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def get_inactive_users_for_warn(chat_id: int, cutoff_iso: str) -> list[dict]:
    """
    Возвращает пользователей в чате, которые:
    - не стафф (ранг user/vip)
    - не забанены
    - неактивны дольше cutoff
    - ещё не получали авто-варн в текущем периоде неактивности
    """
    async with postgres_connect() as db:
        async with db.execute(
            """
            SELECT us.user_id,
                   COALESCE(u.full_name, CAST(us.user_id AS TEXT)) AS full_name,
                   u.username,
                   COALESCE(us.last_active, us.first_active) AS last_seen,
                   us.inactivity_warned_at
            FROM user_stats us
            LEFT JOIN users u ON u.user_id = us.user_id
            WHERE us.chat_id = ?
              AND us.is_banned = 0
              AND us.rank IN ('user', 'vip')
              AND COALESCE(us.last_active, us.first_active) IS NOT NULL
              AND COALESCE(us.last_active, us.first_active) < ?
              AND (
                  us.inactivity_warned_at IS NULL
                  OR us.last_active > us.inactivity_warned_at
              )
            """,
            (chat_id, cutoff_iso),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def get_inactive_users_24h(chat_id: int, limit: int = 50) -> list[dict]:
    """Вернуть участников чата, чья last_active < 24 часа назад.
    Исключает стафф и забаненных. Сортировка: самые давно-неактивные первыми."""
    async with postgres_connect() as db:
        async with db.execute(
            """
            SELECT us.user_id,
                   COALESCE(u.full_name, CAST(us.user_id AS TEXT)) AS full_name,
                   u.username,
                   us.rank,
                   COALESCE(us.last_active, us.first_active) AS last_seen,
                   COALESCE(us.message_count, 0) AS message_count
            FROM user_stats us
            LEFT JOIN users u ON u.user_id = us.user_id
            WHERE us.chat_id = ?
              AND us.is_banned = 0
              AND COALESCE(us.rank, 'user') IN ('user', 'vip')
              AND COALESCE(us.last_active, us.first_active) IS NOT NULL
              AND COALESCE(us.last_active, us.first_active) < NOW() - INTERVAL '24 hours'
            ORDER BY COALESCE(us.last_active, us.first_active) ASC
            LIMIT ?
            """,
            (chat_id, limit),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def set_inactivity_warned(user_id: int, chat_id: int, when_iso: str) -> None:
    """Записать время авто-варна за неактив."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_stats (user_id, chat_id, inactivity_warned_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id)
               DO UPDATE SET inactivity_warned_at = excluded.inactivity_warned_at""",
            (user_id, chat_id, when_iso),
        )
        await db.commit()


# ─── Запланированная чистка ───────────────────────────────────────────────────

async def get_chats_with_scheduled_cleanup() -> list[dict]:
    """Все чаты у которых задана дата следующей чистки."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT chat_id, next_cleanup_at, cleanup_reminder_sent,
                      COALESCE(cleanup_message_norm, 70) AS cleanup_message_norm,
                      COALESCE(cleanup_warn_hours, 48)   AS cleanup_warn_hours
               FROM chat_settings
               WHERE next_cleanup_at IS NOT NULL"""
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def set_cleanup_reminder_sent(chat_id: int, sent: int) -> None:
    await set_chat_setting(chat_id, "cleanup_reminder_sent", sent)


async def get_cleanup_config(chat_id: int) -> dict:
    """Return current cleanup configuration for a chat."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT next_cleanup_at, cleanup_reminder_sent,
                      COALESCE(cleanup_message_norm, 70) AS cleanup_message_norm,
                      COALESCE(cleanup_warn_hours, 48)   AS cleanup_warn_hours
               FROM chat_settings WHERE chat_id = ?""",
            (chat_id,),
        ) as c:
            row = await c.fetchone()
    if row:
        return dict(row)
    return {
        "next_cleanup_at": None,
        "cleanup_reminder_sent": 0,
        "cleanup_message_norm": 70,
        "cleanup_warn_hours": 48,
    }


async def set_cleanup_config(
    chat_id: int,
    next_cleanup_at: str | None = None,
    cleanup_message_norm: int | None = None,
    cleanup_warn_hours: int | None = None,
) -> None:
    """Update one or more cleanup config fields for a chat."""
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO chat_settings (chat_id) VALUES (?) ON CONFLICT (chat_id) DO NOTHING",
            (chat_id,),
        )
        if next_cleanup_at is not None:
            # Normalise to a tz-aware ISO string.
            # NOTE: the postgres wrapper (_maybe_datetime) converts ISO strings back to
            # datetime objects, which asyncpg then rejects for the TEXT column
            # next_cleanup_at.  We bypass the wrapper by using the raw asyncpg pool
            # so that the isoformat() string is passed through unchanged.
            from datetime import datetime as _dt, timezone as _tz
            _nc = next_cleanup_at
            if isinstance(_nc, str):
                _s = _nc.replace('Z', '+00:00')
                try:
                    _parsed = _dt.fromisoformat(_s)
                except ValueError:
                    if '.' in _s and ('+' in _s[_s.index('.'):] or _s.endswith('00')):
                        dot = _s.index('.')
                        off = _s.index('+', dot) if '+' in _s[dot:] else len(_s)
                        _s = _s[:dot] + _s[off:]
                    _parsed = _dt.fromisoformat(_s)
                _nc = _parsed if _parsed.tzinfo else _parsed.replace(tzinfo=_tz.utc)
            elif hasattr(_nc, 'tzinfo') and _nc.tzinfo is None:
                _nc = _nc.replace(tzinfo=_tz.utc)
            # Use raw pool to bypass _maybe_datetime which would re-convert the string
            _pool = await get_pg_pool()
            async with _pool.acquire() as _raw_conn:
                await _raw_conn.execute(
                    "UPDATE chat_settings SET next_cleanup_at = $1, cleanup_reminder_sent = 0 WHERE chat_id = $2",
                    _nc.isoformat(), chat_id,
                )
        if cleanup_message_norm is not None:
            await db.execute(
                "UPDATE chat_settings SET cleanup_message_norm = ? WHERE chat_id = ?",
                (cleanup_message_norm, chat_id),
            )
        if cleanup_warn_hours is not None:
            await db.execute(
                "UPDATE chat_settings SET cleanup_warn_hours = ? WHERE chat_id = ?",
                (cleanup_warn_hours, chat_id),
            )
        await db.commit()
    _invalidate_chat_settings(chat_id)


# ─── Глобальные баффы чата ────────────────────────────────────────────────────

async def activate_chat_buff(
    chat_id: int,
    buff_type: str,
    activated_by: int,
    duration_minutes: int = 60,
) -> dict:
    """Activate (or replace an expired) chat-global buff. Returns expires_at ISO string."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=duration_minutes)
    async with postgres_connect() as db:
        # Insert or replace only if there is no active (non-expired) buff.
        await db.execute(
            """INSERT INTO chat_global_buffs
                   (chat_id, buff_type, activated_by, activated_at, expires_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (chat_id, buff_type) DO UPDATE
                   SET activated_by  = EXCLUDED.activated_by,
                       activated_at  = EXCLUDED.activated_at,
                       expires_at    = EXCLUDED.expires_at
                   WHERE chat_global_buffs.expires_at < NOW()""",
            (chat_id, buff_type, activated_by, now, expires),
        )
        await db.commit()
    return {"ok": True, "buff_type": buff_type, "expires_at": expires.isoformat()}


async def get_active_chat_buff(chat_id: int, buff_type: str) -> dict | None:
    """Return the active buff row, or None if none / expired."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT buff_type, activated_by, activated_at, expires_at "
            "FROM chat_global_buffs "
            "WHERE chat_id = ? AND buff_type = ? AND expires_at > NOW()",
            (chat_id, buff_type),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def cleanup_expired_chat_buffs() -> None:
    """Housekeeping: delete all expired buff rows."""
    async with postgres_connect() as db:
        await db.execute("DELETE FROM chat_global_buffs WHERE expires_at <= NOW()")
        await db.commit()


# ─── Питомцы ──────────────────────────────────────────────────────────────────

async def get_pet(user_id: int, chat_id: int) -> dict | None:
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM pets_global WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
            return dict(row) if row else None


async def get_pets_batch(pairs: list[tuple[int, int]]) -> dict[tuple[int, int], dict]:
    """Batch-fetch pets for multiple (user_id, chat_id) pairs.
    Now uses global pets_global table; chat_id is kept in key for backwards compat."""
    if not pairs:
        return {}
    user_ids = list({uid for uid, _ in pairs})
    placeholders = ",".join("?" * len(user_ids))
    async with postgres_connect() as db:
        async with db.execute(
            f"SELECT * FROM pets_global WHERE user_id IN ({placeholders})",
            tuple(user_ids),
        ) as c:
            rows = await c.fetchall()
    uid_to_row = {r["user_id"]: dict(r) for r in rows}
    return {(uid, cid): uid_to_row[uid] for uid, cid in pairs if uid in uid_to_row}


async def get_marriages_batch(pairs: list[tuple[int, int]]) -> dict[tuple[int, int], dict]:
    """Batch-fetch marriages for multiple (user_id, chat_id) pairs.
    Now uses global marriages_global table; chat_id is kept in key for backwards compat."""
    if not pairs:
        return {}
    user_ids = list({uid for uid, _ in pairs})
    placeholders = ",".join("?" * len(user_ids))
    async with postgres_connect() as db:
        async with db.execute(
            f"SELECT * FROM marriages_global WHERE user_id IN ({placeholders})",
            tuple(user_ids),
        ) as c:
            rows = await c.fetchall()
    uid_to_row = {r["user_id"]: dict(r) for r in rows}
    return {(uid, cid): uid_to_row[uid] for uid, cid in pairs if uid in uid_to_row}


async def adopt_pet(user_id: int, partner_id: int, chat_id: int, pet_type: str) -> None:
    """Создаёт глобального питомца для обоих партнёров."""
    now = datetime.now(timezone.utc).isoformat()
    async with postgres_connect() as db:
        for uid in (user_id, partner_id):
            await db.execute(
                """INSERT INTO pets_global (user_id, pet_type, adopted_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id) DO NOTHING""",
                (uid, pet_type, now),
            )
        await db.commit()
    # Pet achievement for both owners (fire-and-forget)
    try:
        from api.achievements import check_and_award as _ach
        await _ach(user_id, chat_id, "has_pet", 1)
        if partner_id != user_id:
            await _ach(partner_id, chat_id, "has_pet", 1)
    except Exception:
        pass


async def rename_pet(user_id: int, chat_id: int, name: str) -> bool:
    """Переименовать глобального питомца обоих партнёров. Возвращает True если питомец найден."""
    async with postgres_connect() as db:
        # Обновляем имя у самого юзера
        await db.execute(
            "UPDATE pets_global SET name = ? WHERE user_id = ?",
            (name, user_id),
        )
        # Обновляем имя и у партнёра (питомец общий на двоих)
        async with db.execute(
            "SELECT partner_id FROM marriages_global WHERE user_id = ?",
            (user_id,),
        ) as c:
            marriage_row = await c.fetchone()
        if marriage_row:
            partner_id = marriage_row[0]
            await db.execute(
                "UPDATE pets_global SET name = ? WHERE user_id = ?",
                (name, partner_id),
            )
        await db.commit()
        async with db.execute(
            "SELECT user_id FROM pets_global WHERE user_id = ?",
            (user_id,),
        ) as c:
            return await c.fetchone() is not None


# ─── Экспедиции питомцев ──────────────────────────────────────────────────────

async def start_expedition(user_id: int, chat_id: int, duration_h: int,
                           reward_min: int, reward_max: int) -> bool:
    """Начать экспедицию. Возвращает False если экспедиция уже идёт.

    Атомарна: ON CONFLICT DO UPDATE только если предыдущая экспедиция завершена
    (finished=1), что устраняет гонку при одновременных запросах.
    """
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        cursor = await db.execute(
            """INSERT INTO pet_expeditions (user_id, chat_id, started_at, duration_h,
                                           reward_min, reward_max, finished)
               VALUES (?, ?, ?, ?, ?, ?, 0)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                   started_at=excluded.started_at, duration_h=excluded.duration_h,
                   reward_min=excluded.reward_min, reward_max=excluded.reward_max, finished=0
               WHERE pet_expeditions.finished=1""",
            (user_id, chat_id, now, duration_h, reward_min, reward_max),
        )
        if cursor.rowcount == 0:
            # Conflict with an active expedition (finished=0) — do not overwrite
            return False
        await db.commit()
        return True


async def get_active_expedition(user_id: int, chat_id: int):
    """Возвращает активную экспедицию или None."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM pet_expeditions WHERE user_id=? AND chat_id=? AND finished=0",
            (user_id, chat_id),
        ) as c:
            return await c.fetchone()


async def get_all_finished_expeditions() -> list:
    """Вернуть все незавершённые экспедиции, время которых истекло."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM pet_expeditions WHERE finished=0"
        ) as c:
            rows = await c.fetchall()
    result = []
    for r in rows:
        started = r["started_at"]
        if isinstance(started, str):
            started = datetime.fromisoformat(started)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if now >= started + timedelta(hours=r["duration_h"]):
            result.append(r)
    return result


async def finish_expedition(user_id: int, chat_id: int):
    """Пометить экспедицию как завершённую."""
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE pet_expeditions SET finished=1 WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        await db.commit()


# ─── Гача (Молитвы) ──────────────────────────────────────────────────────────

async def get_gacha_pity(user_id: int, chat_id: int) -> int:
    """Сколько круток без леги (pity counter). Считаем непрерывную серию без lego."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT COUNT(*) FROM gacha_inventory
               WHERE user_id=? AND chat_id=?
               AND id > COALESCE(
                   (SELECT MAX(id) FROM gacha_inventory
                    WHERE user_id=? AND chat_id=? AND rarity='legendary'), 0)""",
            (user_id, chat_id, user_id, chat_id),
        ) as c:
            row = await c.fetchone()
            return row[0] if row else 0


async def add_gacha_item(user_id: int, chat_id: int, item_key: str,
                         item_name: str, rarity: str,
                         atk: int = 0, def_val: int = 0, hp: int = 0,
                         crit_rate: float = 0.0, slot=None):
    async with postgres_connect() as db:
        # Stack non-equipment items (no combat stats) up to 99 per stack
        if atk == 0 and def_val == 0 and hp == 0 and crit_rate == 0.0:
            async with db.execute(
                "SELECT id, stack_count FROM gacha_inventory "
                "WHERE user_id=? AND item_key=? AND equipped=0 "
                "AND COALESCE(enhancement_level,0)=0 ORDER BY id LIMIT 1",
                (user_id, item_key),
            ) as c:
                existing = await c.fetchone()
            if existing and existing[1] < 99:
                await db.execute(
                    "UPDATE gacha_inventory SET stack_count = stack_count + 1 WHERE id=?",
                    (existing[0],),
                )
                await db.commit()
                return
        await db.execute(
            """INSERT INTO gacha_inventory
               (user_id, chat_id, item_key, item_name, rarity, obtained_at, atk, def_val, hp, crit_rate, slot, stack_count)
               VALUES (?, ?, ?, ?, ?, NOW(), ?, ?, ?, ?, ?, 1)""",
            (user_id, chat_id, item_key, item_name, rarity, atk, def_val, hp, crit_rate, slot),
        )
        await db.commit()


async def get_gacha_inventory(user_id: int, chat_id: int) -> list:
    """Global inventory — chat_id param kept for backward compat but ignored."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM gacha_inventory WHERE user_id=? ORDER BY id DESC",
            (user_id,),
        ) as c:
            return await c.fetchall()


async def sell_gacha_junk(user_id: int, chat_id: int) -> tuple[int, int]:
    """Продать весь мусор (rarity='junk'). Возвращает (count, total_mora)."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COALESCE(stack_count, 1) FROM gacha_inventory WHERE user_id=? AND rarity='junk'",
            (user_id,),
        ) as c:
            rows = await c.fetchall()
        count = sum(r[0] for r in rows)
        if count == 0:
            return 0, 0
        await db.execute(
            "DELETE FROM gacha_inventory WHERE user_id=? AND rarity='junk'",
            (user_id,),
        )
        await db.commit()
    from config import GACHA_SELL_PRICES
    sell_price = count * GACHA_SELL_PRICES.get("junk", 10)
    await add_mora(user_id, chat_id, sell_price)
    return count, sell_price


async def equip_gacha_item(user_id: int, chat_id: int, item_id: int) -> bool:
    """Экипировать лего-предмет (обновить gacha_display). Возвращает False если не найден/не лего."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM gacha_inventory WHERE id=? AND user_id=?",
            (item_id, user_id),
        ) as c:
            item = await c.fetchone()
        if not item or item["rarity"] != "legendary":
            return False
        # Убираем экипировку с других предметов
        await db.execute(
            "UPDATE gacha_inventory SET equipped=0 WHERE user_id=? AND equipped=1",
            (user_id,),
        )
        await db.execute(
            "UPDATE gacha_inventory SET equipped=1 WHERE id=?", (item_id,),
        )
        # Обновляем gacha_display в user_mora
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, gacha_display) VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET gacha_display = excluded.gacha_display""",
            (user_id, chat_id, item["item_name"]),
        )
        await db.commit()
        return True


# ─── Банк Северного Королевства ───────────────────────────────────────────────

async def create_deposit(user_id: int, chat_id: int, amount: int,
                         rate: float, days: int) -> int:
    """Создать вклад. Возвращает id вклада."""
    now = datetime.now(timezone.utc)
    matures = now + timedelta(days=days)
    async with postgres_connect() as db:
        cursor = await db.execute(
            """INSERT INTO bank_deposits (user_id, chat_id, amount, rate, created_at, matures_at)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (user_id, chat_id, amount, rate, now, matures),
        )
        row = await cursor.fetchone()
        await db.commit()
        return row[0] if row else cursor.lastrowid


async def get_user_deposits(user_id: int, chat_id: int) -> list:
    """Вернуть все активные (не снятые) вклады пользователя."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM bank_deposits WHERE user_id=? AND chat_id=? AND withdrawn=0 ORDER BY id",
            (user_id, chat_id),
        ) as c:
            return await c.fetchall()


async def withdraw_deposit(deposit_id: int) -> dict | None:
    """Снять вклад. Возвращает dict с инфо о вкладе или None."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM bank_deposits WHERE id=? AND withdrawn=0",
            (deposit_id,),
        ) as c:
            dep = await c.fetchone()
        if not dep:
            return None
        await db.execute(
            "UPDATE bank_deposits SET withdrawn=1 WHERE id=?", (deposit_id,),
        )
        await db.commit()
        return dict(dep)


# ─── Магазин (покупки) ─────────────────────────────────────────────────────────

async def buy_shop_item(user_id: int, chat_id: int, item_type: str,
                        item_value: str) -> int:
    """Записать покупку товара. Возвращает id."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        cursor = await db.execute(
            """INSERT INTO shop_items (user_id, chat_id, item_type, item_value, purchased_at)
               VALUES (?, ?, ?, ?, ?) RETURNING id""",
            (user_id, chat_id, item_type, item_value, now),
        )
        row = await cursor.fetchone()
        await db.commit()
        return row[0] if row else cursor.lastrowid


async def has_shop_item(user_id: int, chat_id: int, item_type: str,
                        item_value: str | None = None) -> bool:
    """Проверить, есть ли у юзера купленный товар данного типа (и значения). Global — chat_id ignored."""
    async with postgres_connect() as db:
        if item_value is not None:
            async with db.execute(
                "SELECT 1 FROM shop_items WHERE user_id=? AND item_type=? AND item_value=?",
                (user_id, item_type, item_value),
            ) as c:
                return await c.fetchone() is not None
        else:
            async with db.execute(
                "SELECT 1 FROM shop_items WHERE user_id=? AND item_type=?",
                (user_id, item_type),
            ) as c:
                return await c.fetchone() is not None


async def get_user_owned_frames(user_id: int, chat_id: int) -> set[str]:
    """Вернуть set ключей рамок, которые юзер уже купил. Global — chat_id ignored."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT item_value FROM shop_items WHERE user_id=? AND item_type='frame'",
            (user_id,),
        ) as c:
            rows = await c.fetchall()
    return {r[0] for r in rows}


async def add_shop_item(user_id: int, item_type: str, item_value: str) -> None:
    """Добавить предмет (рамку или косметику) в shop_items. chat_id=0 — глобально."""
    async with postgres_connect() as db:
        # Avoid duplicates: skip if exact (user_id, item_type, item_value) already exists
        async with db.execute(
            "SELECT 1 FROM shop_items WHERE user_id=? AND item_type=? AND item_value=?",
            (user_id, item_type, item_value),
        ) as c:
            exists = await c.fetchone()
        if not exists:
            await db.execute(
                "INSERT INTO shop_items (user_id, chat_id, item_type, item_value, purchased_at)"
                " VALUES (?, 0, ?, ?, NOW())",
                (user_id, item_type, item_value),
            )
            await db.commit()


async def add_vip_days(user_id: int, chat_id: int, days: int) -> None:
    """Добавить VIP на N дней. Если уже есть — продлить; если нет — начать с сейчас."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, vip, vip_expires_at)
               VALUES (?, ?, 1, NOW() + ?::INTERVAL)
               ON CONFLICT(user_id, chat_id) DO UPDATE
               SET vip = 1,
                   vip_expires_at = GREATEST(
                       COALESCE(user_mora.vip_expires_at, NOW()),
                       NOW()
                   ) + ?::INTERVAL""",
            (user_id, chat_id, f"{days} days", f"{days} days"),
        )
        await db.commit()


async def has_active_cosmetic(user_id: int, item_value: str) -> bool:
    """Проверить, есть ли у пользователя активная косметика с данным item_value."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT 1 FROM shop_items WHERE user_id=? AND item_type='cosmetic' AND item_value=?",
            (user_id, item_value),
        ) as c:
            return bool(await c.fetchone())


async def set_pet_color(user_id: int, chat_id: int, color_name: str):
    """Установить цвет имени глобального питомца."""
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE pets_global SET color_name=? WHERE user_id=?",
            (color_name, user_id),
        )
        # Обновить и у партнёра
        async with db.execute(
            "SELECT partner_id FROM marriages_global WHERE user_id=?",
            (user_id,),
        ) as c:
            m = await c.fetchone()
        if m:
            await db.execute(
                "UPDATE pets_global SET color_name=? WHERE user_id=?",
                (color_name, m[0]),
            )
        await db.commit()


async def set_pet_emoji_status(user_id: int, chat_id: int, emoji_status: str):
    """Установить эмодзи-статус глобального питомца."""
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE pets_global SET emoji_status=? WHERE user_id=?",
            (emoji_status, user_id),
        )
        async with db.execute(
            "SELECT partner_id FROM marriages_global WHERE user_id=?",
            (user_id,),
        ) as c:
            m = await c.fetchone()
        if m:
            await db.execute(
                "UPDATE pets_global SET emoji_status=? WHERE user_id=?",
                (emoji_status, m[0]),
            )
        await db.commit()


async def set_custom_title_in_chat(user_id: int, chat_id: int, title: str):
    """Установить кастомный титул."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_stats (user_id, chat_id, custom_title) VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET custom_title = excluded.custom_title""",
            (user_id, chat_id, title),
        )
        await db.commit()


# ─── Подарки (брак) ───────────────────────────────────────────────────────────

async def give_gift(from_user: int, to_user: int, chat_id: int,
                    gift_key: str, gift_name: str, gift_price: int):
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO marriage_gifts (from_user, to_user, chat_id, gift_key, gift_name, gift_price, gifted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (from_user, to_user, chat_id, gift_key, gift_name, gift_price, now),
        )
        await db.commit()


async def get_gifts_summary(user_id: int, partner_id: int, chat_id: int) -> tuple[int, int]:
    """Возвращает (count, total_value) подарков между парой."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT COUNT(*), COALESCE(SUM(gift_price), 0)
               FROM marriage_gifts
               WHERE chat_id=? AND (
                   (from_user=? AND to_user=?) OR (from_user=? AND to_user=?)
               )""",
            (chat_id, user_id, partner_id, partner_id, user_id),
        ) as c:
            row = await c.fetchone()
            return (row[0] or 0, row[1] or 0)


async def get_received_gifts(user_id: int, chat_id: int) -> list[dict]:
    """Список полученных подарков: [{gift_key, gift_name, count}]."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT gift_key, gift_name, COUNT(*) as cnt
               FROM marriage_gifts
               WHERE to_user=? AND chat_id=?
               GROUP BY gift_key, gift_name
               ORDER BY cnt DESC""",
            (user_id, chat_id),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


# ─── Баффы ────────────────────────────────────────────────────────────────────

async def add_buff(user_id: int, chat_id: int, buff_type: str,
                   hours: int, source: str = ""):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=hours)
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO active_buffs (user_id, chat_id, buff_type, expires_at, source)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, chat_id, buff_type, expires, source),
        )
        await db.commit()


async def get_active_buffs(user_id: int, chat_id: int) -> list:
    """Вернуть все активные (не истёкшие) баффы."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM active_buffs WHERE user_id=? AND chat_id=? AND expires_at > ?",
            (user_id, chat_id, now),
        ) as c:
            return await c.fetchall()


async def get_mora_boost_pct(user_id: int, chat_id: int) -> float:
    """Вернуть суммарный процент бонуса к добыче моры из баффов (0.0 – 1.0)."""
    buffs = await get_active_buffs(user_id, chat_id)
    pct = 0.0
    for b in buffs:
        bt = b["buff_type"]
        if bt == "mora_boost_10":
            pct += 0.10
        elif bt == "mora_boost_15":
            pct += 0.15
        elif bt == "mora_boost_20":
            pct += 0.20
    return pct


# ─── Активные чаты для налоговых/scheduler ивентов ────────────────────────────

async def get_active_group_chat_ids() -> list[int]:
    """Вернуть все активные групповые чаты (исключая изолированные: admin_groups + test_chats)."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT chat_id FROM chats WHERE is_active=1 AND chat_type IN ('group','supergroup')"
        ) as c:
            ids = [r[0] for r in await c.fetchall()]
    return [cid for cid in ids if not is_isolated_chat(cid)]


# ═══════════════════════════════════════════════════════════════════════════════
#  🎨  Темы профиля
# ═══════════════════════════════════════════════════════════════════════════════

async def get_user_themes(user_id: int, chat_id: int) -> list:
    """Вернуть все темы, которыми владеет юзер. Global — chat_id ignored."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT DISTINCT ON (theme_key) * FROM user_themes WHERE user_id=? ORDER BY theme_key, obtained_at",
            (user_id,),
        ) as c:
            return await c.fetchall()


async def add_user_theme(user_id: int, chat_id: int, theme_key: str, source: str = "shop"):
    """Добавить тему юзеру (если ещё нет). Global — inserts only when (user_id, theme_key) doesn't exist."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_themes (user_id, chat_id, theme_key, source, obtained_at)
               SELECT ?, ?, ?, ?, ?
               WHERE NOT EXISTS (SELECT 1 FROM user_themes WHERE user_id=? AND theme_key=?)""",
            (user_id, chat_id, theme_key, source, now, user_id, theme_key),
        )
        await db.commit()


async def set_active_theme(user_id: int, chat_id: int, theme_key: str):
    """Установить активную тему профиля."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, active_theme)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET active_theme=?""",
            (user_id, chat_id, theme_key, theme_key),
        )
        await db.commit()


async def get_active_theme(user_id: int, chat_id: int) -> str:
    """Вернуть ключ активной темы (по умолчанию 'default')."""
    row = await get_mora(user_id, chat_id)
    if row and row["active_theme"]:
        return row["active_theme"]
    return "default"


# ═══════════════════════════════════════════════════════════════════════════════
#  🏅  Бейджи (значки)
# ═══════════════════════════════════════════════════════════════════════════════

async def get_user_badges(user_id: int, chat_id: int) -> list:
    """Вернуть все бейджи юзера."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT badge_key FROM user_badges WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            return [r["badge_key"] for r in await c.fetchall()]


async def award_badge(user_id: int, chat_id: int, badge_key: str):
    """Дать бейдж юзеру (если ещё нет)."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_badges (user_id, chat_id, badge_key, obtained_at) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING""",
            (user_id, chat_id, badge_key, datetime.now(timezone.utc)),
        )
        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
#  👋  Личные приветствия
# ═══════════════════════════════════════════════════════════════════════════════

async def get_user_greeting(user_id: int, chat_id: int):
    """Вернуть строку greeting (template_key) или None."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM user_greetings WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            return await c.fetchone()


async def set_user_greeting(user_id: int, chat_id: int, template_key: str, source: str = "gacha"):
    """Назначить или сменить приветствие юзеру."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_greetings (user_id, chat_id, template_key, source, obtained_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET template_key=?, source=?""",
            (user_id, chat_id, template_key, source, datetime.now(timezone.utc),
             template_key, source),
        )
        await db.commit()


async def check_greeting_today(user_id: int, chat_id: int, today_str: str) -> bool:
    """True если приветствие уже показано сегодня."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT last_greeting_date FROM user_stats WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
            if row and row["last_greeting_date"] == today_str:
                return True
    return False


async def mark_greeting_shown(user_id: int, chat_id: int, today_str: str):
    """Отметить что приветствие показано сегодня."""
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE user_stats SET last_greeting_date=? WHERE user_id=? AND chat_id=?",
            (today_str, user_id, chat_id),
        )
        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
#  ✨  Богатый сундук (замена налогового ивента)
# ═══════════════════════════════════════════════════════════════════════════════

async def create_chest_event(chat_id: int, duration_sec: int = 60) -> int:
    """Создать ивент сундука. Возвращает event_id."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=duration_sec)
    async with postgres_connect() as db:
        cur = await db.execute(
            """INSERT INTO chest_events (chat_id, started_at, expires_at)
               VALUES (?, ?, ?) RETURNING id""",
            (chat_id, now, expires),
        )
        row = await cur.fetchone()
        await db.commit()
        return row[0] if row else cur.lastrowid


async def get_chest_event_winners(event_id: int) -> list:
    """Вернуть победителей сундука с именами пользователей."""
    async with postgres_connect() as db:
        async with db.execute(
            """
            SELECT c.position, c.reward, c.user_id,
                   u.username, u.full_name
            FROM chest_event_clicks c
            LEFT JOIN users u ON u.user_id = c.user_id
            WHERE c.event_id = ?
            ORDER BY c.position
            """,
            (event_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_expired_unfinished_chest_events() -> list:
    """Вернуть все ивенты с просроченным expires_at и finished=0."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT id, chat_id, message_id FROM chest_events WHERE finished=0 AND expires_at < ?",
            (now,),
        ) as cur:
            return await cur.fetchall()


async def is_user_single(user_id: int, chat_id: int) -> bool:
    """Вернуть True если у пользователя нет активного брака (глобально)."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT 1 FROM marriages_global WHERE user_id=?",
            (user_id,),
        ) as cur:
            return (await cur.fetchone()) is None


async def set_chest_event_message(event_id: int, message_id: int):
    """Обновить message_id ивента сундука."""
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE chest_events SET message_id=? WHERE id=?",
            (message_id, event_id),
        )
        await db.commit()


async def add_chest_click(event_id: int, user_id: int, position: int, reward: int) -> bool:
    """Кликнуть по сундуку. Возвращает True если клик записан (первый для юзера)."""
    try:
        async with postgres_connect() as db:
            await db.execute(
                """INSERT INTO chest_event_clicks (event_id, user_id, clicked_at, position, reward)
                   VALUES (?, ?, ?, ?, ?)""",
                (event_id, user_id, datetime.now(timezone.utc), position, reward),
            )
            await db.commit()
            return True
    except Exception:
        return False


async def get_chest_click_count(event_id: int) -> int:
    """Количество кликов по сундуку."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM chest_event_clicks WHERE event_id=?",
            (event_id,),
        ) as c:
            return (await c.fetchone())[0]


async def finish_chest_event(event_id: int):
    """Пометить ивент как завершённый."""
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE chest_events SET finished=1 WHERE id=?", (event_id,),
        )
        await db.commit()


async def get_equipped_legendary(user_id: int, chat_id: int):
    """Вернуть экипированный легендарный предмет или None."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT item_name, item_key FROM gacha_inventory WHERE user_id=? AND equipped=1 LIMIT 1",
            (user_id,),
        ) as c:
            return await c.fetchone()


async def increment_tracker(user_id: int, chat_id: int, field: str, amount: int = 1):
    """Инкрементировать один из трекинг-счётчиков в user_mora."""
    if field not in ("expeditions_sent", "chests_opened", "casino_wins"):
        return
    async with postgres_connect() as db:
        await db.execute(
            f"UPDATE user_mora SET {field} = COALESCE({field}, 0) + ? WHERE user_id=? AND chat_id=?",
            (amount, user_id, chat_id),
        )
        await db.commit()
        async with db.execute(
            f"SELECT {field} FROM user_mora WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
            new_val = row[0] if row else amount
    # Check expedition achievements when expeditions_sent is incremented
    if field == "expeditions_sent":
        try:
            from api.achievements import check_and_award as _ach
            await _ach(user_id, chat_id, "expeditions", new_val)
        except Exception:
            pass


# ─── Шпионаж ──────────────────────────────────────────────────────────────────

async def log_espionage(spy_id: int, target_id: int, chat_id: int, success: bool):
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO espionage_log (spy_id, target_id, chat_id, success, attempted_at) VALUES (?,?,?,?,?)",
            (spy_id, target_id, chat_id, 1 if success else 0, now),
        )
        await db.commit()


async def get_espionage_cooldown(spy_id: int, target_id: int, chat_id: int) -> int:
    """Сколько секунд осталось до следующей возможности шпионить за target_id. 0 = можно."""
    cooldown_sec = 3600  # 1 час кулдаун на одну пару
    since = datetime.now(timezone.utc) - timedelta(seconds=cooldown_sec)
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM espionage_log WHERE spy_id=? AND target_id=? AND chat_id=? AND attempted_at > ?",
            (spy_id, target_id, chat_id, since),
        ) as c:
            count = (await c.fetchone())[0]
    if count == 0:
        return 0
    # Find the most recent attempt to calculate remaining cooldown
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT attempted_at FROM espionage_log WHERE spy_id=? AND target_id=? AND chat_id=? ORDER BY id DESC LIMIT 1",
            (spy_id, target_id, chat_id),
        ) as c:
            row = await c.fetchone()
    if not row:
        return 0
    last = row[0]
    if isinstance(last, str):
        last = datetime.fromisoformat(last)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    remaining = cooldown_sec - int(elapsed)
    return max(0, remaining)


# ─── Облигации ────────────────────────────────────────────────────────────────

from shared_prices import BOND_DEFAULTS


async def get_bond_prices(chat_id: int) -> dict:
    """Вернуть текущие цены облигаций {key: price}.
    Биржа ГЛОБАЛЬНАЯ — цены едины во всех чатах (chat_id игнорируется)."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT bond_key, price FROM bond_prices WHERE chat_id=0",
        ) as c:
            rows = await c.fetchall()
    prices = {r["bond_key"]: r["price"] for r in rows}
    # Fill defaults for any missing bonds
    for key, info in BOND_DEFAULTS.items():
        if key not in prices:
            prices[key] = info["base_price"]
    return prices


async def update_bond_prices(chat_id: int):
    """
    Update bond prices with realistic market dynamics:
      • Gaussian random walk  (σ = per-asset volatility)
      • Market correlation    (global_mood ±2% applied to every asset)
      • Mean reversion        (if price > 40% off base, 60% chance to pull back)
      • Volatility spikes     (1% chance per asset — "black swan" σ × 5-10×)
      • Bull / Bear trend     (10% chance per tick to enter; lasts 2-3 ticks; ±5% mood bias)
      • History pruning       (keep only last 24 records)
    Биржа ГЛОБАЛЬНАЯ — chat_id игнорируется, всегда используется chat_id=0.
    """
    import random
    import math

    current = await get_bond_prices(0)
    now = datetime.now(timezone.utc)

    # ── 1. Load / advance bull/bear state ────────────────────────────────────
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT trend, ticks_left FROM market_state WHERE chat_id=0",
        ) as c:
            state_row = await c.fetchone()

    trend = "neutral"
    ticks_left = 0
    if state_row:
        trend      = state_row["trend"]
        ticks_left = state_row["ticks_left"]

    # Decrement active trend; roll for new one if expired
    if ticks_left > 0:
        ticks_left -= 1
        if ticks_left == 0:
            trend = "neutral"
    if trend == "neutral" and random.random() < 0.12:   # 12% chance each tick
        trend      = random.choice(["bull", "bear"])
        ticks_left = random.randint(2, 3)

    # Trend bias on global mood
    trend_bias = 0.05 if trend == "bull" else (-0.05 if trend == "bear" else 0.0)

    # ── 2. Global market mood (correlation) ──────────────────────────────────
    global_mood = random.gauss(0, 0.01) + trend_bias   # σ=1%, shifted by trend

    # ── 3. Per-asset price calculation ───────────────────────────────────────
    new_prices: dict[str, int] = {}
    async with postgres_connect() as db:
        for key, info in BOND_DEFAULTS.items():
            base_price  = info["base_price"]
            vol         = info["volatility"]
            cap_mult    = info.get("cap_mult", 5)
            old_price   = current.get(key, base_price)

            # Volatility spike (black swan) — 1% chance
            sigma = vol
            if random.random() < 0.01:
                sigma = vol * random.uniform(5, 10)

            # Gaussian random walk
            delta = random.gauss(0, sigma) + global_mood

            # Mean reversion: if price is >40% off base, 60% chance to correct
            deviation = (old_price - base_price) / base_price
            if abs(deviation) > 0.40 and random.random() < 0.60:
                # Pull toward base proportional to deviation
                reversion = -math.copysign(min(abs(deviation) * 0.30, vol * 2), deviation)
                delta += reversion

            # Soft price floor = 12% of base price (no absolute minimum — meme coins can tank to 1)
            floor_price = max(1, int(base_price * 0.12))

            # Near-floor zone: price within bottom 25% of base → add noise but NOT guaranteed rebound
            # Buying at floor is risky: 35% chance price continues to drop further
            # Threshold is based on base_price (not floor) so it works for low-base meme coins too
            if old_price <= max(int(base_price * 0.20), floor_price + 1):
                r = random.random()
                if r < 0.35:
                    # Continued drop — punishes floor-buyers
                    delta -= vol * random.uniform(0.2, 0.6)
                elif r < 0.65:
                    # Mild rebound
                    delta += vol * random.uniform(0.2, 0.5)
                # else: neutral (remaining ~35%) — stays near floor

            raw_price = round(old_price * (1 + delta))
            # Soft floor: 70% bounce back to floor, 30% can pierce through (goes to 1)
            if raw_price < floor_price:
                if random.random() < 0.70:
                    new_price = floor_price
                else:
                    new_price = max(1, raw_price)
            else:
                new_price = raw_price
            new_price = min(new_price, base_price * cap_mult)
            new_prices[key] = new_price

            await db.execute(
                """INSERT INTO bond_prices (bond_key, chat_id, price, updated_at)
                   VALUES (?,0,?,?)
                   ON CONFLICT(bond_key, chat_id) DO UPDATE
                   SET price=excluded.price, updated_at=excluded.updated_at""",
                (key, new_price, now),
            )
            await db.execute(
                "INSERT INTO bond_price_history (chat_id, bond_key, price, recorded_at) VALUES (0,?,?,?)",
                (key, new_price, now),
            )
            # Prune history — keep last 120 ticks per asset (~15 days at 3h intervals)
            await db.execute(
                """DELETE FROM bond_price_history
                   WHERE chat_id=0 AND bond_key=? AND id NOT IN (
                       SELECT id FROM bond_price_history
                       WHERE chat_id=0 AND bond_key=?
                       ORDER BY id DESC LIMIT 120
                   )""",
                (key, key),
            )

        # Persist updated market state
        await db.execute(
            """INSERT INTO market_state (chat_id, trend, ticks_left, updated_at)
               VALUES (0,?,?,?)
               ON CONFLICT(chat_id) DO UPDATE
               SET trend=excluded.trend, ticks_left=excluded.ticks_left, updated_at=excluded.updated_at""",
            (trend, ticks_left, now),
        )
        await db.commit()

    return {"trend": trend, "ticks_left": ticks_left, "global_mood": round(global_mood * 100, 2)}


async def get_user_bonds(user_id: int, chat_id: int) -> list[dict]:
    """Returns user's bond holdings globally (chat_id ignored — bonds are global market)."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM user_bonds WHERE user_id=? AND chat_id=0",
            (user_id,),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def get_bond_price_history(chat_id: int, bond_key: str, limit: int = 30) -> list[dict]:
    """Return recent price history for a bond (global market — chat_id ignored). Limited to last 7 days."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT price, recorded_at FROM bond_price_history
               WHERE chat_id=0 AND bond_key=?
                 AND recorded_at >= NOW() - INTERVAL '7 days'
               ORDER BY id DESC LIMIT ?""",
            (bond_key, limit),
        ) as c:
            rows = [dict(r) for r in await c.fetchall()]
    return list(reversed(rows))  # return oldest first


async def get_singles(chat_id: int, limit: int = 20) -> list[dict]:
    """Return users in this chat who have no active marriage."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT s.user_id, u.full_name, s.xp, s.level
               FROM user_stats s
               LEFT JOIN users u ON u.user_id = s.user_id
               WHERE s.chat_id = ?
                 AND s.user_id NOT IN (SELECT user_id FROM marriages_global)
               ORDER BY s.xp DESC LIMIT ?""",
            (chat_id, limit),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def get_rpg_stats(user_id: int, chat_id: int) -> dict:
    """Return combined RPG stats: base + equipped item bonuses."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM user_rpg_stats WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
        base = dict(row) if row else {
            "base_hp": 150, "base_atk": 75, "base_def": 30, "base_crit": 0.08,  # РЕБАЛАНС: увеличены базовые статы
            "weapon_id": None, "armor_id": None, "artifact_id": None,
        }
        # Sum bonuses from equipped gacha items
        bonus_atk = bonus_def = bonus_hp = bonus_crit = 0.0
        for slot_col in ("weapon_id", "armor_id", "artifact_id"):
            iid = base.get(slot_col)
            if iid:
                async with db.execute(
                    "SELECT atk, def_val, hp, crit_rate FROM gacha_inventory WHERE id=?",
                    (iid,),
                ) as ci:
                    item = await ci.fetchone()
                if item:
                    bonus_atk  += item["atk"] or 0
                    bonus_def  += item["def_val"] or 0
                    bonus_hp   += item["hp"] or 0
                    bonus_crit += item["crit_rate"] or 0.0
    return {
        "hp":        base["base_hp"] + int(bonus_hp),
        "atk":       base["base_atk"] + int(bonus_atk),
        "def":       base["base_def"] + int(bonus_def),
        "crit_rate": round(base["base_crit"] + bonus_crit, 3),
        "weapon_id": base.get("weapon_id"),
        "armor_id":  base.get("armor_id"),
        "artifact_id": base.get("artifact_id"),
    }


async def equip_item(user_id: int, chat_id: int, item_id: int, slot: str) -> str | None:
    """Equip a gacha item into a slot (weapon/armor/artifact).

    Returns the item_name on success, or None if the item wasn't found / slot invalid.
    """
    col = {"weapon": "weapon_id", "armor": "armor_id", "artifact": "artifact_id"}.get(slot)
    if not col:
        return None
    async with postgres_connect() as db:
        # Verify item belongs to user and fetch its name
        async with db.execute(
            "SELECT id, item_name FROM gacha_inventory WHERE id=? AND user_id=?",
            (item_id, user_id),
        ) as c:
            row = await c.fetchone()
        if not row:
            return None
        item_name = row["item_name"]
        await db.execute(
            f"""INSERT INTO user_rpg_stats (user_id, chat_id, {col})
                VALUES (?,?,?)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET {col}=excluded.{col}""",
            (user_id, chat_id, item_id),
        )
        await db.commit()
    return item_name



async def buy_bonds(user_id: int, chat_id: int, bond_key: str, amount: int, price_per: int) -> bool:
    """Купить облигации. Биржа глобальна — chat_id игнорируется (используется 0)."""
    total_invested = amount * price_per
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        # Record individual lot for per-lot tracking (FIFO sell)
        await db.execute(
            """INSERT INTO user_bond_lots (user_id, chat_id, bond_key, quantity, price_per, bought_at)
               VALUES (?,0,?,?,?,?)""",
            (user_id, bond_key, amount, price_per, now),
        )
        # Keep aggregate table in sync for display compatibility
        await db.execute(
            """INSERT INTO user_bonds (user_id, chat_id, bond_key, amount, invested)
               VALUES (?,0,?,?,?)
               ON CONFLICT(user_id, chat_id, bond_key)
               DO UPDATE SET amount   = user_bonds.amount   + excluded.amount,
                             invested = user_bonds.invested + excluded.invested""",
            (user_id, bond_key, amount, total_invested),
        )
        await db.commit()
    return True


async def sell_bonds(user_id: int, chat_id: int, bond_key: str, amount: int,
                     credit_mora: int = 0) -> tuple[bool, int]:
    """Продать облигации методом FIFO по лотам. Биржа глобальная — chat_id игнорируется (используется 0).
    Если credit_mora > 0, начисляет эту сумму пользователю В ТОЙ ЖЕ транзакции (атомарно).
    Возвращает (success, actual_amount_sold)."""
    async with postgres_connect() as db:
        # Verify total holding
        async with db.execute(
            "SELECT COALESCE(SUM(quantity),0) AS total FROM user_bond_lots WHERE user_id=? AND chat_id=0 AND bond_key=?",
            (user_id, bond_key),
        ) as c:
            row = await c.fetchone()
        total_held = row["total"] if row else 0
        if total_held < amount:
            # Data inconsistency: aggregate may have bonds bought before lot tracking.
            # Check user_bonds aggregate and synthesize missing lots if needed.
            async with db.execute(
                "SELECT amount, invested FROM user_bonds WHERE user_id=? AND chat_id=0 AND bond_key=?",
                (user_id, bond_key),
            ) as c:
                agg_row = await c.fetchone()
            agg_amount = agg_row["amount"] if agg_row else 0
            if agg_amount < amount:
                return (False, 0)
            # Reconcile: insert synthetic lot for the delta
            missing_qty = agg_amount - total_held
            if missing_qty > 0:
                avg_price = int(agg_row["invested"] / agg_amount) if agg_amount > 0 else 0
                await db.execute(
                    "INSERT INTO user_bond_lots (user_id, chat_id, bond_key, quantity, price_per, bought_at)"
                    " VALUES (?,0,?,?,?,NOW())",
                    (user_id, bond_key, missing_qty, avg_price),
                )
            total_held = agg_amount

        # Fetch lots oldest-first (FIFO)
        async with db.execute(
            "SELECT id, quantity FROM user_bond_lots WHERE user_id=? AND chat_id=0 AND bond_key=? ORDER BY bought_at ASC, id ASC",
            (user_id, bond_key),
        ) as c:
            lots = [dict(r) for r in await c.fetchall()]

        remaining = amount
        for lot in lots:
            if remaining <= 0:
                break
            if lot["quantity"] <= remaining:
                # Consume this lot entirely
                await db.execute("DELETE FROM user_bond_lots WHERE id=?", (lot["id"],))
                remaining -= lot["quantity"]
            else:
                # Partially consume this lot
                await db.execute(
                    "UPDATE user_bond_lots SET quantity = quantity - ? WHERE id=?",
                    (remaining, lot["id"]),
                )
                remaining = 0

        # Update aggregate; proportionally reduce invested
        async with db.execute(
            "SELECT amount, invested FROM user_bonds WHERE user_id=? AND chat_id=0 AND bond_key=?",
            (user_id, bond_key),
        ) as c:
            agg = await c.fetchone()
        if agg:
            new_amount = agg["amount"] - amount
            if new_amount <= 0:
                await db.execute(
                    "DELETE FROM user_bonds WHERE user_id=? AND chat_id=0 AND bond_key=?",
                    (user_id, bond_key),
                )
            else:
                frac = amount / agg["amount"]
                new_invested = max(0, int(agg["invested"] * (1 - frac)))
                await db.execute(
                    "UPDATE user_bonds SET amount=?, invested=? WHERE user_id=? AND chat_id=0 AND bond_key=?",
                    (new_amount, new_invested, user_id, bond_key),
                )
        await db.commit()

        if credit_mora > 0:
            await db.execute(
                """UPDATE users SET
                       balance      = GREATEST(0, COALESCE(balance, 0) + ?),
                       total_earned = COALESCE(total_earned, 0) + ?
                   WHERE user_id = ?""",
                (credit_mora, credit_mora, user_id),
            )
            await db.commit()

    return (True, amount)


# ─── Казна чата ──────────────────────────────────────────────────────────────

async def get_treasury(chat_id: int) -> int:
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT balance FROM chat_treasury WHERE chat_id=?", (chat_id,)
        ) as c:
            row = await c.fetchone()
    return row[0] if row else 0


async def add_to_treasury(
    chat_id: int,
    amount: int,
    source: str = "",
    user_id: int = 0,
) -> int:
    """Добавляет amount в казну чата и логирует НДС-транзакцию. Возвращает новый баланс."""
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO chat_treasury (chat_id, balance) VALUES (?,?)"
            " ON CONFLICT(chat_id) DO UPDATE SET balance = chat_treasury.balance + excluded.balance",
            (chat_id, amount),
        )
        if source or user_id:
            await db.execute(
                """INSERT INTO treasury_log (chat_id, user_id, amount, source, created_at)
                   VALUES (?,?,?,?,NOW())""",
                (chat_id, user_id, amount, source),
            )
        await db.commit()
        async with db.execute(
            "SELECT balance FROM chat_treasury WHERE chat_id=?", (chat_id,)
        ) as c:
            row = await c.fetchone()
    return row[0] if row else amount


async def reset_treasury(chat_id: int):
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE chat_treasury SET balance = 0 WHERE chat_id=?", (chat_id,)
        )
        await db.commit()


# ─── Персистентное состояние планировщика ─────────────────────────────────────

async def get_scheduler_state(task_key: str) -> str | None:
    """Получить сохранённое значение для задачи планировщика."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT value FROM scheduler_state WHERE task_key=?",
            (task_key,),
        ) as c:
            row = await c.fetchone()
    return row["value"] if row else None


async def set_scheduler_state(task_key: str, value: str) -> None:
    """Сохранить значение для задачи планировщика (upsert)."""
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO scheduler_state (task_key, value, updated_at) VALUES (?,?,NOW()) "
            "ON CONFLICT(task_key) DO UPDATE SET value=excluded.value, updated_at=NOW()",
            (task_key, value),
        )
        await db.commit()


# ─── Усталость питомца ───────────────────────────────────────────────────────

async def get_pet_fatigue(user_id: int, chat_id: int) -> int:
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT fatigue FROM pets_global WHERE user_id=?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
    return row[0] if row else 0


async def add_pet_fatigue(user_id: int, chat_id: int, amount: int):
    """Увеличивает усталость глобального питомца (max 100)."""
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE pets_global SET fatigue = LEAST(100, COALESCE(fatigue,0) + ?) WHERE user_id=?",
            (amount, user_id),
        )
        await db.commit()


async def reduce_pet_fatigue(user_id: int, chat_id: int, amount: int):
    """Уменьшает усталость глобального питомца (min 0)."""
    async with postgres_connect() as db:
        await db.execute(
            "UPDATE pets_global SET fatigue = GREATEST(0, COALESCE(fatigue,0) - ?) WHERE user_id=?",
            (amount, user_id),
        )
        await db.commit()


async def start_pet_walk(user_id: int, chat_id: int) -> tuple[bool, int]:
    """Start a 3-hour pet walk. Returns (ok, mins_left_existing_walk).
    On success: reduces fatigue by 30, sets walk_end_at = now+3h.
    Returns (False, mins_left) if walk already in progress.
    NOTE: This is a thin wrapper — prefer start_pet_walk_full() for new code."""
    result = await start_pet_walk_full(user_id, chat_id)
    if result["ok"]:
        return True, 0
    return False, result.get("mins_left", 0)


# ──────────────────────────────────────────────────────────────────────────────
# ЕДИНАЯ СЕРВИСНАЯ ФУНКЦИЯ — ЕДИНСТВЕННЫЙ ИСТОЧНИК ПРАВДЫ ДЛЯ ЛОГИКИ ПРОГУЛКИ
# Используется и ботом, и Mini App. НЕ ДУБЛИРОВАТЬ ЛОГИКУ НИГДЕ БОЛЬШЕ.
# ──────────────────────────────────────────────────────────────────────────────
WALK_DURATION_HOURS = 3
WALK_FATIGUE_REDUCTION = 30
WALK_MORA_REWARD = 20  # получает хозяин И партнёр


async def start_pet_walk_full(user_id: int, chat_id: int) -> dict:
    """Единая логика выгула глобального питомца.

    Returns dict:
      ok=True  → "pet_type","pet_name","fatigue","walk_mins","reward","partner_rewarded"
      ok=False → "error" (str), optional "mins_left" (int) if already walking
    """
    from datetime import timedelta, timezone
    async with postgres_connect() as db:

        # 1. Читаем глобального питомца
        async with db.execute(
            "SELECT pet_type, name, COALESCE(fatigue,0) AS fatigue, walk_end_at "
            "FROM pets_global WHERE user_id=?",
            (user_id,),
        ) as c:
            pet = await c.fetchone()

        if not pet:
            return {"ok": False, "error": "У тебя нет питомца"}

        now = datetime.now(timezone.utc)

        # 2. Проверяем уже идущую прогулку
        if pet["walk_end_at"]:
            try:
                end_dt = datetime.fromisoformat(str(pet["walk_end_at"]))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                if end_dt > now:
                    mins_left = int((end_dt - now).total_seconds() / 60) + 1
                    return {
                        "ok": False,
                        "error": f"Питомец уже на прогулке. Осталось {mins_left} мин.",
                        "mins_left": mins_left,
                    }
            except Exception:
                pass

        # 3. Обновляем глобального питомца
        new_fatigue = max(0, pet["fatigue"] - WALK_FATIGUE_REDUCTION)
        walk_end_dt = now + timedelta(hours=WALK_DURATION_HOURS)
        await db.execute(
            "UPDATE pets_global SET fatigue=?, walk_end_at=? WHERE user_id=?",
            (new_fatigue, walk_end_dt, user_id),
        )

        # 4. Начисляем Мору хозяину (глобальный баланс)
        await db.execute(
            "UPDATE users SET balance = COALESCE(balance,0) + ?,"
            " total_earned = COALESCE(total_earned,0) + ? WHERE user_id=?",
            (WALK_MORA_REWARD, WALK_MORA_REWARD, user_id),
        )

        # 5. Начисляем Мору партнёру (если есть глобальный брак)
        partner_id: int | None = None
        async with db.execute(
            "SELECT partner_id FROM marriages_global WHERE user_id=?",
            (user_id,),
        ) as c:
            marriage = await c.fetchone()
        if marriage:
            partner_id = marriage["partner_id"]
            await db.execute(
                "UPDATE users SET balance = COALESCE(balance,0) + ?,"
                " total_earned = COALESCE(total_earned,0) + ? WHERE user_id=?",
                (WALK_MORA_REWARD, WALK_MORA_REWARD, partner_id),
            )

        await db.commit()

    return {
        "ok": True,
        "pet_type": pet["pet_type"],
        "pet_name": pet["name"] or "Питомец",
        "fatigue": new_fatigue,
        "fatigue_reduced": WALK_FATIGUE_REDUCTION,
        "walk_mins": WALK_DURATION_HOURS * 60,
        "reward": WALK_MORA_REWARD,
        "partner_rewarded": partner_id is not None,
        "partner_id": partner_id,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  💎 КРИСТАЛЛЫ — премиум-валюта (Telegram Stars)
# ═══════════════════════════════════════════════════════════════════════════════

async def get_crystals(user_id: int) -> int:
    """Возвращает текущий баланс кристаллов пользователя."""
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT balance FROM user_crystals WHERE user_id=?", (user_id,)
        )
    return row["balance"] if row else 0


async def add_crystals(user_id: int, amount: int) -> int:
    """Начисляет кристаллы; возвращает новый баланс."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO user_crystals (user_id, balance, total_purchased)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE
               SET balance         = user_crystals.balance + EXCLUDED.balance,
                   total_purchased = user_crystals.total_purchased + EXCLUDED.total_purchased""",
            (user_id, amount, amount),
        )
        row = await db.fetchone(
            "SELECT balance FROM user_crystals WHERE user_id=?", (user_id,)
        )
        await db.commit()
    return row["balance"] if row else amount


async def spend_crystals(user_id: int, amount: int) -> bool:
    """Списывает кристаллы. Возвращает True при успехе, False — недостаточно средств."""
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT balance FROM user_crystals WHERE user_id=?", (user_id,)
        )
        balance = row["balance"] if row else 0
        if balance < amount:
            return False
        await db.execute(
            "UPDATE user_crystals SET balance = balance - ? WHERE user_id = ?",
            (amount, user_id),
        )
        await db.commit()
    return True


async def log_stars_purchase(
    user_id: int, stars_amount: int, crystals_amount: int,
    pack_key: str, telegram_charge_id: str = "",
) -> None:
    """Записывает покупку кристаллов за Stars в журнал."""
    from datetime import datetime, timezone
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO stars_purchases
               (user_id, stars_amount, crystals_amount, pack_key, telegram_charge_id, purchased_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, stars_amount, crystals_amount, pack_key,
             telegram_charge_id, datetime.now(timezone.utc)),
        )
        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
#  🟢 ONLINE STATUS — mini app heartbeat
# ═══════════════════════════════════════════════════════════════════════════════

async def touch_miniapp_online(user_id: int) -> None:
    """Update last_seen for the mini app online indicator."""
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO miniapp_online (user_id, last_seen)
               VALUES (?, NOW())
               ON CONFLICT(user_id) DO UPDATE SET last_seen = NOW()""",
            (user_id,),
        )
        await db.commit()


async def get_online_status(user_id: int) -> dict:
    """Return online status for a single user."""
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT last_seen FROM miniapp_online WHERE user_id=?", (user_id,),
        )
    if not row:
        return {"online": False, "status": "offline", "last_seen": None}
    from datetime import datetime, timezone
    last = row["last_seen"]
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    diff = (datetime.now(timezone.utc) - last).total_seconds()
    if diff < 90:
        return {"online": True, "status": "online", "last_seen": str(last)}
    elif diff < 300:
        return {"online": False, "status": "recently", "last_seen": str(last)}
    return {"online": False, "status": "offline", "last_seen": str(last)}


# ── Block 3: Crystal shop item helpers ────────────────────────────────────────

async def get_transfer_passes(user_id: int) -> int:
    """Возвращает количество пропусков переноса (для обхода 3-дневного правила)."""
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT passes FROM crystal_transfer_passes WHERE user_id=?", (user_id,)
        )
    return int(row["passes"]) if row else 0


async def use_transfer_pass(user_id: int) -> bool:
    """Тратит 1 пропуск переноса. Возвращает True если успешно."""
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE crystal_transfer_passes SET passes = passes - 1 "
            "WHERE user_id=? AND passes >= 1",
            (user_id,),
        )
        await db.commit()
    return cursor.rowcount > 0


async def add_transfer_passes(user_id: int, amount: int) -> int:
    """Добавляет пропуска переноса. Возвращает новое количество."""
    async with postgres_connect() as db:
        row = await db.fetchone(
            """INSERT INTO crystal_transfer_passes (user_id, passes)
               VALUES (?, ?)
               ON CONFLICT (user_id) DO UPDATE
               SET passes = crystal_transfer_passes.passes + ?
               RETURNING passes""",
            (user_id, amount, amount),
        )
        await db.commit()
    return int(row["passes"]) if row else amount


async def get_guarantee_scrolls(user_id: int) -> int:
    """Возвращает количество свитков гаранта."""
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT scrolls FROM crystal_guarantee_scrolls WHERE user_id=?", (user_id,)
        )
    return int(row["scrolls"]) if row else 0


async def add_guarantee_scrolls(user_id: int, amount: int) -> int:
    """Добавляет свитки гаранта. Возвращает новое количество."""
    async with postgres_connect() as db:
        row = await db.fetchone(
            """INSERT INTO crystal_guarantee_scrolls (user_id, scrolls)
               VALUES (?, ?)
               ON CONFLICT (user_id) DO UPDATE
               SET scrolls = crystal_guarantee_scrolls.scrolls + ?
               RETURNING scrolls""",
            (user_id, amount, amount),
        )
        await db.commit()
    return int(row["scrolls"]) if row else amount


async def use_guarantee_scroll(user_id: int) -> bool:
    """Тратит 1 свиток гаранта. Возвращает True если успешно."""
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE crystal_guarantee_scrolls SET scrolls = scrolls - 1 "
            "WHERE user_id=? AND scrolls >= 1",
            (user_id,),
        )
        await db.commit()
    return cursor.rowcount > 0


async def get_enhancement_stones(user_id: int) -> int:
    """Возвращает количество камней улучшения."""
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT stones FROM crystal_enhancement_stones WHERE user_id=?", (user_id,)
        )
    return int(row["stones"]) if row else 0


async def add_enhancement_stones(user_id: int, amount: int) -> int:
    """Добавляет камни улучшения. Возвращает новое количество."""
    async with postgres_connect() as db:
        row = await db.fetchone(
            """INSERT INTO crystal_enhancement_stones (user_id, stones)
               VALUES (?, ?)
               ON CONFLICT (user_id) DO UPDATE
               SET stones = crystal_enhancement_stones.stones + ?
               RETURNING stones""",
            (user_id, amount, amount),
        )
        await db.commit()
    return int(row["stones"]) if row else amount


async def use_enhancement_stone(user_id: int) -> bool:
    """Тратит 1 камень улучшения. Возвращает True если успешно."""
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE crystal_enhancement_stones SET stones = stones - 1 "
            "WHERE user_id=? AND stones >= 1",
            (user_id,),
        )
        await db.commit()
    return cursor.rowcount > 0


async def is_avatar_unlocked(user_id: int) -> bool:
    """Возвращает True если аватар уже разблокирован."""
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT user_id FROM crystal_avatar_unlocks WHERE user_id=?", (user_id,)
        )
    return row is not None


async def unlock_avatar(user_id: int, avatar_path: str | None = None) -> None:
    """Записывает разблокировку аватара, опционально сохраняя path."""
    from datetime import datetime, timezone
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO crystal_avatar_unlocks (user_id, avatar_path, unlocked_at)
               VALUES (?, ?, ?)
               ON CONFLICT (user_id) DO UPDATE
               SET avatar_path = EXCLUDED.avatar_path""",
            (user_id, avatar_path, datetime.now(timezone.utc)),
        )
        await db.commit()


async def get_avatar_path(user_id: int) -> str | None:
    """Возвращает путь к аватару или None."""
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT avatar_path FROM crystal_avatar_unlocks WHERE user_id=?", (user_id,)
        )
    return row["avatar_path"] if row else None


async def get_crystal_chat_role(user_id: int, chat_id: int) -> str | None:
    """Возвращает кастомную роль юзера в чате или None."""
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT role_text FROM crystal_chat_roles WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
    return row["role_text"] if row else None


# ─── 🅱️ Block 4: Season Pass functions ──────────────────────────────────────

async def seed_first_season():
    """Create the first test season if no seasons exist."""
    from datetime import datetime, timezone, timedelta
    
    async with postgres_connect() as db:
        # Check if any seasons exist
        row = await db.fetchone("SELECT id FROM seasons LIMIT 1")
        if row:
            return  # Season already exists
            
        # Create first test season
        now = datetime.now(timezone.utc)
        start_date = now
        end_date = now + timedelta(days=30)
        
        season_row = await db.fetchone(
            "INSERT INTO seasons (name, start_date, end_date, active) "
            "VALUES (?, ?, ?, ?) RETURNING id",
            ("Сезон Предвестника", start_date, end_date, True)
        )
        season_id = season_row["id"]
        
        # Add sample rewards for levels 1-30
        rewards = []
        for level in range(1, 31):
            # Free track rewards
            if level % 5 == 0:  # Every 5th level
                rewards.append((season_id, level, False, "mora", str(level * 50)))
            elif level % 3 == 0:  # Every 3rd level
                rewards.append((season_id, level, False, "item", "gacha_ticket"))
            else:
                rewards.append((season_id, level, False, "mora", str(level * 20)))
                
            # Premium track rewards
            if level == 30:
                rewards.append((season_id, level, True, "title", "🌟 Завершитель Сезона"))
            elif level % 10 == 0:  # Every 10th level
                rewards.append((season_id, level, True, "crystals", str(level)))
            elif level % 7 == 0:  # Every 7th level
                rewards.append((season_id, level, True, "item", "enhancement_stone"))
            else:
                rewards.append((season_id, level, True, "mora", str(level * 40)))
        
        # Insert all rewards
        for season_id, level, is_premium, reward_type, reward_data in rewards:
            await db.execute(
                "INSERT INTO season_rewards (season_id, level, is_premium, reward_type, reward_data) "
                "VALUES (?, ?, ?, ?, ?)",
                (season_id, level, is_premium, reward_type, reward_data)
            )
        
        await db.commit()


async def get_active_season() -> dict | None:
    """Get currently active season."""
    from datetime import datetime, timezone
    
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT * FROM seasons WHERE active = TRUE "
            "AND start_date <= ? AND end_date >= ? "
            "ORDER BY start_date DESC LIMIT 1",
            (datetime.now(timezone.utc), datetime.now(timezone.utc))
        )
    return dict(row) if row else None


async def get_season_progress(user_id: int, season_id: int) -> dict:
    """Get user's progress in a specific season."""
    import json
    
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT * FROM season_progress WHERE user_id = ? AND season_id = ?",
            (user_id, season_id)
        )
    
    if row:
        data = dict(row)
        data["claimed_levels"] = json.loads(data["claimed_levels"] or "[]")
        return data
    else:
        return {
            "user_id": user_id,
            "season_id": season_id,
            "season_xp": 0,
            "level": 0,
            "claimed_levels": [],
            "premium_purchased": False
        }


async def add_season_xp(user_id: int, xp_amount: int) -> dict:
    """Add season XP to user. Returns {"level_up": bool, "new_level": int, "new_xp": int}."""
    import json
    
    # Check if there's an active season
    season = await get_active_season()
    if not season:
        return {"level_up": False, "new_level": 0, "new_xp": 0}
    
    season_id = season["id"]
    
    async with postgres_connect() as db:
        # Get or create progress record
        row = await db.fetchone(
            "SELECT * FROM season_progress WHERE user_id = ? AND season_id = ?",
            (user_id, season_id)
        )
        
        if row:
            current_xp = row["season_xp"]
            current_level = row["level"]
            claimed_levels = json.loads(row["claimed_levels"] or "[]")
            premium_purchased = row["premium_purchased"]
        else:
            current_xp = 0
            current_level = 0
            claimed_levels = []
            premium_purchased = False
        
        # Add XP
        new_xp = current_xp + xp_amount
        
        # Calculate new level (150 XP per level, max level 30)
        new_level = min(30, new_xp // 150)
        level_up = new_level > current_level
        
        # Update or insert progress
        await db.execute(
            """INSERT INTO season_progress (user_id, season_id, season_xp, level, claimed_levels, premium_purchased)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT (user_id, season_id) DO UPDATE
               SET season_xp = ?, level = ?""",
            (user_id, season_id, new_xp, new_level, json.dumps(claimed_levels), premium_purchased, new_xp, new_level)
        )
        await db.commit()
        
        return {
            "level_up": level_up,
            "new_level": new_level,
            "new_xp": new_xp,
            "season_name": season.get("name", "")
        }


async def claim_season_reward(user_id: int, season_id: int, level: int, is_premium: bool) -> dict:
    """Claim a season reward. Returns {"ok": bool, "reward": dict}."""
    import json
    
    async with postgres_connect() as db:
        # Get progress
        progress_row = await db.fetchone(
            "SELECT * FROM season_progress WHERE user_id = ? AND season_id = ?",
            (user_id, season_id)
        )
        
        if not progress_row:
            return {"ok": False, "error": "No progress found"}
        
        user_level = progress_row["level"]
        claimed_levels = json.loads(progress_row["claimed_levels"] or "[]")
        premium_purchased = progress_row["premium_purchased"]
        
        # Check if user has reached this level
        if user_level < level:
            return {"ok": False, "error": "Level not reached"}
        
        # Check if premium reward requires premium pass
        if is_premium and not premium_purchased:
            return {"ok": False, "error": "Premium pass required"}
        
        # Check if already claimed
        claim_key = f"{level}_{'premium' if is_premium else 'free'}"
        if claim_key in claimed_levels:
            return {"ok": False, "error": "Already claimed"}
        
        # Get reward data
        reward_row = await db.fetchone(
            "SELECT * FROM season_rewards WHERE season_id = ? AND level = ? AND is_premium = ?",
            (season_id, level, is_premium)
        )
        
        if not reward_row:
            return {"ok": False, "error": "Reward not found"}
        
        reward_type = reward_row["reward_type"]
        reward_data = reward_row["reward_data"]
        
        # Apply reward
        if reward_type == "mora":
            await add_mora(user_id, 0, int(reward_data))
        elif reward_type == "crystals":
            await add_crystals(user_id, int(reward_data))
        elif reward_type == "item":
            # Handle specific items
            if reward_data == "gacha_ticket":
                # Give free gacha ticket (not implemented yet, just give mora equivalent)
                await add_mora(user_id, 0, 120)
            elif reward_data == "enhancement_stone":
                await add_enhancement_stones(user_id, 1)
        # title rewards are cosmetic only
        
        # Mark as claimed
        claimed_levels.append(claim_key)
        await db.execute(
            "UPDATE season_progress SET claimed_levels = ? WHERE user_id = ? AND season_id = ?",
            (json.dumps(claimed_levels), user_id, season_id)
        )
        await db.commit()
        
        return {
            "ok": True,
            "reward": {
                "type": reward_type,
                "data": reward_data,
                "level": level,
                "is_premium": is_premium
            }
        }


async def buy_season_premium(user_id: int, season_id: int) -> bool:
    """Buy premium pass for season. Returns True if successful."""
    import json
    
    # Check crystal balance (500 crystals for premium)
    crystals = await get_crystals(user_id)
    if crystals < 500:
        return False
    
    async with postgres_connect() as db:
        # Check if already purchased
        progress_row = await db.fetchone(
            "SELECT premium_purchased FROM season_progress WHERE user_id = ? AND season_id = ?",
            (user_id, season_id)
        )
        
        if progress_row and progress_row["premium_purchased"]:
            return False  # Already purchased
        
        # Spend crystals
        ok = await spend_crystals(user_id, 500)
        if not ok:
            return False
        
        # Mark premium as purchased
        if progress_row:
            await db.execute(
                "UPDATE season_progress SET premium_purchased = TRUE WHERE user_id = ? AND season_id = ?",
                (user_id, season_id)
            )
        else:
            # Create new progress record with premium
            await db.execute(
                """INSERT INTO season_progress (user_id, season_id, season_xp, level, claimed_levels, premium_purchased)
                   VALUES (?, ?, 0, 0, '[]', TRUE)""",
                (user_id, season_id)
            )
        
        await db.commit()
        return True


async def get_season_rewards(season_id: int) -> list[dict]:
    """Get all rewards for a season."""
    async with postgres_connect() as db:
        rows = await db.fetch(
            "SELECT * FROM season_rewards WHERE season_id = ? ORDER BY level, is_premium",
            (season_id,)
        )
    return [dict(row) for row in rows]


# ═══════════════════════════════════════════════════════════════════════════════


async def set_crystal_chat_role(user_id: int, chat_id: int, role_text: str) -> None:
    """Устанавливает кастомную роль юзера в чате."""
    from datetime import datetime, timezone
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO crystal_chat_roles (user_id, chat_id, role_text, purchased_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (user_id, chat_id) DO UPDATE
               SET role_text = EXCLUDED.role_text, purchased_at = EXCLUDED.purchased_at""",
            (user_id, chat_id, role_text, datetime.now(timezone.utc)),
        )
        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
#  🏗️ CHAT CONFIGS — конфигурация бота по чатам (multi-tenant)
# ═══════════════════════════════════════════════════════════════════════════════

_CHAT_CONFIG_DEFAULTS = {
    "display_name":   "Предвестник",
    "theme_pack":     "default",
    "currency_name":  "Мора",
    "currency_emoji": "🪙",
    "gacha_enabled":  True,
    "casino_enabled": True,
    "boss_enabled":   True,
    "custom_config":  {},
    "owner_user_id":  None,
}


async def get_chat_config(chat_id: int) -> dict:
    """Возвращает конфигурацию чата; если не задана — возвращает дефолты."""
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT * FROM chat_configs WHERE chat_id=?", (chat_id,)
        )
    if not row:
        return dict(_CHAT_CONFIG_DEFAULTS)
    import json
    return {
        "display_name":   row["display_name"],
        "theme_pack":     row["theme_pack"],
        "currency_name":  row["currency_name"],
        "currency_emoji": row["currency_emoji"],
        "gacha_enabled":  bool(row["gacha_enabled"]),
        "casino_enabled": bool(row["casino_enabled"]),
        "boss_enabled":   bool(row["boss_enabled"]),
        "custom_config":  json.loads(row["custom_config"] or "{}"),
        "owner_user_id":  row["owner_user_id"],
    }


async def upsert_chat_config(chat_id: int, **kwargs) -> None:
    """Обновляет (или создаёт) конфигурацию чата."""
    import json
    allowed = {
        "display_name", "theme_pack", "currency_name", "currency_emoji",
        "gacha_enabled", "casino_enabled", "boss_enabled",
        "custom_config", "owner_user_id",
    }
    kwargs = {k: v for k, v in kwargs.items() if k in allowed}
    if "custom_config" in kwargs and isinstance(kwargs["custom_config"], dict):
        kwargs["custom_config"] = json.dumps(kwargs["custom_config"], ensure_ascii=False)

    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO chat_configs (chat_id) VALUES (?) ON CONFLICT DO NOTHING",
            (chat_id,),
        )
        for key, value in kwargs.items():
            await db.execute(
                f"UPDATE chat_configs SET {key}=? WHERE chat_id=?",
                (value, chat_id),
            )
        await db.commit()



# ─── Топ-10 по недельной активности (для дивидендов) ─────────────────────────

async def get_weekly_top_users(chat_id: int, limit: int = 10) -> list[int]:
    """Возвращает list user_id по убыванию сообщений за текущую неделю."""
    from datetime import date
    week_start = date.today().strftime("%Y-%m-") + str(
        date.today().day - date.today().weekday()
    ).zfill(2)
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT user_id, SUM(message_count) as cnt
               FROM user_stats
               WHERE chat_id=?
               GROUP BY user_id
               ORDER BY cnt DESC LIMIT ?""",
            (chat_id, limit),
        ) as c:
            rows = await c.fetchall()
    return [r[0] for r in rows]


# ─── Weekly top-10 message rewards ───────────────────────────────────────────

WEEKLY_TOP_REWARDS = {1: 500, 2: 450, 3: 400, 4: 350, 5: 300,
                      6: 250, 7: 200, 8: 150, 9: 100, 10: 50}


async def is_weekly_top_rewarded(chat_id: int, week_key: str) -> bool:
    """True if rewards for this chat+week were already distributed."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT 1 FROM weekly_top_reward_log WHERE chat_id=? AND week_key=? LIMIT 1",
            (chat_id, week_key),
        ) as c:
            return (await c.fetchone()) is not None


async def record_weekly_top_rewards(chat_id: int, week_key: str,
                                    rewards: list[tuple[int, int, int, str]]) -> None:
    """Save reward records and credit each user's mora.
    rewards: list of (user_id, place, amount, full_name)
    """
    async with postgres_connect() as db:
        for uid, place, amount, fname in rewards:
            await db.execute(
                """INSERT INTO weekly_top_reward_log
                       (chat_id, week_key, user_id, place, amount, full_name)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT DO NOTHING""",
                (chat_id, week_key, uid, place, amount, fname),
            )
        await db.commit()
    # Credit mora outside the transaction loop to avoid holding connection
    for uid, place, amount, fname in rewards:
        await add_mora(uid, chat_id, amount)


async def get_weekly_top_reward_history(chat_id: int, week_key: str) -> list:
    """Return reward records for a given chat+week, ordered by place."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT user_id, place, amount, full_name
               FROM weekly_top_reward_log
               WHERE chat_id=? AND week_key=?
               ORDER BY place ASC""",
            (chat_id, week_key),
        ) as c:
            return await c.fetchall()


async def get_vip_users(chat_id: int) -> list[int]:
    """Возвращает list user_id у кого активный (не истёкший) vip=1 в данном чате."""
    now = datetime.now(timezone.utc)
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT user_id FROM user_mora WHERE chat_id=? AND vip=1 "
            "AND (vip_expires_at IS NULL OR vip_expires_at > ?)",
            (chat_id, now),
        ) as c:
            rows = await c.fetchall()
    return [r[0] for r in rows]


async def get_all_active_chats() -> list[int]:
    """Все основные чаты где бот активен (исключая изолированные: admin_groups + test_chats)."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT chat_id FROM chats WHERE is_active=1"
        ) as c:
            rows = await c.fetchall()
    return [r[0] for r in rows if not is_isolated_chat(r[0])]



# ─── Ежедневный чекин ─────────────────────────────────────────────────────────

from shared_prices import CHECKIN_REWARDS as _CHECKIN_REWARDS, CHECKIN_CHECKPOINTS as _CHECKIN_CHECKPOINTS
_CHECKIN_RESET_TO = {5: 5, 10: 10, 15: 15, 20: 20}  # пробел → к последнему чекпоинту


async def get_daily_checkin(user_id: int, chat_id: int) -> dict:
    """Вернуть данные ежедневного чекина юзера."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM daily_checkin WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
    if not row:
        return {"streak": 0, "total_days": 0, "last_checkin": None, "checkpoint": 0}
    return dict(row)


async def perform_checkin(user_id: int, chat_id: int) -> dict:
    """Выполнить чекин. Возвращает {ok, mora, streak, total_days, is_checkpoint, free_gacha, already_done}."""
    from utils.helpers import bot_today
    today = bot_today()

    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM daily_checkin WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()

        if row and row["last_checkin"] == today:
            return {"already_done": True, "streak": row["streak"], "total_days": row["total_days"]}

        streak = (row["streak"] if row else 0) + 1
        total_days = (row["total_days"] if row else 0) + 1
        checkpoint = row["checkpoint"] if row else 0

        # Если пропустить день — сброс к последнему чекпоинту
        if row and row["last_checkin"]:
            from datetime import date
            prev = date.fromisoformat(row["last_checkin"])
            diff = (date.fromisoformat(today) - prev).days
            if diff > 1:
                streak = min(streak, checkpoint) if checkpoint else 1

        # Capped at 20
        day_idx = min(streak, 20)
        mora_reward = _CHECKIN_REWARDS.get(day_idx, 40)
        is_checkpoint = day_idx in _CHECKIN_CHECKPOINTS
        free_gacha = (day_idx == 20)
        if is_checkpoint:
            checkpoint = day_idx

        await db.execute("""
            INSERT INTO daily_checkin (user_id, chat_id, streak, total_days, last_checkin, checkpoint)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
                streak=excluded.streak, total_days=excluded.total_days,
                last_checkin=excluded.last_checkin, checkpoint=excluded.checkpoint
        """, (user_id, chat_id, streak, total_days, today, checkpoint))
        await db.commit()

    return {
        "already_done": False,
        "ok": True,
        "mora": mora_reward,
        "streak": streak,
        "total_days": total_days,
        "is_checkpoint": is_checkpoint,
        "free_gacha": free_gacha,
    }


# ─── Boss damage log ──────────────────────────────────────────────────────────

async def add_boss_damage(user_id: int, chat_id: int, damage: int):
    """Записать урон по боссу (batch-safe, потом суммируется)."""
    from datetime import timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO boss_damage_log (user_id, chat_id, damage, session_date) VALUES (?, ?, ?, ?)",
            (user_id, chat_id, damage, today),
        )
        await db.commit()


async def get_boss_daily_user_damage(user_id: int, chat_id: int) -> int:
    """Get today's total damage by *user_id* in *chat_id* (UTC date)."""
    from datetime import timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COALESCE(SUM(damage), 0) FROM boss_damage_log "
            "WHERE user_id=? AND chat_id=? AND session_date=?",
            (user_id, chat_id, today),
        ) as c:
            row = await c.fetchone()
    return row[0] if row else 0


async def get_boss_chat_damage_today(chat_id: int) -> int:
    """Get today's total damage for the whole chat (UTC date)."""
    from datetime import timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COALESCE(SUM(damage), 0) FROM boss_damage_log "
            "WHERE chat_id=? AND session_date=?",
            (chat_id, today),
        ) as c:
            row = await c.fetchone()
    return row[0] if row else 0


async def get_boss_leaderboard(chat_id: int, limit: int = 10) -> list[dict]:
    """Топ по суммарному урону боссу в текущем чате."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT b.user_id, u.full_name, SUM(b.damage) as total_damage
               FROM boss_damage_log b
               LEFT JOIN users u ON u.user_id = b.user_id
               WHERE b.chat_id = ?
               GROUP BY b.user_id
               ORDER BY total_damage DESC LIMIT ?""",
            (chat_id, limit),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def get_boss_my_damage(user_id: int, chat_id: int) -> int:
    """Вернуть суммарный урон конкретного юзера по боссу в чате."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COALESCE(SUM(damage), 0) FROM boss_damage_log WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
    return row[0] if row else 0


# ─── Leaderboard helpers ──────────────────────────────────────────────────────

async def get_leaderboard_xp(chat_id: int, limit: int = 10) -> list[dict]:
    """Топ по XP в чате."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT s.user_id, u.full_name, s.xp, s.level,
                      p.color_name, m.vip
               FROM user_stats s
               LEFT JOIN users u ON u.user_id = s.user_id
               LEFT JOIN pets p ON p.user_id = s.user_id AND p.chat_id = s.chat_id
               LEFT JOIN user_mora m ON m.user_id = s.user_id AND m.chat_id = s.chat_id
               WHERE s.chat_id = ? ORDER BY s.xp DESC LIMIT ?""",
            (chat_id, limit),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def get_leaderboard_messages(chat_id: int, limit: int = 10) -> list[dict]:
    """Топ по сообщениям в чате."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT s.user_id, u.full_name, s.message_count,
                      p.color_name, m.vip
               FROM user_stats s
               LEFT JOIN users u ON u.user_id = s.user_id
               LEFT JOIN pets_global p ON p.user_id = s.user_id
               LEFT JOIN user_mora m ON m.user_id = s.user_id AND m.chat_id = s.chat_id
               WHERE s.chat_id = ? ORDER BY s.message_count DESC LIMIT ?""",
            (chat_id, limit),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]

# ─── Enhancement System ──────────────────────────────────────────────────────
async def enhance_item(user_id: int, chat_id: int, item_id: int) -> tuple[bool, str, int]:
    """Enhance an RPG item. Returns (success, message, new_enhancement_level)."""
    import random
    from datetime import datetime
    
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT slot, enhancement_level, atk, def_val, hp, crit_rate, item_name FROM gacha_inventory "
            "WHERE id=? AND user_id=? AND chat_id=? AND slot IN ('weapon', 'armor', 'artifact')",
            (item_id, user_id, chat_id),
        ) as c:
            item = await c.fetchone()
        
        if not item:
            return False, "Предмет не найден или его нельзя заточить", 0
        
        current_level = item[1] or 0
        if current_level >= 20:
            return False, "Максимальный уровень заточки (20)", current_level

        # Стоимость растёт геометрически
        base_cost = 80
        cost = int(base_cost * (1.3 ** current_level))

        # Check if user has enhancement stones first
        stones_count = await get_enhancement_stones(user_id)
        using_stones = stones_count > 0

        if using_stones:
            # Use free enhancement stone
            await use_enhancement_stone(user_id)
            balance = 0  # Not needed for error message, just set for consistency
        else:
            # Check mora balance
            async with db.execute(
                "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?",
                (user_id,)
            ) as c:
                balance_row = await c.fetchone()

            balance = balance_row[0] if balance_row else 0
            if balance < cost:
                return False, f"Недостаточно Моры ({balance}/{cost} 🪙)", current_level

        # ─── НОВАЯ ЛОГИКА ЗАТОЧКИ ─────────────────────────────────────────
        # До +5 включительно: ВСЕГДА успешно (100%)
        # После +5: может не пройти (остаться на уровне) или с малым шансом упасть
        #
        # Таблица при current_level < 5 (будет +1 100%)
        # +5  → 85% успех, 12% нейтрально, 3% понижение
        # +6  → 80% успех, 14% нейтрально, 6% понижение
        # +7  → 70% успех, 18% нейтрально, 12% понижение
        # +8  → 60% успех, 22% нейтрально, 18% понижение
        # +9  → 50% успех, 25% нейтрально, 25% понижение
        # +10 → 40% успех, 30% нейтрально, 30% понижение
        # +11–20 → 30% успех, 40% нейтрально, 30% понижение

        if current_level < 5:
            success_pct = 100
            neutral_pct = 0
            fail_pct = 0
        elif current_level == 5:
            success_pct, neutral_pct, fail_pct = 85, 12, 3
        elif current_level == 6:
            success_pct, neutral_pct, fail_pct = 80, 14, 6
        elif current_level == 7:
            success_pct, neutral_pct, fail_pct = 70, 18, 12
        elif current_level == 8:
            success_pct, neutral_pct, fail_pct = 60, 22, 18
        elif current_level == 9:
            success_pct, neutral_pct, fail_pct = 50, 25, 25
        elif current_level == 10:
            success_pct, neutral_pct, fail_pct = 40, 30, 30
        else:
            success_pct, neutral_pct, fail_pct = 30, 40, 30

        if not using_stones:
            # Deduct мору только если не используем камни
            cursor = await db.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id=? AND COALESCE(balance, 0) >= ?",
                (cost, user_id, cost)
            )
            if cursor.rowcount == 0:
                await db.commit()
                return False, f"Недостаточно Моры ({balance}/{cost} 🪙)", current_level

        roll = random.randint(1, 100)
        if roll <= success_pct:
            # ✅ Успех — +1 уровень
            new_level = current_level + 1
            await db.execute(
                "UPDATE gacha_inventory SET enhancement_level=? WHERE id=?",
                (new_level, item_id)
            )
            await db.commit()
            cost_msg = "🔮 Использован камень заточки" if using_stones else f"💸 Потрачено {cost} 🪙"
            return True, (
                f"✨ Заточка успешна! {item[6]} → <b>+{new_level}</b>\n"
                f"{cost_msg}\n"
                f"Шанс успеха был: {success_pct}%"
            ), new_level
        elif roll <= success_pct + neutral_pct:
            # ⚡ Нейтрально — уровень не меняется
            await db.commit()
            cost_msg = "🔮 Использован камень заточки" if using_stones else f"💸 Потрачено {cost} 🪙"
            return False, (
                f"⚡ Заточка не прошла! {item[6]} остался <b>+{current_level}</b>\n"
                f"{cost_msg}\n"
                f"Предмет цел. Шанс успеха был: {success_pct}%"
            ), current_level
        else:
            # 💔 Неудача — уровень понижается на 1 (но не ниже 0), предмет НЕ ломается
            new_level = max(0, current_level - 1)
            await db.execute(
                "UPDATE gacha_inventory SET enhancement_level=? WHERE id=?",
                (new_level, item_id)
            )
            await db.commit()
            cost_msg = "🔮 Использован камень заточки" if using_stones else f"💸 Потрачено {cost} 🪙"
            return False, (
                f"💔 Неудача! {item[6]}: +{current_level} → <b>+{new_level}</b>\n"
                f"{cost_msg}\n" 
                f"Предмет цел. Шанс успеха был: {success_pct}%"
            ), new_level


async def get_active_buffs(user_id: int, chat_id: int) -> list[dict]:
    """Get active potion buffs for user."""
    from datetime import datetime, timezone
    
    async with postgres_connect() as db:
        # Clean expired buffs first
        now = datetime.now(timezone.utc)
        await db.execute(
            "DELETE FROM active_buffs WHERE expires_at < ?", (now,)
        )
        async with db.execute(
            "SELECT * FROM active_buffs WHERE user_id=? AND chat_id=? AND expires_at > ?",
            (user_id, chat_id, now)
        ) as c:
            rows = await c.fetchall()
        await db.commit()
    
    return [dict(r) for r in rows]


async def get_user_name(user_id: int) -> str | None:
    """Get user's full name from database."""
    async with postgres_connect() as db:
        async with db.execute("SELECT full_name FROM users WHERE user_id=?", (user_id,)) as c:
            row = await c.fetchone()
        return row[0] if row else None


async def consume_potion(user_id: int, chat_id: int, item_id: int) -> tuple[bool, str]:
    """Consume a potion item to gain buff."""
    from datetime import datetime, timezone, timedelta
    
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT item_key, item_name, slot FROM gacha_inventory "
            "WHERE id=? AND user_id=? AND chat_id=? AND slot IN ('potion','consume')",
            (item_id, user_id, chat_id)
        ) as c:
            item = await c.fetchone()
        
        if not item:
            return False, "Предмет не найден"

        item_key2, item_name2, item_slot2 = item[0], item[1], item[2]

        # ── Consume (instant-effect) items ───────────────────────────────────
        if item_slot2 == 'consume':
            _CONSUME_EFFECTS = {
                'cmn_xp_shard':    ('xp',   25,  '+25 XP'),
                'cmn_herb':        ('mora', 15,  '+15 🪙'),
                'rare_xp_crystal': ('xp',  150, '+150 XP'),
                'rare_mora_bag':   ('mora', 120, '+120 🪙'),
                'rare_mora_chest': ('mora', 250, '+250 🪙'),
            }
            effect = _CONSUME_EFFECTS.get(item_key2)
            if not effect:
                return False, 'Неизвестный тип расходника'
            eff_type, eff_val, eff_desc = effect
            await db.execute('DELETE FROM gacha_inventory WHERE id=?', (item_id,))
            await db.commit()
            if eff_type == 'xp':
                await add_xp_in_chat(user_id, chat_id, eff_val)
            else:
                await add_mora(user_id, chat_id, eff_val)
            return True, f'✨ {item_name2} использован! {eff_desc}'

        # ── Potion (timed buff) items ────────────────────────────────────────────
        from shared_prices import POTIONS_CATALOG
        potion_data = POTIONS_CATALOG.get(item_key2)
        if not potion_data:
            return False, 'Неизвестный тип зелья'
        
        # Calculate expiration time
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=potion_data["duration"])
        
        # Remove any existing buff of the same type (refreshes timer)
        await db.execute(
            "DELETE FROM active_buffs WHERE user_id=? AND chat_id=? AND buff_type=?",
            (user_id, chat_id, potion_data["buff_type"])
        )
        
        # Add new buff
        await db.execute(
            "INSERT INTO active_buffs (user_id, chat_id, buff_type, expires_at, source) "
            "VALUES (?,?,?,?,?)",
            (user_id, chat_id, potion_data["buff_type"], expires_at, f"potion:{item_key2}")
        )
        
        # Remove consumed potion from inventory
        await db.execute("DELETE FROM gacha_inventory WHERE id=?", (item_id,))
        
        await db.commit()
        
        duration_text = f"{potion_data['duration']//60}ч {potion_data['duration']%60}м" if potion_data['duration'] >= 60 else f"{potion_data['duration']}м"
        return True, f"🧪 {item_name2} выпито! {potion_data['desc'].split(':')[1]} ({duration_text})"


async def batch_sell_items(
    user_id: int, chat_id: int, item_ids: list[int],
    sell_qtys: dict[int, int] | None = None,
) -> tuple[int, int]:
    """Batch sell multiple items. Returns (units_sold, total_mora).
    sell_qtys: optional {item_id: qty} to sell partial stacks."""
    if not item_ids:
        return 0, 0

    async with postgres_connect() as db:
        total_mora = 0
        sold_count = 0

        placeholders = ",".join(["?"] * len(item_ids))
        async with db.execute(
            f"SELECT id, item_key, COALESCE(stack_count, 1) FROM gacha_inventory "
            f"WHERE id IN ({placeholders}) AND user_id=? AND chat_id=?",
            (*item_ids, user_id, chat_id)
        ) as c:
            items = await c.fetchall()

        if not items:
            return 0, 0

        from shared_prices import ITEM_METADATA

        for row in items:
            item_id, item_key, stack_count = row[0], row[1], row[2]
            meta = ITEM_METADATA.get(item_key, {})
            sell_price = meta.get("sell", 0)

            if sell_price == 0:  # Skip unsellable items (legendaries, cosmetics)
                continue

            # Qty to sell: from sell_qtys or default to full stack
            qty = min(int((sell_qtys or {}).get(item_id, stack_count)), stack_count)
            qty = max(1, qty)

            total_mora += sell_price * qty
            sold_count += qty

            if qty >= stack_count:
                await db.execute("DELETE FROM gacha_inventory WHERE id=?", (item_id,))
            else:
                await db.execute(
                    "UPDATE gacha_inventory SET stack_count = stack_count - ? WHERE id=?",
                    (qty, item_id),
                )

        if sold_count > 0:
            await db.execute(
                "UPDATE users SET balance = COALESCE(balance, 0) + ?,"
                " total_earned = COALESCE(total_earned, 0) + ? WHERE user_id=?",
                (total_mora, total_mora, user_id)
            )

        await db.commit()

    return sold_count, total_mora

# --- Couple Boss System (Married Pairs) --------------------------------------

async def get_couple_boss_session(user_a_id: int, user_b_id: int, chat_id: int) -> dict | None:
    """Get active couple boss session for married pair."""
    from datetime import timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Ensure user_a_id < user_b_id for consistency
    if user_a_id > user_b_id:
        user_a_id, user_b_id = user_b_id, user_a_id
    
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT * FROM couple_boss_sessions 
               WHERE user_a_id=? AND user_b_id=? AND chat_id=? AND session_date=? AND is_completed=0""",
            (user_a_id, user_b_id, chat_id, today),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def create_couple_boss_session(user_a_id: int, user_b_id: int, chat_id: int, boss_level: int = 1) -> dict:
    """Create new couple boss session."""
    from datetime import timezone
    import random
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Ensure user_a_id < user_b_id for consistency
    if user_a_id > user_b_id:
        user_a_id, user_b_id = user_b_id, user_a_id
        
    # Boss HP scales with level: base 500k + 250k per level
    boss_max_hp = 500_000 + (boss_level - 1) * 250_000
    
    # Check if this is a repeat (already cleared this level today)
    progress = await get_couple_boss_progress(user_a_id, user_b_id, chat_id)
    is_repeat = progress and progress.get("max_level", 0) >= boss_level
    
    async with postgres_connect() as db:
        cursor = await db.execute(
            """INSERT INTO couple_boss_sessions 
               (user_a_id, user_b_id, chat_id, boss_level, boss_max_hp, boss_current_hp, 
                is_repeat, session_date)
               VALUES (?,?,?,?,?,?,?,?) RETURNING id""",
            (user_a_id, user_b_id, chat_id, boss_level, boss_max_hp, boss_max_hp, 
             1 if is_repeat else 0, today),
        )
        row = await cursor.fetchone()
        await db.commit()
        session_id = row[0] if row else None
    
    return {
        "id": session_id,
        "user_a_id": user_a_id,
        "user_b_id": user_b_id,
        "chat_id": chat_id,
        "boss_level": boss_level,
        "boss_max_hp": boss_max_hp,
        "boss_current_hp": boss_max_hp,
        "user_a_damage": 0,
        "user_b_damage": 0,
        "user_a_hits": 0,
        "user_b_hits": 0,
        "user_a_aggro": 0,
        "user_b_aggro": 0,
        "is_repeat": is_repeat,
        "is_completed": 0,
    }


async def apply_couple_boss_damage(user_id: int, session: dict, damage: int, user_stats: dict = None) -> dict:
    """Apply damage to couple boss and handle aggro system."""
    import random
    
    session_id = session["id"]
    user_a_id = session["user_a_id"]
    user_b_id = session["user_b_id"]
    
    # Determine which user is attacking
    is_user_a = (user_id == user_a_id)
    
    # Get user's combat stats from RPG system
    total_atk = (user_stats.get("atk", 0) if user_stats else 0) if user_stats else 0
    total_crit_rate = (user_stats.get("crit_rate", 0.0) if user_stats else 0.0) if user_stats else 0.0
    
    # Calculate actual damage with crit chance
    base_damage = damage
    if random.random() < total_crit_rate:
        base_damage = int(base_damage * 1.5)
        
    # Apply resistance if both players are active (hit within last 5 minutes)
    resistance = 1.0
    if session["user_a_hits"] > 0 and session["user_b_hits"] > 0:
        # Both partners active - boss gets 25% resistance
        resistance = 0.75
        
    actual_damage = int(base_damage * resistance)
    
    # Update boss HP
    new_hp = max(0, session["boss_current_hp"] - actual_damage)
    is_defeated = (new_hp == 0)
    
    # Update user's stats
    if is_user_a:
        new_a_damage = session["user_a_damage"] + actual_damage
        new_a_hits = session["user_a_hits"] + 1
        new_a_aggro = session["user_a_aggro"] + 1
        
        # Check for aggro trigger (3-8 hits)
        boss_retaliation = None
        if new_a_aggro >= random.randint(3, 8):
            # Boss attacks user A
            boss_damage = random.randint(50, 150) + session["boss_level"] * 10
            boss_retaliation = {"target": user_a_id, "damage": boss_damage}
            new_a_aggro = 0  # Reset aggro
            
        user_values = (new_a_damage, new_a_hits, new_a_aggro, session["user_b_damage"], 
                      session["user_b_hits"], session["user_b_aggro"])
    else:
        new_b_damage = session["user_b_damage"] + actual_damage
        new_b_hits = session["user_b_hits"] + 1
        new_b_aggro = session["user_b_aggro"] + 1
        
        # Check for aggro trigger (3-8 hits)
        boss_retaliation = None
        if new_b_aggro >= random.randint(3, 8):
            # Boss attacks user B
            boss_damage = random.randint(50, 150) + session["boss_level"] * 10
            boss_retaliation = {"target": user_b_id, "damage": boss_damage}
            new_b_aggro = 0  # Reset aggro
            
        user_values = (session["user_a_damage"], session["user_a_hits"], session["user_a_aggro"],
                      new_b_damage, new_b_hits, new_b_aggro)
    
    # Update database
    async with postgres_connect() as db:
        await db.execute(
            """UPDATE couple_boss_sessions SET 
               boss_current_hp=?, user_a_damage=?, user_a_hits=?, user_a_aggro=?,
               user_b_damage=?, user_b_hits=?, user_b_aggro=?, is_completed=?,
               completed_at=CASE WHEN ? THEN NOW() ELSE completed_at END
               WHERE id=?""",
            (new_hp, *user_values, 1 if is_defeated else 0, is_defeated, session_id),
        )
        
        # If boss defeated, update progress
        if is_defeated:
            await update_couple_boss_progress(user_a_id, user_b_id, session["chat_id"], session["boss_level"])
            
        await db.commit()
    
    return {
        "damage_dealt": actual_damage,
        "boss_hp": new_hp,
        "boss_defeated": is_defeated,
        "boss_retaliation": boss_retaliation,
        "resistance_active": resistance < 1.0,
        "crit": base_damage != damage,
    }


async def get_couple_boss_progress(user_a_id: int, user_b_id: int, chat_id: int) -> dict | None:
    """Get couple's boss progress (max level completed)."""
    # Ensure user_a_id < user_b_id for consistency
    if user_a_id > user_b_id:
        user_a_id, user_b_id = user_b_id, user_a_id
        
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM couple_boss_progress WHERE user_a_id=? AND user_b_id=? AND chat_id=?",
            (user_a_id, user_b_id, chat_id),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def update_couple_boss_progress(user_a_id: int, user_b_id: int, chat_id: int, completed_level: int):
    """Update couple's maximum completed boss level."""
    # Ensure user_a_id < user_b_id for consistency
    if user_a_id > user_b_id:
        user_a_id, user_b_id = user_b_id, user_a_id
        
    async with postgres_connect() as db:
        await db.execute(
            """INSERT INTO couple_boss_progress (user_a_id, user_b_id, chat_id, max_level, last_completed)
               VALUES (?,?,?,?,NOW())
               ON CONFLICT(user_a_id, user_b_id, chat_id) DO UPDATE SET
               max_level=GREATEST(couple_boss_progress.max_level, EXCLUDED.max_level),
               last_completed=NOW()""",
            (user_a_id, user_b_id, chat_id, completed_level),
        )
        await db.commit()


async def get_couple_boss_rewards(session: dict) -> dict:
    """Calculate rewards for couple boss completion."""
    boss_level = session["boss_level"]
    is_repeat = session["is_repeat"]
    
    # Base rewards scale with boss level
    base_mora_each = 200 + (boss_level - 1) * 100
    base_xp_each = 150 + (boss_level - 1) * 75
    
    # Repeat runs give only 25% rewards
    if is_repeat:
        base_mora_each = int(base_mora_each * 0.25)
        base_xp_each = int(base_xp_each * 0.25)
    
    return {
        "mora_each": base_mora_each,
        "xp_each": base_xp_each,
        "is_repeat": is_repeat,
        "level": boss_level,
    }


# ─── Marriage proposals ───────────────────────────────────────────────────────

async def create_marriage_proposal(from_user_id: int, to_user_id: int, chat_id: int) -> int | None:
    """Create a marriage proposal. Returns new proposal id, or None if duplicate.
    Предложения глобальны — chat_id сохраняется для показа откуда пришло предложение,
    но уникальность проверяется только по паре (from, to)."""
    async with postgres_connect() as db:
        cursor = await db.execute(
            """INSERT INTO marriage_proposals (from_user_id, to_user_id, chat_id)
               VALUES (?, ?, ?) ON CONFLICT(from_user_id, to_user_id, chat_id) DO UPDATE
               SET status='pending', created_at=NOW()
               RETURNING id""",
            (from_user_id, to_user_id, chat_id),
        )
        row = await cursor.fetchone()
        await db.commit()
        return row[0] if row else None


async def get_pending_proposals(to_user_id: int, chat_id: int) -> list:
    """Return incoming pending proposals for a user — globally (ignores chat_id scope)."""
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT mp.id, mp.from_user_id, u.full_name as from_name, mp.created_at
               FROM marriage_proposals mp
               JOIN users u ON u.user_id = mp.from_user_id
               WHERE mp.to_user_id=? AND mp.status='pending'
               ORDER BY mp.created_at DESC""",
            (to_user_id,),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def respond_to_proposal(proposal_id: int, status: str) -> dict | None:
    """Accept or decline a proposal. Returns proposal data if found."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM marriage_proposals WHERE id=? AND status='pending'",
            (proposal_id,),
        ) as c:
            row = await c.fetchone()
        if not row:
            return None
        proposal = dict(row)
        await db.execute(
            "UPDATE marriage_proposals SET status=? WHERE id=?",
            (status, proposal_id),
        )
        await db.commit()
    return proposal


# ─── Solo Boss ────────────────────────────────────────────────────────────────

async def get_solo_boss_session(user_id: int, chat_id: int) -> dict | None:
    """Return the current incomplete solo boss session, or None."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with postgres_connect() as db:
        async with db.execute(
            """SELECT * FROM solo_boss_sessions
               WHERE user_id=? AND chat_id=? AND session_date=? AND is_completed=0""",
            (user_id, chat_id, today),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def get_solo_boss_progress(user_id: int, chat_id: int) -> dict | None:
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT * FROM solo_boss_progress WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None


async def create_solo_boss_session(user_id: int, chat_id: int, boss_level: int = 1) -> dict:
    """Create a new solo boss session and return its data."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    progress = await get_solo_boss_progress(user_id, chat_id)
    is_repeat = progress and progress.get("max_level", 0) >= boss_level
    boss_max_hp = 300_000 + (boss_level - 1) * 150_000

    async with postgres_connect() as db:
        cursor = await db.execute(
            """INSERT INTO solo_boss_sessions
               (user_id, chat_id, boss_level, boss_max_hp, boss_current_hp, is_repeat, session_date)
               VALUES (?,?,?,?,?,?,?) RETURNING id""",
            (user_id, chat_id, boss_level, boss_max_hp, boss_max_hp, 1 if is_repeat else 0, today),
        )
        row = await cursor.fetchone()
        await db.commit()

    return {
        "id": row[0] if row else None,
        "user_id": user_id,
        "chat_id": chat_id,
        "boss_level": boss_level,
        "boss_max_hp": boss_max_hp,
        "boss_current_hp": boss_max_hp,
        "user_damage": 0,
        "user_hits": 0,
        "is_completed": 0,
        "is_repeat": is_repeat,
    }


async def apply_solo_boss_damage(user_id: int, session: dict, damage: int) -> dict:
    """Apply damage to a solo boss session. Returns result dict."""
    import random as _rnd
    session_id = session["id"]
    current_hp = session["boss_current_hp"]
    crit = _rnd.random() < 0.08
    actual_damage = int(damage * 1.5) if crit else damage
    new_hp = max(0, current_hp - actual_damage)
    is_defeated = new_hp == 0

    update_fields = "boss_current_hp=?, user_damage=user_damage+?, user_hits=user_hits+1"
    params: list = [new_hp, actual_damage]
    if is_defeated:
        update_fields += ", is_completed=1, completed_at=NOW()"

    async with postgres_connect() as db:
        await db.execute(
            f"UPDATE solo_boss_sessions SET {update_fields} WHERE id=?",
            (*params, session_id),
        )
        if is_defeated:
            boss_level = session["boss_level"]
            await db.execute(
                """INSERT INTO solo_boss_progress (user_id, chat_id, max_level, last_completed)
                   VALUES (?,?,?,NOW()::text)
                   ON CONFLICT(user_id, chat_id) DO UPDATE
                   SET max_level=GREATEST(solo_boss_progress.max_level, excluded.max_level),
                       last_completed=excluded.last_completed""",
                (user_id, session["chat_id"], boss_level),
            )
        await db.commit()

    return {
        "damage_dealt": actual_damage,
        "boss_hp": new_hp,
        "boss_defeated": is_defeated,
        "crit": crit,
    }



# ─── Error log helpers ───────────────────────────────────────────────────────

async def log_app_error(source: str, context: str, error_msg: str, traceback_text: str = "", user_id=None, chat_id=None):
    """Persist an application error to app_error_logs. Never raises."""
    try:
        async with postgres_connect() as db:
            await db.execute(
                "INSERT INTO app_error_logs (source, context, error_msg, traceback, user_id, chat_id) "
                "VALUES (?,?,?,?,?,?)",
                (source, context[:200], error_msg[:500], traceback_text[:8000], user_id, chat_id),
            )
            await db.commit()
    except Exception:
        pass


async def get_af2_config(chat_id: int = 0) -> dict:
    """Return AF2 config overrides for a specific chat (chat_id=0 for global fallback)."""
    async with postgres_connect() as db:
        try:
            rows = await db.fetch("SELECT key, value FROM af2_config WHERE chat_id=?", (chat_id,))
            return {row["key"]: float(row["value"]) for row in (rows or [])}
        except Exception:
            return {}


async def set_af2_config(cfg: dict, chat_id: int = 0) -> None:
    """Upsert AF2 config key-value pairs for a specific chat into the database."""
    async with postgres_connect() as db:
        for key, value in cfg.items():
            await db.execute(
                "INSERT INTO af2_config (chat_id, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT (chat_id, key) DO UPDATE SET value = EXCLUDED.value",
                (chat_id, key, float(value)),
            )
        await db.commit()


async def get_app_error_logs(limit: int = 1000) -> list:
    """Return the most recent error log entries (newest first)."""
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT id, source, context, error_msg, traceback, user_id, chat_id, created_at "
            "FROM app_error_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as c:
            rows = await c.fetchall()
    return [dict(r) for r in rows]


async def clear_app_error_logs():
    """Delete all rows from app_error_logs."""
    async with postgres_connect() as db:
        await db.execute("DELETE FROM app_error_logs")
        await db.commit()
