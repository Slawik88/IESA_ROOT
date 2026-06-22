"""services/cosmetics.py — Конструктор внешнего вида профиля.

Бизнес-логика косметики: каталог, покупка (мульти/альт-валюта), экипировка, выдача.
No bot.*/FastAPI.* imports. Только косметика — без игрового преимущества.
"""
from core.cosmetics import (
    COSMETICS, COSMETIC_SLOTS, WELCOME_ANIMATIONS, WELCOME_DEFAULT,
)
from services.vip import is_vip_active

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


def _public(cid: str, cos: dict, owned: set[str], loadout: dict[str, str]) -> dict:
    """Публичная карточка косметики для каталога."""
    return {
        "id": cid,
        "name": cos["name"],
        "slot": cos["slot"],
        "rarity": cos["rarity"],
        "css": cos.get("css"),
        "text": cos.get("text"),
        "desc": cos.get("desc", ""),
        "vip_required": bool(cos.get("vip_required")),
        "source": cos.get("source", "shop"),
        "price": cos.get("price"),                       # список вариантов оплаты | None
        "owned": cid in owned,
        "equipped": loadout.get(cos["slot"]) == cid,
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
        slots.setdefault(cos["slot"], []).append(_public(cid, cos, owned, loadout))
    welcome_cur = _effective_welcome(loadout, vip)
    return {
        "vip": vip,
        "balances": await _balances(db, user_id),
        "slots": slots,
        "currency_icons": _CUR_ICON,
        "welcome": {"current": welcome_cur, "options": _welcome_options(welcome_cur, vip)},
    }


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


async def buy(db, user_id: int, cosmetic_id: str, option_index: int = 0) -> tuple[bool, str]:
    """Купить косметику за выбранный вариант оплаты (мульти/альт-валюта). Атомарно."""
    cos = COSMETICS.get(cosmetic_id)
    if not cos:
        return False, "Нет такой косметики."
    price = cos.get("price")
    if not price:
        return False, "Эта косметика не продаётся — выдаётся за VIP / БП / достижения."
    if cosmetic_id in await _owned(db, user_id):
        return False, "Эта косметика у тебя уже есть."
    if cos.get("vip_required") and not await is_vip_active(db, user_id):
        return False, "🔒 Покупка доступна только при активной VIP."
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

    paid = ", ".join(f"{int(amt)}{_CUR_ICON[cur]}" for cur, amt in chosen.items())
    return True, f"🎨 Куплено: {cos['name']} ({paid})"


async def get_active_cosmetics(db, user_id: int) -> dict:
    """Надетая косметика для рендера профиля (веб + титул в боте).
    → {"name_glow": {"css","name"}, "avatar_frame": {...}, "title": "текст"}"""
    loadout = await _loadout(db, user_id)
    out: dict = {}
    for slot, cid in loadout.items():
        if slot == _WELCOME_SLOT:
            continue
        cos = COSMETICS.get(cid)
        if not cos:
            continue
        if slot == "title":
            out["title"] = cos.get("text") or cos["name"]
        else:
            out[slot] = {"css": cos.get("css"), "name": cos["name"]}
    # Приветственная анимация (VIP-гейт; is_vip спрашиваем только если выбран премиум-вариант).
    chosen = loadout.get(_WELCOME_SLOT)
    anim = WELCOME_ANIMATIONS.get(chosen) if chosen else None
    if anim and anim.get("vip_required"):
        out["welcome"] = chosen if await is_vip_active(db, user_id) else WELCOME_DEFAULT
    else:
        out["welcome"] = chosen if anim else WELCOME_DEFAULT
    return out
