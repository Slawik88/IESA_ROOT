"""
scripts/cleanup_isolated_chats.py
──────────────────────────────────────────────────────────────────────────────
Removes per-chat data for admin_groups and test_chats (isolated chats).

WHY THIS EXISTS
───────────────
Before the multi-channel isolation update, add_mora() and add_xp_in_chat()
had no guard — any activity in an admin or test chat wrote to the same global
users.balance and per-chat tables.  This script cleans up the per-chat
artefacts left by those chats.

WHAT IS DELETED (safe to delete — isolated-chat-only data)
───────────────────────────────────────────────────────────
  user_stats, user_mora, user_quests, user_achievements, rep_log,
  user_rpg_stats, casino_duels, casino_lottery, family_wallet,
  family_wallet_log, wallet_ledger, active_buffs, chest_events,
  chest_event_clicks, tax_events, tax_event_clicks, couple_boss_sessions,
  couple_boss_progress, solo_boss_sessions, solo_boss_progress,
  chat_treasury, treasury_log, treasury_donations, boss_damage_log,
  chat_global_buffs, feast_log, daily_checkin, singles_bonus_log,
  weekly_top_reward_log, cleanup_counts, cleanup_passes,
  anniversary_log, espionage_log, market_state, shop_items,
  bond_prices, user_bonds, user_bond_lots, bond_price_history,
  mora_loans, chat_configs, notes, chat_filters, blacklist, locks,
  polls, poll_votes, rest_users

WHAT IS NOT TOUCHED (global or main-chat data)
────────────────────────────────────────────────
  users            — global user records including balance (cannot be split
                     by source-chat retroactively)
  users.balance    — global mora balance; historical cross-chat pollution
                     cannot be reversed without transaction-level logs
  marriages / marriages_global
  pets / pets_global
  user_crystals, user_themes, user_badges, user_greetings
  seasons, season_progress, season_rewards
  admin_groups, test_chats, chats  (structural tables, not game data)
  pending_user_imports, pending_marriage_imports
  gacha_inventory (global)

USAGE
─────
  # Dry-run (default) — shows what WOULD be deleted:
  python scripts/cleanup_isolated_chats.py

  # Live run — actually deletes:
  python scripts/cleanup_isolated_chats.py --execute

Run from the PredvestnikBot/ directory with the venv activated.
"""

import asyncio
import sys
import os

# Allow running from PredvestnikBot/ dir
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.postgres import connect as postgres_connect, ddl_connect


# Tables with a chat_id column that should be wiped for isolated chats.
# Each entry: (table_name, chat_id_column)
PER_CHAT_TABLES = [
    ("user_stats",              "chat_id"),
    ("user_mora",               "chat_id"),
    ("user_quests",             "chat_id"),
    ("user_achievements",       "chat_id"),
    ("rep_log",                 "chat_id"),
    ("user_rpg_stats",          "chat_id"),
    ("casino_duels",            "chat_id"),
    ("casino_lottery",          "chat_id"),
    ("family_wallet",           "chat_id"),
    ("family_wallet_log",       "chat_id"),
    ("wallet_ledger",           "chat_id"),
    ("active_buffs",            "chat_id"),
    ("chest_events",            "chat_id"),
    ("chest_event_clicks",      "chat_id"),
    ("tax_events",              "chat_id"),
    ("tax_event_clicks",        "chat_id"),
    ("couple_boss_sessions",    "chat_id"),
    ("couple_boss_progress",    "chat_id"),
    ("solo_boss_sessions",      "chat_id"),
    ("solo_boss_progress",      "chat_id"),
    ("chat_treasury",           "chat_id"),
    ("treasury_log",            "chat_id"),
    ("treasury_donations",      "chat_id"),
    ("boss_damage_log",         "chat_id"),
    ("chat_global_buffs",       "chat_id"),
    ("feast_log",               "chat_id"),
    ("daily_checkin",           "chat_id"),
    ("singles_bonus_log",       "chat_id"),
    ("weekly_top_reward_log",   "chat_id"),
    ("cleanup_counts",          "chat_id"),
    ("cleanup_passes",          "chat_id"),
    ("anniversary_log",         "chat_id"),
    ("espionage_log",           "chat_id"),
    ("market_state",            "chat_id"),
    ("bond_prices",             "chat_id"),
    ("user_bonds",              "chat_id"),
    ("user_bond_lots",          "chat_id"),
    ("bond_price_history",      "chat_id"),
    ("mora_loans",              "chat_id"),
    ("chat_configs",            "chat_id"),
    ("notes",                   "chat_id"),
    ("chat_filters",            "chat_id"),
    ("blacklist",               "chat_id"),
    ("locks",                   "chat_id"),
    ("polls",                   "chat_id"),
    ("poll_votes",              "chat_id"),
    ("rest_users",              "chat_id"),
    ("chat_settings",           "chat_id"),
    ("auctions",                "chat_id"),
    ("auction_bids",            "chat_id"),
    ("leave_log",               "chat_id"),
    ("user_banlist",            "chat_id"),
    ("marriage_gifts",          "chat_id"),
    ("marriage_proposals",      "chat_id"),
    ("community_roles",         "chat_id"),
    ("user_roles",              "chat_id"),
    ("pending_roles",           "chat_id"),
    ("pets",                    "chat_id"),
    ("shop_items",              "chat_id"),
    ("crystal_chat_roles",      "chat_id"),
    ("season_progress",         "chat_id"),
]


