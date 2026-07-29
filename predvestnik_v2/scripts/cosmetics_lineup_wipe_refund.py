#!/usr/bin/env python3
"""
scripts/cosmetics_lineup_wipe_refund.py — рефанд + полное снятие ВСЕЙ косметики
перед переходом на систему "линеек" (редизайн 2026-07-29, см.
predvestnik_v2/tools/artifact_fx_prototypes.html).

═══════════════════════════════════════════════════════════════════════════════
ЗАПУСК (из корня репозитория):

  python predvestnik_v2/scripts/cosmetics_lineup_wipe_refund.py --dry-run
      → только показывает в консоли, кому сколько будет начислено. НИЧЕГО не
        меняет в БД, ничего не отправляет в Telegram.

  python predvestnik_v2/scripts/cosmetics_lineup_wipe_refund.py
      → РЕАЛЬНЫЙ прогон: начисляет зарники, снимает косметику, шлёт уведомления.
        Перед стартом просит ввести "YES" (большой blast radius — вся БД разом).

ЗАВИСИМОСТИ: DATABASE_URL и BOT_TOKEN в .env / переменных окружения.
═══════════════════════════════════════════════════════════════════════════════
ЛОГИКА РЕФАНДА:

  - Каждый предмет из user_cosmetics оценивается по ТЕКУЩЕЙ цене из
    core/cosmetics.py (владелец: "по актуальной цене на продакшене" — не по
    исторической цене покупки, как в старом scripts/cosmetics_refund.py).
  - Владелец явно решил (2026-07-29): рефандится ЛЮБОЙ owned предмет, вне
    зависимости от способа получения. Причина: таблица user_cosmetics хранит
    только (user_id, cosmetic_id, acquired_at) — НЕТ поля "как получено".
    Покупка за зарники, авто-выдача по VIP/БП, дроп из сундука, крафт из
    осколков и подарок от другого игрока пишут ОДИНАКОВУЮ строку — отличить
    технически нельзя. Простой и честный выбор: раз предмет можно было купить
    за зарники — компенсируем его стоимость, независимо от факта оплаты.
  - Сверху +5% бонус от суммы рефанда каждому юзеру (округление к ближайшему).
  - Удаляет предметы из user_cosmetics И user_cosmetic_loadout (если экипированы).
  - Уведомление в Telegram каждому затронутому юзеру — raw HTTP sendMessage
    (тот же паттерн, что _tg_call в FastAPI/routers/admin.py и др. — без живого
    aiogram.Bot, скрипт работает вне процессов бота/веба).
  - Идемпотентность: таблица cosmetics_lineup_wipe_log (user_id PK). Повторный
    запуск скипнет уже обработанных пользователей целиком.
  - Аудит: одна запись на юзера в admin_grant_log (action='cosmetics_lineup_wipe').
  - welcome-анимации НЕ трогает — это отдельный слот без записи владения
    (гейт по VIP, не по user_cosmetics), редизайна линеек не касается.
═══════════════════════════════════════════════════════════════════════════════
"""
import asyncio
import argparse
import json
import os
import sys
from pathlib import Path

# Винда по умолчанию открывает stdout в cp1251 — эмодзи (✨🎁💰) роняют print()
# с UnicodeEncodeError. Консоль скрипта должна работать и на Windows-машине
# разработчика, не только в Linux-проде.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

try:
    import asyncpg
    import httpx
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: pip install asyncpg httpx python-dotenv")
    sys.exit(1)

# core/cosmetics.py не тянет ничего из bot.*/FastAPI.* — безопасно импортировать
# напрямую из скрипта для актуальных цен (единственный источник правды).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.cosmetics import COSMETICS  # noqa: E402

load_dotenv()

BONUS_RATE = 0.05  # +5% сверху владелец попросил явно


def _current_zarniki_price(cosmetic_id: str) -> int | None:
    """Текущая цена предмета в зарниках из core/cosmetics.py, или None если
    предмета больше нет в реестре (снят/переименован — легаси-ID) или у него
    вообще нет зарниковой цены (на момент написания скрипта таких нет)."""
    cos = COSMETICS.get(cosmetic_id)
    if not cos:
        return None
    for opt in cos.get("price") or []:
        if "zarniki" in opt:
            return int(opt["zarniki"])
    return None


async def _send_telegram(token: str, chat_id: int, text: str) -> tuple[bool, str]:
    """chat_id для ЛС — положительный, равен user_tg_id (см. память проекта:
    группа отрицательный, ЛС положительный)."""
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            data = r.json()
            return bool(data.get("ok")), data.get("description", "")
    except Exception as e:
        return False, str(e)


