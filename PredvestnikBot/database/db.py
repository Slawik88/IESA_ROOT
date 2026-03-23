import math
from datetime import datetime, timedelta, date

from database.sql_compat import aiosqlite_compat as aiosqlite
from config import DATABASE_PATH


async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id       INTEGER PRIMARY KEY,
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
                chat_id           INTEGER PRIMARY KEY,
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
                chat_id   INTEGER PRIMARY KEY,
                title     TEXT    DEFAULT '',
                username  TEXT    DEFAULT '',
                chat_type TEXT    DEFAULT 'private',
                is_active INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                name    TEXT    NOT NULL COLLATE NOCASE,
                content TEXT    NOT NULL,
                UNIQUE(chat_id, name)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_filters (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id  INTEGER NOT NULL,
                keyword  TEXT    NOT NULL,
                response TEXT    NOT NULL,
                UNIQUE(chat_id, keyword)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                word    TEXT    NOT NULL COLLATE NOCASE,
                UNIQUE(chat_id, word)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS locks (
                chat_id  INTEGER PRIMARY KEY,
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
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                from_uid  INTEGER NOT NULL,
                to_uid    INTEGER NOT NULL,
                chat_id   INTEGER NOT NULL,
                amount    INTEGER NOT NULL DEFAULT 1,
                given_at  TEXT    NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS cleanup_counts (
                chat_id    INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
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
                user_id    INTEGER NOT NULL,
                chat_id    INTEGER NOT NULL,
                quest_date TEXT    NOT NULL,
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
                user_id   INTEGER NOT NULL,
                badge     TEXT    NOT NULL,
                earned_at TEXT    NOT NULL,
                PRIMARY KEY (user_id, badge)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id      INTEGER NOT NULL,
                message_id   INTEGER NOT NULL,
                question     TEXT    NOT NULL,
                options_json TEXT    NOT NULL,
                created_at   TEXT    NOT NULL,
                closed       INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS poll_votes (
                poll_id    INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                option_idx INTEGER NOT NULL,
                PRIMARY KEY (poll_id, user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                user_id  INTEGER PRIMARY KEY,
                birthday TEXT    NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS marriages (
                user_id    INTEGER NOT NULL,
                chat_id    INTEGER NOT NULL,
                partner_id INTEGER NOT NULL,
                married_at TEXT    NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # Ожидающие импорты — применяются при первом сообщении юзера в чат
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_user_imports (
                username      TEXT    NOT NULL COLLATE NOCASE,
                chat_id       INTEGER NOT NULL,
                message_count INTEGER DEFAULT 0,
                PRIMARY KEY (username, chat_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_marriage_imports (
                username1  TEXT    NOT NULL COLLATE NOCASE,
                username2  TEXT    NOT NULL COLLATE NOCASE,
                chat_id    INTEGER NOT NULL,
                married_at TEXT    NOT NULL,
                PRIMARY KEY (username1, chat_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS allowed_groups (
                chat_id INTEGER PRIMARY KEY
            )
        """)

        # ─── Профили пользователей привязанные к конкретному чату ─────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id       INTEGER NOT NULL,
                chat_id       INTEGER NOT NULL,
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
            "first_seen  TEXT    DEFAULT NULL",
            "custom_title TEXT   DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col_def}")
            except Exception:
                pass  # колонка уже существует

        # Добавляем новые колонки в cleanup_counts (для обновлений существующей БД)
        for col_def in [
            "week_count INTEGER DEFAULT 0",
            "day_count  INTEGER DEFAULT 0",
            "week_start TEXT    DEFAULT NULL",
            "day_start  TEXT    DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE cleanup_counts ADD COLUMN {col_def}")
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
            "next_cleanup_at         TEXT    DEFAULT NULL",
            "cleanup_reminder_sent   INTEGER DEFAULT 0",
            "antiflood_window  REAL    DEFAULT 2.0",
        ]:
            try:
                await db.execute(
                    f"ALTER TABLE chat_settings ADD COLUMN {col_def}"
                )
            except Exception:
                pass

        # Миграция: добавить message_count в user_stats (для обновлений БД)
        for col_def in [
            "message_count       INTEGER DEFAULT 0",
            "first_active        TEXT    DEFAULT NULL",
            "last_active         TEXT    DEFAULT NULL",
            "inactivity_warned_at TEXT   DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_stats ADD COLUMN {col_def}")
            except Exception:
                pass

        # Миграция: новые колонки user_mora (VIP, буст XP, рамка топа)
        for col_def in [
            "vip            INTEGER DEFAULT 0",
            "xp_boost_until TEXT    DEFAULT NULL",
            "top_frame      TEXT    DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_mora ADD COLUMN {col_def}")
            except Exception:
                pass

        # Таблица отдыхающих (защита от чистки)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rest_users (
                user_id    INTEGER NOT NULL,
                chat_id    INTEGER NOT NULL,
                days       INTEGER NOT NULL DEFAULT 7,
                added_at   TEXT    NOT NULL,
                added_by   INTEGER NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # Таблица админ-групп (для системных уведомлений)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_groups (
                chat_id INTEGER PRIMARY KEY
            )
        """)

        # Таблица типов каналов (правила/основной/etc.)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_types (
                type     TEXT PRIMARY KEY,
                chat_id  INTEGER NOT NULL
            )
        """)

        # Таблица ролей сообщества
        await db.execute("""
            CREATE TABLE IF NOT EXISTS community_roles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                emoji       TEXT    NOT NULL DEFAULT '',
                description TEXT    NOT NULL DEFAULT '',
                created_at  TEXT    NOT NULL
            )
        """)

        # Таблица назначенных ролей пользователям
        # role_id UNIQUE гарантирует: одна роль — один человек (1:1)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                role_id INTEGER NOT NULL UNIQUE REFERENCES community_roles(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL
            )
        """)

        # Журнал добровольных выходов из чата
        await db.execute("""
            CREATE TABLE IF NOT EXISTS leave_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id   INTEGER NOT NULL,
                user_id   INTEGER NOT NULL,
                full_name TEXT    DEFAULT '',
                username  TEXT    DEFAULT '',
                left_at   TEXT    NOT NULL
            )
        """)

        # Чёрный список пользователей по Telegram ID (per-chat)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_banlist (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id   INTEGER NOT NULL,
                user_id   INTEGER NOT NULL,
                added_by  INTEGER DEFAULT 0,
                reason    TEXT    DEFAULT '',
                added_at  TEXT    NOT NULL,
                UNIQUE(chat_id, user_id)
            )
        """)

        # Ожидающие назначения ролей (до вступления в основной чат)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_roles (
                user_id     INTEGER PRIMARY KEY,
                role_name   TEXT    NOT NULL,
                reserved_at TEXT    NOT NULL
            )
        """)

        # ─── Питомцы (разблокируются через брак) ───────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                user_id    INTEGER NOT NULL,
                chat_id    INTEGER NOT NULL,
                pet_type   TEXT    NOT NULL,
                name       TEXT    DEFAULT NULL,
                adopted_at TEXT    NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # Система экономики: валюта Мора
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_mora (
                user_id        INTEGER NOT NULL,
                chat_id        INTEGER NOT NULL,
                balance        INTEGER DEFAULT 0,
                total_earned   INTEGER DEFAULT 0,
                streak_days    INTEGER DEFAULT 0,
                last_daily     TEXT    DEFAULT NULL,
                mora_public    INTEGER DEFAULT 1,
                vip            INTEGER DEFAULT 0,
                xp_boost_until TEXT    DEFAULT NULL,
                top_frame      TEXT    DEFAULT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # Казино: вызовы на дуэль (кубик)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS casino_duels (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id       INTEGER NOT NULL,
                challenger_id INTEGER NOT NULL,
                target_id     INTEGER NOT NULL,
                bet           INTEGER NOT NULL,
                status        TEXT    DEFAULT 'pending',
                msg_id        INTEGER DEFAULT NULL,
                created_at    TEXT    NOT NULL
            )
        """)

        # Казино: лотерейные билеты (обновляются еженедельно)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS casino_lottery (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id  INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                week_key TEXT    NOT NULL,
                tickets  INTEGER DEFAULT 1,
                UNIQUE(chat_id, user_id, week_key)
            )
        """)

        # Семейный кошелёк (совместный баланс для пар)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS family_wallet (
                chat_id   INTEGER NOT NULL,
                user_id   INTEGER NOT NULL,
                balance   INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

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

        # ─── Новые таблицы (обновление v2: экспедиции, гача, банк, налоги, магазин, подарки, баффы) ────

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pet_expeditions (
                user_id     INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                started_at  TEXT    NOT NULL,
                duration_h  INTEGER NOT NULL,
                reward_min  INTEGER NOT NULL,
                reward_max  INTEGER NOT NULL,
                finished    INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS gacha_inventory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                item_key    TEXT    NOT NULL,
                item_name   TEXT    NOT NULL,
                rarity      TEXT    NOT NULL,
                obtained_at TEXT    NOT NULL,
                equipped    INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bank_deposits (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                amount      INTEGER NOT NULL,
                rate        REAL    NOT NULL,
                created_at  TEXT    NOT NULL,
                matures_at  TEXT    NOT NULL,
                withdrawn   INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tax_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                message_id  INTEGER,
                prize       INTEGER NOT NULL,
                penalty_pct REAL    DEFAULT 0.05,
                started_at  TEXT    NOT NULL,
                expires_at  TEXT    NOT NULL,
                finished    INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tax_event_clicks (
                event_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                clicked_at  TEXT    NOT NULL,
                position    INTEGER NOT NULL,
                PRIMARY KEY (event_id, user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS shop_items (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                chat_id      INTEGER NOT NULL,
                item_type    TEXT    NOT NULL,
                item_value   TEXT    NOT NULL,
                purchased_at TEXT    NOT NULL,
                active       INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS marriage_gifts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user   INTEGER NOT NULL,
                to_user     INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                gift_key    TEXT    NOT NULL,
                gift_name   TEXT    NOT NULL,
                gift_price  INTEGER NOT NULL,
                gifted_at   TEXT    NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS active_buffs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                buff_type   TEXT    NOT NULL,
                expires_at  TEXT    NOT NULL,
                source      TEXT
            )
        """)

        # ─── Миграция: новые колонки в user_mora ──────────────────────────
        for col_def in [
            "gacha_display TEXT DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_mora ADD COLUMN {col_def}")
            except Exception:
                pass

        # ─── Миграция: новые колонки в pets (косметика) ───────────────────
        for col_def in [
            "color_name   TEXT DEFAULT NULL",
            "emoji_status TEXT DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE pets ADD COLUMN {col_def}")
            except Exception:
                pass

        # ─── Темы профиля (какие куплены/получены и какая активна) ────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_themes (
                user_id   INTEGER NOT NULL,
                chat_id   INTEGER NOT NULL,
                theme_key TEXT    NOT NULL,
                source    TEXT    NOT NULL DEFAULT 'shop',
                obtained_at TEXT  NOT NULL,
                PRIMARY KEY (user_id, chat_id, theme_key)
            )
        """)

        # ─── Активная тема (у каждого юзера одна на чат) ──────────────────
        for col_def in [
            "active_theme TEXT DEFAULT 'default'",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_mora ADD COLUMN {col_def}")
            except Exception:
                pass

        # ─── Бейджи (значки) профиля ─────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_badges (
                user_id   INTEGER NOT NULL,
                chat_id   INTEGER NOT NULL,
                badge_key TEXT    NOT NULL,
                obtained_at TEXT  NOT NULL,
                PRIMARY KEY (user_id, chat_id, badge_key)
            )
        """)

        # ─── Личные приветствия ───────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_greetings (
                user_id      INTEGER NOT NULL,
                chat_id      INTEGER NOT NULL,
                template_key TEXT    NOT NULL,
                source       TEXT    NOT NULL DEFAULT 'gacha',
                obtained_at  TEXT    NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # ─── Богатый сундук (замена налогового ивента) ────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chest_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                message_id  INTEGER,
                started_at  TEXT    NOT NULL,
                expires_at  TEXT    NOT NULL,
                finished    INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS chest_event_clicks (
                event_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                clicked_at  TEXT    NOT NULL,
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
                await db.execute(f"ALTER TABLE user_mora ADD COLUMN {col_def}")
            except Exception:
                pass

        # ─── Трекинг: юзер видел приветствие сегодня ──────────────────────
        for col_def in [
            "last_greeting_date TEXT DEFAULT NULL",
        ]:
            try:
                await db.execute(f"ALTER TABLE user_stats ADD COLUMN {col_def}")
            except Exception:
                pass

        # Миграция: сделать баланс Моры видимым по умолчанию для всех
        await db.execute("UPDATE user_mora SET mora_public = 1 WHERE mora_public = 0")

        # ─── Переводы и долги ─────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS mora_loans (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                lender_id    INTEGER NOT NULL,
                borrower_id  INTEGER NOT NULL,
                chat_id      INTEGER NOT NULL,
                amount       INTEGER NOT NULL,
                loaned_at    TEXT    NOT NULL,
                repaid_at    TEXT    DEFAULT NULL
            )
        """)

        await db.commit()

    # PostgreSQL: widen all Telegram ID columns from int32 (INTEGER) → int64 (BIGINT).
    # Telegram supergroup/channel IDs like -1003xxxxxxxxx exceed int32 range.
    # Each ALTER runs in its own transaction so one failure doesn't abort the rest.
    from database.sql_compat import _is_postgres_dsn
    if _is_postgres_dsn(DATABASE_PATH):
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
            ("allowed_groups",    "chat_id"),
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
        ]
        for _tbl, _col in _bigint_migrations:
            try:
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    await db.execute(
                        f"ALTER TABLE {_tbl} ALTER COLUMN {_col} TYPE BIGINT"
                    )
            except Exception:
                pass

    # Seed allowed_groups from config (if any)
    from config import ALLOWED_GROUPS
    if ALLOWED_GROUPS:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            for cid in ALLOWED_GROUPS:
                await db.execute(
                    "INSERT OR IGNORE INTO allowed_groups (chat_id) VALUES (?)",
                    (cid,),
                )
            await db.commit()

    # Load whitelist into memory
    await load_whitelist()
    await load_admin_groups()
    await enforce_rank_invariants()


async def enforce_rank_invariants():
    """Normalize rank data invariants:
    - developer: only DEVELOPER_ID (global)
    - owner: only one per chat (others downgraded to co_owner)
    """
    from config import DEVELOPER_ID

    async with aiosqlite.connect(DATABASE_PATH) as db:
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


# ─── Whitelist (белый список групп) ───────────────────────────────────────────

_whitelist: set[int] = set()


async def load_whitelist():
    """Load allowed groups from DB into the in-memory cache."""
    global _whitelist
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT chat_id FROM allowed_groups") as c:
            rows = await c.fetchall()
    _whitelist = {r[0] for r in rows}


def is_group_allowed(chat_id: int) -> bool:
    """Check if a group is in the whitelist. Empty whitelist = allow all."""
    if not _whitelist:
        return True
    return chat_id in _whitelist


async def get_allowed_groups() -> list[int]:
    """Return list of all whitelisted chat_ids from DB."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT chat_id FROM allowed_groups") as c:
            return [r[0] for r in await c.fetchall()]


async def add_allowed_group(chat_id: int):
    """Add a group to the whitelist (DB + cache)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO allowed_groups (chat_id) VALUES (?)",
            (chat_id,),
        )
        await db.commit()
    _whitelist.add(chat_id)


async def remove_allowed_group(chat_id: int):
    """Remove a group from the whitelist (DB + cache)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM allowed_groups WHERE chat_id = ?",
            (chat_id,),
        )
        await db.commit()
    _whitelist.discard(chat_id)


# ─── Admin groups (группы администрации) ──────────────────────────────────────

_admin_groups: set[int] = set()


async def load_admin_groups():
    global _admin_groups
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT chat_id FROM admin_groups") as c:
            rows = await c.fetchall()
    _admin_groups = {r[0] for r in rows}


async def get_admin_groups() -> list[int]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT chat_id FROM admin_groups") as c:
            return [r[0] for r in await c.fetchall()]


async def add_admin_group(chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO admin_groups (chat_id) VALUES (?)",
            (chat_id,),
        )
        await db.commit()
    _admin_groups.add(chat_id)


async def remove_admin_group(chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM admin_groups WHERE chat_id = ?", (chat_id,),
        )
        await db.commit()
    _admin_groups.discard(chat_id)


def get_admin_group_ids() -> set[int]:
    return _admin_groups


# ─── Rest users (отдыхающие — защита от чистки) ──────────────────────────────

async def add_rest_user(user_id: int, chat_id: int, days: int, added_by: int):
    now_iso = datetime.utcnow().isoformat(timespec="seconds")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO rest_users (user_id, chat_id, days, added_at, added_by)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE
               SET days = excluded.days, added_at = excluded.added_at, added_by = excluded.added_by""",
            (user_id, chat_id, days, now_iso, added_by),
        )
        await db.commit()


async def remove_rest_user(user_id: int, chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM rest_users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        await db.commit()


async def get_rest_users(chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT days, added_at FROM rest_users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
    if not row:
        return False
    added = datetime.fromisoformat(row["added_at"])
    return (datetime.utcnow() - added).days < row["days"]


async def get_resting_user_ids(chat_id: int) -> set[int]:
    """Return set of user_ids currently on active rest in this chat."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, days, added_at FROM rest_users WHERE chat_id = ?",
            (chat_id,),
        ) as c:
            rows = await c.fetchall()
    result: set[int] = set()
    now = datetime.utcnow()
    for r in rows:
        added = datetime.fromisoformat(r["added_at"])
        if (now - added).days < r["days"]:
            result.add(r["user_id"])
    return result


async def get_rest_info_map(chat_id: int) -> dict[int, dict]:
    """Return {user_id: {'days': N, 'days_left': N, 'expires': datetime}} for active rest users."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, days, added_at FROM rest_users WHERE chat_id = ?",
            (chat_id,),
        ) as c:
            rows = await c.fetchall()
    result: dict[int, dict] = {}
    now = datetime.utcnow()
    for r in rows:
        added = datetime.fromisoformat(r["added_at"])
        elapsed = (now - added).days
        if elapsed < r["days"]:
            expires = added + timedelta(days=r["days"])
            result[r["user_id"]] = {
                "days": r["days"],
                "days_left": r["days"] - elapsed,
                "expires": expires,
            }
    return result


# ─── Users ────────────────────────────────────────────────────────────────────

async def get_user(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            return await cursor.fetchone()


async def get_user_by_username(username: str):
    uname = (username or "").strip().lstrip("@").lower()
    if not uname:
        return None
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE LOWER(username) IN (?, ?)",
            (uname, f"@{uname}"),
        ) as cursor:
            return await cursor.fetchone()


async def upsert_user(user_id: int, username: str, full_name: str):
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    Возвращает {'ok_direct': int, 'ok_pending': int, 'errors': list[str]}
    """
    now = datetime.utcnow().isoformat()
    ok_direct = 0
    errors: list[str] = []
    pending_records: list[dict] = []

    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
                    "DELETE FROM marriages WHERE chat_id=? AND (user_id=? OR user_id=?)",
                    (chat_id, user_id, partner_id),
                )
                await db.execute(
                    "INSERT OR IGNORE INTO marriages (user_id, chat_id, partner_id, married_at) VALUES (?,?,?,?)",
                    (user_id, chat_id, partner_id, married_at),
                )
                await db.execute(
                    "INSERT OR IGNORE INTO marriages (user_id, chat_id, partner_id, married_at) VALUES (?,?,?,?)",
                    (partner_id, chat_id, user_id, married_at),
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO chats (chat_id, is_active) VALUES (?, ?)",
            (chat_id, is_active),
        )
        await db.execute(
            "UPDATE chats SET is_active = ? WHERE chat_id = ?",
            (is_active, chat_id),
        )
        await db.commit()


async def get_active_chats():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM chats WHERE is_active = 1"
        ) as cursor:
            return await cursor.fetchall()

async def get_chat_settings(chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM chat_settings WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            return await cursor.fetchone()


# Допустимые колонки для защиты от SQL-инъекции
_ALLOWED_CHAT_SETTING_KEYS = {
    "welcome_text", "farewell_text", "rules_text",
    "antiflood_enabled", "antiflood_limit", "antiflood_action", "antiflood_window",
    "cleanup_threshold", "blacklist_enabled", "welcome_call",
    "social_tiktok", "social_youtube", "social_instagram",
    "cleanup_locked",
    "inactivity_warn_enabled", "inactivity_warn_days",
    "next_cleanup_at", "cleanup_reminder_sent",
}
_ALLOWED_LOCK_TYPES = {"links", "stickers", "gifs", "forwards", "voice", "video", "photo", "audio"}


async def set_chat_setting(chat_id: int, key: str, value):
    if key not in _ALLOWED_CHAT_SETTING_KEYS:
        raise ValueError(f"Invalid chat setting key: {key!r}")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO chat_settings (chat_id) VALUES (?)", (chat_id,)
        )
        await db.execute(
            f"UPDATE chat_settings SET {key} = ? WHERE chat_id = ?", (value, chat_id)
        )
        await db.commit()


async def get_locked_chats() -> list[int]:
    """Return chat_ids where cleanup_locked=1 (чаты заблокированные чисткой)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT chat_id FROM chat_settings WHERE cleanup_locked = 1"
        ) as c:
            return [r[0] for r in await c.fetchall()]


# ─── Notes ────────────────────────────────────────────────────────────────────

async def save_note(chat_id: int, name: str, content: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO notes (chat_id, name, content) VALUES (?, ?, ?)
            ON CONFLICT(chat_id, name) DO UPDATE SET content = excluded.content
            """,
            (chat_id, name.lower(), content),
        )
        await db.commit()


async def get_note(chat_id: int, name: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM notes WHERE chat_id = ? AND name = ?",
            (chat_id, name.lower()),
        ) as cursor:
            return await cursor.fetchone()


async def list_notes(chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT name FROM notes WHERE chat_id = ? ORDER BY name", (chat_id,)
        ) as cursor:
            return await cursor.fetchall()


async def delete_note(chat_id: int, name: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM notes WHERE chat_id = ? AND name = ?",
            (chat_id, name.lower()),
        )
        await db.commit()
        return cursor.rowcount > 0


# ─── Filters ──────────────────────────────────────────────────────────────────

async def add_filter(chat_id: int, keyword: str, response: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO chat_filters (chat_id, keyword, response) VALUES (?, ?, ?)
            ON CONFLICT(chat_id, keyword) DO UPDATE SET response = excluded.response
            """,
            (chat_id, keyword.lower(), response),
        )
        await db.commit()


async def get_filters(chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM chat_filters WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            return await cursor.fetchall()


async def delete_filter(chat_id: int, keyword: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM chat_filters WHERE chat_id = ? AND keyword = ?",
            (chat_id, keyword.lower()),
        )
        await db.commit()
        return cursor.rowcount > 0


# ─── Blacklist ────────────────────────────────────────────────────────────────

async def add_blacklist_word(chat_id: int, word: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO blacklist (chat_id, word) VALUES (?, ?)",
                (chat_id, word.lower()),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove_blacklist_word(chat_id: int, word: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM blacklist WHERE chat_id = ? AND word = ?",
            (chat_id, word.lower()),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_blacklist(chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT word FROM blacklist WHERE chat_id = ? ORDER BY word", (chat_id,)
        ) as cursor:
            return await cursor.fetchall()


# ─── Locks ────────────────────────────────────────────────────────────────────

async def get_locks(chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM locks WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            return await cursor.fetchone()


async def set_lock(chat_id: int, lock_type: str, value: int):
    if lock_type not in _ALLOWED_LOCK_TYPES:
        raise ValueError(f"Invalid lock type: {lock_type!r}")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO locks (chat_id) VALUES (?)", (chat_id,)
        )
        await db.execute(
            f"UPDATE locks SET {lock_type} = ? WHERE chat_id = ?", (value, chat_id)
        )
        await db.commit()


# ─── Reputation ───────────────────────────────────────────────────────────────

async def get_rep_count_today(from_uid: int, to_uid: int, chat_id: int) -> int:
    """Сколько раз from_uid давал репутацию to_uid в чате за сегодня (UTC)."""
    today = datetime.utcnow().date().isoformat()  # "YYYY-MM-DD"
    cutoff = today + "T00:00:00"
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM rep_log WHERE from_uid=? AND to_uid=? AND chat_id=? AND given_at>=?",
            (from_uid, to_uid, chat_id, cutoff),
        ) as c:
            row = await c.fetchone()
            return row[0] if row else 0


async def can_give_rep(from_uid: int, to_uid: int, chat_id: int) -> bool:
    """Обратная совместимость: проверяет 2-часовой кулдаун (устарела, используй get_rep_count_today)."""
    cutoff = (datetime.utcnow() - timedelta(hours=2)).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id)
        )
        await db.commit()
    return True


# ─── Cleanup counts ───────────────────────────────────────────────────────────

async def increment_cleanup_count(chat_id: int, user_id: int):
    today    = date.today().isoformat()
    iso      = date.today().isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM cleanup_counts WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ) as c:
            row = await c.fetchone()

        if row is None:
            await db.execute(
                """
                INSERT INTO cleanup_counts
                    (chat_id, user_id, count, week_count, day_count, week_start, day_start)
                VALUES (?, ?, 1, 1, 1, ?, ?)
                """,
                (chat_id, user_id, week_key, today),
            )
        else:
            new_week   = row["week_start"] != week_key
            new_day    = row["day_start"]  != today
            week_count = 1 if new_week else (row["week_count"] or 0) + 1
            day_count  = 1 if new_day  else (row["day_count"]  or 0) + 1
            await db.execute(
                """
                UPDATE cleanup_counts
                SET count=count+1, week_count=?, day_count=?, week_start=?, day_start=?
                WHERE chat_id=? AND user_id=?
                """,
                (
                    week_count, day_count,
                    week_key if new_week else row["week_start"],
                    today    if new_day  else row["day_start"],
                    chat_id, user_id,
                ),
            )
        await db.commit()


async def get_activity_report(chat_id: int):
    """Все отслеживаемые участники чата с их счётчиками (всего / за неделю / за день)."""
    today    = date.today().isoformat()
    iso      = date.today().isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE cleanup_counts SET count = 0 WHERE chat_id = ?", (chat_id,)
        )
        await db.commit()


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
    """Return the user's actual quest for today (may differ from default after reroll)."""
    row = await get_quest_progress(user_id, chat_id, today_str)
    if row and row["quest_type"]:
        # Find matching quest in DAILY_QUESTS by type+goal
        for q in DAILY_QUESTS:
            if q["type"] == row["quest_type"] and q["goal"] == row["goal"]:
                return q
        # Fallback: build from stored data
        return {"type": row["quest_type"], "goal": row["goal"],
                "xp": 50, "mora": 5, "desc": f"Задание: {row['quest_type']}"}
    return get_todays_quest(today_str)


