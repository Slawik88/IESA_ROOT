"""
services/battle_pass.py
B5: Боевой пропуск — сезонная прогрессия с бесплатным и платным (VIP) треками.
No bot.*/FastAPI.* imports.
"""
from datetime import date

from core.constants import (
    BATTLE_PASS_BUY_LEVEL_BASE,
    BATTLE_PASS_BUY_LEVEL_MARGIN,
    BATTLE_PASS_BUY_LEVEL_STEP,
    BATTLE_PASS_MAX_LEVEL,
    BATTLE_PASS_XP_ACTION_LABELS,
    BATTLE_PASS_XP_DAILY_CAPS,
    BATTLE_PASS_XP_PER_LEVEL,
    BATTLE_PASS_XP_WEIGHTS,
)
from core.registry import BATTLE_PASS_REWARDS, BATTLE_PASS_SEASONS, ITEMS_REGISTRY
from core.themes import THEMES
from infrastructure.repositories.economy import add_balance
from infrastructure.repositories.themes import grant_theme
from services.vip import is_vip_active

# Сезоны из БД (создаются через Консоль разработчика на сайте). Кэш на процесс:
# бот обновляет его раз в минуту в scheduler, FastAPI — при GET /battle_pass/status
# и при правках сезонов в консоли. DB перекрывает registry по совпадающему id.
_db_seasons_cache: dict[str, dict] = {}


async def refresh_seasons_cache(db) -> None:
    global _db_seasons_cache
    async with db.execute(
        "SELECT id, label, starts_at, ends_at, COALESCE(max_level, 50) AS max_level "
        "FROM battle_pass_seasons"
    ) as c:
        rows = await c.fetchall()
    _db_seasons_cache = {
        row["id"]: {"label": row["label"], "starts_at": row["starts_at"],
                    "ends_at": row["ends_at"], "max_level": row["max_level"]}
        for row in rows
    }


def all_seasons() -> dict[str, dict]:
    """registry + БД (БД перекрывает registry по id)."""
    return {**BATTLE_PASS_SEASONS, **_db_seasons_cache}


def get_active_season() -> dict | None:
    """Текущий сезон по дате (registry + БД-кэш), либо None между сезонами."""
    today = date.today().isoformat()
    for season_id, season in all_seasons().items():
        if season["starts_at"] <= today <= season["ends_at"]:
            return {**season, "id": season_id}
    return None


async def _get_or_create_progress(db, user_id: int, season_id: str) -> dict:
    async with db.execute(
        "SELECT xp, level, claimed_free_levels, claimed_paid_levels "
        "FROM battle_pass_progress WHERE user_id = ? AND season_id = ?",
        (user_id, season_id),
    ) as c:
        row = await c.fetchone()
    if row:
        return dict(row)

    await db.execute(
        "INSERT INTO battle_pass_progress (user_id, season_id) VALUES (?, ?) "
        "ON CONFLICT (user_id, season_id) DO NOTHING",
        (user_id, season_id),
    )
    return {"xp": 0, "level": 1, "claimed_free_levels": [], "claimed_paid_levels": []}


async def _effective_xp_config(db, metric_name: str) -> tuple[int, bool, int]:
    """(weight, enabled, daily_cap) для метрики с учётом БД-оверрайдов.
    Строка в bp_xp_weight_overrides перекрывает дефолты constants (единый
    источник → паритет бот↔сайт). daily_cap: 0 = без лимита."""
    async with db.execute(
        "SELECT weight, enabled, daily_cap FROM bp_xp_weight_overrides WHERE metric = ?",
        (metric_name,),
    ) as c:
        row = await c.fetchone()
    if row is not None:
        return int(row["weight"] or 0), bool(row["enabled"]), int(row["daily_cap"] or 0)
    return (
        int(BATTLE_PASS_XP_WEIGHTS.get(metric_name, 0)),
        True,
        int(BATTLE_PASS_XP_DAILY_CAPS.get(metric_name, 0)),
    )


