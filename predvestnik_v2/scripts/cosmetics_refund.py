#!/usr/bin/env python3
"""
scripts/cosmetics_refund.py — ОДНОРАЗОВЫЙ рефанд косметики (смена ценовой иерархии).

═══════════════════════════════════════════════════════════════════════════════
ЗАПУСК (из корня репозитория):

  python predvestnik_v2/scripts/cosmetics_refund.py --dry-run   # превью
  python predvestnik_v2/scripts/cosmetics_refund.py              # реальный рефанд

ЗАВИСИМОСТИ: DATABASE_URL в .env или переменной окружения.

═══════════════════════════════════════════════════════════════════════════════
ЛОГИКА РЕФАНДА — по СТАРЫМ ценам (то, что игрок реально заплатил):

Было 3 ценовых эпохи:
  EPOCH_1 (до 2026-06-27 14:27 UTC): мора/алмазы (без зарников или маленькие зарники)
  EPOCH_2 (2026-06-27 14:27 – 2026-06-30 18:37 UTC): зарники + вторичная валюта (мора/алмазы)
  EPOCH_3 (2026-06-30 18:37 – 23:59 UTC): только зарники (50/140/280)

Для EPOCH_1 (мора/алмазы): цена была ИЛИ/ИЛИ (два варианта оплаты на выбор).
Т.к. мы не знаем что выбрал игрок — возвращаем ОБОИМИ вариантами отдельными
проходами, но только если в одном из них есть записи. По умолчанию возвращаем
максимальный вариант (мора > алмазы; если равны — мора).

Для EPOCH_2: точная пара (зарники + вторичная) — возвращаем обе.

Для EPOCH_3: только зарники.

═══════════════════════════════════════════════════════════════════════════════
ИДЕМПОТЕНТНОСТЬ:

  - Таблица cosmetic_refund_log помечает обработанные (user_id, cosmetic_id).
  - REFUND_CUTOFF_UTC отрезает новые покупки по новым ценам.
  - Повторный запуск скипнет уже обработанные записи.
  - НЕ вызывается автоматически при деплое — только вручную.
═══════════════════════════════════════════════════════════════════════════════
"""
import asyncio
import argparse
import os
import sys
from datetime import datetime

try:
    import asyncpg
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: pip install asyncpg python-dotenv")
    sys.exit(1)

load_dotenv()

# ── Временные границы эпох (UTC, без таймзоны для сравнения с naive TIMESTAMP из PG) ─

# Коммит 7104413d — ребаланс: 2026-06-27 14:27:25 UTC
EPOCH2_START = datetime(2026, 6, 27, 14, 27, 25)

# Коммит e7ed2e73 — зарники-только: 2026-06-30 18:37:07 UTC
EPOCH3_START = datetime(2026, 6, 30, 18, 37, 7)

# Stars добавлены: коммит da7e52ab — 2026-06-30 18:49:27 UTC
STARS_START = datetime(2026, 6, 30, 18, 49, 27)

# Граница рефанда: всё ДО этого момента было куплено по старым ценам.
# Покупки ПОСЛЕ — уже по новым ценам (не рефандим).
REFUND_CUTOFF = datetime(2026, 6, 30, 23, 59, 59)

# ── Исторические цены по эпохам ──────────────────────────────────────────────
# Формат: {"mora": N, "diamonds": N, "dark_mora": N, "zarniki": N}
# Только указанные валюты — остальных нет.
# Для OR-вариантов (EPOCH_1) берём максимальный единственный.
# Источник: git history (коммиты 81dddfcc / a1b90795 / 7104413d / e7ed2e73).

# EPOCH_1 (до ребаланса): игрок мог выбрать один из двух вариантов.
# Мы возвращаем МАКСИМАЛЬНЫЙ из двух (в пользу игрока).
# Если был только один вариант — возвращаем его.
EPOCH1_PRICES: dict[str, dict] = {
    # Правило: только зарники если были; иначе — ничего (предмет не рефандится из EPOCH_1)
    "glow_silver":  {},                        # не было зарников → нет рефанда
    "glow_gold":    {"zarniki": 120},
    "glow_crimson": {"zarniki": 180},
    "glow_ember":   {},                        # не было зарников → нет рефанда
    "frame_bronze": {},
    "frame_neon":   {"zarniki": 150},
    "frame_abyss":  {},
    "frame_iron":   {},
    "title_wanderer": {},
    "title_patron": {"zarniki": 100},
    "halo_glow":    {},
    "halo_pulse":   {"zarniki": 140},
    "halo_runic":   {},
    "pbg_carbon":   {},
    "pbg_nebula":   {"zarniki": 160},
    "pbg_abyss":    {},
    "pbg_forest":   {},
    "pbg_ember":    {"zarniki": 130},
    "pbg_galaxy":   {"zarniki": 160},
    "cfx_sparks":   {},
    "cfx_snow":     {"zarniki": 140},
    "cfx_petals":   {"zarniki": 140},
    "cfx_stars":    {"zarniki": 190},
    # pbg_ocean, pbg_dusk появились в EPOCH_2 — нет EPOCH_1 цены
}