async def reroll_user_quest(user_id: int, chat_id: int, quest_date: str) -> dict:
    """Delete old progress and assign a random DIFFERENT quest. Returns the new quest."""
    import random
    old_quest = await get_user_quest(user_id, chat_id, quest_date)
    candidates = [q for q in DAILY_QUESTS
                  if q["type"] != old_quest["type"] or q["goal"] != old_quest["goal"]]
    if not candidates:
        candidates = DAILY_QUESTS
    new_quest = random.choice(candidates)
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_quests WHERE user_id=? AND chat_id=? AND quest_date=?",
            (user_id, chat_id, quest_date),
        ) as c:
            return await c.fetchone()


async def quest_tick(user_id: int, chat_id: int, quest_date: str, quest_type: str, goal: int) -> tuple[int, int, bool]:
    """Ticks progress +1. Returns (new_progress, goal, just_completed). Creates row on first call."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT progress, goal, completed FROM user_quests WHERE user_id=? AND chat_id=? AND quest_date=?",
            (user_id, chat_id, quest_date),
        ) as c:
            row = await c.fetchone()

        if row is None:
            new_progress = 1
            just_completed = new_progress >= goal
            await db.execute(
                """INSERT OR IGNORE INTO user_quests
                   (user_id, chat_id, quest_date, quest_type, goal, progress, completed)
                   VALUES (?,?,?,?,?,?,?)""",
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE user_quests SET rewarded=1 WHERE user_id=? AND chat_id=? AND quest_date=?",
            (user_id, chat_id, quest_date),
        )
        await db.commit()


# ─── Achievements ─────────────────────────────────────────────────────────────

async def get_achievements(user_id: int) -> list:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT badge, earned_at FROM user_achievements WHERE user_id=? ORDER BY earned_at",
            (user_id,),
        ) as c:
            return await c.fetchall()


async def award_achievement(user_id: int, badge: str) -> bool:
    """Awards achievement. Returns True if newly awarded."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO user_achievements (user_id, badge, earned_at) VALUES (?,?,?)",
                (user_id, badge, now),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


