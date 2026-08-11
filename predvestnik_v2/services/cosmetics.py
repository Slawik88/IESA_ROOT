"""services/cosmetics.py — Конструктор внешнего вида профиля.

Бизнес-логика косметики: каталог, покупка (мульти/альт-валюта), экипировка, выдача.
No bot.*/FastAPI.* imports. Только косметика — без игрового преимущества.
"""
import json
import random

from core.cosmetics import (
    COSMETICS, COSMETIC_SLOTS, CURATED_LOOKS, LINEUPS,
    WELCOME_ANIMATIONS, WELCOME_DEFAULT, is_vip_locked,
    lineup_items,
)
from core.constants import (
    COSMETIC_CHESTS, COSMETIC_DUPE_SHARDS, COSMETIC_CRAFT_SHARDS,
)
from core.registry import ITEMS_REGISTRY
from services.vip import is_vip_active, is_vip_active_batch

# Слот приветственной анимации в user_cosmetic_loadout (отдельно от носимой косметики;
# без записи владения — гейт по VIP, а не по обладанию).
_WELCOME_SLOT = "welcome"

# Валюты косметики → колонка баланса в users (whitelist: имя колонки НЕ из ввода).
_CUR_COL = {
    "mora": "user_balance_mora",
    "diamonds": "user_balance_diamonds",
    "dark_mora": "user_balance_dark_mora",
    "zarniki": "user_balance_zarniki",
}
_CUR_ICON = {"mora": "🪙", "diamonds": "💎", "dark_mora": "🌑", "zarniki": "✨"}



async def ensure_tables(db) -> None:
    """Создать таблицы косметики (для веб-процесса — init бота не всегда прогнан)."""
    await db.execute(
        "CREATE TABLE IF NOT EXISTS user_cosmetics ("
        "user_id BIGINT NOT NULL, cosmetic_id TEXT NOT NULL, "
        "acquired_at TIMESTAMP DEFAULT NOW(), PRIMARY KEY (user_id, cosmetic_id))"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS user_cosmetic_loadout ("
        "user_id BIGINT NOT NULL, slot TEXT NOT NULL, cosmetic_id TEXT NOT NULL, "
        "PRIMARY KEY (user_id, slot))"
    )
    await migrate_legacy_ids(db)


async def migrate_legacy_ids(db) -> None:
    """БЛОК 39 HOTFIX: авто-миграция старых ID косметики → cos_{slot}_{name}.

    Прод-инцидент 2026-07-08: код с новыми ID задеплоился ДО ручного прогона
    scripts/migrate_cosmetics_ids.py — у игроков «пропала» оплаченная косметика
    (данные целы, просто старые ID не находились в реестре). Теперь миграция
    выполняется САМА при каждом старте процесса: идемпотентно, one-shot через
    маркер в schema_migrations (по образцу migrate_clan_coins_to_shards).
    """
    from core.cosmetics import COSMETIC_LEGACY_ID_MAP as _MAP

    await db.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "key TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT NOW())"
    )
    async with db.execute(
        "SELECT 1 FROM schema_migrations WHERE key = 'cosmetics_ids_v2'"
    ) as c:
        if await c.fetchone():
            return  # уже мигрировано

    import json as _json
    from loguru import logger as _log
    total = 0
    # 1-2) плоские колонки: инвентарь + экипировка (welcome-слот не задет —
    #      его ID не входят в маппинг)
    for old_id, new_id in _MAP.items():
        async with db.execute(
            "UPDATE user_cosmetics SET cosmetic_id = ? WHERE cosmetic_id = ? "
            "AND NOT EXISTS (SELECT 1 FROM user_cosmetics uc2 "
            "  WHERE uc2.user_id = user_cosmetics.user_id AND uc2.cosmetic_id = ?) "
            "RETURNING user_id",
            (new_id, old_id, new_id),
        ) as c:
            total += len(await c.fetchall())
        await db.execute("DELETE FROM user_cosmetics WHERE cosmetic_id = ?", (old_id,))
        await db.execute(
            "UPDATE user_cosmetic_loadout SET cosmetic_id = ? WHERE cosmetic_id = ?",
            (new_id, old_id),
        )
    # 3-4) JSON-таблицы: пресеты и витрина недели (построчная замена токенов)
    for table, pk, col in (("cosmetic_presets", "id", "loadout"),
                           ("weekly_showcase", "week_key", "slots_json")):
        try:
            async with db.execute(f"SELECT {pk} AS pk, {col} AS payload FROM {table}") as c:
                rows = [dict(r) for r in await c.fetchall()]
            for r in rows:
                payload = r["payload"] or ""
                new_payload = payload
                for old_id, new_id in _MAP.items():
                    new_payload = new_payload.replace(f'"{old_id}"', f'"{new_id}"')
                if new_payload != payload:
                    _json.loads(new_payload)  # страховка: JSON не сломан
                    await db.execute(
                        f"UPDATE {table} SET {col} = ? WHERE {pk} = ?",
                        (new_payload, r["pk"]),
                    )
                    total += 1
        except Exception:
            pass  # таблицы может не быть на свежей БД
    # 5) рефанд-лог (исторический, для консистентности)
    try:
        for old_id, new_id in _MAP.items():
            await db.execute(
                "UPDATE cosmetic_refund_log SET cosmetic_id = ? WHERE cosmetic_id = ? "
                "AND NOT EXISTS (SELECT 1 FROM cosmetic_refund_log rl2 "
                "  WHERE rl2.user_id = cosmetic_refund_log.user_id AND rl2.cosmetic_id = ?)",
                (new_id, old_id, new_id),
            )
            await db.execute(
                "DELETE FROM cosmetic_refund_log WHERE cosmetic_id = ?", (old_id,))
    except Exception:
        pass

    await db.execute(
        "INSERT INTO schema_migrations (key) VALUES ('cosmetics_ids_v2') "
        "ON CONFLICT (key) DO NOTHING"
    )
    await db.commit()
    _log.info(f"БЛОК 39: ID косметики мигрированы (затронуто строк: {total}) — "
              f"оплаченная косметика игроков возвращена")


