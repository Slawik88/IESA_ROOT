"""services/cosmetics.py — Конструктор внешнего вида профиля.

Бизнес-логика косметики: каталог, покупка (мульти/альт-валюта), экипировка, выдача.
No bot.*/FastAPI.* imports. Только косметика — без игрового преимущества.
"""
import math
import random

from core.cosmetics import (
    COSMETICS, COSMETIC_SLOTS, WELCOME_ANIMATIONS, WELCOME_DEFAULT,
)
from core.constants import (
    ZARNIKI_PER_STAR, COSMETIC_CHESTS, COSMETIC_DUPE_SHARDS, COSMETIC_CRAFT_SHARDS,
)
from core.registry import ITEMS_REGISTRY
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


async def get_flex_cosmetics_batch(db, user_ids: list[int]) -> dict[int, dict]:
    """БЛОК21: лёгкая косметика для «флекса» в топах/списках — ник-глоу (css) + титул,
    ОДНИМ запросом на всех. → {user_id: {"glow": css|None, "title": str|None}}.
    Виден статус везде, где есть зрители → главный драйвер конверсии (зависть)."""
    ids = [int(u) for u in (user_ids or [])]
    if not ids:
        return {}
    out: dict[int, dict] = {}
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
        elif slot == "name_glow":
            d["glow"] = cos.get("css")
    return out


def _gift_stars(cos: dict) -> int | None:
    """Цена подарка в ⭐ из зарникового варианта косметики (1⭐ = ZARNIKI_PER_STAR✨).
    None — косметику нельзя подарить (нет зарниковой цены: VIP/БП/ачивка)."""
    for opt in cos.get("price") or []:
        if "zarniki" in opt:
            return max(1, math.ceil(opt["zarniki"] / ZARNIKI_PER_STAR))
    return None


async def giftable_cosmetics(db, recipient_id: int) -> list[dict]:
    """БЛОК21: косметика, которую можно подарить за ⭐ (есть зарниковая цена),
    + флаг owned получателем (чтобы не дарить дубликат). Драйвер виральности."""
    owned = await _owned(db, recipient_id)
    out = []
    for cid, cos in COSMETICS.items():
        stars = _gift_stars(cos)
        if stars is None:
            continue
        out.append({
            "id": cid, "name": cos["name"], "slot": cos["slot"], "rarity": cos["rarity"],
            "css": cos.get("css"), "text": cos.get("text"),
            "stars": stars, "owned": cid in owned,
        })
    out.sort(key=lambda x: (x["owned"], x["stars"]))
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


async def chest_catalog(db, user_id: int) -> list[dict]:
    """Сундуки: цена в ⭐ + сколько уже у игрока готово к открытию."""
    out = []
    for cid, ch in COSMETIC_CHESTS.items():
        async with db.execute(
            "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?", (user_id, cid)
        ) as c:
            row = await c.fetchone()
        out.append({"id": cid, "name": ch["name"], "stars": ch["stars"],
                    "owned": int(row[0]) if row else 0})
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
                            "rarity": rarity, "css": cos.get("css"), "text": cos.get("text")}
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
