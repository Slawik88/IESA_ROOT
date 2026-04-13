"""
import_chat_export.py — Парсинг Telegram JSON-экспорта (result.json).

Читает файл экспорта, подсчитывает сообщения по пользователям,
выводит статистику за текущий день / вчера / прошлую неделю / всё время.

Опционально записывает общие счётчики в user_stats.message_count (--apply).

Пользователей, которых нет в таблице users, пропускает (они ушли из чата).

Использование:
  python scripts/import_chat_export.py <result.json> <chat_id> [--apply]
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone, date


def parse_export(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    messages = data.get("messages") or []
    return [m for m in messages if m.get("type") == "message" and m.get("from_id")]


def extract_uid(from_id: str) -> int | None:
    """'user123456' → 123456"""
    if isinstance(from_id, str) and from_id.startswith("user"):
        try:
            return int(from_id[4:])
        except ValueError:
            return None
    if isinstance(from_id, int):
        return from_id
    return None


def count_messages(messages: list[dict]) -> dict:
    """Returns {user_id: {total, today, yesterday, week, by_date: {date_str: int}}}"""
    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=7)

    stats: dict[int, dict] = defaultdict(lambda: {
        "total": 0, "today": 0, "yesterday": 0, "week": 0, "name": "",
    })

    for m in messages:
        uid = extract_uid(m.get("from_id"))
        if uid is None:
            continue

        stats[uid]["total"] += 1
        stats[uid]["name"] = m.get("from", "") or stats[uid]["name"]

        ts = m.get("date_unixtime")
        if ts:
            msg_date = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
            if msg_date == today:
                stats[uid]["today"] += 1
            if msg_date == yesterday:
                stats[uid]["yesterday"] += 1
            if msg_date >= week_start:
                stats[uid]["week"] += 1

    return dict(stats)


def print_stats(stats: dict, label: str, key: str, limit: int = 30):
    ranked = sorted(stats.items(), key=lambda x: x[1][key], reverse=True)
    ranked = [(uid, s) for uid, s in ranked if s[key] > 0]
    print(f"\n{'='*50}")
    print(f" {label} (топ-{min(limit, len(ranked))} из {len(ranked)})")
    print(f"{'='*50}")
    for i, (uid, s) in enumerate(ranked[:limit], 1):
        name = s["name"] or f"user_{uid}"
        print(f"  {i:3}. {name:<30} {s[key]:>6} сообщ.")


async def apply_to_db(stats: dict, chat_id: int, known_uids: set[int]):
    """Update message_count in user_stats for known users only."""
    from database.postgres import connect as postgres_connect

    applied = 0
    skipped = 0
    for uid, s in stats.items():
        if uid not in known_uids:
            skipped += 1
            continue
        total = s["total"]
        async with postgres_connect() as db:
            # Only set if export total > current count
            row = await db.fetchone(
                "SELECT message_count FROM user_stats WHERE user_id=? AND chat_id=?",
                uid, chat_id,
            )
            current = row["message_count"] if row else 0
            if total > current:
                await db.execute(
                    """INSERT INTO user_stats (user_id, chat_id, message_count)
                       VALUES (?, ?, ?)
                       ON CONFLICT(user_id, chat_id) DO UPDATE
                       SET message_count = EXCLUDED.message_count""",
                    (uid, chat_id, total),
                )
                await db.commit()
                applied += 1
            else:
                skipped += 1
    print(f"\n✅ Обновлено: {applied}, пропущено: {skipped}")


async def get_known_users() -> set[int]:
    from database.postgres import connect as postgres_connect
    async with postgres_connect() as db:
        async with db.execute("SELECT user_id FROM users") as c:
            rows = await c.fetchall()
    return {r["user_id"] for r in rows}


def main():
    parser = argparse.ArgumentParser(description="Import Telegram chat export")
    parser.add_argument("file", help="Path to result.json")
    parser.add_argument("chat_id", type=int, help="Chat ID to import stats for")
    parser.add_argument("--apply", action="store_true", help="Write counts to DB")
    parser.add_argument("--limit", type=int, default=30, help="Top N to show")
    args = parser.parse_args()

    print(f"📂 Загрузка {args.file}...")
    messages = parse_export(args.file)
    print(f"📊 Загружено {len(messages)} сообщений")

    stats = count_messages(messages)
    print(f"👥 Уникальных пользователей: {len(stats)}")

    print_stats(stats, "🏆 Всё время", "total", args.limit)
    print_stats(stats, "📅 Сегодня", "today", args.limit)
    print_stats(stats, "📅 Вчера", "yesterday", args.limit)
    print_stats(stats, "📅 Последние 7 дней", "week", args.limit)

    if args.apply:
        import asyncio
        # Ensure we can import database modules
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        async def _apply():
            known = await get_known_users()
            print(f"\n🔍 Известных пользователей в БД: {len(known)}")
            export_uids = set(stats.keys())
            matching = export_uids & known
            missing = export_uids - known
            print(f"✅ Совпадающих: {len(matching)}, ❌ пропущено (нет в БД): {len(missing)}")
            await apply_to_db(stats, args.chat_id, known)

        asyncio.run(_apply())
    else:
        print("\n💡 Добавьте --apply чтобы записать в БД")


if __name__ == "__main__":
    main()
