"""scripts/migrate_account_levels.py — миграция на уровни аккаунта.

Что делает (идемпотентно, повторный запуск пропускает уже обработанных):
  1. account_xp  = SUM(user_xp) по всем чатам игрока (XP не теряется);
  2. account_level = уровень по новой экспоненциальной кривой (services.leveling);
  3. разовый «Пакет Обновления 2.0»: 2000 🪙 + 5 💎 + 3× 🎟 Жетон Гачи
     (ретро-наград за «конвертированные» уровни НЕТ — осознанно, анти-инфляция);
  4. лог в rebuild_grant_log — гарант одноразовости пакета.

Запуск:  python scripts/migrate_account_levels.py --dry-run   # превью, БД не трогается
         python scripts/migrate_account_levels.py             # боевой прогон
Нужен DATABASE_URL в окружении/.env (тот же формат, что у прод-процессов).
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from services.leveling import calculate_account_level  # noqa: E402

WELCOME_MORA = 2000.0
WELCOME_DIAMONDS = 5.0
WELCOME_SPIN_TOKENS = 3


async def main(dry_run: bool) -> None:
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL не задан (env/.env)"); sys.exit(1)

    conn = await asyncpg.connect(url, timeout=20)
    await conn.execute("SET search_path TO predvestnik, public")

    # Колонки/лог-таблица — ВСЕГДА, даже в --dry-run: CREATE/ADD ... IF NOT EXISTS
    # идемпотентны и не трогают ничьи данные (тот же паттерн, что и в lifespan/
    # init_db на каждом старте прод-процессов), а без rebuild_grant_log дальнейший
    # SELECT ниже не может даже посчитать, кого показывать в превью.
    for stmt in (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_xp BIGINT DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_level INTEGER DEFAULT 1",
        """CREATE TABLE IF NOT EXISTS rebuild_grant_log (
            user_id    BIGINT PRIMARY KEY,
            old_sum_xp BIGINT NOT NULL,
            new_level  INTEGER NOT NULL,
            granted_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
    ):
        try:
            await conn.execute(stmt)
        except Exception as e:
            print(f"DDL warn: {e}")

    rows = await conn.fetch(
        "SELECT u.user_tg_id, u.user_tg_username, COALESCE(SUM(s.user_xp), 0) AS total_xp "
        "FROM users u LEFT JOIN user_chat_stats s ON s.user_tg_id = u.user_tg_id "
        "WHERE NOT EXISTS (SELECT 1 FROM rebuild_grant_log g WHERE g.user_id = u.user_tg_id) "
        "GROUP BY u.user_tg_id, u.user_tg_username ORDER BY total_xp DESC"
    )

    # Telegram обязывает: username ЛЮБОГО бота оканчивается на "bot" (правило
    # платформы, не догадка) — до фикса db_middleware (2026-07-03, БЛОК 37/38)
    # чужие боты в группах качали XP на общих основаниях с игроками. Не выдаём
    # им «Пакет Обновления 2.0» молча — просто НЕ трогаем (не пишем в
    # rebuild_grant_log), чтобы решение по спорным случаям осталось за человеком.
    def _looks_like_bot(username) -> bool:
        return bool(username) and username.strip().lower().endswith("bot")

    eligible = [r for r in rows if not _looks_like_bot(r["user_tg_username"])]
    excluded = [r for r in rows if _looks_like_bot(r["user_tg_username"])]

    print(f"К миграции: {len(eligible)} игроков{' (DRY-RUN)' if dry_run else ''}")
    if excluded:
        print(f"⚠️  Исключено как похожие на ботов (username оканчивается на 'bot'): {len(excluded)}")
        for r in excluded:
            print(f"  🤖 {r['user_tg_id']} (@{r['user_tg_username']}): xp={int(r['total_xp'] or 0)} — пропущен")

    done = 0
    for r in eligible:
        uid, total_xp = r["user_tg_id"], int(r["total_xp"] or 0)
        new_level = calculate_account_level(total_xp)
        if dry_run:
            if done < 15:
                print(f"  {uid}: xp={total_xp} → L{new_level}")
            done += 1
            continue
        async with conn.transaction():
            after = await conn.fetchrow(
                "UPDATE users SET account_xp = $1, account_level = $2, "
                "user_balance_mora = user_balance_mora + $3, "
                "user_balance_diamonds = user_balance_diamonds + $4 "
                "WHERE user_tg_id = $5 "
                "RETURNING user_balance_mora, user_balance_diamonds",
                total_xp, new_level, WELCOME_MORA, WELCOME_DIAMONDS, uid,
            )
            await conn.execute(
                "INSERT INTO inventory (user_id, item_id, quantity) VALUES ($1, 'spin_token', $2) "
                "ON CONFLICT (user_id, item_id) DO UPDATE SET quantity = inventory.quantity + $2",
                uid, WELCOME_SPIN_TOKENS,
            )
            await conn.execute(
                "INSERT INTO wallet_log (user_id, delta_mora, delta_diamonds, "
                "balance_mora_after, balance_diamonds_after, source, note) "
                "VALUES ($1, $2, $3, $4, $5, 'system', 'Пакет Обновления 2.0 (миграция уровней)')",
                uid, WELCOME_MORA, WELCOME_DIAMONDS,
                float(after["user_balance_mora"]), float(after["user_balance_diamonds"]),
            )
            await conn.execute(
                "INSERT INTO rebuild_grant_log (user_id, old_sum_xp, new_level) VALUES ($1, $2, $3)",
                uid, total_xp, new_level,
            )
        done += 1
        if done % 25 == 0:
            print(f"  …{done}/{len(eligible)}")

    print(f"Готово: {done} игроков{' (dry-run, БД не тронута)' if dry_run else ''}")
    await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="превью без изменений БД")
    asyncio.run(main(ap.parse_args().dry_run))