# ─── Weekly / Daily top ───────────────────────────────────────────────────────

async def get_weekly_top(chat_id: int, limit: int = 10) -> list:
    iso = date.today().isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    today = date.today().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    """Top users for the previous calendar week."""
    prev_week_date = date.today() - timedelta(days=7)
    iso = prev_week_date.isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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


async def get_yesterday_top(chat_id: int, limit: int = 10) -> list:
    """Top users for yesterday."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT u.user_id, u.full_name, u.username,
                      CASE WHEN cc.day_start=? THEN COALESCE(cc.day_count,0) ELSE 0 END AS dc
               FROM cleanup_counts cc
               JOIN users u ON u.user_id=cc.user_id
               LEFT JOIN user_stats us ON us.user_id=cc.user_id AND us.chat_id=cc.chat_id
               WHERE cc.chat_id=? AND COALESCE(us.is_banned,0)=0
                 AND CASE WHEN cc.day_start=? THEN COALESCE(cc.day_count,0) ELSE 0 END >= 1
               ORDER BY dc DESC LIMIT ?""",
            (yesterday, chat_id, yesterday, limit),
        ) as c:
            return await c.fetchall()


async def get_chat_members(chat_id: int, ranks: list[str] | None = None) -> list:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM marriages WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            return await c.fetchone()


