#!/usr/bin/env python3
"""
Скрипт сканирования истории Telegram-чата для Predvestnik.

Что делает:
  1. Подключается как userbot через Telethon (от имени пользователя)
  2. Считывает историю сообщений нужного чата
  3. Считает кол-во сообщений и последнюю активность по каждому user_id
  4. Записывает результаты в таблицы users и user_stats базы данных Predvestnik

Почему нужен отдельный скрипт:
  Telegram Bot API не позволяет боту читать историю чата — это техническое
  ограничение платформы. Только userbot (аккаунт пользователя) имеет доступ
  к истории. Скрипт запускается один раз для импорта накопленных данных.

Использование:
  python scan_history.py \\
      --api-id 12345678 \\
      --api-hash abcdef1234567890abcdef1234567890 \\
      --chat -1001234567890 \\
      --db path/to/bot.db \\
      [--marriages marriages.txt] \\
      [--limit 100000]

Как получить API ID и Hash:
  Зайди на https://my.telegram.org → Apps → создай приложение.

Формат --chat:
  Используй Bot API формат:
    -1001234567890  (супергруппа/канал, с префиксом -100)
    -1234567890     (обычная группа)
    @username       (публичная группа)

Формат marriages.txt (по одному браку на строку, пары через пробел):
  # комментарии начинаются с #
  123456789 987654321
  @alice @bob
  123456789 @carol

Зависимости:
  pip install telethon
"""

import argparse
import asyncio
import sqlite3
import sys
from datetime import datetime, timezone

try:
    from telethon import TelegramClient
    from telethon.tl.types import MessageService, PeerUser
except ImportError:
    print("❌ Установите зависимость: pip install telethon")
    sys.exit(1)


async def _resolve_id(client: TelegramClient, ref: str) -> int | None:
    """Возвращает Telegram user_id по @username или числовому ID."""
    ref = ref.strip()
    try:
        if ref.lstrip("-").isdigit():
            return int(ref)
        ent = await client.get_entity(ref)
        return ent.id
    except Exception as exc:
        print(f"  ⚠  Не удалось определить ID для '{ref}': {exc}")
        return None