async def add_xp(db, user_id: int, metric_name: str, delta: float = 1.0) -> None:
    """Начислить XP Боевого пропуска за игровое действие. No commit — caller handles commit.

    B (конструктор): вес и вкл/выкл берутся из bp_xp_weight_overrides (БД > constants).
    A (анти-абуз): дневной потолок XP на это действие усекает прибавку до остатка.
    """
    weight, enabled, daily_cap = await _effective_xp_config(db, metric_name)
    if not enabled or weight <= 0:
        return
    season = get_active_season()
    if not season:
        return
    if await is_bp_frozen(db):   # ШАГ3: заморозка — XP не начисляется
        return

    xp_gain = int(weight * delta)
    if xp_gain <= 0:
        return

    # C7. Бонус выходного дня (+X% XP), если включён в конструкторе.
    boost_on, boost_pct = await weekend_boost_active(db)
    if boost_on:
        xp_gain = int(xp_gain * (100 + boost_pct) / 100)

    # A. Дневной потолок XP на это действие (0 = без лимита). Усекаем прибавку до
    # остатка лимита; счётчик инкрементим в той же транзакции, что и начисление XP.
    if daily_cap > 0:
        today = date.today().isoformat()
        async with db.execute(
            "SELECT xp_today FROM bp_xp_daily WHERE user_id = ? AND day = ? AND metric = ?",
            (user_id, today, metric_name),
        ) as c:
            drow = await c.fetchone()
        used = int(drow["xp_today"]) if drow else 0
        remaining = daily_cap - used
        if remaining <= 0:
            return
        if xp_gain > remaining:
            xp_gain = remaining
        await db.execute(
            "INSERT INTO bp_xp_daily (user_id, day, metric, xp_today) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (user_id, day, metric) "
            "DO UPDATE SET xp_today = bp_xp_daily.xp_today + ?",
            (user_id, today, metric_name, xp_gain, xp_gain),
        )

    await _get_or_create_progress(db, user_id, season["id"])
    await db.execute(
        "UPDATE battle_pass_progress SET xp = xp + ? WHERE user_id = ? AND season_id = ?",
        (xp_gain, user_id, season["id"]),
    )

    async with db.execute(
        "SELECT xp FROM battle_pass_progress WHERE user_id = ? AND season_id = ?",
        (user_id, season["id"]),
    ) as c:
        row = await c.fetchone()
    new_xp = row["xp"] if row else xp_gain
    new_level = min(BATTLE_PASS_MAX_LEVEL, 1 + new_xp // BATTLE_PASS_XP_PER_LEVEL)

    await db.execute(
        "UPDATE battle_pass_progress SET level = ? "
        "WHERE user_id = ? AND season_id = ? AND level < ?",
        (new_level, user_id, season["id"], new_level),
    )


async def get_progress(db, user_id: int) -> dict | None:
    """None если сейчас нет активного сезона. Иначе — снимок прогресса игрока."""
    season = get_active_season()
    if not season:
        return None

    progress = await _get_or_create_progress(db, user_id, season["id"])
    xp = progress["xp"]
    level = progress["level"]
    xp_in_level = xp % BATTLE_PASS_XP_PER_LEVEL
    xp_to_next = 0 if level >= BATTLE_PASS_MAX_LEVEL else BATTLE_PASS_XP_PER_LEVEL - xp_in_level

    return {
        "season": season,
        "level": level,
        "xp": xp,
        "xp_in_level": xp_in_level,
        "xp_to_next": xp_to_next,
        "max_level": BATTLE_PASS_MAX_LEVEL,
        "claimed_free": list(progress["claimed_free_levels"] or []),
        "claimed_paid": list(progress["claimed_paid_levels"] or []),
        "paid_track_open": await is_vip_active(db, user_id),
    }


def level_status(level: int, track: str, progress: dict) -> str:
    """claimed | available | locked_vip | locked_level — для рендера списка наград."""
    claimed = progress["claimed_free"] if track == "free" else progress["claimed_paid"]
    if level in claimed:
        return "claimed"
    if level > progress["level"]:
        return "locked_level"
    if track == "paid" and not progress["paid_track_open"]:
        return "locked_vip"
    return "available"


def _opt_to_reward(opt: dict) -> dict:
    """Один вариант reward_options → стандартный reward-dict."""
    return {
        "mora": opt.get("mora", 0) or 0,
        "diamonds": opt.get("diamonds", 0) or 0,
        "items": tuple(tuple(x) for x in (opt.get("items") or [])),
        "theme": opt.get("theme"),
    }


def reward_short_text(reward: dict) -> str:
    """Краткое текстовое описание награды (для кнопок выбора)."""
    parts = []
    if reward.get("mora"):
        parts.append(f"+{int(reward['mora'])}🪙")
    if reward.get("diamonds"):
        parts.append(f"+{int(reward['diamonds'])}💎")
    for item_id, qty in reward.get("items", ()):
        name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
        parts.append(f"+{qty} {name}")
    if reward.get("theme"):
        parts.append(f"🎨 {THEMES.get(reward['theme'], {}).get('name', reward['theme'])}")
    return ", ".join(parts) if parts else "—"


async def get_level_options(db, level: int, track: str) -> list[dict] | None:
    """Если уровень/трек — это ВЫБОР между ≥2 наградами (reward_options в DB),
    вернуть список reward-dict'ов (с полем 'text' для кнопки). Иначе None."""
    import json as _json
    season = get_active_season()
    if not season:
        return None
    async with db.execute(
        "SELECT reward_options FROM battle_pass_reward_overrides "
        "WHERE season_id = ? AND level = ? AND track = ?",
        (season["id"], level, track),
    ) as _c:
        _row = await _c.fetchone()
    if not _row or not _row[0]:
        return None
    try:
        opts = _json.loads(_row[0])
    except Exception:
        return None
    if not isinstance(opts, list) or len(opts) < 2:
        return None
    result = []
    for opt in opts:
        rw = _opt_to_reward(opt)
        rw["text"] = reward_short_text(rw)
        result.append(rw)
    return result


async def claim_reward(db, user_id: int, level: int, track: str,
                       choice_index: int | None = None) -> tuple[bool, str]:
    """Забрать награду уровня `level` из трека `track` ('free' | 'paid').
    Если уровень — выбор между вариантами (reward_options), нужен choice_index."""
    if track not in ("free", "paid"):
        return False, "❌ Некорректный трек."
    if level < 1 or level > BATTLE_PASS_MAX_LEVEL:
        return False, "❌ Некорректный уровень."

    season = get_active_season()
    if not season:
        return False, "Сейчас нет активного сезона Боевого пропуска."
    if await is_bp_frozen(db):   # ШАГ3: заморозка — награды не выдаются
        return False, "❄️ Сезон временно заморожен — награды недоступны."

    progress = await _get_or_create_progress(db, user_id, season["id"])
    if level > progress["level"]:
        return False, f"🔒 Уровень {level} ещё не достигнут (сейчас {progress['level']})."

    claimed_col = "claimed_free_levels" if track == "free" else "claimed_paid_levels"
    claimed = progress[claimed_col] or []
    if level in claimed:
        return False, "Эта награда уже получена."

    if track == "paid" and not await is_vip_active(db, user_id):
        return False, "🔒 Нужен активный VIP, чтобы забрать награду платного трека."

    # DB-переопределения перекрывают registry (управляются из dev-консоли)
    import json as _json
    db_reward = None
    db_options = None
    async with db.execute(
        "SELECT mora, diamonds, items, theme_id, reward_options FROM battle_pass_reward_overrides "
        "WHERE season_id = ? AND level = ? AND track = ?",
        (season["id"], level, track),
    ) as _c:
        _row = await _c.fetchone()
    if _row:
        raw_opts = _row[4]
        if raw_opts:
            try:
                parsed = _json.loads(raw_opts)
                if isinstance(parsed, list) and len(parsed) >= 2:
                    db_options = parsed
            except Exception:
                db_options = None
        if db_options is None:
            db_reward = {
                "mora": _row[0] or 0,
                "diamonds": _row[1] or 0,
                "items": tuple(tuple(x) for x in _json.loads(_row[2] or "[]")),
                "theme": _row[3],
            }

    # Уровень-выбор: нужен валидный choice_index
    if db_options is not None:
        if choice_index is None or not (0 <= choice_index < len(db_options)):
            return False, "Выберите один из вариантов награды."
        reward = _opt_to_reward(db_options[choice_index])
    else:
        reward = db_reward if db_reward is not None else BATTLE_PASS_REWARDS.get(level, {}).get(track, {})
    mora = reward.get("mora", 0)
    diamonds = reward.get("diamonds", 0)
    items = reward.get("items", ())
    theme_id = reward.get("theme")  # сезонная тема (топ платного трека)

    # ATOMIC GUARD: lock the progress row and re-check `claimed` inside the
    # transaction before granting anything. Without this, two concurrent
    # claims (double-click / bot+site race) can both pass the check above
    # and both grant the reward, appending the level twice.
    async with db.connection.transaction():
        async with db.execute(
            f"SELECT {claimed_col} FROM battle_pass_progress "
            "WHERE user_id = ? AND season_id = ? FOR UPDATE",
            (user_id, season["id"]),
        ) as c:
            row = await c.fetchone()
        locked_claimed = (row[0] if row else None) or []
        if level in locked_claimed:
            return False, "Эта награда уже получена."

        if mora or diamonds:
            await add_balance(
                db, user_id, mora=mora, diamonds=diamonds, commit=False,
                source="battle_pass_reward", note=f"{season['id']}_lv{level}_{track}",
            )

        for item_id, qty in items:
            await db.execute(
                "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
                (user_id, item_id, qty, qty),
            )

        if theme_id:
            await grant_theme(db, user_id, theme_id)

        await db.execute(
            f"UPDATE battle_pass_progress SET {claimed_col} = array_append({claimed_col}, ?) "
            "WHERE user_id = ? AND season_id = ?",
            (level, user_id, season["id"]),
        )

    parts = []
    if mora:
        parts.append(f"+{int(mora)} 🪙")
    if diamonds:
        parts.append(f"+{int(diamonds)} 💎")
    for item_id, qty in items:
        name = ITEMS_REGISTRY.get(item_id, {}).get("name", item_id)
        parts.append(f"+{qty} {name}")
    if theme_id:
        theme_name = THEMES.get(theme_id, {}).get("name", theme_id)
        parts.append(f"🎨 Тема «{theme_name}»")
    reward_text = ", ".join(parts) if parts else "—"

    track_label = "Бесплатный" if track == "free" else "VIP"
    return True, f"🎫 Уровень {level} ({track_label}): получено {reward_text}"


# ── XP-конструктор (дев-консоль) ─────────────────────────────────────────────

async def all_xp_actions(db) -> list[dict]:
    """Полный список действий, дающих XP БП: дефолты constants ⊕ БД-оверрайды.
    Для дев-конструктора и игровой справки «за что сколько XP»."""
    overrides: dict[str, dict] = {}
    async with db.execute(
        "SELECT metric, weight, enabled, daily_cap, label FROM bp_xp_weight_overrides"
    ) as c:
        for row in await c.fetchall():
            overrides[row["metric"]] = dict(row)
    metrics = set(BATTLE_PASS_XP_WEIGHTS) | set(BATTLE_PASS_XP_DAILY_CAPS) | set(overrides)
    out = []
    for m in sorted(metrics):
        ov = overrides.get(m)
        if ov is not None:
            weight = int(ov["weight"] or 0)
            enabled = bool(ov["enabled"])
            cap = int(ov["daily_cap"] or 0)
            label = ov["label"]
        else:
            weight = int(BATTLE_PASS_XP_WEIGHTS.get(m, 0))
            enabled = True
            cap = int(BATTLE_PASS_XP_DAILY_CAPS.get(m, 0))
            label = None
        out.append({
            "metric": m,
            "weight": weight,
            "enabled": enabled,
            "daily_cap": cap,
            "label": label or BATTLE_PASS_XP_ACTION_LABELS.get(m, m),
            "is_override": ov is not None,
            "is_custom": m not in BATTLE_PASS_XP_WEIGHTS and m not in BATTLE_PASS_XP_DAILY_CAPS,
        })
    return out


async def set_xp_weight_override(db, metric: str, weight: int, enabled: bool = True,
                                 daily_cap: int = 0, label: str | None = None) -> None:
    """Создать/обновить оверрайд веса XP для действия (дев-конструктор). Commits."""
    await db.execute(
        "INSERT INTO bp_xp_weight_overrides (metric, weight, enabled, daily_cap, label, updated_at) "
        "VALUES (?, ?, ?, ?, ?, NOW()) "
        "ON CONFLICT (metric) DO UPDATE SET "
        "weight = ?, enabled = ?, daily_cap = ?, label = ?, updated_at = NOW()",
        (metric, int(weight), bool(enabled), int(daily_cap), label,
         int(weight), bool(enabled), int(daily_cap), label),
    )
    await db.commit()


async def reset_xp_weight_override(db, metric: str) -> None:
    """Удалить оверрайд → действие вернётся к дефолтам constants. Commits."""
    await db.execute("DELETE FROM bp_xp_weight_overrides WHERE metric = ?", (metric,))
    await db.commit()


# ── C5: 💎-открытие следующего уровня ────────────────────────────────────────

async def _level_diamond_value(db, season_id: str, level: int) -> int:
    """Максимум алмазов, которые игрок получит на этом уровне (free+paid; выбор → max
    варианта). Для анти-цикл-floor цены 💎-открытия."""
    import json as _json
    total = 0
    for track in ("free", "paid"):
        async with db.execute(
            "SELECT diamonds, reward_options FROM battle_pass_reward_overrides "
            "WHERE season_id = ? AND level = ? AND track = ?",
            (season_id, level, track),
        ) as c:
            row = await c.fetchone()
        if row:
            raw_opts = row[1]
            if raw_opts:
                try:
                    opts = _json.loads(raw_opts)
                    if isinstance(opts, list) and opts:
                        total += max(int(o.get("diamonds", 0) or 0) for o in opts)
                        continue
                except Exception:
                    pass
            total += int(row[0] or 0)
        else:
            total += int(BATTLE_PASS_REWARDS.get(level, {}).get(track, {}).get("diamonds", 0) or 0)
    return total


def next_level_price(target_level: int, diamond_value: int) -> int:
    """Цена открыть уровень target_level за 💎: BASE + STEP*(L-2), не ниже алмазов+MARGIN."""
    base = BATTLE_PASS_BUY_LEVEL_BASE + BATTLE_PASS_BUY_LEVEL_STEP * (target_level - 2)
    return max(base, diamond_value + BATTLE_PASS_BUY_LEVEL_MARGIN)


async def buy_next_level(db, user_id: int) -> tuple[bool, str, dict]:
    """C5: открыть следующий уровень БП за 💎 (только +1, последовательно).
    Атомарно: проверяем баланс, списываем 💎, поднимаем уровень. Награду игрок
    забирает отдельно. Транзакция коммитит сама."""
    season = get_active_season()
    if not season:
        return False, "Сейчас нет активного сезона.", {}
    progress = await _get_or_create_progress(db, user_id, season["id"])
    cur = int(progress["level"])
    if cur >= BATTLE_PASS_MAX_LEVEL:
        return False, "Достигнут максимальный уровень.", {}
    target = cur + 1
    dval = await _level_diamond_value(db, season["id"], target)
    price = next_level_price(target, dval)
    new_xp = (target - 1) * BATTLE_PASS_XP_PER_LEVEL

    async with db.connection.transaction():
        async with db.execute(
            "SELECT COALESCE(user_balance_diamonds, 0) FROM users "
            "WHERE user_tg_id = ? FOR UPDATE",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        bal = float(row[0]) if row else 0.0
        if bal < price:
            return False, f"Недостаточно 💎: нужно {price}, есть {int(bal)}.", {"price": price}

        # Лочим прогресс и перечитываем уровень — защита от гонки (не перескочить >1).
        async with db.execute(
            "SELECT level FROM battle_pass_progress "
            "WHERE user_id = ? AND season_id = ? FOR UPDATE",
            (user_id, season["id"]),
        ) as c:
            prow = await c.fetchone()
        locked = int(prow[0]) if prow else cur
        if locked != cur:
            return False, "Уровень изменился, попробуйте ещё раз.", {}
        if locked >= BATTLE_PASS_MAX_LEVEL:
            return False, "Достигнут максимальный уровень.", {}

        await add_balance(db, user_id, diamonds=-price, commit=False,
                          source="battle_pass_buy_level",
                          note=f"{season['id']}_open_lv{target}")
        await db.execute(
            "UPDATE battle_pass_progress SET xp = GREATEST(xp, ?), level = ? "
            "WHERE user_id = ? AND season_id = ?",
            (new_xp, target, user_id, season["id"]),
        )

    return True, f"🎫 Открыт уровень {target} за {price}💎! Не забудь забрать награду.", {
        "level": target, "price": price,
    }


# ── C7: бонус XP выходного дня (флаг конструктора) ───────────────────────────

def _is_weekend() -> bool:
    return date.today().weekday() >= 5   # 5=Sb, 6=Vs (по времени сервера)


async def get_weekend_boost_pct(db) -> int:
    """% бонуса XP по выходным (0 = выключен)."""
    async with db.execute(
        "SELECT value FROM bp_settings WHERE key = 'weekend_boost_pct'"
    ) as c:
        row = await c.fetchone()
    if row and row[0]:
        try:
            return max(0, min(500, int(row[0])))
        except (TypeError, ValueError):
            return 0
    return 0


async def set_weekend_boost_pct(db, pct: int) -> None:
    """Установить % бонуса выходного дня (0 = выключить). Commits."""
    pct = max(0, min(500, int(pct)))
    await db.execute(
        "INSERT INTO bp_settings (key, value) VALUES ('weekend_boost_pct', ?) "
        "ON CONFLICT (key) DO UPDATE SET value = ?",
        (str(pct), str(pct)),
    )
    await db.commit()


async def weekend_boost_active(db) -> tuple[bool, int]:
    """(активен_ли_сейчас, процент). Активен = выходной И процент > 0."""
    pct = await get_weekend_boost_pct(db)
    return (_is_weekend() and pct > 0), pct


async def is_bp_frozen(db) -> bool:
    """БП заморожен админом (ШАГ3): не начисляем XP и не выдаём награды всем юзерам.
    Глобальный флаг в bp_settings — применяется к активному сезону (XP/награды всегда
    идут в активный сезон, поэтому глобальный = заморозка текущего БП)."""
    async with db.execute("SELECT value FROM bp_settings WHERE key = 'frozen'") as c:
        row = await c.fetchone()
    return bool(row and str(row[0]) == "1")


async def set_bp_frozen(db, frozen: bool) -> None:
    """Заморозить/разморозить БП. Commits."""
    val = "1" if frozen else "0"
    await db.execute(
        "INSERT INTO bp_settings (key, value) VALUES ('frozen', ?) "
        "ON CONFLICT (key) DO UPDATE SET value = ?",
        (val, val),
    )
    await db.commit()