async def create_marriage(user_a: int, user_b: int, chat_id: int):
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM marriages WHERE chat_id=? AND (user_id=? OR user_id=?)",
            (chat_id, user_a, user_b),
        )
        await db.execute(
            "INSERT INTO marriages (user_id, chat_id, partner_id, married_at) VALUES (?,?,?,?)",
            (user_a, chat_id, user_b, now),
        )
        await db.execute(
            "INSERT INTO marriages (user_id, chat_id, partner_id, married_at) VALUES (?,?,?,?)",
            (user_b, chat_id, user_a, now),
        )
        await db.commit()


async def delete_marriage(user_id: int, chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT partner_id FROM marriages WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
        if row:
            partner_id = row[0]
            await db.execute(
                "DELETE FROM marriages WHERE chat_id=? AND (user_id=? OR user_id=?)",
                (chat_id, user_id, partner_id),
            )
            await db.commit()


async def import_marriage_with_date(user_a: int, user_b: int, chat_id: int, married_at: str):
    """Создаёт/обновляет брак с указанной датой (для импорта из JSON)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM marriages WHERE chat_id=? AND (user_id=? OR user_id=?)",
            (chat_id, user_a, user_b),
        )
        await db.execute(
            "INSERT INTO marriages (user_id, chat_id, partner_id, married_at) VALUES (?,?,?,?)",
            (user_a, chat_id, user_b, married_at),
        )
        await db.execute(
            "INSERT INTO marriages (user_id, chat_id, partner_id, married_at) VALUES (?,?,?,?)",
            (user_b, chat_id, user_a, married_at),
        )
        await db.commit()


async def get_migration_stats(chat_id: int) -> dict:
    """Возвращает статистику по данным в БД для данного чата (для команды бот скан)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
            "SELECT COUNT(*) AS cnt FROM marriages WHERE chat_id=?", (chat_id,)
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_stats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ) as cursor:
            return await cursor.fetchone()


async def upsert_user_stats(user_id: int, chat_id: int):
    """Ensure a row exists in user_stats for this user+chat."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_stats (user_id, chat_id) VALUES (?, ?)",
            (user_id, chat_id),
        )
        await db.commit()


async def increment_message_count_chat(user_id: int, chat_id: int) -> int:
    """Increment message count and return the new value."""
    now_iso = datetime.utcnow().isoformat(timespec="seconds")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO user_stats (user_id, chat_id, message_count, first_active, last_active)
               VALUES (?, ?, 1, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                   message_count = user_stats.message_count + 1,
                   first_active = COALESCE(user_stats.first_active, EXCLUDED.first_active),
                   last_active = EXCLUDED.last_active""",
            (user_id, chat_id, now_iso, now_iso),
        )
        await db.commit()
        async with db.execute(
            "SELECT message_count FROM user_stats WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
            return row[0] if row else 1


async def set_rank_in_chat(user_id: int, chat_id: int, rank: str):
    from config import DEVELOPER_ID

    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO user_stats (user_id, chat_id, is_banned, ban_reason) VALUES (?, ?, 1, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET is_banned = 1, ban_reason = excluded.ban_reason""",
            (user_id, chat_id, reason),
        )
        await db.commit()


async def unban_user_in_chat(user_id: int, chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE user_stats SET is_banned = 0, ban_reason = NULL WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        await db.commit()


async def add_warn_in_chat(user_id: int, chat_id: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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


async def get_staff_in_chat(chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    """Add XP in a specific chat. Returns (new_xp, new_level, leveled_up)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_stats (user_id, chat_id) VALUES (?, ?)",
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
    return new_xp, new_level, leveled_up


# ─── Мора (внутричатовая валюта) ──────────────────────────────────────────────

async def get_mora(user_id: int, chat_id: int):
    """Returns user_mora row or None."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_mora WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            return await c.fetchone()


async def add_mora(user_id: int, chat_id: int, amount: int) -> int:
    """Add (or subtract) Мора. Balance never goes below 0. Returns new balance."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, balance, total_earned)
               VALUES (?, ?, GREATEST(0, ?), CASE WHEN ? > 0 THEN ? ELSE 0 END)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                   balance      = GREATEST(0, user_mora.balance + ?),
                   total_earned = user_mora.total_earned + CASE WHEN ? > 0 THEN ? ELSE 0 END""",
            (user_id, chat_id, amount, amount, amount, amount, amount, amount),
        )
        await db.commit()
        async with db.execute(
            "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
            return row[0] if row else 0


async def check_daily_mora(user_id: int, chat_id: int) -> tuple[bool, int, bool]:
    """
    Check if this is the first message today for Мора purposes.
    Updates streak and last_daily. Returns (is_first_daily, new_streak, streak_7day_bonus).
    """
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT last_daily, streak_days FROM user_mora WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()

        if row is None:
            await db.execute(
                """INSERT OR IGNORE INTO user_mora (user_id, chat_id, last_daily, streak_days)
                   VALUES (?, ?, ?, 1)""",
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, mora_public)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET mora_public = excluded.mora_public""",
            (user_id, chat_id, public),
        )
        await db.commit()


async def deduct_mora(user_id: int, chat_id: int, amount: int) -> tuple[bool, int]:
    """Deduct Мора if balance is sufficient. Atomic UPDATE prevents race conditions."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """UPDATE user_mora
               SET balance = balance - ?
               WHERE user_id = ? AND chat_id = ? AND balance >= ?""",
            (amount, user_id, chat_id, amount),
        )
        if cursor.rowcount == 0:
            async with db.execute(
                "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?",
                (user_id, chat_id),
            ) as c:
                row = await c.fetchone()
            return False, (row["balance"] if row else 0)
        await db.commit()
        async with db.execute(
            "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
        return True, (row["balance"] if row else 0)


async def get_vip(user_id: int, chat_id: int) -> int:
    """Returns 1 if user has VIP in this chat, else 0."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT vip FROM user_mora WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
    return (row["vip"] or 0) if row else 0


async def set_vip(user_id: int, chat_id: int, value: int):
    """Set VIP status for user in chat."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, vip) VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET vip = excluded.vip""",
            (user_id, chat_id, value),
        )
        await db.commit()


