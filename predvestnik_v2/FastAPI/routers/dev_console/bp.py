"""dev_console/bp.py — Боевой пропуск: сезоны, награды, XP-конструктор, импорт/копирование."""
import re
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from FastAPI.deps import get_db, require_tg_user
from core.constants import BATTLE_PASS_MAX_LEVEL, BATTLE_PASS_XP_PER_LEVEL
from core.registry import BATTLE_PASS_SEASONS, BATTLE_PASS_REWARDS, ITEMS_REGISTRY
from core.cosmetics import COSMETICS
from infrastructure.repositories import admin_log as _admin_log
from services.battle_pass import (
    all_xp_actions,
    get_active_season,
    get_weekend_boost_pct,
    is_bp_frozen,
    refresh_seasons_cache,
    reset_xp_weight_override,
    set_bp_frozen,
    set_weekend_boost_pct,
    set_xp_weight_override,
)
from services.battle_pass_rewards import normalize_configured_reward_items
from ._common import require_console_perm

router = APIRouter()


_SEASON_ID_RE = re.compile(r"^[a-z0-9_]{1,32}$")


# ── 6. Battle Pass: XP и сезоны ──────────────────────────────────────────────────
class BpXpRequest(BaseModel):
    user_id: int
    xp: int


@router.post("/bp/xp")
async def dev_bp_xp(body: BpXpRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "bp_manage")
    await refresh_seasons_cache(db)
    season = get_active_season()
    if not season:
        raise HTTPException(400, "Нет активного сезона.")
    if body.xp == 0:
        raise HTTPException(400, "xp не может быть 0.")

    # battle_pass_progress.user_id REFERENCES users(user_tg_id) — гарантируем строку,
    # иначе FK-violation на юзере, который ещё не писал боту (как в dev_balance).
    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (body.user_id,))
    await db.execute(
        "INSERT INTO battle_pass_progress (user_id, season_id) VALUES (?, ?) "
        "ON CONFLICT (user_id, season_id) DO NOTHING",
        (body.user_id, season["id"]),
    )
    await db.execute(
        "UPDATE battle_pass_progress SET xp = GREATEST(0, xp + ?) "
        "WHERE user_id = ? AND season_id = ?",
        (body.xp, body.user_id, season["id"]),
    )
    async with db.execute(
        "SELECT xp FROM battle_pass_progress WHERE user_id = ? AND season_id = ?",
        (body.user_id, season["id"]),
    ) as c:
        row = await c.fetchone()
    new_xp = row["xp"] if row else 0
    new_level = min(BATTLE_PASS_MAX_LEVEL, 1 + new_xp // BATTLE_PASS_XP_PER_LEVEL)
    await db.execute(
        "UPDATE battle_pass_progress SET level = ? WHERE user_id = ? AND season_id = ?",
        (new_level, body.user_id, season["id"]),
    )
    await db.commit()
    return {"ok": True, "xp": new_xp, "level": new_level}


# ── XP-конструктор: вес/вкл-выкл/дневной потолок за каждое действие ──────────────
_METRIC_RE = re.compile(r"^[a-z0-9_]{1,40}$")


class BpXpWeightRequest(BaseModel):
    metric: str
    weight: int
    enabled: bool = True
    daily_cap: int = 0
    label: Optional[str] = None


class BpMetricRequest(BaseModel):
    metric: str


@router.get("/bp/xp-actions")
async def dev_bp_xp_actions(db=Depends(get_db), user=Depends(require_tg_user)):
    """Список всех действий, дающих XP БП (дефолты ⊕ БД-оверрайды) — для конструктора."""
    await require_console_perm(db, user, "bp_manage")
    actions = await all_xp_actions(db)
    return {
        "actions": actions,
        "xp_per_level": BATTLE_PASS_XP_PER_LEVEL,
        "max_level": BATTLE_PASS_MAX_LEVEL,
        "weekend_boost_pct": await get_weekend_boost_pct(db),
    }


@router.post("/bp/xp-weight")
async def dev_bp_xp_weight_set(body: BpXpWeightRequest, db=Depends(get_db),
                               user=Depends(require_tg_user)):
    """Создать/обновить оверрайд: вес XP, вкл/выкл, дневной потолок, ярлык."""
    await require_console_perm(db, user, "bp_manage")
    metric = (body.metric or "").strip().lower()
    if not _METRIC_RE.match(metric):
        raise HTTPException(400, "metric: только a-z, 0-9, _ (до 40 символов).")
    if not (0 <= body.weight <= 100000):
        raise HTTPException(400, "weight вне диапазона 0..100000.")
    if not (0 <= body.daily_cap <= 1000000):
        raise HTTPException(400, "daily_cap вне диапазона 0..1000000.")
    label = (body.label or "").strip()[:64] or None
    await set_xp_weight_override(db, metric, body.weight, body.enabled, body.daily_cap, label)
    return {"ok": True}


@router.post("/bp/xp-weight/reset")
async def dev_bp_xp_weight_reset(body: BpMetricRequest, db=Depends(get_db),
                                 user=Depends(require_tg_user)):
    """Удалить оверрайд → действие вернётся к дефолтам constants."""
    await require_console_perm(db, user, "bp_manage")
    metric = (body.metric or "").strip().lower()
    if not _METRIC_RE.match(metric):
        raise HTTPException(400, "metric некорректен.")
    await reset_xp_weight_override(db, metric)
    return {"ok": True}


class BpWeekendRequest(BaseModel):
    pct: int


@router.post("/bp/weekend-boost")
async def dev_bp_weekend_boost(body: BpWeekendRequest, db=Depends(get_db),
                               user=Depends(require_tg_user)):
    """C7: % бонуса XP по выходным (0 = выключить)."""
    await require_console_perm(db, user, "bp_manage")
    if not (0 <= body.pct <= 500):
        raise HTTPException(400, "pct вне диапазона 0..500.")
    await set_weekend_boost_pct(db, body.pct)
    return {"ok": True, "pct": body.pct}


@router.get("/bp/seasons")
async def dev_bp_seasons(db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "bp_manage")
    async with db.execute(
        "SELECT id, label, starts_at, ends_at, COALESCE(max_level,50) AS max_level "
        "FROM battle_pass_seasons ORDER BY starts_at"
    ) as c:
        db_rows = {r["id"]: dict(r) for r in await c.fetchall()}

    await refresh_seasons_cache(db)
    active = get_active_season()
    active_id = active["id"] if active else None

    out = []
    for sid, s in BATTLE_PASS_SEASONS.items():
        if sid in db_rows:
            continue  # перекрыт БД-версией
        out.append({"id": sid, "label": s["label"], "starts_at": s["starts_at"],
                    "ends_at": s["ends_at"], "max_level": s.get("max_level", 50),
                    "source": "registry", "active": sid == active_id})
    for sid, s in db_rows.items():
        out.append({**s, "source": "db", "active": sid == active_id})
    out.sort(key=lambda x: x["starts_at"])
    return {"seasons": out, "frozen": await is_bp_frozen(db)}


class BpFreezeRequest(BaseModel):
    frozen: bool


@router.post("/bp/freeze")
async def dev_bp_freeze(body: BpFreezeRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Заморозить/разморозить БП (ШАГ3): при заморозке middleware/сервис не начисляют
    XP и не выдают награды; у игроков на странице БП висит плашка ❄️."""
    await require_console_perm(db, user, "bp_manage")
    await set_bp_frozen(db, body.frozen)
    action = "bp_freeze" if body.frozen else "bp_unfreeze"
    await _admin_log.add_sys(db, user["id"], action, "❄️ БП заморожен" if body.frozen else "🟢 БП разморожен")
    await db.commit()
    return {"ok": True, "frozen": body.frozen}


class SeasonRequest(BaseModel):
    id: str
    label: str
    starts_at: str   # YYYY-MM-DD
    ends_at: str
    max_level: int = 50


@router.post("/bp/seasons")
async def dev_bp_season_upsert(body: SeasonRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "bp_manage")
    if not _SEASON_ID_RE.match(body.id):
        raise HTTPException(400, "id: латиница/цифры/_, до 32 символов.")
    try:
        s = datetime.strptime(body.starts_at, "%Y-%m-%d")
        e = datetime.strptime(body.ends_at, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Даты — в формате YYYY-MM-DD.")
    if e <= s:
        raise HTTPException(400, "ends_at должен быть позже starts_at.")
    if not body.label.strip():
        raise HTTPException(400, "label пустой.")
    if not 1 <= body.max_level <= BATTLE_PASS_MAX_LEVEL:
        raise HTTPException(400, f"max_level: 1..{BATTLE_PASS_MAX_LEVEL}.")

    await db.execute(
        "INSERT INTO battle_pass_seasons (id, label, starts_at, ends_at, max_level) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (id) DO UPDATE SET label = EXCLUDED.label, "
        "starts_at = EXCLUDED.starts_at, ends_at = EXCLUDED.ends_at, "
        "max_level = EXCLUDED.max_level",
        (body.id, body.label.strip(), body.starts_at, body.ends_at, body.max_level),
    )
    await _admin_log.add_sys(db, user["id"], "season_upsert",
                             f"Сезон «{body.id}» ({body.label.strip()}) {body.starts_at}–{body.ends_at}")
    await db.commit()
    await refresh_seasons_cache(db)
    return {"ok": True}


@router.delete("/bp/seasons/{season_id}")
async def dev_bp_season_delete(season_id: str, db=Depends(get_db), user=Depends(require_tg_user)):
    await require_console_perm(db, user, "bp_manage")
    async with db.execute(
        "DELETE FROM battle_pass_seasons WHERE id = ? RETURNING id", (season_id,)
    ) as c:
        row = await c.fetchone()
    if row:
        # КАСКАД (ШАГ3-багфикс): у battle_pass_reward_overrides/progress нет FK на
        # сезон → удаляли только строку сезона, оставляя «сирот». Чистим вручную.
        await db.execute("DELETE FROM battle_pass_reward_overrides WHERE season_id = ?", (season_id,))
        await db.execute("DELETE FROM battle_pass_progress WHERE season_id = ?", (season_id,))
        await _admin_log.add_sys(db, user["id"], "season_delete",
                                 f"Сезон «{season_id}» удалён из БД (каскад: оверрайды+прогресс)")
    await db.commit()
    await refresh_seasons_cache(db)
    if not row:
        raise HTTPException(404, "Сезон не найден в БД (registry-сезоны удалить нельзя — только перекрыть).")
    # all_seasons() = {**registry, **db_cache} — если season_id ТАКЖЕ зашит в
    # core.registry.BATTLE_PASS_SEASONS, удаление DB-override не убирает сезон
    # из списка: он «откатывается» к версии из кода (другие даты!). Раньше это
    # выглядело как «кнопка не работает» — теперь явно говорим, что произошло.
    reverted = season_id in BATTLE_PASS_SEASONS
    return {"ok": True, "reverted_to_registry": reverted}


@router.get("/bp/cosmetics-catalog")
async def dev_bp_cosmetics_catalog(db=Depends(get_db), user=Depends(require_tg_user)):
    """id→{name,css,rarity,slot} для всей косметики — таблица наград хранит/показывает
    сырые item_id (cos_name_glow_silver и т.п.), дев не мог понять, что это за
    предмет, не заглядывая в код. Фронт резолвит имя и рисует кликабельный превью."""
    await require_console_perm(db, user, "bp_manage")
    return {cid: {"name": c["name"], "css": c.get("css", ""),
                  "rarity": c["rarity"], "slot": c["slot"]} for cid, c in COSMETICS.items()}


@router.get("/bp/rewards")
async def dev_bp_rewards(season_id: str | None = None, db=Depends(get_db), user=Depends(require_tg_user)):
    """Все награды БП ВЫБРАННОГО сезона (registry + DB-переопределения). DB побеждает.
    season_id необязателен: если не задан/неизвестен — берётся активный сезон. Так
    таблица и операции записи (save/bulk/import) всегда работают с одним сезоном."""
    import json as _json
    await require_console_perm(db, user, "bp_manage")
    await refresh_seasons_cache(db)
    from services.battle_pass import all_seasons as _all_seasons
    if not season_id or season_id not in _all_seasons():
        season = get_active_season()
        season_id = season["id"] if season else None

    # DB overrides for active season
    db_overrides: dict[tuple, dict] = {}
    if season_id:
        async with db.execute(
            "SELECT level, track, mora, diamonds, items, theme_id, reward_options "
            "FROM battle_pass_reward_overrides WHERE season_id = ?",
            (season_id,),
        ) as c:
            for row in await c.fetchall():
                entry = {
                    "mora": row[2] or 0,
                    "diamonds": row[3] or 0,
                    "items": _json.loads(row[4] or "[]"),
                    "theme": row[5],
                }
                if row[6]:
                    try:
                        opts = _json.loads(row[6])
                        if isinstance(opts, list) and len(opts) >= 2:
                            entry["options"] = opts
                    except Exception:
                        pass
                db_overrides[(row[0], row[1])] = entry

    rewards = []
    for lv in range(1, BATTLE_PASS_MAX_LEVEL + 1):
        reg = BATTLE_PASS_REWARDS.get(lv, {})
        for track in ("free", "paid"):
            key = (lv, track)
            if key in db_overrides:
                r = {**db_overrides[key], "source": "db"}
            else:
                r = {**reg.get(track, {}), "source": "registry"}
                if "items" in r:
                    r["items"] = list(list(x) for x in r["items"])
            rewards.append({"level": lv, "track": track, **r})

    return {"season_id": season_id, "rewards": rewards, "items_registry": list(ITEMS_REGISTRY.keys())}


class BpRewardRequest(BaseModel):
    season_id: str
    level: int
    track: str
    mora: int = 0
    diamonds: int = 0
    items: list = []   # [[item_id, qty], ...]
    theme_id: str | None = None
    # Если задан массив из ≥2 вариантов — уровень становится ВЫБОРОМ игрока.
    # Каждый вариант: {"mora":N,"diamonds":N,"items":[[id,qty]],"theme":id|null}
    reward_options: list | None = None


@router.post("/bp/rewards")
async def dev_bp_reward_set(body: BpRewardRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Установить награду уровня+трека. Перезаписывает registry. Если задан
    reward_options (≥2 варианта) — уровень становится выбором игрока."""
    import json as _json
    await require_console_perm(db, user, "bp_manage")
    if body.track not in ("free", "paid"):
        raise HTTPException(400, "track: 'free' или 'paid'.")
    if not 1 <= body.level <= BATTLE_PASS_MAX_LEVEL:
        raise HTTPException(400, f"level: 1..{BATTLE_PASS_MAX_LEVEL}.")

    opts_json = None
    try:
        clean_items = normalize_configured_reward_items(body.items)
        if body.reward_options:
            if not isinstance(body.reward_options, list) or len(body.reward_options) < 2:
                raise ValueError("reward_options: нужно ≥2 вариантов (или null).")
            clean_options = []
            for option in body.reward_options:
                if not isinstance(option, dict):
                    raise ValueError("каждый reward_options должен быть объектом")
                clean_options.append({
                    **option,
                    "items": normalize_configured_reward_items(option.get("items") or []),
                })
            opts_json = _json.dumps(clean_options, ensure_ascii=False)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    items_json = _json.dumps(clean_items, ensure_ascii=False)
    await db.execute(
        "INSERT INTO battle_pass_reward_overrides "
        "(season_id, level, track, mora, diamonds, items, theme_id, reward_options) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (season_id, level, track) DO UPDATE SET "
        "mora=EXCLUDED.mora, diamonds=EXCLUDED.diamonds, items=EXCLUDED.items, "
        "theme_id=EXCLUDED.theme_id, reward_options=EXCLUDED.reward_options",
        (body.season_id, body.level, body.track, body.mora, body.diamonds,
         items_json, body.theme_id, opts_json),
    )
    await db.commit()
    return {"ok": True}


class BpBulkRequest(BaseModel):
    season_id: str
    track: str
    level_from: int
    level_to: int
    mora_base: int = 0
    mora_step: int = 0      # +mora_step за каждый уровень выше level_from
    diamonds_base: int = 0
    diamonds_step: int = 0


@router.post("/bp/rewards/bulk")
async def dev_bp_reward_bulk(body: BpBulkRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Массовое автозаполнение диапазона уровней по формуле base+step×(lv-from)."""
    await require_console_perm(db, user, "bp_manage")
    if body.track not in ("free", "paid"):
        raise HTTPException(400, "track: 'free' или 'paid'.")
    lo, hi = body.level_from, body.level_to
    if not (1 <= lo <= hi <= BATTLE_PASS_MAX_LEVEL):
        raise HTTPException(400, f"Диапазон 1..{BATTLE_PASS_MAX_LEVEL}, from ≤ to.")
    count = 0
    for lv in range(lo, hi + 1):
        mora = body.mora_base + body.mora_step * (lv - lo)
        dia = body.diamonds_base + body.diamonds_step * (lv - lo)
        await db.execute(
            "INSERT INTO battle_pass_reward_overrides "
            "(season_id, level, track, mora, diamonds, items, theme_id, reward_options) "
            "VALUES (?, ?, ?, ?, ?, '[]', NULL, NULL) "
            "ON CONFLICT (season_id, level, track) DO UPDATE SET "
            "mora=EXCLUDED.mora, diamonds=EXCLUDED.diamonds, items='[]', "
            "theme_id=NULL, reward_options=NULL",
            (body.season_id, lv, body.track, mora, dia),
        )
        count += 1
    await db.commit()
    return {"ok": True, "updated": count}


class BpDistributeRequest(BaseModel):
    season_id: str
    track: str
    level_from: int
    level_to: int
    total_mora: int = 0
    total_diamonds: int = 0
    curve: str = "linear"   # flat | linear | progressive


@router.post("/bp/rewards/distribute")
async def dev_bp_reward_distribute(body: BpDistributeRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """«Раскидать» суммарный пул ресурсов по диапазону уровней автоматически.
    curve: flat (поровну) / linear (растёт линейно) / progressive (растёт круче).
    Сумма по уровням точно равна заданному пулу (остаток от округления → последнему уровню)."""
    await require_console_perm(db, user, "bp_manage")
    if body.track not in ("free", "paid"):
        raise HTTPException(400, "track: 'free' или 'paid'.")
    lo, hi = body.level_from, body.level_to
    if not (1 <= lo <= hi <= BATTLE_PASS_MAX_LEVEL):
        raise HTTPException(400, f"Диапазон 1..{BATTLE_PASS_MAX_LEVEL}, from ≤ to.")
    if body.total_mora < 0 or body.total_diamonds < 0:
        raise HTTPException(400, "Суммы не могут быть отрицательными.")
    n = hi - lo + 1
    if body.curve == "flat":
        weights = [1.0] * n
    elif body.curve == "progressive":
        weights = [(i + 1) ** 2 for i in range(n)]
    else:  # linear
        weights = [float(i + 1) for i in range(n)]
    wsum = sum(weights) or 1.0

    def _split(total: int) -> list[int]:
        if total <= 0:
            return [0] * n
        parts = [int(total * w / wsum) for w in weights]
        parts[-1] += total - sum(parts)   # остаток округления — последнему уровню
        return parts

    moras = _split(body.total_mora)
    dias = _split(body.total_diamonds)
    for idx, lv in enumerate(range(lo, hi + 1)):
        await db.execute(
            "INSERT INTO battle_pass_reward_overrides "
            "(season_id, level, track, mora, diamonds, items, theme_id, reward_options) "
            "VALUES (?, ?, ?, ?, ?, '[]', NULL, NULL) "
            "ON CONFLICT (season_id, level, track) DO UPDATE SET "
            "mora=EXCLUDED.mora, diamonds=EXCLUDED.diamonds, items='[]', "
            "theme_id=NULL, reward_options=NULL",
            (body.season_id, lv, body.track, moras[idx], dias[idx]),
        )
    await db.commit()
    return {"ok": True, "updated": n,
            "mora_per_level": moras, "diamonds_per_level": dias}


class BpImportRequest(BaseModel):
    season_id: str
    rewards: list   # [{level, track, mora?, diamonds?, items?:[[id,qty]], theme_id?, reward_options?}]


@router.post("/bp/rewards/import")
async def dev_bp_reward_import(body: BpImportRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Импорт наград БП пачкой из JSON (чтобы не вбивать каждый уровень вручную).
    Каждый элемент: {level, track:'free'|'paid', mora?, diamonds?, items?:[[id,qty]],
    theme_id?, reward_options?}. Невалидные предметы/уровни → в errors, остальные применяются."""
    import json as _json
    await require_console_perm(db, user, "bp_manage")
    if not isinstance(body.rewards, list) or not body.rewards:
        raise HTTPException(400, "rewards: непустой список наград.")
    count = 0
    errors: list[str] = []
    for idx, r in enumerate(body.rewards):
        try:
            lv = int(r["level"])
            track = r["track"]
            if track not in ("free", "paid"):
                raise ValueError("track должен быть free/paid")
            if not (1 <= lv <= BATTLE_PASS_MAX_LEVEL):
                raise ValueError(f"level вне 1..{BATTLE_PASS_MAX_LEVEL}")
            mora = int(r.get("mora", 0) or 0)
            dia = int(r.get("diamonds", 0) or 0)
            clean_items = normalize_configured_reward_items(r.get("items") or [])
            theme_id = r.get("theme_id") or None
            opts = r.get("reward_options")
            clean_options = None
            if opts:
                if not isinstance(opts, list) or len(opts) < 2:
                    raise ValueError("reward_options: нужно ≥2 вариантов")
                clean_options = []
                for option in opts:
                    if not isinstance(option, dict):
                        raise ValueError("каждый reward_options должен быть объектом")
                    clean_options.append({
                        **option,
                        "items": normalize_configured_reward_items(option.get("items") or []),
                    })
            opts_json = _json.dumps(clean_options, ensure_ascii=False) if clean_options else None
            await db.execute(
                "INSERT INTO battle_pass_reward_overrides "
                "(season_id, level, track, mora, diamonds, items, theme_id, reward_options) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (season_id, level, track) DO UPDATE SET "
                "mora=EXCLUDED.mora, diamonds=EXCLUDED.diamonds, items=EXCLUDED.items, "
                "theme_id=EXCLUDED.theme_id, reward_options=EXCLUDED.reward_options",
                (body.season_id, lv, track, mora, dia,
                 _json.dumps(clean_items, ensure_ascii=False), theme_id, opts_json),
            )
            count += 1
        except Exception as e:
            errors.append(f"#{idx}: {e}")
    await db.commit()
    return {"ok": True, "imported": count, "errors": errors}


class BpCopyRequest(BaseModel):
    from_season: str
    to_season: str


@router.post("/bp/rewards/copy")
async def dev_bp_reward_copy(body: BpCopyRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    """Скопировать ВСЕ переопределения наград из одного сезона в другой
    (стартовый шаблон для нового сезона). Существующие в to_season перезаписываются."""
    await require_console_perm(db, user, "bp_manage")
    if body.from_season == body.to_season:
        raise HTTPException(400, "Сезоны должны различаться.")
    async with db.execute(
        "SELECT level, track, mora, diamonds, items, theme_id, reward_options "
        "FROM battle_pass_reward_overrides WHERE season_id = ?",
        (body.from_season,),
    ) as c:
        rows = await c.fetchall()
    for r in rows:
        await db.execute(
            "INSERT INTO battle_pass_reward_overrides "
            "(season_id, level, track, mora, diamonds, items, theme_id, reward_options) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (season_id, level, track) DO UPDATE SET "
            "mora=EXCLUDED.mora, diamonds=EXCLUDED.diamonds, items=EXCLUDED.items, "
            "theme_id=EXCLUDED.theme_id, reward_options=EXCLUDED.reward_options",
            (body.to_season, r[0], r[1], r[2], r[3], r[4], r[5], r[6]),
        )
    await db.commit()
    return {"ok": True, "copied": len(rows)}


@router.get("/bp/season-summary")
async def dev_bp_season_summary(db=Depends(get_db), user=Depends(require_tg_user)):
    """Сводная «ценность сезона»: сумма мора/алмазов/предметов по трекам
    (registry + DB-переопределения, DB побеждает). Плюс список пустых уровней."""
    import json as _json
    await require_console_perm(db, user, "bp_manage")
    await refresh_seasons_cache(db)
    season = get_active_season()
    season_id = season["id"] if season else None

    overrides: dict[tuple, dict] = {}
    if season_id:
        async with db.execute(
            "SELECT level, track, mora, diamonds, items, theme_id, reward_options "
            "FROM battle_pass_reward_overrides WHERE season_id = ?",
            (season_id,),
        ) as c:
            for row in await c.fetchall():
                overrides[(row[0], row[1])] = row

    summary = {"free": {"mora": 0, "diamonds": 0, "items": 0},
               "paid": {"mora": 0, "diamonds": 0, "items": 0}}
    empty_levels = []
    for lv in range(1, BATTLE_PASS_MAX_LEVEL + 1):
        lv_has_any = False
        for track in ("free", "paid"):
            if (lv, track) in overrides:
                row = overrides[(lv, track)]
                if row[6]:  # reward_options — берём максимум по варианту как «потолок ценности»
                    try:
                        opts = _json.loads(row[6])
                        best = max(opts, key=lambda o: (o.get("mora", 0) + o.get("diamonds", 0) * 60))
                        summary[track]["mora"] += best.get("mora", 0)
                        summary[track]["diamonds"] += best.get("diamonds", 0)
                        summary[track]["items"] += len(best.get("items", []))
                        lv_has_any = True
                        continue
                    except Exception:
                        pass
                summary[track]["mora"] += row[2] or 0
                summary[track]["diamonds"] += row[3] or 0
                summary[track]["items"] += len(_json.loads(row[4] or "[]"))
                if (row[2] or row[3] or row[4] not in (None, "[]") or row[5]):
                    lv_has_any = True
            else:
                reg = BATTLE_PASS_REWARDS.get(lv, {}).get(track, {})
                summary[track]["mora"] += reg.get("mora", 0)
                summary[track]["diamonds"] += reg.get("diamonds", 0)
                summary[track]["items"] += len(reg.get("items", ()))
                if reg.get("mora") or reg.get("diamonds") or reg.get("items") or reg.get("theme"):
                    lv_has_any = True
        if not lv_has_any:
            empty_levels.append(lv)

    return {"season_id": season_id, "summary": summary, "empty_levels": empty_levels,
            "max_level": BATTLE_PASS_MAX_LEVEL}


@router.delete("/bp/rewards/{season_id}/{level}/{track}")
async def dev_bp_reward_reset(
    season_id: str, level: int, track: str,
    db=Depends(get_db), user=Depends(require_tg_user),
):
    """Сбросить награду к значению из registry (удалить DB-переопределение)."""
    await require_console_perm(db, user, "bp_manage")
    async with db.execute(
        "DELETE FROM battle_pass_reward_overrides WHERE season_id=? AND level=? AND track=? RETURNING level",
        (season_id, level, track),
    ) as c:
        row = await c.fetchone()
    await db.commit()
    if not row:
        raise HTTPException(404, "Переопределения не было.")
    return {"ok": True}