async def _owned(db, user_id: int) -> set[str]:
    async with db.execute(
        "SELECT cosmetic_id FROM user_cosmetics WHERE user_id = ?", (user_id,)
    ) as c:
        return {r[0] for r in await c.fetchall()}


async def _loadout(db, user_id: int) -> dict[str, str]:
    async with db.execute(
        "SELECT slot, cosmetic_id FROM user_cosmetic_loadout WHERE user_id = ?", (user_id,)
    ) as c:
        return {r[0]: r[1] for r in await c.fetchall()}


async def _balances(db, user_id: int) -> dict[str, float]:
    async with db.execute(
        "SELECT COALESCE(user_balance_mora,0), COALESCE(user_balance_diamonds,0), "
        "COALESCE(user_balance_dark_mora,0), COALESCE(user_balance_zarniki,0) "
        "FROM users WHERE user_tg_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    if not row:
        return {"mora": 0.0, "diamonds": 0.0, "dark_mora": 0.0, "zarniki": 0.0}
    return {"mora": float(row[0]), "diamonds": float(row[1]),
            "dark_mora": float(row[2]), "zarniki": float(row[3])}


def _public(cid: str, cos: dict, owned: set[str], loadout: dict[str, str], vip: bool) -> dict:
    """Публичная карточка косметики для каталога."""
    is_owned = cid in owned
    return {
        "id": cid,
        "name": cos["name"],
        "slot": cos["slot"],
        "rarity": cos["rarity"],
        "lineup": cos.get("lineup"),
        "css": cos.get("css"),
        "text": cos.get("text"),
        "desc": cos.get("desc", ""),
        "vip_required": bool(cos.get("vip_required")),
        "source": cos.get("source", "shop"),
        "price": cos.get("price"),
        "owned": is_owned,
        "equipped": loadout.get(cos["slot"]) == cid,
        # БЛОК: «спит» без активной VIP — есть в инвентаре, но эффект не показывается.
        "vip_locked_inactive": is_owned and is_vip_locked(cos) and not vip,
    }


async def sync_auto_grants(db, user_id: int) -> None:
    """Авто-выдача косметики по источникам (идемпотентно): vip → при активной VIP;
    bp → при открытом платном треке И достигнутом `bp_level`. Вызывается при загрузке каталога."""
    owned = await _owned(db, user_id)
    pending = [(cid, cos) for cid, cos in COSMETICS.items()
               if cid not in owned and cos.get("source") in ("vip", "bp")]
    if not pending:
        return
    vip = None
    bp = None
    granted = False
    for cid, cos in pending:
        ok = False
        if cos["source"] == "vip":
            if vip is None:
                vip = await is_vip_active(db, user_id)
            ok = vip
        elif cos["source"] == "bp":
            need = cos.get("bp_level")
            if need:
                if bp is None:
                    from services.battle_pass import get_progress
                    bp = await get_progress(db, user_id)
                ok = bool(bp and bp.get("paid_track_open") and (bp.get("level") or 0) >= need)
        if ok:
            await db.execute(
                "INSERT INTO user_cosmetics (user_id, cosmetic_id) VALUES (?, ?) "
                "ON CONFLICT DO NOTHING", (user_id, cid))
            granted = True
    if granted:
        await db.commit()


# ── Приветственные анимации (вход / прелоадер) ──────────────────────────────────
def _effective_welcome(loadout: dict[str, str], vip: bool) -> str:
    """Действующий id анимации с учётом VIP-гейта (не-VIP → дефолт). Без запросов в БД."""
    chosen = loadout.get(_WELCOME_SLOT)
    anim = WELCOME_ANIMATIONS.get(chosen) if chosen else None
    if not anim:
        return WELCOME_DEFAULT
    if anim.get("vip_required") and not vip:
        return WELCOME_DEFAULT
    return chosen


def _welcome_options(current: str, vip: bool) -> list[dict]:
    return [{
        "id": aid, "name": a["name"], "rarity": a.get("rarity", "common"),
        "desc": a.get("desc", ""), "vip_required": bool(a.get("vip_required")),
        "locked": bool(a.get("vip_required")) and not vip,
        "current": aid == current,
    } for aid, a in WELCOME_ANIMATIONS.items()]


async def set_welcome(db, user_id: int, anim_id: str) -> tuple[bool, str]:
    """Выбрать приветственную анимацию (VIP-гейт для премиум-вариантов). Commits."""
    anim = WELCOME_ANIMATIONS.get(anim_id)
    if not anim:
        return False, "Нет такой анимации."
    if anim.get("vip_required") and not await is_vip_active(db, user_id):
        return False, "🔒 Выбор приветствия доступен только при активной VIP."
    await db.execute(
        "INSERT INTO user_cosmetic_loadout (user_id, slot, cosmetic_id) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id, slot) DO UPDATE SET cosmetic_id = ?",
        (user_id, _WELCOME_SLOT, anim_id, anim_id))
    await db.commit()
    return True, f"🎬 Приветствие: {anim['name']}"


async def get_catalog(db, user_id: int) -> dict:
    """Каталог по слотам + балансы + статус VIP + приветствия (для конструктора на сайте)."""
    await sync_auto_grants(db, user_id)
    owned = await _owned(db, user_id)
    loadout = await _loadout(db, user_id)
    vip = await is_vip_active(db, user_id)
    slots: dict[str, list] = {s: [] for s in COSMETIC_SLOTS}
    for cid, cos in COSMETICS.items():
        slots.setdefault(cos["slot"], []).append(_public(cid, cos, owned, loadout, vip))
    welcome_cur = _effective_welcome(loadout, vip)
    return {
        "vip": vip,
        "balances": await _balances(db, user_id),
        "slots": slots,
        "lineups": LINEUPS,
        "curated_looks": _curated_looks(owned),
        "currency_icons": _CUR_ICON,
        "welcome": {"current": welcome_cur, "options": _welcome_options(welcome_cur, vip)},
    }


def _curated_looks(owned: set[str]) -> list[dict]:
    """Публичные кураторские наборы с честной ценой недостающих предметов."""
    result = []
    for look_id, look in CURATED_LOOKS.items():
        items = dict(look.get("items") or {})
        missing = [cid for cid in items.values() if cid not in owned]
        missing_price = sum(
            int((COSMETICS[cid].get("price") or [{}])[0].get("zarniki", 0))
            for cid in missing
        )
        result.append({
            "id": look_id,
            "name": look["name"],
            "mood": look["mood"],
            "lineup": look["lineup"],
            "items": items,
            "owned_count": len(items) - len(missing),
            "total_count": len(items),
            "missing_price": missing_price,
            "fully_owned": not missing,
        })
    return result


async def grant_cosmetic(db, user_id: int, cosmetic_id: str) -> bool:
    """Выдать косметику (источники VIP/БП/ачивки). Идемпотентно. Commits."""
    if cosmetic_id not in COSMETICS:
        return False
    await db.execute(
        "INSERT INTO user_cosmetics (user_id, cosmetic_id) VALUES (?, ?) "
        "ON CONFLICT DO NOTHING", (user_id, cosmetic_id))
    await db.commit()
    return True


async def equip(db, user_id: int, cosmetic_id: str) -> tuple[bool, str]:
    cos = COSMETICS.get(cosmetic_id)
    if not cos:
        return False, "Нет такой косметики."
    if cosmetic_id not in await _owned(db, user_id):
        return False, "Сначала нужно получить эту косметику."
    await db.execute(
        "INSERT INTO user_cosmetic_loadout (user_id, slot, cosmetic_id) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id, slot) DO UPDATE SET cosmetic_id = ?",
        (user_id, cos["slot"], cosmetic_id, cosmetic_id))
    await db.commit()
    return True, f"✅ Надето: {cos['name']}"


async def unequip(db, user_id: int, slot: str) -> tuple[bool, str]:
    if slot not in COSMETIC_SLOTS:
        return False, "Неизвестный слот."
    await db.execute(
        "DELETE FROM user_cosmetic_loadout WHERE user_id = ? AND slot = ?", (user_id, slot))
    await db.commit()
    return True, "Снято."


async def buy(db, user_id: int, cosmetic_id: str, option_index: int = 0,
              price_override: dict | None = None) -> tuple[bool, str]:
    """Купить косметику за выбранный вариант оплаты (мульти/альт-валюта). Атомарно.
    price_override — СЕРВЕРНАЯ подмена цены (R4.2 Витрина недели: скидка считается
    на бэке, клиентской цене не доверяем); формат {"zarniki": 200}."""
    cos = COSMETICS.get(cosmetic_id)
    if not cos:
        return False, "Нет такой косметики."
    price = cos.get("price")
    if not price:
        return False, "Эта косметика не продаётся — выдаётся за VIP / БП / достижения."
    if cosmetic_id in await _owned(db, user_id):
        return False, "Эта косметика у тебя уже есть."
    if price_override is not None:
        chosen = price_override
    else:
        if not (0 <= option_index < len(price)):
            return False, "Некорректный вариант оплаты."
        chosen = price[option_index]

    async with db.connection.transaction():
        async with db.execute(
            "SELECT COALESCE(user_balance_mora,0), COALESCE(user_balance_diamonds,0), "
            "COALESCE(user_balance_dark_mora,0), COALESCE(user_balance_zarniki,0) "
            "FROM users WHERE user_tg_id = ? FOR UPDATE", (user_id,)
        ) as c:
            row = await c.fetchone()
        bal = {"mora": float(row[0]), "diamonds": float(row[1]),
               "dark_mora": float(row[2]), "zarniki": float(row[3])} if row else \
              {"mora": 0.0, "diamonds": 0.0, "dark_mora": 0.0, "zarniki": 0.0}

        for cur, amt in chosen.items():
            if cur not in _CUR_COL:
                return False, "Некорректная валюта цены."
            if bal.get(cur, 0) < amt:
                return False, (f"Недостаточно {_CUR_ICON[cur]}: нужно {int(amt)}, "
                               f"есть {int(bal.get(cur, 0))}.")

        for cur, amt in chosen.items():
            col = _CUR_COL[cur]  # whitelisted, не пользовательский ввод
            await db.execute(
                f"UPDATE users SET {col} = {col} - ? WHERE user_tg_id = ?", (amt, user_id))

        await db.execute(
            "INSERT INTO user_cosmetics (user_id, cosmetic_id) VALUES (?, ?) "
            "ON CONFLICT DO NOTHING", (user_id, cosmetic_id))

    # Ачивка «Модник» (fashionista) — считаем купленные предметы косметики.
    # Вне транзакции покупки: increment_metric открывает свою (самокоммит).
    try:
        from services.achievements import increment_metric
        await increment_metric(db, user_id, "cosmetics_bought", delta=1.0)
        await db.commit()
    except Exception:
        pass

    paid = ", ".join(f"{int(amt)}{_CUR_ICON[cur]}" for cur, amt in chosen.items())
    msg = f"🎨 Куплено: {cos['name']} ({paid})"
    if cos.get("rarity", "common") != "common" and not await is_vip_active(db, user_id):
        msg += "\n\n⚠️ Эта косметика отображается только при активной VIP-подписке. Без VIP она сохранена в инвентаре, но не будет видна на профиле."
    return True, msg


def lineup_buy_quote(lineup_id: str, owned: set[str]) -> dict | None:
    """Раскладка покупки «всё недостающее» для линейки (Стадия 3 косметики):
    {"missing": [id,...], "price_min": int, "price_max": int, "total": int}.
    Цена считается по каждому реальному предмету: титул, рамка, фон и эффект
    имеют разный визуальный вес. None если линейки нет, хотя бы один предмет не
    продаётся за зарники или всё уже принадлежит игроку."""
    if lineup_id not in LINEUPS:
        return None
    items = lineup_items(lineup_id)
    missing = [cid for cid in items if cid not in owned]
    if not missing:
        return None
    prices = []
    for cosmetic_id in missing:
        price_opt = (items[cosmetic_id].get("price") or [None])[0]
        if not price_opt or "zarniki" not in price_opt:
            return None
        prices.append(int(price_opt["zarniki"]))
    return {
        "missing": missing,
        "price_min": min(prices),
        "price_max": max(prices),
        "total": sum(prices),
    }


async def buy_lineup(db, user_id: int, lineup_id: str) -> tuple[bool, str]:
    """Купить ВСЕ недостающие предметы линейки одной транзакцией («Купить всё
    недостающее», Стадия 3 редизайна «Внешний вид»). Мирроит buy_bundle()
    (FastAPI/routers/showcase.py, витрина недели) — тот же паттерн SELECT ...
    FOR UPDATE + одно списание + N выдач в одной транзакции — но без скидки
    комплекта: сервер складывает актуальные поштучные цены недостающих предметов.

    Финальный ревью Стадии 3 (2026-07-31): владение читалось ДО открытия
    транзакции/блокировки баланса — двойной тап по кнопке (или 2 параллельных
    запроса) считали одну и ту же "missing" ДВАЖДЫ и списывали total дважды,
    хотя предметы выдавались только один раз (ON CONFLICT DO NOTHING). Второй
    SELECT ... FOR UPDATE блокируется на строке юзера, пока первая транзакция
    не закоммитится — поэтому владение теперь читается ПОСЛЕ захвата блокировки:
    второй вызов увидит уже выданные первым предметы и посчитает missing/total
    заново (меньше или 0), а не спишет цену за уже подаренное."""
    meta = LINEUPS.get(lineup_id)
    if not meta:
        return False, "Нет такой линейки."

    async with db.connection.transaction():
        async with db.execute(
            "SELECT COALESCE(user_balance_zarniki,0) FROM users WHERE user_tg_id = ? FOR UPDATE",
            (user_id,)
        ) as c:
            row = await c.fetchone()
        bal = float(row[0]) if row else 0.0

        owned = await _owned(db, user_id)
        quote = lineup_buy_quote(lineup_id, owned)
        if not quote:
            return False, "Эта линейка уже собрана полностью или недоступна для покупки."
        missing, total = quote["missing"], quote["total"]

        if bal < total:
            return False, f"Нужно {total}✨ за всю линейку (у тебя {int(bal)})."
        await db.execute(
            "UPDATE users SET user_balance_zarniki = user_balance_zarniki - ? WHERE user_tg_id = ?",
            (total, user_id))
        for cid in missing:
            await db.execute(
                "INSERT INTO user_cosmetics (user_id, cosmetic_id) VALUES (?, ?) "
                "ON CONFLICT DO NOTHING", (user_id, cid))

    # Ачивка «Модник» — считаем ВСЕ докупленные предметы, не только 1 (buy() делает
    # то же самое при одиночной покупке). Вне транзакции — increment_metric коммитит сам.
    try:
        from services.achievements import increment_metric
        await increment_metric(db, user_id, "cosmetics_bought", delta=float(len(missing)))
        await db.commit()
    except Exception:
        pass

    return True, f"🎨 «{meta['name']}» собрана полностью! Докуплено {len(missing)} шт. за {total}✨"


async def buy_many(db, user_id: int, cosmetic_ids: list[str]) -> tuple[bool, str]:
    """Купить выбранные предметы примерочной одной транзакцией.

    В отличие от buy_lineup(), набор может содержать предметы из разных линеек
    и с разной ценой. Владение читается только после блокировки баланса: это
    предотвращает повторное списание при двух параллельных запросах.
    """
    ids = list(dict.fromkeys(cosmetic_ids))
    if not ids:
        return False, "Список предметов пуст."

    for cosmetic_id in ids:
        cos = COSMETICS.get(cosmetic_id)
        if not cos:
            return False, f"Нет такой косметики: {cosmetic_id}."
        price = cos.get("price")
        if not price or "zarniki" not in price[0]:
            return False, f"«{cos['name']}» не продаётся за зарники."

    async with db.connection.transaction():
        async with db.execute(
            "SELECT COALESCE(user_balance_zarniki,0) FROM users WHERE user_tg_id = ? FOR UPDATE",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        balance = float(row[0]) if row else 0.0

        owned = await _owned(db, user_id)
        missing = [cosmetic_id for cosmetic_id in ids if cosmetic_id not in owned]
        if not missing:
            return False, "Всё это у тебя уже есть."

        total = sum(int(COSMETICS[cosmetic_id]["price"][0]["zarniki"])
                    for cosmetic_id in missing)
        if balance < total:
            return False, f"Нужно {total}✨ (у тебя {int(balance)})."

        await db.execute(
            "UPDATE users SET user_balance_zarniki = user_balance_zarniki - ? WHERE user_tg_id = ?",
            (total, user_id),
        )
        for cosmetic_id in missing:
            await db.execute(
                "INSERT INTO user_cosmetics (user_id, cosmetic_id) VALUES (?, ?) "
                "ON CONFLICT DO NOTHING",
                (user_id, cosmetic_id),
            )

    try:
        from services.achievements import increment_metric
        await increment_metric(db, user_id, "cosmetics_bought", delta=float(len(missing)))
        await db.commit()
    except Exception:
        pass

    return True, f"🎨 Куплено {len(missing)} шт. за {total}✨"


async def get_active_cosmetics(db, user_id: int) -> dict:
    """Надетая косметика для рендера профиля (веб + титул в боте).
    → {"name_glow": {"css","name","lineup"}, "avatar_frame": {...},
       "title": "текст", "lineage": {"id","source_slot"}}
    VIP-гейт: косметика с is_vip_locked() показывается только при активной VIP —
    без неё «спит» (выбор слота в БД не трогаем, чтобы при продлении VIP она
    вернулась сама, без переэкипировки)."""
    loadout = await _loadout(db, user_id)
    out: dict = {}
    locked: dict[str, bool] = {}
    for slot, cid in loadout.items():
        if slot == _WELCOME_SLOT:
            continue
        cos = COSMETICS.get(cid)
        if not cos:
            continue
        if slot == "title":
            out["title"] = cos.get("text") or cos["name"]
            if cos.get("css"):
                out["title_css"] = cos["css"]
        else:
            out[slot] = {
                "css": cos.get("css"),
                "name": cos["name"],
                "lineup": cos.get("lineup"),
            }
        locked[slot] = is_vip_locked(cos)

    chosen = loadout.get(_WELCOME_SLOT)
    anim = WELCOME_ANIMATIONS.get(chosen) if chosen else None
    welcome_vip_locked = bool(anim and anim.get("vip_required"))

    vip = await is_vip_active(db, user_id) if (any(locked.values()) or welcome_vip_locked) else False
    out["welcome"] = (chosen if vip else WELCOME_DEFAULT) if welcome_vip_locked else (chosen if anim else WELCOME_DEFAULT)

    for slot, is_locked in locked.items():
        if is_locked and not vip:
            out.pop(slot, None)
            if slot == "title":
                out.pop("title_css", None)

    # Родословная образа вычисляется ПОСЛЕ VIP-фильтра: профиль не должен
    # подсвечиваться цветом предмета, который сейчас «спит». Приоритет отражает
    # близость к аватару; клиент получает готовый lineup id и не поддерживает
    # хрупкую карту cosmetic_id → lineup.
    for source_slot in ("avatar_frame", "avatar_halo", "card_fx", "profile_bg"):
        item = out.get(source_slot)
        lineup_id = item.get("lineup") if isinstance(item, dict) else None
        if lineup_id:
            out["lineage"] = {"id": lineup_id, "source_slot": source_slot}
            break
    return out


async def get_flex_cosmetics_batch(db, user_ids: list[int]) -> dict[int, dict]:
    """БЛОК21: лёгкая косметика для «флекса» в топах/списках — ник-глоу (css) + титул,
    ОДНИМ запросом на всех. → {user_id: {"glow": css|None, "title": str|None}}.
    Виден статус везде, где есть зрители → главный драйвер конверсии (зависть)."""
    ids = [int(u) for u in (user_ids or [])]
    if not ids:
        return {}
    out: dict[int, dict] = {}
    pending_vip_check: set[int] = set()  # юзеры с хотя бы 1 VIP-locked косметикой в выборке
    ph = ",".join(["?"] * len(ids))
    async with db.execute(
        f"SELECT user_id, slot, cosmetic_id FROM user_cosmetic_loadout "
        f"WHERE user_id IN ({ph}) AND slot IN ('name_glow', 'title')",
        tuple(ids),
    ) as c:
        rows = await c.fetchall()
    for r in rows:
        uid, slot, cid = int(r[0]), r[1], r[2]
        cos = COSMETICS.get(cid)
        if not cos:
            continue
        d = out.setdefault(uid, {})
        if slot == "title":
            d["title"] = cos.get("text") or cos["name"]
            if cos.get("css"):
                d["title_css"] = cos["css"]
        elif slot == "name_glow":
            d["glow"] = cos.get("css")
        if is_vip_locked(cos):
            pending_vip_check.add(uid)
    if pending_vip_check:
        vip_ids = await is_vip_active_batch(db, list(pending_vip_check))
        for uid in pending_vip_check - vip_ids:
            d = out.get(uid)
            if not d:
                continue
            cid_glow = next((r[2] for r in rows if int(r[0]) == uid and r[1] == "name_glow"), None)
            cid_title = next((r[2] for r in rows if int(r[0]) == uid and r[1] == "title"), None)
            if cid_glow and is_vip_locked(COSMETICS.get(cid_glow, {})):
                d.pop("glow", None)
            if cid_title and is_vip_locked(COSMETICS.get(cid_title, {})):
                d.pop("title", None)
                d.pop("title_css", None)
            if not d:
                out.pop(uid, None)
    return out


def _gift_zarniki(cos: dict) -> int | None:
    """Цена подарка в ✨ Зарниках = зарниковая цена косметики. None — нельзя подарить
    (нет зарниковой цены: VIP/БП/ачивка). В мини-аппе всё покупается за ✨, не за ⭐."""
    for opt in cos.get("price") or []:
        if "zarniki" in opt:
            return int(opt["zarniki"])
    return None


async def giftable_cosmetics(db, recipient_id: int) -> list[dict]:
    """БЛОК21: косметика для подарка за ✨ Зарники + флаг owned получателем (анти-дубль)."""
    owned = await _owned(db, recipient_id)
    out = []
    for cid, cos in COSMETICS.items():
        zar = _gift_zarniki(cos)
        if zar is None:
            continue
        out.append({
            "id": cid, "name": cos["name"], "slot": cos["slot"], "rarity": cos["rarity"],
            "css": cos.get("css"), "text": cos.get("text"),
            "zarniki": zar, "owned": cid in owned,
        })
    out.sort(key=lambda x: (x["owned"], x["zarniki"]))
    return out


# ── БЛОК21 #3: сундуки-сюрпризы + осколки + крафт косметики ───────────────────────
async def _add_item(db, user_id: int, item_id: str, qty: int) -> None:
    await db.execute(
        "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
        (user_id, item_id, qty, qty))


async def _shard_balance(db, user_id: int) -> int:
    async with db.execute(
        "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = 'cosmetic_shard'", (user_id,)
    ) as c:
        row = await c.fetchone()
    return int(row[0]) if row else 0


def _shop_cosmetics(rarity: str) -> list[str]:
    """Косметика source=="shop" нужной редкости — пул для сундуков/крафта (эксклюзивы не входят)."""
    return [cid for cid, c in COSMETICS.items()
            if c.get("source") == "shop" and c.get("rarity") == rarity]


_RARITY_RU = {"common": "Обычная", "rare": "Редкая", "epic": "Эпическая",
              "legendary": "Легендарная", "mythic": "Мифическая"}


def _chest_odds(ch: dict) -> list[dict]:
    """«Что внутри» — честные шансы дропа сундука (витрина, как gacha-odds → доверие + FOMO)."""
    loot = ch["loot"]
    total = sum(e[-1] for e in loot) or 1
    out = []
    for kind, val, w in loot:
        pct = round(w / total * 100)
        if kind == "shards":
            label, rar = f"🔹 {val} осколков", None
        elif kind == "item":
            label, rar = ITEMS_REGISTRY.get(val, {}).get("name", val), None
        else:  # cosmetic
            label, rar = f"Косметика · {_RARITY_RU.get(val, val)}", val
        out.append({"label": label, "pct": pct, "rarity": rar})
    out.sort(key=lambda x: -x["pct"])
    return out


async def chest_catalog(db, user_id: int) -> list[dict]:
    """Сундуки: цена в ✨ Зарники + готовые к открытию + честные шансы дропа («что внутри»)."""
    out = []
    for cid, ch in COSMETIC_CHESTS.items():
        async with db.execute(
            "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?", (user_id, cid)
        ) as c:
            row = await c.fetchone()
        out.append({"id": cid, "name": ch["name"], "zarniki": ch["zarniki"],
                    "owned": int(row[0]) if row else 0, "odds": _chest_odds(ch)})
    return out


async def open_chest(db, user_id: int, chest_id: str) -> tuple[bool, str, dict | None]:
    """Открыть сундук: списать токен, прокрутить лут, выдать (дубль косметики → осколки).
    Атомарно (FOR UPDATE). Возвращает (ok, msg, drop) — drop для реветь-анимации в UI."""
    chest = COSMETIC_CHESTS.get(chest_id)
    if not chest:
        return False, "Сундук не найден.", None
    drop: dict | None = None
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? AND quantity > 0 FOR UPDATE",
                (user_id, chest_id),
            ) as c:
                if not await c.fetchone():
                    return False, "У тебя нет этого сундука.", None
            await db.execute("UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = ?", (user_id, chest_id))
            await db.execute("DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0", (user_id, chest_id))

            loot = chest["loot"]
            total = sum(e[-1] for e in loot)
            r = random.uniform(0, total); acc = 0.0; pick = loot[-1]
            for e in loot:
                acc += e[-1]
                if r <= acc:
                    pick = e; break

            if pick[0] == "shards":
                n = int(pick[1])
                await _add_item(db, user_id, "cosmetic_shard", n)
                drop = {"kind": "shards", "shards": n, "name": f"🔹 {n} осколков"}
            elif pick[0] == "item":
                iid = pick[1]
                await _add_item(db, user_id, iid, 1)
                drop = {"kind": "item", "item_id": iid,
                        "name": ITEMS_REGISTRY.get(iid, {}).get("name", iid)}
            else:  # cosmetic
                rarity = pick[1]
                owned = await _owned(db, user_id)
                pool = [cid for cid in _shop_cosmetics(rarity) if cid not in owned]
                if pool:
                    cid = random.choice(pool)
                    await db.execute(
                        "INSERT INTO user_cosmetics (user_id, cosmetic_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
                        (user_id, cid))
                    cos = COSMETICS[cid]
                    drop = {"kind": "cosmetic", "cosmetic_id": cid, "name": cos["name"],
                            "rarity": rarity, "css": cos.get("css"), "text": cos.get("text"),
                            "slot": cos["slot"]}
                else:
                    n = COSMETIC_DUPE_SHARDS.get(rarity, 5)
                    await _add_item(db, user_id, "cosmetic_shard", n)
                    drop = {"kind": "shards", "shards": n, "dupe": True,
                            "name": f"🔹 {n} осколков (всё собрано — компенсация)"}
    except Exception as e:
        return False, f"Ошибка: {e}", None
    return True, "Сундук открыт!", drop


async def craft_catalog(db, user_id: int) -> dict:
    """Каталог крафта косметики из осколков (только source=="shop")."""
    owned = await _owned(db, user_id)
    shards = await _shard_balance(db, user_id)
    items = []
    for cid, cos in COSMETICS.items():
        if cos.get("source") != "shop":
            continue
        cost = COSMETIC_CRAFT_SHARDS.get(cos["rarity"], 9999)
        items.append({"id": cid, "name": cos["name"], "slot": cos["slot"], "rarity": cos["rarity"],
                      "css": cos.get("css"), "text": cos.get("text"), "cost": cost,
                      "owned": cid in owned, "can": (shards >= cost and cid not in owned)})
    items.sort(key=lambda x: (x["owned"], x["cost"]))
    return {"shards": shards, "items": items}


async def craft_cosmetic(db, user_id: int, cosmetic_id: str) -> tuple[bool, str]:
    """Скрафтить косметику из осколков. Атомарно (списание + выдача под FOR UPDATE)."""
    cos = COSMETICS.get(cosmetic_id)
    if not cos or cos.get("source") != "shop":
        return False, "Эту косметику нельзя скрафтить."
    if cosmetic_id in await _owned(db, user_id):
        return False, "Косметика уже у тебя."
    cost = COSMETIC_CRAFT_SHARDS.get(cos["rarity"], 9999)
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = 'cosmetic_shard' FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            have = int(row[0]) if row else 0
            if have < cost:
                return False, f"Нужно {cost} 🔹, у тебя {have}."
            await db.execute(
                "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = 'cosmetic_shard'",
                (cost, user_id))
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND item_id = 'cosmetic_shard' AND quantity <= 0",
                (user_id,))
            await db.execute(
                "INSERT INTO user_cosmetics (user_id, cosmetic_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
                (user_id, cosmetic_id))
        return True, f"✨ Скрафчено: {cos['name']}! Надень в конструкторе."
    except Exception as e:
        return False, f"Ошибка: {e}"