async def get_xp_boost_active(user_id: int, chat_id: int) -> bool:
    """Returns True if user has an active XP boost right now."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT xp_boost_until FROM user_mora WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
    if not row or not row["xp_boost_until"]:
        return False
    try:
        until = datetime.fromisoformat(row["xp_boost_until"])
        return datetime.utcnow() < until
    except Exception:
        return False


async def set_xp_boost(user_id: int, chat_id: int, until_iso: str):
    """Set XP boost expiry for user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, xp_boost_until) VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET xp_boost_until = excluded.xp_boost_until""",
            (user_id, chat_id, until_iso),
        )
        await db.commit()


async def get_top_frame(user_id: int, chat_id: int) -> str | None:
    """Returns the active top frame key for user, or None."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT top_frame FROM user_mora WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
    return row["top_frame"] if row else None


async def set_top_frame(user_id: int, chat_id: int, frame: str | None):
    """Set top frame for user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, top_frame) VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET top_frame = excluded.top_frame""",
            (user_id, chat_id, frame),
        )
        await db.commit()


# ─── Казино ───────────────────────────────────────────────────────────────────

async def create_duel(chat_id: int, challenger_id: int, target_id: int, bet: int, msg_id: int) -> int:
    """Create a pending dice duel. Returns duel id."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO casino_duels (chat_id, challenger_id, target_id, bet, status, msg_id, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?, ?) RETURNING id""",
            (chat_id, challenger_id, target_id, bet, msg_id, now),
        )
        row = await cursor.fetchone()
        await db.commit()
        return row[0] if row else None


async def get_duel(duel_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM casino_duels WHERE id=?", (duel_id,)
        ) as c:
            return await c.fetchone()


async def set_duel_status(duel_id: int, status: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE casino_duels SET status=? WHERE id=?",
            (status, duel_id),
        )
        await db.commit()


async def cancel_expired_duels():
    """Cancel duels older than 5 minutes that are still pending."""
    cutoff = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE casino_duels SET status='expired' WHERE status='pending' AND created_at < ?",
            (cutoff,),
        )
        await db.commit()


async def get_pending_duels_for_chat(chat_id: int, challenger_id: int) -> list:
    """Return pending duels by this challenger in this chat (to prevent spam)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM casino_duels WHERE chat_id=? AND challenger_id=? AND status='pending'",
            (chat_id, challenger_id),
        ) as c:
            return await c.fetchall()


async def buy_lottery_ticket(chat_id: int, user_id: int, week_key: str):
    """Buy one lottery ticket for this week. Returns new ticket count."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO casino_lottery (chat_id, user_id, week_key, tickets)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(chat_id, user_id, week_key) DO UPDATE SET
                   tickets = casino_lottery.tickets + 1""",
            (chat_id, user_id, week_key),
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT tickets FROM casino_lottery WHERE chat_id=? AND user_id=? AND week_key=?",
            (chat_id, user_id, week_key),
        ) as c:
            row = await c.fetchone()
        return row["tickets"] if row else 1


async def get_lottery_tickets(chat_id: int, user_id: int, week_key: str) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT tickets FROM casino_lottery WHERE chat_id=? AND user_id=? AND week_key=?",
            (chat_id, user_id, week_key),
        ) as c:
            row = await c.fetchone()
    return (row["tickets"] or 0) if row else 0


async def get_all_lottery_participants(chat_id: int, week_key: str) -> list:
    """Return all (user_id, tickets) rows for this chat and week."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, tickets FROM casino_lottery WHERE chat_id=? AND week_key=?",
            (chat_id, week_key),
        ) as c:
            return await c.fetchall()


async def get_all_lottery_chats_week(week_key: str) -> list[int]:
    """Return distinct chat_ids that have tickets for this week."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT chat_id FROM casino_lottery WHERE week_key=?",
            (week_key,),
        ) as c:
            return [r[0] for r in await c.fetchall()]


# ─── Семейный кошелёк ─────────────────────────────────────────────────────────

async def get_family_wallet(chat_id: int, user_id: int) -> int:
    """Returns the shared family wallet balance, or 0 if not found."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT balance FROM family_wallet WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ) as c:
            row = await c.fetchone()
    return (row["balance"] or 0) if row else 0


async def add_to_family_wallet(chat_id: int, user_id: int, amount: int) -> int:
    """Add or subtract from family wallet. Returns new balance."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO family_wallet (chat_id, user_id, balance)
               VALUES (?, ?, GREATEST(0, ?))
               ON CONFLICT(chat_id, user_id) DO UPDATE SET
                   balance = GREATEST(0, family_wallet.balance + ?)""",
            (chat_id, user_id, amount, amount),
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT balance FROM family_wallet WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ) as c:
            row = await c.fetchone()
        return (row["balance"] or 0) if row else 0


async def get_all_marriages_for_anniversary() -> list:
    """Return all marriages for anniversary check (all chats)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, chat_id, partner_id, married_at FROM marriages"
        ) as c:
            return await c.fetchall()


async def is_anniversary_awarded(user_id: int, chat_id: int, date_str: str) -> bool:
    """True если юбилейная Мора уже была начислена этому пользователю сегодня."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM anniversary_log WHERE user_id=? AND chat_id=? AND date_str=?",
            (user_id, chat_id, date_str),
        ) as c:
            return (await c.fetchone()) is not None


async def mark_anniversary_awarded(user_id: int, chat_id: int, date_str: str):
    """Записать факт начисления юбилейной Моры."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO anniversary_log (user_id, chat_id, date_str) VALUES (?,?,?)",
            (user_id, chat_id, date_str),
        )
        await db.commit()
        # Автоочистка: удаляем записи старше 90 дней
        cutoff = (datetime.utcnow().date().isoformat()[:7])  # "YYYY-MM"
        await db.execute(
            "DELETE FROM anniversary_log WHERE date_str < ?",
            (cutoff + "-01",),
        )
        await db.commit()


# ─── Singles weekly bonus log (persistent guard) ─────────────────────────────

async def is_singles_bonus_awarded(week_key: str) -> bool:
    """Check if singles bonus has been awarded for this week."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM singles_bonus_log WHERE week_key=?", (week_key,)
        ) as c:
            return bool(await c.fetchone())


async def mark_singles_bonus_awarded(week_key: str):
    """Mark singles bonus as awarded for this week and cleanup old records."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO singles_bonus_log (week_key) VALUES (?)", (week_key,)
        )
        
        # Auto-cleanup: remove records older than 12 weeks
        cutoff_year = datetime.utcnow().year
        if week_key.startswith(str(cutoff_year)) and int(week_key[-2:]) <= 12:
            cutoff_year -= 1
        await db.execute(
            "DELETE FROM singles_bonus_log WHERE week_key < ?", (f"{cutoff_year}-W01",)
        )
        await db.commit()


async def get_all_singles_for_weekly_bonus():
    """Get all single (unmarried) users who are active."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT us.user_id, us.chat_id
            FROM user_stats us
            WHERE us.is_banned = 0
              AND us.message_count > 10
              AND NOT EXISTS (
                  SELECT 1 FROM marriages m
                  WHERE (m.user_id = us.user_id OR m.partner_id = us.user_id)
                    AND m.chat_id = us.chat_id
              )
        """) as c:
            return await c.fetchall()


# ─── Lottery draw log (persistent guard) ─────────────────────────────────────

async def is_lottery_drawn(week_key: str) -> bool:
    """True если розыгрыш лотереи уже был проведён на этой неделе (выживает перезапуск)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM lottery_draws WHERE week_key=?", (week_key,)
        ) as c:
            return (await c.fetchone()) is not None


async def mark_lottery_drawn(week_key: str):
    """Записать факт проведения розыгрыша лотереи на этой неделе."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO lottery_draws (week_key) VALUES (?)", (week_key,)
        )
        await db.commit()
        # Автоочистка: удаляем записи старше 12 недель
        cutoff_year = datetime.utcnow().year - 1
        await db.execute(
            "DELETE FROM lottery_draws WHERE week_key < ?", (f"{cutoff_year}-W01",)
        )
        await db.commit()


# ─── Mora balance management ──────────────────────────────────────────────────

async def set_mora_balance(user_id: int, chat_id: int, new_balance: int):
    """Устанавливает баланс Моры напрямую (для developer-команд)."""
    new_balance = max(0, new_balance)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, balance)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET balance = excluded.balance""",
            (user_id, chat_id, new_balance),
        )
        await db.commit()


# ─── Переводы Моры ────────────────────────────────────────────────────────────

