#!/usr/bin/env python3
"""
achievements_catchup.py — Скрипт догоняющей миграции достижений.

Проходит по всем парам (user_id, chat_id), собирает текущие счётчики
и вызывает check_and_grant() для каждого типа действий.
Идемпотентно: повторный запуск безопасен (INSERT ON CONFLICT DO NOTHING).

Использование:
    cd PredvestnikBot
    python -m scripts.achievements_catchup          # полный прогон
    python -m scripts.achievements_catchup --dry     # только подсчёт, без выдачи
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import os

# Убеждаемся что PredvestnikBot в sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
_log = logging.getLogger("achievements_catchup")


async def run(dry: bool = False) -> None:
    from database.postgres import get_pg_pool
    from services.achievements import (
        ACH_BY_TYPE, check_and_grant, _fetch_counters,
    )

    pool = await get_pg_pool()

    # Получаем все уникальные пары (user_id, chat_id) из user_stats
    async with pool.acquire() as conn:
        pairs = await conn.fetch(
            "SELECT DISTINCT user_id, chat_id FROM user_stats WHERE message_count > 0"
        )

    total_pairs = len(pairs)
    _log.info("Найдено %d пар (user_id, chat_id) для проверки", total_pairs)

    total_awarded = 0
    errors = 0

    for idx, row in enumerate(pairs, 1):
        user_id = row["user_id"]
        chat_id = row["chat_id"]

        try:
            # Собираем все счётчики для этого юзера
            async with pool.acquire() as conn:
                counters = await _fetch_counters(conn, user_id, chat_id)

            if dry:
                # В dry-mode просто считаем потенциальные ачивки
                potential = 0
                for action_type, value in counters.items():
                    candidates = ACH_BY_TYPE.get(action_type, [])
                    for ach in candidates:
                        if value >= ach["threshold"]:
                            potential += 1
                if potential > 0:
                    _log.info("[%d/%d] uid=%d chat=%d — потенциально %d ачивок",
                              idx, total_pairs, user_id, chat_id, potential)
            else:
                # Реальная выдача
                user_awarded = 0
                for action_type, value in counters.items():
                    if value <= 0:
                        continue
                    newly = await check_and_grant(user_id, chat_id, action_type, value)
                    user_awarded += len(newly)
                    for ach in newly:
                        _log.info("  🏆 uid=%d chat=%d: %s %s (+%d мора, +%d xp)",
                                  user_id, chat_id, ach["emoji"], ach["title"],
                                  ach["mora"], ach.get("xp", 0))

                if user_awarded > 0:
                    _log.info("[%d/%d] uid=%d chat=%d — выдано %d ачивок",
                              idx, total_pairs, user_id, chat_id, user_awarded)
                total_awarded += user_awarded

        except Exception as e:
            errors += 1
            _log.error("[%d/%d] uid=%d chat=%d — ошибка: %s",
                       idx, total_pairs, user_id, chat_id, e)

        # Прогресс каждые 100 пар
        if idx % 100 == 0:
            _log.info("Прогресс: %d/%d обработано, %d ачивок выдано, %d ошибок",
                      idx, total_pairs, total_awarded, errors)

    _log.info("=" * 60)
    if dry:
        _log.info("DRY RUN завершён. Пар проверено: %d, ошибок: %d", total_pairs, errors)
    else:
        _log.info("Миграция завершена. Пар: %d, ачивок выдано: %d, ошибок: %d",
                  total_pairs, total_awarded, errors)
    _log.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Догоняющая миграция достижений")
    parser.add_argument("--dry", action="store_true", help="Только подсчёт, без выдачи")
    args = parser.parse_args()
    asyncio.run(run(dry=args.dry))


if __name__ == "__main__":
    main()