# EPOCH_2 (после ребаланса: зарники + вторая валюта одновременно):
EPOCH2_PRICES: dict[str, dict] = {
    "glow_silver":  {"zarniki": 50, "mora": 4000},
    "glow_gold":    {"zarniki": 140, "diamonds": 6},
    "glow_crimson": {"zarniki": 280, "diamonds": 9},
    "glow_ember":   {"zarniki": 280},
    "frame_bronze": {"zarniki": 50, "mora": 4000},
    "frame_neon":   {"zarniki": 140, "diamonds": 6},
    "frame_abyss":  {"zarniki": 280, "diamonds": 9},
    "frame_iron":   {"zarniki": 140},
    "title_wanderer": {"zarniki": 40, "mora": 3000},
    "title_patron": {"zarniki": 110, "diamonds": 5},
    "halo_glow":    {"zarniki": 50, "mora": 4000},
    "halo_pulse":   {"zarniki": 140, "diamonds": 6},
    "halo_runic":   {"zarniki": 280, "diamonds": 9},
    "pbg_carbon":   {"zarniki": 50, "mora": 4000},
    "pbg_nebula":   {"zarniki": 140, "diamonds": 6},
    "pbg_abyss":    {"zarniki": 280, "diamonds": 9},
    "pbg_forest":   {"zarniki": 50, "mora": 4000},
    "pbg_ocean":    {"zarniki": 50, "mora": 4000},
    "pbg_ember":    {"zarniki": 140, "diamonds": 6},
    "pbg_galaxy":   {"zarniki": 140, "diamonds": 6},
    "pbg_dusk":     {"zarniki": 280},
    "cfx_sparks":   {"zarniki": 50, "mora": 4000},
    "cfx_snow":     {"zarniki": 140, "diamonds": 6},
    "cfx_petals":   {"zarniki": 140},
    "cfx_stars":    {"zarniki": 280, "diamonds": 9},
}

# EPOCH_3 (зарники-only, 50/140/280 в зависимости от редкости):
EPOCH3_PRICES: dict[str, dict] = {
    "glow_silver":  {"zarniki": 50},
    "glow_gold":    {"zarniki": 140},
    "glow_crimson": {"zarniki": 280},
    "glow_ember":   {"zarniki": 280},
    "frame_bronze": {"zarniki": 50},
    "frame_neon":   {"zarniki": 140},
    "frame_abyss":  {"zarniki": 280},
    "frame_iron":   {"zarniki": 140},
    "title_wanderer": {"zarniki": 50},
    "title_patron": {"zarniki": 140},
    "halo_glow":    {"zarniki": 50},
    "halo_pulse":   {"zarniki": 140},
    "halo_runic":   {"zarniki": 280},
    "pbg_carbon":   {"zarniki": 50},
    "pbg_nebula":   {"zarniki": 140},
    "pbg_abyss":    {"zarniki": 280},
    "pbg_forest":   {"zarniki": 50},
    "pbg_ocean":    {"zarniki": 50},
    "pbg_ember":    {"zarniki": 140},
    "pbg_galaxy":   {"zarniki": 140},
    "pbg_dusk":     {"zarniki": 280},
    "cfx_sparks":   {"zarniki": 50},
    "cfx_snow":     {"zarniki": 140},
    "cfx_petals":   {"zarniki": 140},
    "cfx_stars":    {"zarniki": 280},
}

# Все ID предметов, которые продавались в магазине за реальные ресурсы
SHOP_IDS = set(EPOCH3_PRICES.keys())