async def transfer_mora(from_uid: int, to_uid: int, chat_id: int, amount: int) -> tuple[bool, int, int]:
    """Атомарный перевод Моры. Возвращает (ok, from_new_bal, to_new_bal)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?",
            (from_uid, chat_id),
        ) as c:
            row = await c.fetchone()
        from_bal = row["balance"] if row else 0
        if from_bal < amount:
            return False, from_bal, 0

        new_from_bal = from_bal - amount
        await db.execute(
            "UPDATE user_mora SET balance=? WHERE user_id=? AND chat_id=?",
            (new_from_bal, from_uid, chat_id),
        )
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, balance, total_earned) VALUES (?,?,?,?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                   balance = balance + ?,
                   total_earned = total_earned + ?""",
            (to_uid, chat_id, amount, amount, amount, amount),
        )
        await db.commit()

        async with db.execute(
            "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?", (to_uid, chat_id)
        ) as c:
            row = await c.fetchone()
        to_new_bal = row["balance"] if row else 0
        return True, new_from_bal, to_new_bal


# ─── Долги (займы) ────────────────────────────────────────────────────────────

async def create_loan(lender_id: int, borrower_id: int, chat_id: int, amount: int) -> tuple[bool, int, int]:
    """Создаёт заём: списывает с кредитора, зачисляет заёмщику.
    Возвращает (ok, lender_new_bal, loan_id)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?",
            (lender_id, chat_id),
        ) as c:
            row = await c.fetchone()
        lender_bal = row["balance"] if row else 0
        if lender_bal < amount:
            return False, lender_bal, 0

        now = datetime.utcnow().isoformat()
        new_lender_bal = lender_bal - amount

        await db.execute(
            "UPDATE user_mora SET balance=? WHERE user_id=? AND chat_id=?",
            (new_lender_bal, lender_id, chat_id),
        )
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, balance, total_earned) VALUES (?,?,?,?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                   balance = balance + ?,
                   total_earned = total_earned + ?""",
            (borrower_id, chat_id, amount, amount, amount, amount),
        )
        cursor = await db.execute(
            "INSERT INTO mora_loans (lender_id, borrower_id, chat_id, amount, loaned_at) VALUES (?,?,?,?,?) RETURNING id",
            (lender_id, borrower_id, chat_id, amount, now),
        )
        row = await cursor.fetchone()
        loan_id = row[0] if row else None
        await db.commit()
        return True, new_lender_bal, loan_id


async def get_active_loans_as_lender(user_id: int, chat_id: int) -> list:
    """Займы, выданные пользователем (не погашенные)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM mora_loans
               WHERE lender_id=? AND chat_id=? AND repaid_at IS NULL
               ORDER BY loaned_at ASC""",
            (user_id, chat_id),
        ) as c:
            return list(await c.fetchall())


async def get_active_loans_as_borrower(user_id: int, chat_id: int) -> list:
    """Займы, которые пользователь должен вернуть."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM mora_loans
               WHERE borrower_id=? AND chat_id=? AND repaid_at IS NULL
               ORDER BY loaned_at ASC""",
            (user_id, chat_id),
        ) as c:
            return list(await c.fetchall())


async def repay_loan(loan_id: int, borrower_id: int, chat_id: int) -> tuple[bool, int]:
    """Полностью погашает заём. Возвращает (ok, borrower_new_bal)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM mora_loans WHERE id=? AND chat_id=? AND borrower_id=? AND repaid_at IS NULL",
            (loan_id, chat_id, borrower_id),
        ) as c:
            loan = await c.fetchone()
        if not loan:
            return False, 0

        amount = loan["amount"]
        lender_id = loan["lender_id"]

        async with db.execute(
            "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?",
            (borrower_id, chat_id),
        ) as c:
            row = await c.fetchone()
        borrower_bal = row["balance"] if row else 0
        if borrower_bal < amount:
            return False, borrower_bal

        now = datetime.utcnow().isoformat()
        new_borrower_bal = borrower_bal - amount

        await db.execute(
            "UPDATE user_mora SET balance=? WHERE user_id=? AND chat_id=?",
            (new_borrower_bal, borrower_id, chat_id),
        )
        await db.execute(
            """INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET balance = balance + ?""",
            (lender_id, chat_id, amount, amount),
        )
        await db.execute(
            "UPDATE mora_loans SET repaid_at=? WHERE id=?",
            (now, loan_id),
        )
        await db.commit()
        return True, new_borrower_bal


# ─── Смена вида питомца ───────────────────────────────────────────────────────

async def change_pet_type(user_id: int, chat_id: int, new_type: str) -> bool:
    """Меняет вид питомца (user + партнёр). Возвращает True если питомец найден."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT 1 FROM pets WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            if not await c.fetchone():
                return False
        await db.execute(
            "UPDATE pets SET pet_type=? WHERE user_id=? AND chat_id=?",
            (new_type, user_id, chat_id),
        )
        async with db.execute(
            "SELECT partner_id FROM marriages WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
        if row:
            await db.execute(
                "UPDATE pets SET pet_type=? WHERE user_id=? AND chat_id=?",
                (new_type, row[0], chat_id),
            )
        await db.commit()
        return True


async def reset_user_quest(user_id: int, chat_id: int, quest_date: str):
    """Delete today's quest progress so it will be re-assigned fresh."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM user_quests WHERE user_id=? AND chat_id=? AND quest_date=?",
            (user_id, chat_id, quest_date),
        )
        await db.commit()


async def add_reputation_in_chat(from_uid: int, to_uid: int, chat_id: int, amount: int = 1) -> int:
    """Add reputation in chat. Returns new rep value."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO rep_log (from_uid, to_uid, chat_id, amount, given_at) VALUES (?,?,?,?,?)",
            (from_uid, to_uid, chat_id, amount, now),
        )
        await db.execute(
            "INSERT OR IGNORE INTO user_stats (user_id, chat_id) VALUES (?, ?)",
            (to_uid, chat_id),
        )
        await db.execute(
            "UPDATE user_stats SET reputation = reputation + ? WHERE user_id = ? AND chat_id = ?",
            (amount, to_uid, chat_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT reputation FROM user_stats WHERE user_id = ? AND chat_id = ?",
            (to_uid, chat_id),
        ) as c:
            row = await c.fetchone()
            return row[0] if row else 0


async def get_banned_in_chat(chat_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT us.user_id, us.ban_reason, u.full_name, u.username
               FROM user_stats us
               JOIN users u ON u.user_id = us.user_id
               WHERE us.chat_id = ? AND us.is_banned = 1""",
            (chat_id,),
        ) as c:
            return await c.fetchall()


async def get_top_by_messages_in_chat(chat_id: int, limit: int = 10):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT us.*, u.full_name, u.username
               FROM user_stats us
               JOIN users u ON u.user_id = us.user_id
               WHERE us.chat_id = ? AND us.is_banned = 0 AND us.message_count >= 1
               ORDER BY us.message_count DESC LIMIT ?""",
            (chat_id, limit),
        ) as c:
            return await c.fetchall()


async def get_top_by_xp_in_chat(chat_id: int, limit: int = 10):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO user_stats (user_id, chat_id, bio) VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET bio = excluded.bio""",
            (user_id, chat_id, bio),
        )
        await db.commit()


async def get_rep_last_time(from_uid: int, to_uid: int, chat_id: int) -> str | None:
    """Get ISO timestamp of last rep given from_uid to to_uid in chat."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO channel_types (type, chat_id) VALUES (?, ?)",
            (type_name, chat_id),
        )
        await db.commit()


async def remove_channel_type(type_name: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM channel_types WHERE type = ?", (type_name,))
        await db.commit()


async def get_channel_type(type_name: str) -> int | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT chat_id FROM channel_types WHERE type = ?", (type_name,)
        ) as c:
            row = await c.fetchone()
            return row[0] if row else None


async def get_all_channel_types() -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT type, chat_id FROM channel_types ORDER BY type") as c:
            return [dict(r) for r in await c.fetchall()]


# ─── Community roles (роли сообщества) ────────────────────────────────────────

async def add_community_role(name: str, emoji: str = "", description: str = "") -> bool:
    """Add a new community role. Returns False if name already exists."""
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO community_roles (name, emoji, description, created_at) VALUES (?, ?, ?, ?)",
                (name, emoji, description, now),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove_community_role(name: str) -> bool:
    """Remove a community role by name. Returns False if not found."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM community_roles WHERE name = ? COLLATE NOCASE", (role_name,)
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT id FROM community_roles WHERE name = ? COLLATE NOCASE", (role_name,)
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM community_roles WHERE name = ? COLLATE NOCASE", (role_name,)
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
    now_iso = datetime.utcnow().isoformat(timespec="seconds")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO leave_log (chat_id, user_id, full_name, username, left_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, full_name, username, now_iso),
        )
        await db.commit()


async def get_voluntary_leaves(chat_id: int, limit: int = 20) -> list[dict]:
    """Return recent voluntary leaves for a chat, newest first."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT user_id, full_name, username, left_at
               FROM leave_log WHERE chat_id = ?
               ORDER BY left_at DESC LIMIT ?""",
            (chat_id, limit),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


# ─── User Banlist (ID-based, per-chat) ────────────────────────────────────────

async def add_user_to_banlist(
    chat_id: int, user_id: int, added_by: int = 0, reason: str = ""
) -> bool:
    """Add a user to the chat banlist. Returns False if already banned."""
    now_iso = datetime.utcnow().isoformat(timespec="seconds")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO user_banlist (chat_id, user_id, added_by, reason, added_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (chat_id, user_id, added_by, reason, now_iso),
            )
            await db.commit()
            return True
        except Exception:
            return False


async def remove_user_from_banlist(chat_id: int, user_id: int) -> bool:
    """Remove a user from the chat banlist. Returns True if removed."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        result = await db.execute(
            "DELETE FROM user_banlist WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        await db.commit()
        return result.rowcount > 0


