"""Transactional PostgreSQL notifications for live player balances.

The triggers cover every writer, including Telegram commands and maintenance
jobs. PostgreSQL delivers NOTIFY only after COMMIT, so clients never render a
balance from a transaction that later rolls back.
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