ITEM_NAMES: dict[str, str] = {
    "glow_silver": "Серебряный ореол",   "glow_gold": "Золотое сияние",
    "glow_crimson": "Багровое пламя",    "glow_ember": "Тлеющий уголь",
    "frame_bronze": "Бронзовая оправа",  "frame_neon": "Неоновый контур",
    "frame_abyss": "Оправа Бездны",      "frame_iron": "Железная оправа",
    "title_wanderer": "Странник Пустошей","title_patron": "Меценат",
    "halo_glow": "Тёплое гало",          "halo_pulse": "Пульсирующий ореол",
    "halo_runic": "Рунический круг",     "pbg_carbon": "Карбон",
    "pbg_nebula": "Туманность",          "pbg_abyss": "Бездна",
    "pbg_forest": "Изумрудный лес",      "pbg_ocean": "Морская бездна",
    "pbg_ember": "Тлеющий вулкан",       "pbg_galaxy": "Спираль галактики",
    "pbg_dusk": "Сумерки",              "cfx_sparks": "Искры",
    "cfx_snow": "Снегопад",             "cfx_petals": "Лепестки",
    "cfx_stars": "Звездопад",
}

CUR_ICON = {"mora": "🪙", "diamonds": "💎", "dark_mora": "🌑", "zarniki": "✨"}
CUR_COL  = {
    "mora":      "user_balance_mora",
    "diamonds":  "user_balance_diamonds",
    "dark_mora": "user_balance_dark_mora",
    "zarniki":   "user_balance_zarniki",
}


def _epoch_price(cosmetic_id: str, acquired_at: datetime) -> dict:
    """Возвращает словарь {валюта: сумма} для рефанда на основе эпохи покупки."""
    if acquired_at < EPOCH2_START:
        price = EPOCH1_PRICES.get(cosmetic_id) or EPOCH2_PRICES.get(cosmetic_id, {})
    elif acquired_at < EPOCH3_START:
        price = EPOCH2_PRICES.get(cosmetic_id, {})
    else:
        price = EPOCH3_PRICES.get(cosmetic_id, {})
    return price


def _price_label(price: dict) -> str:
    parts = [f"{amt}{CUR_ICON[cur]}" for cur, amt in price.items() if amt]
    return " + ".join(parts) if parts else "—"


def _epoch_name(acquired_at: datetime) -> str:
    if acquired_at < EPOCH2_START:
        return "EPOCH1(мора/алм)"
    elif acquired_at < EPOCH3_START:
        return "EPOCH2(✨+вторая)"
    else:
        return "EPOCH3(только✨)"


# ── Основная логика ──────────────────────────────────────────────────────────