async def is_user_in_banlist(chat_id: int, user_id: int) -> bool:
    """Check if a user is in the chat banlist."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM user_banlist WHERE chat_id = ? AND user_id = ? LIMIT 1",
            (chat_id, user_id),
        ) as c:
            return (await c.fetchone()) is not None


async def get_chat_banlist_users(chat_id: int, limit: int = 50) -> list[dict]:
    """Return user banlist for a chat."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    now_iso = datetime.utcnow().isoformat(timespec="seconds")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO pending_roles (user_id, role_name, reserved_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   role_name   = excluded.role_name,
                   reserved_at = excluded.reserved_at""",
            (user_id, role_name, now_iso),
        )
        await db.commit()


async def get_pending_role(user_id: int) -> str | None:
    """Return the pending role name for a user, or None."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT role_name FROM pending_roles WHERE user_id = ?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        return row[0] if row else None


async def clear_pending_role(user_id: int) -> None:
    """Remove any pending role for a user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM pending_roles WHERE user_id = ?", (user_id,))
        await db.commit()


# ─── Авто-варн за неактив ─────────────────────────────────────────────────────

async def get_chats_with_inactivity_warn() -> list[dict]:
    """Return all chats where inactivity_warn_enabled=1."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
                  OR COALESCE(us.last_active, '') > us.inactivity_warned_at
              )
            """,
            (chat_id, cutoff_iso),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def set_inactivity_warned(user_id: int, chat_id: int, when_iso: str) -> None:
    """Записать время авто-варна за неактив."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT chat_id, next_cleanup_at, cleanup_reminder_sent
               FROM chat_settings
               WHERE next_cleanup_at IS NOT NULL"""
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def set_cleanup_reminder_sent(chat_id: int, sent: int) -> None:
    await set_chat_setting(chat_id, "cleanup_reminder_sent", sent)


# ─── Питомцы ──────────────────────────────────────────────────────────────────

async def get_pet(user_id: int, chat_id: int) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pets WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ) as c:
            row = await c.fetchone()
            return dict(row) if row else None


async def adopt_pet(user_id: int, partner_id: int, chat_id: int, pet_type: str) -> None:
    """Создаёт питомца для обоих партнёров."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        for uid in (user_id, partner_id):
            await db.execute(
                """INSERT INTO pets (user_id, chat_id, pet_type, adopted_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id, chat_id) DO NOTHING""",
                (uid, chat_id, pet_type, now),
            )
        await db.commit()


async def rename_pet(user_id: int, chat_id: int, name: str) -> bool:
    """Переименовать питомца обоих партнёров. Возвращает True если питомец найден."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Обновляем имя у самого юзера
        await db.execute(
            "UPDATE pets SET name = ? WHERE user_id = ? AND chat_id = ?",
            (name, user_id, chat_id),
        )
        # Обновляем имя и у партнёра (питомец общий на двоих)
        async with db.execute(
            "SELECT partner_id FROM marriages WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ) as c:
            marriage_row = await c.fetchone()
        if marriage_row:
            partner_id = marriage_row[0]
            await db.execute(
                "UPDATE pets SET name = ? WHERE user_id = ? AND chat_id = ?",
                (name, partner_id, chat_id),
            )
        await db.commit()
        async with db.execute(
            "SELECT user_id FROM pets WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ) as c:
            return await c.fetchone() is not None


# ─── Экспедиции питомцев ──────────────────────────────────────────────────────

async def start_expedition(user_id: int, chat_id: int, duration_h: int,
                           reward_min: int, reward_max: int) -> bool:
    """Начать экспедицию. Возвращает False если экспедиция уже идёт."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM pet_expeditions WHERE user_id=? AND chat_id=? AND finished=0",
            (user_id, chat_id),
        ) as c:
            if await c.fetchone():
                return False
        await db.execute(
            """INSERT INTO pet_expeditions (user_id, chat_id, started_at, duration_h,
                                           reward_min, reward_max, finished)
               VALUES (?, ?, ?, ?, ?, ?, 0)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                   started_at=excluded.started_at, duration_h=excluded.duration_h,
                   reward_min=excluded.reward_min, reward_max=excluded.reward_max, finished=0""",
            (user_id, chat_id, now, duration_h, reward_min, reward_max),
        )
        await db.commit()
        return True


async def get_active_expedition(user_id: int, chat_id: int):
    """Возвращает активную экспедицию или None."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pet_expeditions WHERE user_id=? AND chat_id=? AND finished=0",
            (user_id, chat_id),
        ) as c:
            return await c.fetchone()


async def get_all_finished_expeditions() -> list:
    """Вернуть все незавершённые экспедиции, время которых истекло."""
    now = datetime.utcnow()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pet_expeditions WHERE finished=0"
        ) as c:
            rows = await c.fetchall()
    result = []
    for r in rows:
        started = datetime.fromisoformat(r["started_at"])
        if now >= started + timedelta(hours=r["duration_h"]):
            result.append(r)
    return result


async def finish_expedition(user_id: int, chat_id: int):
    """Пометить экспедицию как завершённую."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE pet_expeditions SET finished=1 WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        await db.commit()


# ─── Гача (Молитвы) ──────────────────────────────────────────────────────────

async def get_gacha_pity(user_id: int, chat_id: int) -> int:
    """Сколько круток без леги (pity counter). Считаем непрерывную серию без lego."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
                         item_name: str, rarity: str):
    now = datetime.utcnow().isoformat(timespec="seconds")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO gacha_inventory (user_id, chat_id, item_key, item_name, rarity, obtained_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, chat_id, item_key, item_name, rarity, now),
        )
        await db.commit()


async def get_gacha_inventory(user_id: int, chat_id: int) -> list:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM gacha_inventory WHERE user_id=? AND chat_id=? ORDER BY id DESC",
            (user_id, chat_id),
        ) as c:
            return await c.fetchall()


async def sell_gacha_junk(user_id: int, chat_id: int) -> tuple[int, int]:
    """Продать весь мусор (rarity='junk'). Возвращает (count, total_mora)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM gacha_inventory WHERE user_id=? AND chat_id=? AND rarity='junk'",
            (user_id, chat_id),
        ) as c:
            count = (await c.fetchone())[0]
        if count == 0:
            return 0, 0
        await db.execute(
            "DELETE FROM gacha_inventory WHERE user_id=? AND chat_id=? AND rarity='junk'",
            (user_id, chat_id),
        )
        await db.commit()
    from config import GACHA_SELL_PRICES
    sell_price = count * GACHA_SELL_PRICES.get("junk", 10)
    await add_mora(user_id, chat_id, sell_price)
    return count, sell_price


async def equip_gacha_item(user_id: int, chat_id: int, item_id: int) -> bool:
    """Экипировать лего-предмет (обновить gacha_display). Возвращает False если не найден/не лего."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM gacha_inventory WHERE id=? AND user_id=? AND chat_id=?",
            (item_id, user_id, chat_id),
        ) as c:
            item = await c.fetchone()
        if not item or item["rarity"] != "legendary":
            return False
        # Убираем экипировку с других предметов
        await db.execute(
            "UPDATE gacha_inventory SET equipped=0 WHERE user_id=? AND chat_id=? AND equipped=1",
            (user_id, chat_id),
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
    now = datetime.utcnow()
    matures = now + timedelta(days=days)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Используем RETURNING для совместимости с PostgreSQL
        cursor = await db.execute(
            """INSERT INTO bank_deposits (user_id, chat_id, amount, rate, created_at, matures_at)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (user_id, chat_id, amount, rate, now.isoformat(timespec="seconds"),
             matures.isoformat(timespec="seconds")),
        )
        row = await cursor.fetchone()
        await db.commit()
        return row[0] if row else None


