"""
services/battle_pass.py
B5: Боевой пропуск — сезонная прогрессия с бесплатным и платным (VIP) треками.
No bot.*/FastAPI.* imports.
"""
from datetime import date

from core.constants import (
    BATTLE_PASS_MAX_LEVEL,
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


async def add_xp(db, user_id: int, metric_name: str, delta: float = 1.0) -> None:
    """Начислить XP Боевого пропуска за игровое действие. No commit — caller handles commit."""
    weight = BATTLE_PASS_XP_WEIGHTS.get(metric_name)
    if not weight:
        return
    season = get_active_season()
    if not season:
        return

    xp_gain = int(weight * delta)
    if xp_gain <= 0:
        return

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