# ── БЛОК21: покупки за ✨ Зарники (всё в мини-аппе — за ✨, а ✨ — за ⭐) ───────────
async def _charge_zarniki(db, user_id: int, amount: int) -> tuple[bool, str]:
    """Списать ✨ Зарники атомарно (вызывать ВНУТРИ транзакции с FOR UPDATE на users)."""
    async with db.execute(
        "SELECT COALESCE(user_balance_zarniki, 0) FROM users WHERE user_tg_id = ? FOR UPDATE",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    have = float(row[0]) if row else 0.0
    if have < amount:
        return False, f"Недостаточно ✨ Зарников: нужно {amount}, есть {int(have)}."
    await db.execute(
        "UPDATE users SET user_balance_zarniki = user_balance_zarniki - ? WHERE user_tg_id = ?",
        (amount, user_id))
    return True, "ok"


async def gift_cosmetic(db, sender_id: int, recipient_id: int, cosmetic_id: str) -> tuple[bool, str, str]:
    """Подарить косметику за ✨ Зарники: списать у дарителя → выдать получателю.
    Возвращает (ok, msg, cosmetic_name) — имя для уведомления получателя в Telegram."""
    cos = COSMETICS.get(cosmetic_id)
    if not cos:
        return False, "Косметика не найдена.", ""
    if int(sender_id) == int(recipient_id):
        return False, "Нельзя подарить самому себе 🙂", ""
    zar = _gift_zarniki(cos)
    if zar is None:
        return False, "Эту косметику нельзя подарить.", ""
    try:
        async with db.connection.transaction():
            if cosmetic_id in await _owned(db, recipient_id):
                return False, "У игрока уже есть эта косметика.", ""
            ok, msg = await _charge_zarniki(db, sender_id, zar)
            if not ok:
                return False, msg, ""
            await db.execute(
                "INSERT INTO user_cosmetics (user_id, cosmetic_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
                (recipient_id, cosmetic_id))
        return True, f"🎁 Подарок отправлен! −{zar}✨", cos["name"]
    except Exception as e:
        return False, f"Ошибка: {e}", ""


async def buy_chest(db, user_id: int, chest_id: str) -> tuple[bool, str]:
    """Купить сундук за ✨ Зарники → выдать ТОКЕН-сундук (открыть отдельно для реветь-момента)."""
    ch = COSMETIC_CHESTS.get(chest_id)
    if not ch:
        return False, "Сундук не найден."
    zar = int(ch["zarniki"])
    try:
        async with db.connection.transaction():
            ok, msg = await _charge_zarniki(db, user_id, zar)
            if not ok:
                return False, msg
            await _add_item(db, user_id, chest_id, 1)
        return True, f"🎁 {ch['name']} куплен за {zar}✨! Открой его ниже."
    except Exception as e:
        return False, f"Ошибка: {e}"


# ── Пресеты косметики (БЛОК 20.B) ─────────────────────────────────────────────

_MAX_PRESETS = 5
_MAX_NAME_LEN = 30


async def _loadout_snapshot(db, user_id: int) -> dict[str, str]:
    """Текущий экипированный образ — {slot: cosmetic_id} (пустые слоты опускаем)."""
    async with db.execute(
        "SELECT slot, cosmetic_id FROM user_cosmetic_loadout WHERE user_id = ?",
        (user_id,),
    ) as c:
        rows = await c.fetchall()
    return {r[0]: r[1] for r in rows if r[1]}


async def list_presets(db, user_id: int) -> list[dict]:
    """Список пресетов пользователя (не более _MAX_PRESETS)."""
    async with db.execute(
        "SELECT id, name, loadout, created_at FROM cosmetic_presets "
        "WHERE user_id = ? ORDER BY id",
        (user_id,),
    ) as c:
        rows = await c.fetchall()
    return [
        {"id": r[0], "name": r[1], "loadout": json.loads(r[2]), "created_at": str(r[3])}
        for r in rows
    ]


async def save_preset(db, user_id: int, name: str) -> tuple[bool, str, dict | None]:
    """Сохранить текущий образ как новый пресет."""
    name = name.strip()[:_MAX_NAME_LEN] or "Образ"
    async with db.execute(
        "SELECT COUNT(*) FROM cosmetic_presets WHERE user_id = ?", (user_id,)
    ) as c:
        (count,) = await c.fetchone()
    if count >= _MAX_PRESETS:
        return False, f"Максимум {_MAX_PRESETS} пресетов. Удали один из старых.", None
    loadout = await _loadout_snapshot(db, user_id)
    await db.execute(
        "INSERT INTO cosmetic_presets (user_id, name, loadout) VALUES (?, ?, ?)",
        (user_id, name, json.dumps(loadout)),
    )
    await db.commit()
    preset_id = None
    async with db.execute(
        "SELECT id FROM cosmetic_presets WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (user_id,),
    ) as c:
        row = await c.fetchone()
        if row:
            preset_id = row[0]
    return True, f"💾 Образ «{name}» сохранён!", {"id": preset_id, "name": name, "loadout": loadout}


async def apply_preset(db, user_id: int, preset_id: int) -> tuple[bool, str]:
    """Применить пресет: заменяет текущий loadout слотами из пресета."""
    async with db.execute(
        "SELECT name, loadout FROM cosmetic_presets WHERE id = ? AND user_id = ?",
        (preset_id, user_id),
    ) as c:
        row = await c.fetchone()
    if not row:
        return False, "Пресет не найден."
    name, loadout_json = row
    loadout: dict[str, str] = json.loads(loadout_json)
    owned = await _owned(db, user_id)
    for slot, cid in loadout.items():
        cos = COSMETICS.get(cid)
        if not cos or cid not in owned:
            continue
        await db.execute(
            "INSERT INTO user_cosmetic_loadout (user_id, slot, cosmetic_id) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id, slot) DO UPDATE SET cosmetic_id = EXCLUDED.cosmetic_id",
            (user_id, slot, cid),
        )
    await db.commit()
    return True, f"✅ Образ «{name}» применён!"


async def delete_preset(db, user_id: int, preset_id: int) -> tuple[bool, str]:
    """Удалить пресет пользователя."""
    await db.execute(
        "DELETE FROM cosmetic_presets WHERE id = ? AND user_id = ?",
        (preset_id, user_id),
    )
    await db.commit()
    return True, "🗑 Пресет удалён."
