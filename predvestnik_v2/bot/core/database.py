import aiosqlite
from loguru import logger
from bot.config import config

async def init_db():
    logger.info("Проверка и создание таблиц SQLite...")
    async with aiosqlite.connect(config.db_path, timeout=20.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA temp_store=MEMORY;")
        
        # 1. Глобальная таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_tg_id INTEGER PRIMARY KEY,
                user_tg_username TEXT,
                user_balance_mora REAL DEFAULT 0.0,
                user_balance_diamonds REAL DEFAULT 0.0,
                global_rank INTEGER DEFAULT 0,
                user_is_active BOOLEAN DEFAULT TRUE
            )
        """)
        
        # 2. Статистика в чате
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_chat_stats (
                user_tg_id INTEGER,
                chat_tg_id INTEGER,
                user_level INTEGER DEFAULT 1,
                user_xp INTEGER DEFAULT 0,
                local_rank INTEGER DEFAULT 0,
                user_messages_count_per_day INTEGER DEFAULT 0,
                user_messages_count_per_week INTEGER DEFAULT 0,
                user_messages_count_per_month INTEGER DEFAULT 0,
                user_messages_count_all_time INTEGER DEFAULT 0,
                user_messages_count_per_last_day INTEGER DEFAULT 0,
                user_messages_count_per_last_week INTEGER DEFAULT 0,
                user_messages_count_per_last_month INTEGER DEFAULT 0,
                last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_left BOOLEAN DEFAULT 0,
                PRIMARY KEY (user_tg_id, chat_tg_id)
            )
        """)

        # БЕЗОПАСНОЕ ДОБАВЛЕНИЕ НОВЫХ КОЛОНОК (ДЛЯ СИСТЕМЫ ЧИСТКИ И ИММУНИТЕТА)
        new_columns = [
            ("joined_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"), 
            ("immune_until", "TIMESTAMP DEFAULT NULL"),           
            ("is_immune", "BOOLEAN DEFAULT 0"),                   
            ("warnings", "INTEGER DEFAULT 0")                     
        ]
        for col_name, col_type in new_columns:
            try:
                await db.execute(f"ALTER TABLE user_chat_stats ADD COLUMN {col_name} {col_type}")
            except aiosqlite.OperationalError:
                pass 

        # 3. Ежедневная статистика
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_user_stats (
                user_id INTEGER,
                chat_id INTEGER,
                date TEXT, 
                message_count INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, chat_id, date)
            )
        """)

        # 4. Настройки чата
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                shield_duration_days INTEGER DEFAULT 0, 
                max_warnings INTEGER DEFAULT 3,         
                is_purging BOOLEAN DEFAULT 0,           
                purge_min_rank INTEGER DEFAULT 4        
            )
        """)

        # 5. История Варнов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                admin_id INTEGER,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 6. ЧЕРНЫЙ СПИСОК И ЛОГИ
        await db.execute("""
            CREATE TABLE IF NOT EXISTS moderation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                admin_id INTEGER,
                action TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 7. Таблица браков
        await db.execute("""
            CREATE TABLE IF NOT EXISTS marriages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user1_id INTEGER,
                user1_name TEXT,
                user2_id INTEGER,
                user2_name TEXT,
                marriage_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Безопасное добавление Семейного Бюджета к бракам
        try:
            await db.execute("ALTER TABLE marriages ADD COLUMN family_balance REAL DEFAULT 0.0")
        except aiosqlite.OperationalError:
            pass

        # 8. Таблица связок
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_links (
                main_chat_id INTEGER PRIMARY KEY,
                admin_chat_id INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 9. Токены для связок
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_bind_tokens (
                token TEXT PRIMARY KEY,
                main_chat_id INTEGER,
                main_chat_title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 10. ИНВЕНТАРЬ (Предметы пользователя)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                user_id INTEGER,
                item_id TEXT,
                quantity INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, item_id)
            )
        """)

        # 11. СТАТИСТИКА ЗООПАРКА ИГРОКА (Слоты, кулдауны)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_zoo_stats (
                user_id INTEGER PRIMARY KEY,
                max_slots INTEGER DEFAULT 3,
                wolf_cooldown_until TIMESTAMP DEFAULT NULL,
                last_income_collection TIMESTAMP DEFAULT NULL
            )
        """)

        # 12. ПИТОМЦЫ
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,                   -- ID владельца (одиночка)
                marriage_id INTEGER DEFAULT NULL,   -- ID брака (если это семейный питомец)
                name TEXT,
                species_id TEXT,                    -- Связь с PET_SPECIES ('wolf', 'fox')
                rarity TEXT,                        -- 'common', 'rare', 'epic', 'legendary'
                
                -- Локация питомца: 'active' (спутник), 'passive' (в питомнике), 'storage' (на складе)
                placement TEXT DEFAULT 'storage',   
                
                fatigue INTEGER DEFAULT 0,          -- Усталость от 0 до 100
                is_summoned BOOLEAN DEFAULT 0,      -- 1 если из Яйца Призыва (не дает осколок)
                
                buff_active_until TIMESTAMP DEFAULT NULL, -- Для премиум-еды
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        

        # 13. ЭКСПЕДИЦИИ ПИТОМЦЕВ 
        await db.execute("""
            CREATE TABLE IF NOT EXISTS active_expeditions (
                pet_id INTEGER PRIMARY KEY,
                chat_id INTEGER,
                duration_hours INTEGER,
                cost_mora REAL,
                ends_at TIMESTAMP
            )
        """)

        # ==========================================
        # 🚀 ИНДЕКСЫ ДЛЯ УСКОРЕНИЯ
        # ==========================================
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(user_tg_username)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_stats_chat_xp ON user_chat_stats(chat_tg_id, user_xp DESC)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_mod_chat_action ON moderation_logs(chat_id, action)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_marriages_chat_users ON marriages(chat_id, user1_id, user2_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_daily_stats ON daily_user_stats(chat_id, date)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_pets_owner_placement ON pets(owner_id, placement)")

        # 14. Ежедневный стрик (§21)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_login (
                user_id INTEGER,
                chat_id INTEGER,
                streak INTEGER DEFAULT 0,
                last_login TEXT DEFAULT NULL,
                last_notified TEXT DEFAULT NULL,
                recovery_streak INTEGER DEFAULT 0,
                recovery_missed_days INTEGER DEFAULT 0,
                recovery_expires TEXT DEFAULT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_daily_login ON daily_login(user_id, chat_id)")

        # 15. Milestones, выданные конкретному питомцу (одноразовая выдача)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pet_milestones_received (
                pet_id INTEGER,
                milestone INTEGER,
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (pet_id, milestone)
            )
        """)

        # 16. Акция дня (B5)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_deal_current (
                slot INTEGER PRIMARY KEY,
                item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price_mora REAL DEFAULT 0,
                price_diamonds REAL DEFAULT 0,
                generated_at TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_deal_purchases (
                user_id INTEGER,
                slot INTEGER,
                purchase_date TEXT,
                PRIMARY KEY (user_id, slot, purchase_date)
            )
        """)

        # 17. Лог кошелька (B9)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wallet_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER,
                delta_mora REAL DEFAULT 0,
                delta_diamonds REAL DEFAULT 0,
                balance_mora_after REAL NOT NULL,
                balance_diamonds_after REAL NOT NULL,
                source TEXT NOT NULL,
                target_id INTEGER,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_wallet_log_user "
            "ON wallet_log(user_id, created_at DESC)"
        )

        # 18. Достижения (B11)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                achievement_id TEXT NOT NULL,
                level INTEGER DEFAULT 0,
                progress REAL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, achievement_id)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_achievements_user "
            "ON achievements(user_id)"
        )

        # 19. Обмен Мора→Алмазы ивенты (B15)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS exchange_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                starts_at TIMESTAMP NOT NULL,
                ends_at TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'scheduled'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_exchange_quota (
                user_id INTEGER,
                event_id INTEGER,
                diamonds_converted REAL DEFAULT 0,
                PRIMARY KEY (user_id, event_id)
            )
        """)

        # 20. Мини-игры (B16)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS gamble_cooldowns (
                user_id INTEGER,
                game TEXT,
                last_played TIMESTAMP,
                PRIMARY KEY (user_id, game)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS gamble_daily_winnings (
                user_id INTEGER,
                date TEXT,
                total_won REAL DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        """)

        # 21. NSFW согласия (B10)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_nsfw_consents (
                target_user_id INTEGER,
                chat_id INTEGER,
                status TEXT NOT NULL,
                set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (target_user_id, chat_id)
            )
        """)

        # 21. Гача — счётчики пити (B3)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS gacha_pity (
                user_id INTEGER,
                spin_type TEXT,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, spin_type)
            )
        """)

        # 22. Гача — история спинов (B3)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS gacha_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                spin_type TEXT NOT NULL,
                reward_json TEXT NOT NULL,
                rolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_gacha_history_user "
            "ON gacha_history(user_id, rolled_at DESC)"
        )

        # 18. Псевдонимы пользователей (B8)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_nicknames (
                user_id INTEGER,
                chat_id INTEGER,
                nickname TEXT NOT NULL,
                set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        # Unique per (chat_id, LOWER(nickname)) to prevent duplicates within one chat
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_nickname_chat_unique "
            "ON user_nicknames(chat_id, LOWER(nickname))"
        )

        # 23. PvP Дуэли (B12)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS duels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenger_id INTEGER NOT NULL,
                challenged_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                stake REAL NOT NULL,
                challenger_pet_id INTEGER,
                challenged_pet_id INTEGER,
                status TEXT DEFAULT 'pending',
                winner_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS duel_cooldowns (
                user_a INTEGER,
                user_b INTEGER,
                last_duel TIMESTAMP,
                PRIMARY KEY (user_a, user_b)
            )
        """)

        # 24. Аукцион (B13)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auction_lots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                item_type TEXT NOT NULL,
                item_id_or_pet_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                item_name TEXT,
                min_bid REAL NOT NULL,
                buyout REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ends_at TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'active'
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_auction_lots_status ON auction_lots(status, ends_at)")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS auction_bids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lot_id INTEGER NOT NULL,
                bidder_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                is_active INTEGER DEFAULT 1,
                placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_auction_bids_lot ON auction_bids(lot_id, is_active)")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_reserve (
                user_id INTEGER PRIMARY KEY,
                reserved_mora REAL DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS auction_weekly_count (
                user_id INTEGER,
                week_start TEXT,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, week_start)
            )
        """)

        # 25. Сундуки (B14)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chest_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                spawned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'active'
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_chest_events_chat ON chest_events(chat_id, status)")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS chest_claims (
                chest_id INTEGER,
                user_id INTEGER,
                position INTEGER NOT NULL,
                claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chest_id, user_id)
            )
        """)

        # B20 — Ежедневные квесты
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_quests (
                user_id INTEGER,
                chat_id INTEGER,
                date TEXT,
                quest_id TEXT,
                progress REAL DEFAULT 0,
                completed INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id, date, quest_id)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_daily_quests "
            "ON daily_quests(user_id, chat_id, date)"
        )

        # C1-A: Chat blacklist
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_blacklist (
                chat_id INTEGER,
                user_id INTEGER,
                reason TEXT,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        # C1-C: Global blacklist
        await db.execute("""
            CREATE TABLE IF NOT EXISTS global_blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                reason TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(entity_type, entity_id)
            )
        """)

        # C2: Global module toggles
        await db.execute("""
            CREATE TABLE IF NOT EXISTS global_module_toggles (
                module_key TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                disabled_reason TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Safe column additions for new features
        new_schema_columns = [
            ("chat_settings", "chat_title", "TEXT DEFAULT NULL"),
            ("chat_settings", "timezone_offset", "INTEGER DEFAULT 0"),
            ("chat_settings", "last_chest_at", "TIMESTAMP DEFAULT NULL"),
            # B19: rank-based permissions
            ("chat_settings", "rank_warn",          "INT DEFAULT 2"),
            ("chat_settings", "rank_mute",          "INT DEFAULT 3"),
            ("chat_settings", "rank_kick",          "INT DEFAULT 4"),
            ("chat_settings", "rank_ban",           "INT DEFAULT 5"),
            ("chat_settings", "rank_shield",        "INT DEFAULT 4"),
            ("chat_settings", "rank_immune",        "INT DEFAULT 5"),
            ("chat_settings", "events_enabled",     "INT DEFAULT 1"),
            ("chat_settings", "nsfw_warps_allowed", "INT DEFAULT 1"),
            ("chat_settings", "auction_min_rank",   "INT DEFAULT 0"),
            ("pets", "last_fatigue_update", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("pets", "pet_level", "INT DEFAULT 1"),
            ("pets", "duplicates_collected", "INT DEFAULT 0"),
            ("pets", "copy_index", "INT DEFAULT 1"),
            # C2: per-chat module toggles
            ("chat_settings", "module_shop",        "INT DEFAULT 1"),
            ("chat_settings", "module_gacha",       "INT DEFAULT 1"),
            ("chat_settings", "module_expeditions", "INT DEFAULT 1"),
            ("chat_settings", "module_auction",     "INT DEFAULT 1"),
            ("chat_settings", "module_games",       "INT DEFAULT 1"),
            ("chat_settings", "module_exchange",    "INT DEFAULT 1"),
            ("chat_settings", "module_quests",      "INT DEFAULT 1"),
            ("chat_settings", "module_zoo",         "INT DEFAULT 1"),
            ("chat_settings", "module_warps",       "INT DEFAULT 1"),
            ("chat_settings", "module_daily_deal",  "INT DEFAULT 1"),
        ]
        for table, col, col_type in new_schema_columns:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            except aiosqlite.OperationalError:
                pass

        # 26. Промокоды
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                description TEXT DEFAULT '',
                valid_from TEXT DEFAULT NULL,
                valid_until TEXT DEFAULT NULL,
                max_activations INTEGER DEFAULT 0,
                activations_count INTEGER DEFAULT 0,
                reward_mora REAL DEFAULT 0,
                reward_diamonds REAL DEFAULT 0,
                reward_items_json TEXT DEFAULT '{}',
                is_active INTEGER DEFAULT 1,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promocode_redemptions (
                code TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                chat_id INTEGER,
                redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (code, user_id)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_promo_redemptions_user "
            "ON promocode_redemptions(user_id)"
        )

        await db.commit()