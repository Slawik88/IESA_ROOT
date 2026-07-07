"""scripts/migrate_cosmetics_ids.py — БЛОК 39: миграция ID косметики на формат cos_{slot}_{name}.

Что делает (идемпотентно, повторный запуск ничего не портит — старых ID просто не найдёт):
  1. user_cosmetics.cosmetic_id          — инвентарь купленной косметики;
  2. user_cosmetic_loadout.cosmetic_id   — экипированные слоты (slot='welcome' не трогается,
     там ID приветственных анимаций — они не переименовывались);
  3. cosmetic_presets.loadout            — JSON-снимки образов ({slot: cosmetic_id});
  4. weekly_showcase.slots_json          — JSON текущей/прошлых Витрин недели;
  5. cosmetic_refund_log.cosmetic_id     — исторический лог рефанда (для консистентности).

ПОРЯДОК ДЕПЛОЯ (критично!): скрипт гонять на проде ДО перезапуска процесса с новым
core/cosmetics.py. Между деплоем кода и прогоном скрипта старые ID в БД не будут
находиться в реестре → у игроков «слетит» отображение купленной косметики (данные
не теряются, но выглядит как пропажа). Правильный порядок:
  1) python scripts/migrate_cosmetics_ids.py --dry-run   # превью
  2) python scripts/migrate_cosmetics_ids.py             # боевой прогон (старый код ещё крутится —
                                                          # ему всё равно: новых ID он не знает,
                                                          # но и не читает то, чего нет в его реестре)
  ВАЖНО: шаг 2 выполнять непосредственно перед деплоем (окно, пока крутится старый код,
  даёт тот же эффект «слетевшей» косметики — минимизировать его).
  3) деплой нового кода.
Нужен DATABASE_URL в окружении/.env (тот же формат, что у прод-процессов).
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

# Полный маппинг всех 77 переименованных ID (старый → новый).
# Сгенерирован из core/cosmetics.py на момент рефакторинга (2026-07-07).
OLD_TO_NEW_IDS: dict[str, str] = {
    "glow_silver": "cos_name_glow_silver",
    "glow_gold": "cos_name_glow_gold",
    "glow_crimson": "cos_name_glow_crimson",
    "glow_ember": "cos_name_glow_ember",
    "glow_prism": "cos_name_glow_prism",
    "glow_rift": "cos_name_glow_rift",
    "frame_bronze": "cos_avatar_frame_bronze",
    "frame_neon": "cos_avatar_frame_neon",
    "frame_abyss": "cos_avatar_frame_abyss",
    "frame_iron": "cos_avatar_frame_iron",
    "frame_celestial": "cos_avatar_frame_celestial",
    "frame_omen": "cos_avatar_frame_omen",
    "title_wanderer": "cos_title_wanderer",
    "title_patron": "cos_title_patron",
    "title_abysswalker": "cos_title_abysswalker",
    "title_legend": "cos_title_legend",
    "title_omen": "cos_title_omen",
    "halo_glow": "cos_avatar_halo_glow",
    "halo_pulse": "cos_avatar_halo_pulse",
    "halo_runic": "cos_avatar_halo_runic",
    "halo_aurora": "cos_avatar_halo_aurora",
    "halo_celestial": "cos_avatar_halo_celestial",
    "halo_void": "cos_avatar_halo_void",
    "pbg_carbon": "cos_profile_bg_carbon",
    "pbg_nebula": "cos_profile_bg_nebula",
    "pbg_abyss": "cos_profile_bg_abyss",
    "pbg_forest": "cos_profile_bg_forest",
    "pbg_ocean": "cos_profile_bg_ocean",
    "pbg_ember": "cos_profile_bg_ember",
    "pbg_galaxy": "cos_profile_bg_galaxy",
    "pbg_dusk": "cos_profile_bg_dusk",
    "pbg_royal": "cos_profile_bg_royal",
    "pbg_sunrise": "cos_profile_bg_sunrise",
    "pbg_legend": "cos_profile_bg_legend",
    "cfx_sparks": "cos_card_fx_sparks",
    "cfx_snow": "cos_card_fx_snow",
    "cfx_petals": "cos_card_fx_petals",
    "cfx_embers": "cos_card_fx_embers",
    "cfx_stars": "cos_card_fx_stars",
    "cfx_fireflies": "cos_card_fx_fireflies",
    "cfx_void_storm": "cos_card_fx_void_storm",
    "glow_frost": "cos_name_glow_frost",
    "glow_thunder": "cos_name_glow_thunder",
    "glow_solar": "cos_name_glow_solar",
    "frame_crystal": "cos_avatar_frame_crystal",
    "frame_arcane": "cos_avatar_frame_arcane",
    "frame_inferno": "cos_avatar_frame_inferno",
    "halo_ice": "cos_avatar_halo_ice",
    "halo_corona": "cos_avatar_halo_corona",
    "pbg_midnight": "cos_profile_bg_midnight",
    "pbg_crimson": "cos_profile_bg_crimson",
    "pbg_void_dark": "cos_profile_bg_void_dark",
    "pbg_aurora": "cos_profile_bg_aurora",
    "cfx_dust": "cos_card_fx_dust",
    "cfx_nova": "cos_card_fx_nova",
    "title_sentinel": "cos_title_sentinel",
    "title_rift_walker": "cos_title_rift_walker",
    "title_apex": "cos_title_apex",
    "title_harbinger": "cos_title_harbinger",
    "glow_moon": "cos_name_glow_moon",
    "glow_verdant": "cos_name_glow_verdant",
    "glow_void": "cos_name_glow_void",
    "frame_oak": "cos_avatar_frame_oak",
    "frame_tidal": "cos_avatar_frame_tidal",
    "frame_void": "cos_avatar_frame_void",
    "title_novice": "cos_title_novice",
    "title_keeper": "cos_title_keeper",
    "title_ember_born": "cos_title_ember_born",
    "halo_dust": "cos_avatar_halo_dust",
    "halo_thorn": "cos_avatar_halo_thorn",
    "halo_eclipse": "cos_avatar_halo_eclipse",
    "pbg_amber": "cos_profile_bg_amber",
    "pbg_phoenix": "cos_profile_bg_phoenix",
    "pbg_starfall": "cos_profile_bg_starfall",
    "cfx_leaves": "cos_card_fx_leaves",
    "cfx_moths": "cos_card_fx_moths",
    "cfx_eclipse_ash": "cos_card_fx_eclipse_ash",
}

assert len(OLD_TO_NEW_IDS) == 77, f"ожидалось 77 ID, в маппинге {len(OLD_TO_NEW_IDS)}"
assert len(set(OLD_TO_NEW_IDS.values())) == 77, "коллизия новых ID"


async def _migrate_plain_column(conn, table: str, dry_run: bool) -> int:
    """UPDATE cosmetic_id старый→новый с защитой от конфликта PK: если строка с новым
    ID уже существует (частично прогнанная миграция), старую просто удаляем — данные
    те же, дубликат не нужен."""
    total = 0
    for old_id, new_id in OLD_TO_NEW_IDS.items():
        cnt = await conn.fetchval(
            f"SELECT COUNT(*) FROM {table} WHERE cosmetic_id = $1", old_id)
        if not cnt:
            continue
        total += cnt
        if dry_run:
            continue
        # Конфликт-гард: обновляем только строки, у которых нет двойника с новым ID
        # по тому же PK; оставшиеся старые (двойники) удаляем.
        if table == "user_cosmetics":
            await conn.execute(
                "UPDATE user_cosmetics SET cosmetic_id = $2 WHERE cosmetic_id = $1 "
                "AND NOT EXISTS (SELECT 1 FROM user_cosmetics uc2 "
                "  WHERE uc2.user_id = user_cosmetics.user_id AND uc2.cosmetic_id = $2)",
                old_id, new_id)
            await conn.execute(
                "DELETE FROM user_cosmetics WHERE cosmetic_id = $1", old_id)
        elif table == "user_cosmetic_loadout":
            # PK (user_id, slot) — cosmetic_id не в ключе, конфликтов нет
            await conn.execute(
                "UPDATE user_cosmetic_loadout SET cosmetic_id = $2 WHERE cosmetic_id = $1",
                old_id, new_id)
        elif table == "cosmetic_refund_log":
            await conn.execute(
                "UPDATE cosmetic_refund_log SET cosmetic_id = $2 WHERE cosmetic_id = $1 "
                "AND NOT EXISTS (SELECT 1 FROM cosmetic_refund_log rl2 "
                "  WHERE rl2.user_id = cosmetic_refund_log.user_id AND rl2.cosmetic_id = $2)",
                old_id, new_id)
            await conn.execute(
                "DELETE FROM cosmetic_refund_log WHERE cosmetic_id = $1", old_id)
    return total


def _rewrite_json_text(text: str) -> tuple[str, int]:
    """Замена ID внутри JSON-текста: только точные строковые значения в кавычках."""
    hits = 0
    for old_id, new_id in OLD_TO_NEW_IDS.items():
        token_old, token_new = f'"{old_id}"', f'"{new_id}"'
        n = text.count(token_old)
        if n:
            hits += n
            text = text.replace(token_old, token_new)
    return text, hits


async def _migrate_json_column(conn, table: str, pk_col: str, json_col: str,
                               dry_run: bool) -> int:
    rows = await conn.fetch(f"SELECT {pk_col} AS pk, {json_col} AS payload FROM {table}")
    changed = 0
    for r in rows:
        payload = r["payload"]
        if not payload:
            continue
        new_payload, hits = _rewrite_json_text(payload)
        if not hits:
            continue
        json.loads(new_payload)  # валидация: не сломали JSON
        changed += 1
        if not dry_run:
            await conn.execute(
                f"UPDATE {table} SET {json_col} = $2 WHERE {pk_col} = $1",
                r["pk"], new_payload)
    return changed


async def main(dry_run: bool) -> None:
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL не задан (env/.env)"); sys.exit(1)

    conn = await asyncpg.connect(url, timeout=20)
    await conn.execute("SET search_path TO predvestnik, public")

    mode = "DRY-RUN (БД не меняется)" if dry_run else "БОЕВОЙ ПРОГОН"
    print(f"=== Миграция ID косметики: {mode} ===")

    tr = conn.transaction()
    await tr.start()
    try:
        n1 = await _migrate_plain_column(conn, "user_cosmetics", dry_run)
        print(f"user_cosmetics:         {n1} строк со старыми ID")
        n2 = await _migrate_plain_column(conn, "user_cosmetic_loadout", dry_run)
        print(f"user_cosmetic_loadout:  {n2} строк со старыми ID")
        try:
            n3 = await _migrate_plain_column(conn, "cosmetic_refund_log", dry_run)
            print(f"cosmetic_refund_log:    {n3} строк со старыми ID")
        except asyncpg.UndefinedTableError:
            print("cosmetic_refund_log:    таблицы нет (рефанд не гонялся) — пропуск")
        try:
            n4 = await _migrate_json_column(conn, "cosmetic_presets", "id", "loadout", dry_run)
            print(f"cosmetic_presets:       {n4} пресетов обновлено")
        except asyncpg.UndefinedTableError:
            print("cosmetic_presets:       таблицы нет — пропуск")
        try:
            n5 = await _migrate_json_column(conn, "weekly_showcase", "week_key", "slots_json", dry_run)
            print(f"weekly_showcase:        {n5} витрин обновлено")
        except asyncpg.UndefinedTableError:
            print("weekly_showcase:        таблицы нет — пропуск")

        if dry_run:
            await tr.rollback()
            print("DRY-RUN: транзакция откачена, БД не изменена.")
        else:
            await tr.commit()
            print("COMMIT: миграция применена. Теперь деплой нового кода.")
    except Exception:
        await tr.rollback()
        print("ОШИБКА: транзакция откачена, БД не изменена.")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="превью без изменений БД")
    args = ap.parse_args()
    asyncio.run(main(args.dry_run))