async def run(dry_run: bool) -> None:
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL не установлен", file=sys.stderr)
        sys.exit(1)

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Подключаемся к БД...")
    conn = await asyncpg.connect(db_url)

    # ── Создаём таблицу-страховку от повторного запуска ──────────────────────
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS cosmetic_refund_log (
            user_id     BIGINT NOT NULL,
            cosmetic_id TEXT   NOT NULL,
            epoch       TEXT   NOT NULL,
            refund_json TEXT   NOT NULL,
            refunded_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (user_id, cosmetic_id)
        )
    """)

    already_done: set[tuple[int, str]] = set(
        (r["user_id"], r["cosmetic_id"])
        for r in await conn.fetch("SELECT user_id, cosmetic_id FROM cosmetic_refund_log")
    )
    print(f"{prefix}Уже обработано (пропустим): {len(already_done)} записей.")

    # ── Запрос записей для рефанда ────────────────────────────────────────────
    rows = await conn.fetch(
        """
        SELECT uc.user_id, uc.cosmetic_id, uc.acquired_at,
               u.user_tg_username
        FROM user_cosmetics uc
        LEFT JOIN users u ON u.user_tg_id = uc.user_id
        WHERE uc.cosmetic_id = ANY($1::text[])
          AND uc.acquired_at <= $2
        ORDER BY uc.user_id, uc.cosmetic_id
        """,
        list(SHOP_IDS),
        REFUND_CUTOFF,
    )

    to_process = [r for r in rows if (r["user_id"], r["cosmetic_id"]) not in already_done]

    if not to_process:
        print(f"{prefix}Нет записей для рефанда (или все уже обработаны).")
        await conn.close()
        return

    print(f"\n{prefix}Найдено записей: {len(to_process)}")
    print("=" * 75)

    stars_suspects: list[dict] = []
    total_counts = {"mora": 0, "diamonds": 0, "dark_mora": 0, "zarniki": 0}
    total_items = 0

    for row in to_process:
        uid: int     = row["user_id"]
        cid: str     = row["cosmetic_id"]
        acq: datetime = row["acquired_at"]
        username: str = row["user_tg_username"] or f"id{uid}"
        name: str     = ITEM_NAMES.get(cid, cid)

        price = _epoch_price(cid, acq)
        epoch = _epoch_name(acq)
        label = _price_label(price)

        stars_flag = ""
        if acq >= STARS_START:
            stars_flag = " ⭐STARS?"
            stars_suspects.append({"uid": uid, "username": username, "cid": cid, "name": name, "acq": acq})

        print(f"  @{username:<18} | {name:<25} | {epoch} | РЕФАНД: {label}{stars_flag}")

        if not price:
            print(f"    ⚠️  Нет цены для {cid} в эпоху {epoch} — пропущено!")
            continue

        if not dry_run:
            import json
            async with conn.transaction():
                # Получаем балансы до рефанда для лога
                bal_row = await conn.fetchrow(
                    "SELECT COALESCE(user_balance_mora,0) AS m, "
                    "COALESCE(user_balance_diamonds,0) AS d, "
                    "COALESCE(user_balance_dark_mora,0) AS dm, "
                    "COALESCE(user_balance_zarniki,0) AS z "
                    "FROM users WHERE user_tg_id = $1",
                    uid,
                )

                # Начисляем каждую валюту
                for cur, amt in price.items():
                    col = CUR_COL.get(cur)
                    if not col or not amt:
                        continue
                    await conn.execute(
                        f"UPDATE users SET {col} = COALESCE({col}, 0) + $1 WHERE user_tg_id = $2",
                        int(amt), uid,
                    )
                    total_counts[cur] = total_counts.get(cur, 0) + int(amt)

                # Удаляем из user_cosmetics
                await conn.execute(
                    "DELETE FROM user_cosmetics WHERE user_id = $1 AND cosmetic_id = $2",
                    uid, cid,
                )
                # Снимаем из экипировки (если надет)
                await conn.execute(
                    "DELETE FROM user_cosmetic_loadout WHERE user_id = $1 AND cosmetic_id = $2",
                    uid, cid,
                )

                # Лог в admin_grant_log (первая валюта для amount, остальные в detail)
                _, first_amt = next(iter(price.items()))
                after_zar = float(bal_row["z"] if bal_row else 0) + float(price.get("zarniki", 0))
                await conn.execute(
                    """
                    INSERT INTO admin_grant_log
                        (admin_id, target_id, action, detail, amount, reason, before_val, after_val)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    0, uid,
                    "cosmetic_refund",
                    f"{cid} ({name}) — {label}",
                    float(first_amt),
                    f"смена ценовой иерархии 2026-06-30 ({epoch})",
                    float(bal_row["z"] if bal_row else 0),
                    after_zar,
                )

                # Страховка от повторного запуска
                await conn.execute(
                    """
                    INSERT INTO cosmetic_refund_log (user_id, cosmetic_id, epoch, refund_json)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id, cosmetic_id) DO NOTHING
                    """,
                    uid, cid, epoch, json.dumps(price, ensure_ascii=False),
                )

        total_items += 1
        if dry_run:
            for cur, amt in price.items():
                total_counts[cur] = total_counts.get(cur, 0) + int(amt)

    print("=" * 75)
    mode = "ПОКАЗАНО (DRY RUN, не применено)" if dry_run else "ВЫПОЛНЕНО"
    print(f"\n{prefix}{mode}: {total_items} записей")
    print("Суммарно возвращено:")
    for cur, total in total_counts.items():
        if total:
            print(f"  {CUR_ICON[cur]} {cur}: {total}")

    if stars_suspects:
        print(f"\n{'='*40}")
        print(f"⭐ ВНИМАНИЕ: {len(stars_suspects)} покупок за Telegram Stars (реальные деньги)!")
        print("   Зарники/мора/алмазы — выданы. Но Stars НЕЛЬЗЯ вернуть автоматически:")
        print("   нет telegram_payment_charge_id в БД → нужен ручной возврат через BotFather.")
        print()
        for s in stars_suspects:
            print(f"   @{s['username']} (id={s['uid']}) — {s['name']} [{s['acq']}]")
        print()
        print("   Инструкция: @BotFather → Edit Bot → Payments → Refunds")
        print("   Или: Bot API refundStarPayment(user_id, telegram_payment_charge_id)")

    await conn.close()
    print("\nГотово.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ОДНОРАЗОВЫЙ рефанд косметики за старые цены. Запускать ВРУЧНУЮ."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Показать что будет сделано, НЕ менять БД")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))