async def migrate(
    api_id: int,
    api_hash: str,
    chat_ref: str,
    db_path: str,
    marriages_file: str | None,
    limit: int,
) -> None:
    # ── Подключение ──────────────────────────────────────────────────────────
    session_name = "migrate_iris_session"
    client = TelegramClient(session_name, api_id, api_hash)
    await client.start()
    print("✅ Подключение к Telegram — OK")

    # ── Получаем сущность чата ───────────────────────────────────────────────
    try:
        chat_entity = await client.get_entity(
            int(chat_ref) if chat_ref.lstrip("-").isdigit() else chat_ref
        )
        title = getattr(chat_entity, "title", None) or getattr(chat_entity, "username", chat_ref)
        print(f"📢 Чат: {title} (raw id={chat_entity.id})")
    except Exception as exc:
        print(f"❌ Не удалось получить чат '{chat_ref}': {exc}")
        await client.disconnect()
        return

    # Определяем chat_id в Bot API формате (супергруппы: -(1000000000000 + raw_id))
    # Если пользователь передал готовый Bot API ID — используем его напрямую.
    if chat_ref.lstrip("-").isdigit():
        chat_id = int(chat_ref)
    else:
        # Пытаемся вычислить Bot API ID из raw entity id
        raw = chat_entity.id
        from telethon.tl.types import Channel, Chat
        if isinstance(chat_entity, Channel):
            chat_id = int(f"-100{raw}")
        elif isinstance(chat_entity, Chat):
            chat_id = -raw
        else:
            chat_id = raw
    print(f"💾 chat_id в БД Predvestnik: {chat_id}")

    # ── Чтение истории ───────────────────────────────────────────────────────
    print(f"\n📥 Считываем историю (до {limit:,} сообщений)…")
    msg_count: dict[int, int] = {}
    last_active: dict[int, datetime] = {}
    user_info: dict[int, tuple[str, str]] = {}   # uid -> (username, full_name)

    processed = 0
    async for msg in client.iter_messages(chat_entity, limit=limit, reverse=False):
        if isinstance(msg, MessageService):
            continue
        if not msg.from_id or not isinstance(msg.from_id, PeerUser):
            continue
        uid = msg.from_id.user_id
        msg_count[uid] = msg_count.get(uid, 0) + 1
        ts = msg.date.replace(tzinfo=timezone.utc) if msg.date else None
        if ts and (uid not in last_active or ts > last_active[uid]):
            last_active[uid] = ts
        processed += 1
        if processed % 5000 == 0:
            print(f"  … {processed:,} сообщений обработано, {len(msg_count)} пользователей")

    print(f"  Итого: {processed:,} сообщений, {len(msg_count)} уникальных пользователей")

    # ── Резолвим имена участников ────────────────────────────────────────────
    print("\n👥 Загружаем список участников чата…")
    try:
        async for participant in client.iter_participants(chat_entity):
            uid = participant.id
            uname = participant.username or ""
            fname = (participant.first_name or "") + (
                " " + (participant.last_name or "") if participant.last_name else ""
            )
            user_info[uid] = (uname, fname.strip())
    except Exception as exc:
        print(f"  ⚠  Не удалось получить список участников: {exc}")
        print("     Имена будут пустыми для пользователей, которые не написали хотя бы 1 сообщение.")

    # Дополняем user_info из sender объектов (если участники не загрузились)
    async for msg in client.iter_messages(chat_entity, limit=min(limit, 5000), reverse=False):
        if isinstance(msg, MessageService) or not msg.sender:
            continue
        uid = msg.sender_id
        if uid and uid not in user_info:
            s = msg.sender
            uname = getattr(s, "username", "") or ""
            fname = (getattr(s, "first_name", "") or "") + (
                " " + (getattr(s, "last_name", "") or "") if getattr(s, "last_name", None) else ""
            )
            user_info[uid] = (uname, fname.strip())

    # ── Запись в SQLite ──────────────────────────────────────────────────────
    print(f"\n💾 Записываем в базу данных: {db_path}")
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    inserted = updated = 0
    for uid, count in msg_count.items():
        uname, fname = user_info.get(uid, ("", str(uid)))
        la = last_active.get(uid)
        la_str = la.strftime("%Y-%m-%dT%H:%M:%S") if la else None

        # upsert users (не затираем непустые значения)
        cur.execute(
            """
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username  = CASE WHEN excluded.username  != '' THEN excluded.username  ELSE users.username  END,
                full_name = CASE WHEN excluded.full_name != '' THEN excluded.full_name ELSE users.full_name END
            """,
            (uid, uname, fname),
        )

        # upsert user_stats (суммируем message_count, берём более позднюю last_active)
        cur.execute(
            "SELECT message_count FROM user_stats WHERE user_id=? AND chat_id=?", (uid, chat_id)
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                """
                INSERT INTO user_stats (user_id, chat_id, message_count, last_active)
                VALUES (?, ?, ?, ?)
                """,
                (uid, chat_id, count, la_str),
            )
            inserted += 1
        else:
            # Берём максимальное из двух счётчиков (не суммируем, чтобы не задвоить)
            new_count = max(row[0], count)
            cur.execute(
                """
                UPDATE user_stats
                SET message_count = ?,
                    last_active   = CASE
                        WHEN last_active IS NULL OR (? IS NOT NULL AND last_active < ?)
                        THEN ?
                        ELSE last_active
                    END
                WHERE user_id=? AND chat_id=?
                """,
                (new_count, la_str, la_str, la_str, uid, chat_id),
            )
            updated += 1

    con.commit()
    print(f"  user_stats: {inserted} вставлено, {updated} обновлено")

    # ── Импорт браков ────────────────────────────────────────────────────────
    marriages_imported = 0
    if marriages_file:
        print(f"\n💑 Импорт браков из {marriages_file}…")
        try:
            with open(marriages_file, encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
        except FileNotFoundError:
            print(f"  ❌ Файл не найден: {marriages_file}")
            lines = []

        now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        for line in lines:
            parts = line.split()
            if len(parts) < 2:
                print(f"  ⚠  Пропуск (неверный формат): {line!r}")
                continue
            uid1 = await _resolve_id(client, parts[0])
            uid2 = await _resolve_id(client, parts[1])
            if uid1 is None or uid2 is None:
                continue
            # Вставляем запись для обоих партнёров
            for u, p in [(uid1, uid2), (uid2, uid1)]:
                cur.execute(
                    """
                    INSERT INTO marriages (user_id, chat_id, partner_id, married_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, chat_id) DO UPDATE SET
                        partner_id = excluded.partner_id,
                        married_at = excluded.married_at
                    """,
                    (u, chat_id, p, now_str),
                )
            marriages_imported += 1
            print(f"  ✅ Брак [{uid1}] ↔ [{uid2}]")

        con.commit()
        print(f"\n  Браков импортировано: {marriages_imported}")
    else:
        print("\nℹ️  Файл браков не указан (--marriages). Пропуск.")
        print("   Как подготовить файл браков — см. комментарий в начале скрипта.")

    con.close()
    await client.disconnect()

    print("\n✅ Миграция завершена успешно!")
    print(f"   Сообщения: {inserted + updated} пользователей обновлено")
    print(f"   Браки:     {marriages_imported} пар импортировано")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Миграция данных из истории Telegram-чата в базу Predvestnik",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--api-id", type=int, required=True,
        help="Telegram API ID (получить на my.telegram.org)",
    )
    parser.add_argument(
        "--api-hash", type=str, required=True,
        help="Telegram API Hash (получить на my.telegram.org)",
    )
    parser.add_argument(
        "--chat", type=str, required=True,
        help="ID или @username чата (Bot API формат, напр. -1001234567890)",
    )
    parser.add_argument(
        "--db", type=str, required=True,
        help="Путь к файлу bot.db (SQLite)",
    )
    parser.add_argument(
        "--marriages", type=str, default=None,
        help="(необязательно) Путь к файлу браков (см. формат в начале скрипта)",
    )
    parser.add_argument(
        "--limit", type=int, default=100_000,
        help="Максимальное кол-во сообщений для чтения (по умолчанию 100000)",
    )
    args = parser.parse_args()

    asyncio.run(
        migrate(
            api_id=args.api_id,
            api_hash=args.api_hash,
            chat_ref=args.chat,
            db_path=args.db,
            marriages_file=args.marriages,
            limit=args.limit,
        )
    )


if __name__ == "__main__":
    main()