def _notify_text(item_count: int, base: int, bonus: int, total: int) -> str:
    return (
        "🎨 Обновление косметики профиля\n\n"
        f"Мы полностью переделываем систему косметики — вместо редкости теперь "
        f"тематические коллекции («линейки»). Из-за этого твоя текущая косметика "
        f"({item_count} шт.) снята с профиля, а её стоимость по актуальным ценам "
        f"полностью компенсирована зарниками:\n\n"
        f"✨ Компенсация: {base}\n"
        f"🎁 Бонус +5%: {bonus}\n"
        f"💰 Итого начислено: {total}\n\n"
        f"Новые коллекции скоро появятся в магазине — сможешь собрать образ заново."
    )


async def run(dry_run: bool) -> None:
    db_url = os.getenv("DATABASE_URL", "")
    bot_token = os.getenv("BOT_TOKEN", "")
    if not db_url:
        print("ERROR: DATABASE_URL не установлен", file=sys.stderr)
        sys.exit(1)
    if not dry_run and not bot_token:
        print("ERROR: BOT_TOKEN не установлен — нужен для уведомлений в реальном прогоне", file=sys.stderr)
        sys.exit(1)

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Подключаемся к БД...")
    conn = await asyncpg.connect(db_url)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS predvestnik.cosmetics_lineup_wipe_log (
            user_id      BIGINT NOT NULL PRIMARY KEY,
            item_count   INT    NOT NULL,
            base_zarniki INT    NOT NULL,
            bonus_zarniki INT   NOT NULL,
            total_zarniki INT   NOT NULL,
            detail_json  TEXT   NOT NULL,
            notified     BOOLEAN NOT NULL DEFAULT FALSE,
            processed_at TIMESTAMP DEFAULT NOW()
        )
    """)

    already_done: set[int] = {
        r["user_id"] for r in
        await conn.fetch("SELECT user_id FROM predvestnik.cosmetics_lineup_wipe_log")
    }
    print(f"{prefix}Уже обработано ранее (пропустим): {len(already_done)} пользователей.")

    rows = await conn.fetch(
        """
        SELECT uc.user_id, uc.cosmetic_id, u.user_tg_username
        FROM predvestnik.user_cosmetics uc
        LEFT JOIN predvestnik.users u ON u.user_tg_id = uc.user_id
        ORDER BY uc.user_id, uc.cosmetic_id
        """
    )

    if not rows:
        print(f"{prefix}user_cosmetics пуста — нечего рефандить.")
        await conn.close()
        return

    # Группируем по юзеру
    per_user: dict[int, dict] = {}
    unknown_ids: set[str] = set()
    for r in rows:
        uid = r["user_id"]
        cid = r["cosmetic_id"]
        if uid in already_done:
            continue
        price = _current_zarniki_price(cid)
        entry = per_user.setdefault(uid, {
            "username": r["user_tg_username"] or f"id{uid}",
            "items": [],
        })
        if price is None:
            unknown_ids.add(cid)
            continue
        entry["items"].append((cid, price))

    if unknown_ids:
        print(f"\n⚠️  {len(unknown_ids)} cosmetic_id не найдены в текущем core/cosmetics.py "
              f"(легаси/удалённые, пропущены БЕЗ рефанда за них): {sorted(unknown_ids)}")

    # Убираем юзеров, у которых после фильтрации не осталось ни одного предмета с ценой
    per_user = {uid: v for uid, v in per_user.items() if v["items"]}

    if not per_user:
        print(f"\n{prefix}Не осталось пользователей для рефанда после фильтрации.")
        await conn.close()
        return

    print(f"\n{prefix}Пользователей к обработке: {len(per_user)}")
    print("=" * 90)

    grand_base = 0
    grand_bonus = 0
    grand_items = 0

    plan: list[dict] = []
    for uid, data in sorted(per_user.items()):
        base = sum(p for _, p in data["items"])
        # int(x+0.5) вместо round(): Python round() — банковское округление
        # (round-half-to-even), на границе X.5 может округлить ПРОТИВ игрока.
        # Раз уж вся идея этого скрипта — не обделить никого, округляем вверх.
        bonus = int(base * BONUS_RATE + 0.5)
        total = base + bonus
        grand_base += base
        grand_bonus += bonus
        grand_items += len(data["items"])
        plan.append({"uid": uid, "username": data["username"], "items": data["items"],
                     "base": base, "bonus": bonus, "total": total})

        item_list = ", ".join(f"{cid}({p}✨)" for cid, p in data["items"])
        print(f"  @{data['username']:<20} | {len(data['items'])} предм. | "
              f"база {base}✨ + бонус {bonus}✨ = {total}✨")
        print(f"      {item_list}")

    print("=" * 90)
    print(f"\n{prefix}ИТОГО:")
    print(f"  Пользователей:        {len(plan)}")
    print(f"  Предметов снимается:  {grand_items}")
    print(f"  База (стоимость):     {grand_base}✨")
    print(f"  Бонус +{int(BONUS_RATE*100)}%:           {grand_bonus}✨")
    print(f"  ВСЕГО начислится:     {grand_base + grand_bonus}✨")

    if dry_run:
        print("\n[DRY RUN] Ничего не изменено. Запусти без --dry-run для реального прогона.")
        await conn.close()
        return

    print("\n" + "!" * 90)
    print("!! ЭТО НЕОБРАТИМО: у ВСЕХ пользователей выше будет полностью снята косметика,")
    print("!! начислены зарники, и каждому отправлено сообщение в Telegram.")
    print("!" * 90)
    confirm = input("\nВведи YES (заглавными) чтобы продолжить: ")
    if confirm.strip() != "YES":
        print("Отменено.")
        await conn.close()
        return

    ok_count = 0
    notify_fail: list[str] = []
    for p in plan:
        uid = p["uid"]
        try:
            async with conn.transaction():
                bal_row = await conn.fetchrow(
                    "SELECT COALESCE(user_balance_zarniki, 0) AS z FROM predvestnik.users "
                    "WHERE user_tg_id = $1 FOR UPDATE",
                    uid,
                )
                before_zar = float(bal_row["z"]) if bal_row else 0.0
                after_zar = before_zar + p["total"]
                await conn.execute(
                    "UPDATE predvestnik.users SET user_balance_zarniki = "
                    "COALESCE(user_balance_zarniki, 0) + $1 WHERE user_tg_id = $2",
                    p["total"], uid,
                )
                cosmetic_ids = [cid for cid, _ in p["items"]]
                await conn.execute(
                    "DELETE FROM predvestnik.user_cosmetics "
                    "WHERE user_id = $1 AND cosmetic_id = ANY($2::text[])",
                    uid, cosmetic_ids,
                )
                await conn.execute(
                    "DELETE FROM predvestnik.user_cosmetic_loadout "
                    "WHERE user_id = $1 AND cosmetic_id = ANY($2::text[])",
                    uid, cosmetic_ids,
                )
                await conn.execute(
                    """
                    INSERT INTO predvestnik.admin_grant_log
                        (admin_id, target_id, action, detail, amount, reason, before_val, after_val)
                    VALUES (0, $1, 'cosmetics_lineup_wipe', $2, $3, $4, $5, $6)
                    """,
                    uid,
                    f"{len(p['items'])} предметов снято, компенсация {p['base']}✨ + бонус {p['bonus']}✨",
                    float(p["total"]),
                    "переход на систему линеек 2026-07-29 — полный wipe+рефанд косметики",
                    before_zar, after_zar,
                )
                await conn.execute(
                    """
                    INSERT INTO predvestnik.cosmetics_lineup_wipe_log
                        (user_id, item_count, base_zarniki, bonus_zarniki, total_zarniki, detail_json)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    uid, len(p["items"]), p["base"], p["bonus"], p["total"],
                    json.dumps(p["items"], ensure_ascii=False),
                )
            ok_count += 1
        except Exception as e:
            print(f"  ❌ ОШИБКА у @{p['username']} (id={uid}): {e} — пропущен, БД не тронута для него.")
            continue

        sent, err = await _send_telegram(
            bot_token, uid,
            _notify_text(len(p["items"]), p["base"], p["bonus"], p["total"]),
        )
        if sent:
            await conn.execute(
                "UPDATE predvestnik.cosmetics_lineup_wipe_log SET notified = TRUE WHERE user_id = $1",
                uid,
            )
        else:
            notify_fail.append(f"@{p['username']} (id={uid}): {err}")
        await asyncio.sleep(0.05)  # мягкий троттлинг, не долбим Telegram API пачкой

    print(f"\nГотово: обработано {ok_count}/{len(plan)} пользователей.")
    if notify_fail:
        print(f"\n⚠️  Уведомление НЕ доставлено {len(notify_fail)} пользователям "
              f"(деньги/снятие косметики уже применены, это не откатывается):")
        for line in notify_fail:
            print(f"   {line}")

    await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Wipe+рефанд ВСЕЙ косметики перед переходом на линейки. Запускать ВРУЧНУЮ."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Показать план в консоли, НЕ менять БД и не слать сообщения")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))
