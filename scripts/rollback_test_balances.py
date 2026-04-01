#!/usr/bin/env python3
"""
rollback_test_balances.py
=========================
Откатывает глобальный баланс Моры (users.balance) для пользователей
из admin-групп и тест-чатов до значений, рассчитанных ТОЛЬКО по
основным (не изолированным) чатам.

ИСТОЧНИКИ ДАННЫХ (в порядке приоритета):
  1. user_mora.balance  — суммирует только НЕ-изолированные chat_id
                          (старые per-chat данные НЕ удалялись при миграции)
  2. wallet_ledger       — пересчитывает баланс из транзакционной истории
                          (60 дней глубины, по умолчанию)

АЛГОРИТМ:
  Для каждого user_id из целевого списка:
    clean_balance = SUM(user_mora.balance) WHERE chat_id NOT IN isolated_chats
    Если clean_balance < current_balance → перезаписать

БЕЗОПАСНО:
  - Баланс никогда не повышается (только снижается или остаётся)
  - Запись в wallet_ledger: source='rollback_test_balance' для аудита
  - Dry-run режим по умолчанию (--apply чтобы применить)

ЗАПУСК:
  cd G:\IESA_ROOT
  python scripts/rollback_test_balances.py --dry-run          # только отчёт
  python scripts/rollback_test_balances.py --apply            # применить
  python scripts/rollback_test_balances.py --apply --uid 123 456  # конкретные юзеры
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─── path setup ───────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
BOT_DIR = REPO_ROOT / "PredvestnikBot"
sys.path.insert(0, str(BOT_DIR))

# Нужен PREDVESTNIK_DATABASE_URL или DATABASE_URL
DB_URL = (
    os.environ.get("PREDVESTNIK_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or ""
)
if not DB_URL:
    print("ERROR: задайте PREDVESTNIK_DATABASE_URL или DATABASE_URL")
    sys.exit(1)


# ─── helpers ──────────────────────────────────────────────────────────────────

async def get_pg():
    import asyncpg
    return await asyncpg.connect(DB_URL)


async def fetch_isolated_chat_ids(conn) -> set[int]:
    """Все чаты из admin_groups и test_chats."""
    rows_admin = await conn.fetch("SELECT chat_id FROM admin_groups")
    rows_test  = await conn.fetch("SELECT chat_id FROM test_chats")
    return {r["chat_id"] for r in rows_admin} | {r["chat_id"] for r in rows_test}


async def get_target_user_ids(conn, isolated_chat_ids: set[int], explicit_uids: list[int]) -> list[int]:
    """
    Если explicit_uids задан — использовать его.
    Иначе: все user_id у которых есть запись в user_mora для изолированного чата
    (т.е. они хоть раз были активны в admin/test chat).
    """
    if explicit_uids:
        return explicit_uids

    if not isolated_chat_ids:
        print("WARN: таблицы admin_groups и test_chats пусты. Укажи --uid вручную.")
        return []

    placeholders = ", ".join(f"${i+1}" for i in range(len(isolated_chat_ids)))
    rows = await conn.fetch(
        f"SELECT DISTINCT user_id FROM user_mora WHERE chat_id IN ({placeholders})",
        *isolated_chat_ids,
    )
    return [r["user_id"] for r in rows]


async def compute_clean_balance_from_user_mora(conn, user_id: int, isolated_ids: set[int]) -> int | None:
    """
    Суммирует user_mora.balance по НЕ-изолированным чатам.
    Возвращает None если у юзера вообще нет записей в user_mora.
    """
    rows = await conn.fetch(
        "SELECT chat_id, balance FROM user_mora WHERE user_id = $1",
        user_id,
    )
    if not rows:
        return None

    clean_sum = sum(r["balance"] for r in rows if r["chat_id"] not in isolated_ids)
    return clean_sum


async def compute_clean_balance_from_ledger(conn, user_id: int, isolated_ids: set[int]) -> int | None:
    """
    Пересчитывает баланс из wallet_ledger, игнорируя транзакции из изолированных чатов.
    Возвращает None если записей нет.
    """
    if not isolated_ids:
        return None

    placeholders = ", ".join(f"${i+2}" for i in range(len(isolated_ids)))
    rows = await conn.fetch(
        f"""
        SELECT direction, amount FROM wallet_ledger
        WHERE user_id = $1
          AND chat_id NOT IN ({placeholders})
        ORDER BY created_at
        """,
        user_id, *isolated_ids,
    )
    if not rows:
        return None

    balance = 0
    for r in rows:
        if r["direction"] == "in":
            balance += r["amount"]
        else:
            balance -= r["amount"]
    return max(0, balance)


async def main():
    parser = argparse.ArgumentParser(description="Откат балансов Моры из test/admin источников")
    parser.add_argument("--apply", action="store_true", help="Применить изменения (без флага — dry-run)")
    parser.add_argument("--uid", nargs="*", type=int, default=[], help="Конкретные user_id для отката")
    parser.add_argument("--source", choices=["user_mora", "ledger", "min"], default="user_mora",
                        help="user_mora=из per-chat колонки | ledger=из транзакций | min=минимальный из обоих")
    args = parser.parse_args()

    dry_run = not args.apply
    mode = "[DRY-RUN] " if dry_run else "[APPLY]   "
    print(f"\n{'='*60}")
    print(f"  rollback_test_balances.py  {mode}")
    print(f"  source={args.source}  uids={args.uid or 'auto'}")
    print(f"{'='*60}\n")

    conn = await get_pg()
    try:
        isolated_ids = await fetch_isolated_chat_ids(conn)
        print(f"Изолированных чатов: {len(isolated_ids)}")
        if isolated_ids:
            print(f"  {sorted(isolated_ids)}\n")

        target_uids = await get_target_user_ids(conn, isolated_ids, args.uid)
        if not target_uids:
            print("Нет пользователей для обработки. Выход.")
            return

        print(f"Пользователей для проверки: {len(target_uids)}\n")

        changed = 0
        skipped = 0
        errors = 0

        for uid in target_uids:
            # Текущий глобальный баланс
            row = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", uid)
            if row is None:
                print(f"  UID {uid}: нет в таблице users — пропуск")
                skipped += 1
                continue

            current = row["balance"] or 0

            # Рассчитываем «чистый» баланс
            clean_mora   = await compute_clean_balance_from_user_mora(conn, uid, isolated_ids)
            clean_ledger = await compute_clean_balance_from_ledger(conn, uid, isolated_ids)

            if args.source == "user_mora":
                clean = clean_mora
            elif args.source == "ledger":
                clean = clean_ledger
            else:  # min
                candidates = [x for x in [clean_mora, clean_ledger] if x is not None]
                clean = min(candidates) if candidates else None

            if clean is None:
                print(f"  UID {uid}: нет данных для расчёта чистого баланса — пропуск")
                skipped += 1
                continue

            delta = current - clean

            if delta <= 0:
                print(f"  UID {uid}: текущий={current}, чистый={clean} → без изменений")
                skipped += 1
                continue

            print(f"  UID {uid}: {current} → {clean}  (снижение на {delta} 🪙)")

            if not dry_run:
                try:
                    async with conn.transaction():
                        await conn.execute(
                            "UPDATE users SET balance = $1 WHERE user_id = $2",
                            clean, uid,
                        )
                        # Аудит-запись в wallet_ledger
                        await conn.execute(
                            """
                            INSERT INTO wallet_ledger
                                (chat_id, user_id, direction, amount, source, description, created_at)
                            VALUES
                                (0, $1, 'out', $2, 'rollback_test_balance',
                                 'Откат: удаление баланса из тест/admin источников', $3)
                            """,
                            uid, delta, datetime.now(timezone.utc),
                        )
                    changed += 1
                except Exception as e:
                    print(f"    ERROR при обновлении UID {uid}: {e}")
                    errors += 1
            else:
                changed += 1  # считаем как «будет изменён»

        print(f"\n{'─'*60}")
        print(f"Итого:")
        print(f"  {'Будет изменено' if dry_run else 'Изменено'}:  {changed}")
        print(f"  Пропущено:     {skipped}")
        if errors:
            print(f"  Ошибок:        {errors}")
        if dry_run:
            print(f"\n  Для применения запустите с флагом --apply")
        print()

    finally:
        await conn.close()


def print_sql_alternative():
    """
    Если Python-среда недоступна на сервере, можно применить SQL вручную через psql.
    Логика: обнулить вклад изолированных чатов в users.balance.

    Шаг 1 — убедитесь что isolated_chat_ids заполнены правильно:
      SELECT chat_id FROM admin_groups;
      SELECT chat_id FROM test_chats;

    Шаг 2 — Посмотреть что изменится (dry-run SQL):

    WITH isolated AS (
        SELECT chat_id FROM admin_groups
        UNION
        SELECT chat_id FROM test_chats
    ),
    dirty_sum AS (
        SELECT user_id, SUM(balance) AS dirty_balance
        FROM user_mora
        WHERE chat_id IN (SELECT chat_id FROM isolated)
        GROUP BY user_id
    ),
    clean_sum AS (
        SELECT user_id, COALESCE(SUM(balance), 0) AS clean_balance
        FROM user_mora
        WHERE chat_id NOT IN (SELECT chat_id FROM isolated)
        GROUP BY user_id
    )
    SELECT
        u.user_id,
        u.balance AS current_balance,
        COALESCE(cs.clean_balance, 0) AS clean_balance,
        u.balance - COALESCE(cs.clean_balance, 0) AS will_deduct
    FROM users u
    JOIN dirty_sum ds ON u.user_id = ds.user_id
    LEFT JOIN clean_sum cs ON u.user_id = cs.user_id
    WHERE u.balance > COALESCE(cs.clean_balance, 0)
    ORDER BY will_deduct DESC;

    Шаг 3 — Применить (только если Шаг 2 выглядит правильно!):

    WITH isolated AS (
        SELECT chat_id FROM admin_groups
        UNION
        SELECT chat_id FROM test_chats
    ),
    clean_sum AS (
        SELECT user_id, COALESCE(SUM(balance), 0) AS clean_balance
        FROM user_mora
        WHERE chat_id NOT IN (SELECT chat_id FROM isolated)
        GROUP BY user_id
    )
    UPDATE users u
    SET balance = cs.clean_balance
    FROM clean_sum cs
    WHERE u.user_id = cs.user_id
      AND u.balance > cs.clean_balance;

    -- Аудит-запись для всех изменённых (опционально):
    -- INSERT INTO wallet_ledger (chat_id, user_id, direction, amount, source, description, created_at)
    -- ... (использовать Python-скрипт для этого шага)
    """
    print(__doc__)


if __name__ == "__main__":
    if "--sql" in sys.argv:
        print_sql_alternative()
    else:
        asyncio.run(main())
