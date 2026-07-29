#!/usr/bin/env python3
"""
scripts/cosmetics_gap_refund.py — точечный рефанд ПРЕДМЕТОВ, ИСЧЕЗНУВШИХ ИЗ
КАТАЛОГА, накопившихся в окне между scripts/cosmetics_lineup_wipe_refund.py и
фактическим деплоем нового core/cosmetics.py (переход на линейки, 2026-07-29).

ПОЧЕМУ ЭТОТ СКРИПТ ОТДЕЛЬНЫЙ, А НЕ ПОВТОРНЫЙ ЗАПУСК ОСНОВНОГО:
  Пока новый core/cosmetics.py лежал в гите, но НЕ был задеплоен, старый код
  на проде продолжал работать — VIP/БП игрокам молча пере-выдавались
  source="vip"/"bp" предметы (sync_auto_grants при каждой загрузке каталога),
  плюс кто-то успел КУПИТЬ старые предметы напрямую. Часть из этого — предметы,
  которые ВЫЖИЛИ в новой линейке (просто переприписаны, цена та же или другая,
  но предмет РЕАЛЬНО есть в новом core/cosmetics.py) — их трогать НЕ НАДО,
  владение остаётся валидным. Другая часть — предметы, которых в новом
  каталоге ВООБЩЕ НЕТ (были орфанами, удалены при переходе на линейки) — вот
  их нужно снять и компенсировать, иначе игрок просто теряет то, что получил
  (пусть и бесплатно через авто-выдачу, пусть и в узком временном окне).

  Основной scripts/cosmetics_lineup_wipe_refund.py брать не могли — он оценивает
  предмет по ТЕКУЩЕЙ (новой) цене из core/cosmetics.py, а removed-предметов там
  просто нет (skip, ноль компенсации). Этот скрипт использует ИСТОРИЧЕСКИЙ
  прайс-снимок (последние актуальные цены СТАРОГО каталога, до перехода на
  линейки) — единственная осмысленная база для того, что уже не существует.

ЗАПУСК (из корня репозитория):
  python predvestnik_v2/scripts/cosmetics_gap_refund.py --dry-run
  python predvestnik_v2/scripts/cosmetics_gap_refund.py

Безопасно гонять повторно (идемпотентно по построению: после рефанда+удаления
строка исчезает из user_cosmetics, повторный запуск найдёт только НОВЫЕ
накопления, если деплоя всё ещё не было) — специальной таблицы-маркера не
нужно, в отличие от основного скрипта (тот работал по ВСЕЙ user_cosmetics
разом, тут естественная идемпотентность через сам факт удаления строки).
"""
import asyncio
import argparse
import os
import sys
from pathlib import Path

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.cosmetics import COSMETICS as NEW_COSMETICS  # noqa: E402

load_dotenv()

BONUS_RATE = 0.05

# Снимок цен СТАРОГО каталога (до перехода на линейки, 2026-07-29) — только
# для 30 предметов, которые НЕ попали ни в одну линейку и были удалены из
# core/cosmetics.py. Для предметов, которые ВЫЖИЛИ (есть в NEW_COSMETICS),
# скрипт их вообще не трогает — см. фильтр в run().
OLD_PRICE_SNAPSHOT: dict[str, int] = {
    "cos_avatar_frame_arcane": 630, "cos_avatar_frame_bronze": 250,
    "cos_avatar_frame_iron": 440, "cos_avatar_frame_neon": 440,
    "cos_avatar_frame_tidal": 630, "cos_avatar_halo_glow": 250,
    "cos_avatar_halo_runic": 630, "cos_avatar_halo_thorn": 630,
    "cos_card_fx_fireflies": 820, "cos_card_fx_moths": 630,
    "cos_card_fx_petals": 440, "cos_card_fx_sparks": 250,
    "cos_card_fx_stars": 630, "cos_name_glow_gold": 440,
    "cos_name_glow_prism": 820, "cos_name_glow_silver": 250,
    "cos_name_glow_thunder": 630, "cos_profile_bg_amber": 440,
    "cos_profile_bg_carbon": 250, "cos_profile_bg_dusk": 630,
    "cos_profile_bg_galaxy": 440, "cos_profile_bg_nebula": 440,
    "cos_profile_bg_ocean": 250, "cos_profile_bg_phoenix": 820,
    "cos_profile_bg_royal": 630, "cos_title_apex": 820,
    "cos_title_legend": 820, "cos_title_novice": 250,
    "cos_title_patron": 440, "cos_title_wanderer": 250,
}


async def _send_telegram(token: str, chat_id: int, text: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json={"chat_id": chat_id, "text": text})
            data = r.json()
            return bool(data.get("ok")), data.get("description", "")
    except Exception as e:
        return False, str(e)


def _notify_text(item_count: int, base: int, bonus: int, total: int) -> str:
    return (
        "🎨 Донастройка перехода на линейки\n\n"
        f"Пока новый каталог косметики ещё разворачивался, тебе успело "
        f"начислиться {item_count} предм. старой косметики, которой в новом "
        f"каталоге больше нет. Полностью компенсировано зарниками:\n\n"
        f"✨ Компенсация: {base}\n🎁 Бонус +5%: {bonus}\n💰 Итого: {total}\n\n"
        f"Извини за неудобство — донабери образ в обновлённом магазине."
    )