async def get_user_deposits(user_id: int, chat_id: int) -> list:
    """Вернуть все активные (не снятые) вклады пользователя."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bank_deposits WHERE user_id=? AND chat_id=? AND withdrawn=0 ORDER BY id",
            (user_id, chat_id),
        ) as c:
            return await c.fetchall()


async def withdraw_deposit(deposit_id: int) -> dict | None:
    """Снять вклад. Возвращает dict с инфо о вкладе или None."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    now = datetime.utcnow().isoformat(timespec="seconds")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO shop_items (user_id, chat_id, item_type, item_value, purchased_at)
               VALUES (?, ?, ?, ?, ?) RETURNING id""",
            (user_id, chat_id, item_type, item_value, now),
        )
        row = await cursor.fetchone()
        await db.commit()
        return row[0] if row else None


async def has_shop_item(user_id: int, chat_id: int, item_type: str,
                        item_value: str | None = None) -> bool:
    """Проверить, есть ли у юзера купленный товар данного типа (и значения)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if item_value is not None:
            async with db.execute(
                "SELECT 1 FROM shop_items WHERE user_id=? AND chat_id=? AND item_type=? AND item_value=?",
                (user_id, chat_id, item_type, item_value),
            ) as c:
                return await c.fetchone() is not None
        else:
            async with db.execute(
                "SELECT 1 FROM shop_items WHERE user_id=? AND chat_id=? AND item_type=?",
                (user_id, chat_id, item_type),
            ) as c:
                return await c.fetchone() is not None


async def get_user_owned_frames(user_id: int, chat_id: int) -> set[str]:
    """Вернуть set ключей рамок, которые юзер уже купил."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT item_value FROM shop_items WHERE user_id=? AND chat_id=? AND item_type='frame'",
            (user_id, chat_id),
        ) as c:
            rows = await c.fetchall()
    return {r[0] for r in rows}


async def set_pet_color(user_id: int, chat_id: int, color_name: str):
    """Установить цвет имени питомца."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE pets SET color_name=? WHERE user_id=? AND chat_id=?",
            (color_name, user_id, chat_id),
        )
        # Обновить и у партнёра
        async with db.execute(
            "SELECT partner_id FROM marriages WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            m = await c.fetchone()
        if m:
            await db.execute(
                "UPDATE pets SET color_name=? WHERE user_id=? AND chat_id=?",
                (color_name, m[0], chat_id),
            )
        await db.commit()


async def set_pet_emoji_status(user_id: int, chat_id: int, emoji_status: str):
    """Установить эмодзи-статус питомца."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE pets SET emoji_status=? WHERE user_id=? AND chat_id=?",
            (emoji_status, user_id, chat_id),
        )
        async with db.execute(
            "SELECT partner_id FROM marriages WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            m = await c.fetchone()
        if m:
            await db.execute(
                "UPDATE pets SET emoji_status=? WHERE user_id=? AND chat_id=?",
                (emoji_status, m[0], chat_id),
            )
        await db.commit()


async def set_custom_title_in_chat(user_id: int, chat_id: int, title: str):
    """Установить кастомный титул."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO user_stats (user_id, chat_id, custom_title) VALUES (?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET custom_title = excluded.custom_title""",
            (user_id, chat_id, title),
        )
        await db.commit()


# ─── Подарки (брак) ───────────────────────────────────────────────────────────

async def give_gift(from_user: int, to_user: int, chat_id: int,
                    gift_key: str, gift_name: str, gift_price: int):
    now = datetime.utcnow().isoformat(timespec="seconds")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO marriage_gifts (from_user, to_user, chat_id, gift_key, gift_name, gift_price, gifted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (from_user, to_user, chat_id, gift_key, gift_name, gift_price, now),
        )
        await db.commit()


async def get_gifts_summary(user_id: int, partner_id: int, chat_id: int) -> tuple[int, int]:
    """Возвращает (count, total_value) подарков между парой."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
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


# ─── Баффы ────────────────────────────────────────────────────────────────────

async def add_buff(user_id: int, chat_id: int, buff_type: str,
                   hours: int, source: str = ""):
    now = datetime.utcnow()
    expires = now + timedelta(hours=hours)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO active_buffs (user_id, chat_id, buff_type, expires_at, source)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, chat_id, buff_type, expires.isoformat(timespec="seconds"), source),
        )
        await db.commit()


async def get_active_buffs(user_id: int, chat_id: int) -> list:
    """Вернуть все активные (не истёкшие) баффы."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    """Вернуть все активные групповые чаты."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT chat_id FROM chats WHERE is_active=1 AND chat_type IN ('group','supergroup')"
        ) as c:
            return [r[0] for r in await c.fetchall()]


# ═══════════════════════════════════════════════════════════════════════════════
#  🎨  Темы профиля
# ═══════════════════════════════════════════════════════════════════════════════

async def get_user_themes(user_id: int, chat_id: int) -> list:
    """Вернуть все темы, которыми владеет юзер."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_themes WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            return await c.fetchall()


async def add_user_theme(user_id: int, chat_id: int, theme_key: str, source: str = "shop"):
    """Добавить тему юзеру (если ещё нет)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO user_themes (user_id, chat_id, theme_key, source, obtained_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, chat_id, theme_key, source, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def set_active_theme(user_id: int, chat_id: int, theme_key: str):
    """Установить активную тему профиля."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT badge_key FROM user_badges WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            return [r["badge_key"] for r in await c.fetchall()]


async def award_badge(user_id: int, chat_id: int, badge_key: str):
    """Дать бейдж юзеру (если ещё нет)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO user_badges (user_id, chat_id, badge_key, obtained_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, chat_id, badge_key, datetime.utcnow().isoformat()),
        )
        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
#  👋  Личные приветствия
# ═══════════════════════════════════════════════════════════════════════════════

async def get_user_greeting(user_id: int, chat_id: int):
    """Вернуть строку greeting (template_key) или None."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_greetings WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        ) as c:
            return await c.fetchone()


async def set_user_greeting(user_id: int, chat_id: int, template_key: str, source: str = "gacha"):
    """Назначить или сменить приветствие юзеру."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO user_greetings (user_id, chat_id, template_key, source, obtained_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET template_key=?, source=?""",
            (user_id, chat_id, template_key, source, datetime.utcnow().isoformat(),
             template_key, source),
        )
        await db.commit()


async def check_greeting_today(user_id: int, chat_id: int, today_str: str) -> bool:
    """True если приветствие уже показано сегодня."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    now = datetime.utcnow()
    expires = now + timedelta(seconds=duration_sec)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            """INSERT INTO chest_events (chat_id, started_at, expires_at)
               VALUES (?, ?, ?) RETURNING id""",
            (chat_id, now.isoformat(), expires.isoformat()),
        )
        row = await cur.fetchone()
        await db.commit()
        return row[0] if row else None


async def get_chest_event_winners(event_id: int) -> list:
    """Вернуть победителей сундука с именами пользователей."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT c.position, c.reward, c.user_id,
                   u.username
            FROM chest_event_clicks c
            LEFT JOIN users u ON u.user_id = c.user_id
            WHERE c.event_id = ?
            ORDER BY c.position
            """,
            (event_id,),
        ) as cur:
            return await cur.fetchall()


async def get_expired_unfinished_chest_events() -> list:
    """Вернуть все ивенты с просроченным expires_at и finished=0."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, chat_id, message_id FROM chest_events WHERE finished=0 AND expires_at < ?",
            (now,),
        ) as cur:
            return await cur.fetchall()


async def is_user_single(user_id: int, chat_id: int) -> bool:
    """Вернуть True если у пользователя нет активного брака в этом чате."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM marriages WHERE (user_id=? OR partner_id=?) AND chat_id=?",
            (user_id, user_id, chat_id),
        ) as cur:
            return (await cur.fetchone()) is None


async def set_chest_event_message(event_id: int, message_id: int):
    """Обновить message_id ивента сундука."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE chest_events SET message_id=? WHERE id=?",
            (message_id, event_id),
        )
        await db.commit()


async def add_chest_click(event_id: int, user_id: int, position: int, reward: int) -> bool:
    """Кликнуть по сундуку. Возвращает True если клик записан (первый для юзера)."""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                """INSERT INTO chest_event_clicks (event_id, user_id, clicked_at, position, reward)
                   VALUES (?, ?, ?, ?, ?)""",
                (event_id, user_id, datetime.utcnow().isoformat(), position, reward),
            )
            await db.commit()
            return True
    except Exception:
        return False


async def get_chest_click_count(event_id: int) -> int:
    """Количество кликов по сундуку."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM chest_event_clicks WHERE event_id=?",
            (event_id,),
        ) as c:
            return (await c.fetchone())[0]


async def finish_chest_event(event_id: int):
    """Пометить ивент как завершённый."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE chest_events SET finished=1 WHERE id=?", (event_id,),
        )
        await db.commit()


async def get_equipped_legendary(user_id: int, chat_id: int):
    """Вернуть экипированный легендарный предмет или None."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT item_name, item_key FROM gacha_inventory WHERE user_id=? AND chat_id=? AND equipped=1 LIMIT 1",
            (user_id, chat_id),
        ) as c:
            return await c.fetchone()


async def increment_tracker(user_id: int, chat_id: int, field: str, amount: int = 1):
    """Инкрементировать один из трекинг-счётчиков в user_mora."""
    if field not in ("expeditions_sent", "chests_opened", "casino_wins"):
        return
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            f"UPDATE user_mora SET {field} = COALESCE({field}, 0) + ? WHERE user_id=? AND chat_id=?",
            (amount, user_id, chat_id),
        )
        await db.commit()