async def get_isolated_chat_ids() -> list[int]:
    """Return all chat_ids that are admin groups or test chats."""
    chat_ids: set[int] = set()
    async with postgres_connect() as db:
        async with db.execute("SELECT chat_id FROM admin_groups") as c:
            for row in await c.fetchall():
                chat_ids.add(row["chat_id"])
        async with db.execute("SELECT chat_id FROM test_chats") as c:
            for row in await c.fetchall():
                chat_ids.add(row["chat_id"])
    return sorted(chat_ids)


async def count_rows(table: str, col: str, chat_id: int) -> int:
    try:
        async with postgres_connect() as db:
            async with db.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE {col} = $1", chat_id
            ) as c:
                row = await c.fetchone()
                return row["n"] if row else 0
    except Exception:
        return -1  # table may not exist yet


async def delete_rows(table: str, col: str, chat_id: int) -> int:
    try:
        async with postgres_connect() as db:
            status = await db.execute(
                f"DELETE FROM {table} WHERE {col} = $1", chat_id
            )
            await db.commit()
            # status is like "DELETE 42"
            try:
                return int(str(status).split()[-1])
            except (ValueError, IndexError):
                return 0
    except Exception as e:
        print(f"    ✗ Error deleting from {table}: {e}")
        return 0


async def main(execute: bool) -> None:
    print("=" * 72)
    print("Isolated-chat data cleanup")
    mode = "LIVE RUN — changes WILL be committed" if execute else "DRY RUN — no changes"
    print(f"Mode: {mode}")
    print("=" * 72)

    chat_ids = await get_isolated_chat_ids()
    if not chat_ids:
        print("No isolated chats found in admin_groups / test_chats. Nothing to do.")
        return

    print(f"\nIsolated chat IDs ({len(chat_ids)}): {chat_ids}\n")

    total_deleted = 0
    for chat_id in chat_ids:
        print(f"\n── chat_id {chat_id} ──────────────────────────────────────────────")
        for table, col in PER_CHAT_TABLES:
            count = await count_rows(table, col, chat_id)
            if count < 0:
                # table doesn't exist
                continue
            if count == 0:
                continue
            if execute:
                deleted = await delete_rows(table, col, chat_id)
                print(f"  DELETED {deleted:>6} rows  ← {table}")
                total_deleted += deleted
            else:
                print(f"  WOULD DELETE {count:>5} rows  ← {table}")
                total_deleted += count

    print()
    if execute:
        print(f"Done. Total rows deleted: {total_deleted}")
        print()
        print("REMINDER: users.balance was NOT modified.")
        print("  The global balance accumulated from isolated chats cannot be")
        print("  retroactively separated from legitimate main-chat earnings.")
        print("  Use the bot admin panel to manually correct specific user balances.")
    else:
        print(f"Dry-run complete. Would delete ~{total_deleted} rows across all isolated chats.")
        print("Re-run with --execute to apply changes.")


if __name__ == "__main__":
    execute = "--execute" in sys.argv
    if execute:
        confirm = input(
            "\n⚠ This will permanently delete data for all isolated chats.\n"
            "  Type 'YES' to confirm: "
        )
        if confirm.strip() != "YES":
            print("Aborted.")
            sys.exit(0)
    asyncio.run(main(execute))
