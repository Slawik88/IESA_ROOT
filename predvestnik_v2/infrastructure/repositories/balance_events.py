"""Transactional PostgreSQL notifications for live player state.

The triggers cover every writer, including Telegram commands and maintenance
jobs. PostgreSQL delivers NOTIFY only after COMMIT, so clients never render
state from a transaction that later rolls back.
"""
from __future__ import annotations

CHANNEL = "predvestnik_balance_v1"


async def ensure_schema(db) -> None:
    await db.execute(f"""
        CREATE OR REPLACE FUNCTION predvestnik_notify_user_balance_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_notify('{CHANNEL}', json_build_object(
                'type', 'balance_changed',
                'user_id', NEW.user_tg_id,
                'mora', COALESCE(NEW.user_balance_mora, 0),
                'diamonds', COALESCE(NEW.user_balance_diamonds, 0),
                'dark_mora', COALESCE(NEW.user_balance_dark_mora, 0),
                'zarniki', COALESCE(NEW.user_balance_zarniki, 0)
            )::text);
            RETURN NEW;
        END $$
    """)
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname='users_live_balance_v1'
                  AND tgrelid='users'::regclass
            ) THEN
                CREATE TRIGGER users_live_balance_v1
                AFTER UPDATE OF user_balance_mora, user_balance_diamonds,
                    user_balance_dark_mora, user_balance_zarniki ON users
                FOR EACH ROW
                WHEN (
                    OLD.user_balance_mora IS DISTINCT FROM NEW.user_balance_mora OR
                    OLD.user_balance_diamonds IS DISTINCT FROM NEW.user_balance_diamonds OR
                    OLD.user_balance_dark_mora IS DISTINCT FROM NEW.user_balance_dark_mora OR
                    OLD.user_balance_zarniki IS DISTINCT FROM NEW.user_balance_zarniki
                ) EXECUTE FUNCTION predvestnik_notify_user_balance_v1();
            END IF;
        END $$
    """)
    await db.execute(f"""
        CREATE OR REPLACE FUNCTION predvestnik_notify_data_change_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            row_data JSONB;
            target_user BIGINT;
        BEGIN
            row_data := CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
            target_user := NULLIF(row_data ->> TG_ARGV[0], '')::BIGINT;
            IF target_user IS NOT NULL THEN
                PERFORM pg_notify('{CHANNEL}', json_build_object(
                    'type', 'data_changed', 'user_id', target_user,
                    'scope', TG_ARGV[1]
                )::text);
            END IF;
            IF TG_OP='DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END $$
    """)
    # Important personal projections change much less often than chat traffic.
    # Each trigger sends only user id + scope; the browser coalesces bursts into
    # one targeted refresh. Creating them here keeps bot, web and admin writers
    # covered without teaching every mutation path about WebSockets.
    for trigger, table, user_column, scope, operations in (
        ("users_live_profile_v1", "users", "user_tg_id", "profile",
         "AFTER UPDATE OF account_xp, global_rank, user_tg_username"),
        ("vip_live_profile_v1", "vip_subscriptions", "user_id", "profile",
         "AFTER INSERT OR UPDATE OR DELETE"),
        ("achievements_live_profile_v1", "achievements", "user_id", "achievements",
         "AFTER INSERT OR UPDATE OR DELETE"),
        ("achievement_v1_live_profile_v1", "achievement_v1_progress", "user_id", "achievements",
         "AFTER INSERT OR UPDATE OR DELETE"),
        ("quests_live_profile_v1", "quest_v1_assignments", "user_id", "quests",
         "AFTER INSERT OR UPDATE OR DELETE"),
        ("skins_owned_live_profile_v1", "skins_v3_owned", "user_id", "looks",
         "AFTER INSERT OR UPDATE OR DELETE"),
        ("skins_equipped_live_profile_v1", "skins_v3_equipped", "user_id", "looks",
         "AFTER INSERT OR UPDATE OR DELETE"),
        ("pets_live_profile_v1", "pets", "owner_id", "pets",
         "AFTER INSERT OR UPDATE OR DELETE"),
    ):
        await db.execute(f"""
            DO $$ BEGIN
                IF to_regclass('{table}') IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM pg_trigger WHERE tgname='{trigger}'
                      AND tgrelid=to_regclass('{table}')
                ) THEN
                    CREATE TRIGGER {trigger} {operations} ON {table}
                    FOR EACH ROW EXECUTE FUNCTION predvestnik_notify_data_change_v1(
                        '{user_column}', '{scope}'
                    );
                END IF;
            END $$
        """)
    await db.execute(f"""
        CREATE OR REPLACE FUNCTION predvestnik_notify_pending_web_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_notify('{CHANNEL}', json_build_object(
                'type', 'notification_pending', 'user_id', NEW.user_id
            )::text);
            RETURN NEW;
        END $$
    """)
    await db.execute("""
        DO $$ BEGIN
            IF to_regclass('web_notifications') IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname='web_notification_live_v1'
                  AND tgrelid=to_regclass('web_notifications')
            ) THEN
                CREATE TRIGGER web_notification_live_v1
                AFTER INSERT ON web_notifications FOR EACH ROW
                EXECUTE FUNCTION predvestnik_notify_pending_web_v1();
            END IF;
        END $$
    """)
    await db.execute(f"""
        CREATE OR REPLACE FUNCTION predvestnik_notify_essence_balance_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_notify('{CHANNEL}', json_build_object(
                'type', 'balance_changed', 'user_id', NEW.user_id,
                'essence', COALESCE(NEW.balance, 0)
            )::text);
            RETURN NEW;
        END $$
    """)
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname='essence_live_balance_v1'
                  AND tgrelid='skins_v3_essence_accounts'::regclass
            ) THEN
                CREATE TRIGGER essence_live_balance_v1
                AFTER UPDATE OF balance ON skins_v3_essence_accounts
                FOR EACH ROW WHEN (OLD.balance IS DISTINCT FROM NEW.balance)
                EXECUTE FUNCTION predvestnik_notify_essence_balance_v1();
            END IF;
        END $$
    """)
    await db.execute(f"""
        CREATE OR REPLACE FUNCTION predvestnik_notify_echo_balance_v1()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_notify('{CHANNEL}', json_build_object(
                'type', 'balance_changed', 'user_id', NEW.user_id,
                'echo_shards', COALESCE(NEW.balance, 0)
            )::text);
            RETURN NEW;
        END $$
    """)
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname='echo_live_balance_v1'
                  AND tgrelid='echo_shard_accounts_v1'::regclass
            ) THEN
                CREATE TRIGGER echo_live_balance_v1
                AFTER UPDATE OF balance ON echo_shard_accounts_v1
                FOR EACH ROW WHEN (OLD.balance IS DISTINCT FROM NEW.balance)
                EXECUTE FUNCTION predvestnik_notify_echo_balance_v1();
            END IF;
        END $$
    """)
