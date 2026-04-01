"""
Run this script once via the DigitalOcean App Console to drop all bot tables.
After running, restart the app — init_db() will recreate them with correct BIGINT types.

Usage (in DO App Console):
    python drop_tables.py
"""
import asyncio, os, asyncpg

TABLES = [
    "user_roles", "community_roles", "channel_types", "admin_groups",
    "test_chats", "chat_admin_links",
    "rest_users", "user_stats", "allowed_groups", "marriages", "birthdays",
    "poll_votes", "polls", "user_achievements", "user_quests", "cleanup_counts",
    "rep_log", "locks", "blacklist", "chat_filters", "notes",
    "chats", "chat_settings", "users",
]

async def main():
    dsn = os.environ.get("PREDVESTNIK_DATABASE_URL")
    if not dsn:
        print("ERROR: PREDVESTNIK_DATABASE_URL is not set!")
        return
    conn = await asyncpg.connect(dsn)
    for table in TABLES:
        await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        print(f"Dropped: {table}")
    await conn.close()
    print("All bot tables dropped. Restart the app to recreate them.")

asyncio.run(main())