async def run(dry_run: bool) -> None:
    db_url = os.getenv("DATABASE_URL", "")
    bot_token = os.getenv("BOT_TOKEN", "")
    if not db_url:
        print("ERROR: DATABASE_URL не установлен", file=sys.stderr)
        sys.exit(1)

    prefix = "[DRY RUN] " if dry_run else ""
    conn = await asyncpg.connect(db_url)

    rows = await conn.fetch(
        """
        SELECT uc.user_id, uc.cosmetic_id, u.user_tg_username
        FROM predvestnik.user_cosmetics uc
        LEFT JOIN predvestnik.users u ON u.user_tg_id = uc.user_id
        ORDER BY uc.user_id, uc.cosmetic_id
        """
    )
    # Только предметы, которых НЕТ в новом каталоге — выжившие не трогаем.
    gap_rows = [r for r in rows if r["cosmetic_id"] not in NEW_COSMETICS]

    if not gap_rows:
        print(f"{prefix}Нечего компенсировать — все текущие предметы либо валидны "
              f"в новом каталоге, либо таблица пуста.")
        await conn.close()
        return

    per_user: dict[int, dict] = {}
    unpriced: set[str] = set()
    for r in gap_rows:
        uid = r["user_id"]
        cid = r["cosmetic_id"]
        price = OLD_PRICE_SNAPSHOT.get(cid)
        entry = per_user.setdefault(uid, {"username": r["user_tg_username"] or f"id{uid}", "items": []})
        if price is None:
            unpriced.add(cid)
            continue
        entry["items"].append((cid, price))

    if unpriced:
        print(f"⚠️  Нет цены в снимке для: {sorted(unpriced)} — пропущены, ничего не начислено.")

    per_user = {uid: v for uid, v in per_user.items() if v["items"]}
    if not per_user:
        print(f"{prefix}Нечего компенсировать после фильтрации.")
        await conn.close()
        return

    print(f"{prefix}Найдено предметов вне нового каталога: {sum(len(v['items']) for v in per_user.values())} "
          f"у {len(per_user)} пользователей")
    print("=" * 80)

    plan = []
    grand_total = 0
    for uid, data in sorted(per_user.items()):
        base = sum(p for _, p in data["items"])
        bonus = int(base * BONUS_RATE + 0.5)
        total = base + bonus
        grand_total += total
        plan.append({"uid": uid, "username": data["username"], "items": data["items"],
                     "base": base, "bonus": bonus, "total": total})
        names = ", ".join(f"{cid}({p}✨)" for cid, p in data["items"])
        print(f"  @{data['username']:<20} | база {base}✨ + бонус {bonus}✨ = {total}✨")
        print(f"      {names}")

    print("=" * 80)
    print(f"{prefix}ИТОГО начислится: {grand_total}✨ ({len(plan)} пользователей)")

    if dry_run:
        print("\n[DRY RUN] Ничего не изменено.")
        await conn.close()
        return

    for p in plan:
        uid = p["uid"]
        cosmetic_ids = [cid for cid, _ in p["items"]]
        async with conn.transaction():
            bal_row = await conn.fetchrow(
                "SELECT COALESCE(user_balance_zarniki, 0) AS z FROM predvestnik.users "
                "WHERE user_tg_id = $1 FOR UPDATE", uid,
            )
            before_zar = float(bal_row["z"]) if bal_row else 0.0
            after_zar = before_zar + p["total"]
            await conn.execute(
                "UPDATE predvestnik.users SET user_balance_zarniki = "
                "COALESCE(user_balance_zarniki, 0) + $1 WHERE user_tg_id = $2",
                p["total"], uid,
            )
            await conn.execute(
                "DELETE FROM predvestnik.user_cosmetics WHERE user_id = $1 AND cosmetic_id = ANY($2::text[])",
                uid, cosmetic_ids,
            )
            await conn.execute(
                "DELETE FROM predvestnik.user_cosmetic_loadout WHERE user_id = $1 AND cosmetic_id = ANY($2::text[])",
                uid, cosmetic_ids,
            )
            await conn.execute(
                """
                INSERT INTO predvestnik.admin_grant_log
                    (admin_id, target_id, action, detail, amount, reason, before_val, after_val)
                VALUES (0, $1, 'cosmetics_gap_refund', $2, $3, $4, $5, $6)
                """,
                uid, f"{len(p['items'])} предметов вне нового каталога, компенсация "
                     f"{p['base']}✨ + бонус {p['bonus']}✨",
                float(p["total"]), "gap между wipe-рефандом и деплоем линеек 2026-07-29",
                before_zar, after_zar,
            )
        if bot_token:
            sent, err = await _send_telegram(
                bot_token, uid, _notify_text(len(p["items"]), p["base"], p["bonus"], p["total"]))
            if not sent:
                print(f"  ⚠️ уведомление не доставлено @{p['username']}: {err}")
        await asyncio.sleep(0.05)

    print(f"\nГотово: {len(plan)} пользователей компенсировано.")
    await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))
