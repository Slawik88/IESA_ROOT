"""FastAPI/routers/battle_pass.py — статус и получение наград Боевого пропуска (Implementation Block 5.7)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from FastAPI.deps import get_db, require_tg_user
from core.constants import BATTLE_PASS_XP_PER_LEVEL
from core.registry import BATTLE_PASS_REWARDS, ITEMS_REGISTRY
from core.cosmetics import COSMETICS
from core.themes import THEMES
from services.battle_pass import (
    claim_reward, get_active_season, get_progress, level_status, refresh_seasons_cache,
    _opt_to_reward, reward_short_text, buy_next_level, is_bp_frozen,
)

router = APIRouter(prefix="/battle_pass", tags=["battle_pass"])


def _resolve_items(items: tuple) -> list[dict]:
    """Косметика (cos_{slot}_{имя}) живёт в отдельном реестре (core/cosmetics.py),
    не в ITEMS_REGISTRY — раньше такие ID в наградах БП падали в fallback и
    показывались игроку голым айдишником (cos_name_glow_silver). Резолвим отдельно,
    плюс отдаём css/rarity/slot — фронт превращает это в кликабельный превью-чип."""
    out = []
    for item_id, qty in items:
        cos = COSMETICS.get(item_id) if item_id.startswith("cos_") else None
        if cos:
            out.append({
                "item_id": item_id, "name": cos["name"], "qty": qty,
                "is_cosmetic": True, "css": cos.get("css", ""),
                "rarity": cos["rarity"], "slot": cos["slot"],
            })
        else:
            out.append({
                "item_id": item_id,
                "name": ITEMS_REGISTRY.get(item_id, {}).get("name", item_id),
                "qty": qty,
            })
    return out


def _reward_payload(reward: dict, level: int, track: str, progress: dict) -> dict:
    payload = {
        "mora": reward.get("mora", 0),
        "diamonds": reward.get("diamonds", 0),
        "items": _resolve_items(reward.get("items", ())),
        "status": level_status(level, track, progress),
    }
    theme_id = reward.get("theme")
    if theme_id:
        payload["theme"] = THEMES.get(theme_id, {}).get("name", theme_id)
    return payload


@router.get("/status")
async def battle_pass_status(db=Depends(get_db), user=Depends(require_tg_user)):
    # Подхватываем сезоны, созданные через Консоль разработчика (БД-кэш процесса)
    await refresh_seasons_cache(db)
    season = get_active_season()
    if not season:
        return {
            "active": False,
            "retired": True,
            "message": "Старый Боевой пропуск закрыт. Новый сезон появится только после утверждения новой экономики.",
        }

    progress = await get_progress(db, user["id"])
    if not progress:
        return {
            "active": False,
            "retired": True,
            "message": "Старый Боевой пропуск закрыт; у аккаунта нет сохранённого прогресса этого сезона.",
        }

    # DB-переопределения наград активного сезона (правятся в dev-консоли).
    # РАНЬШЕ здесь читались только reward_options (уровни-выбор) — обычные
    # переопределения mora/diamonds/items/theme_id игнорировались, и витрина
    # всегда показывала статичные значения из registry, хотя claim_reward()
    # честно выдавал уже новую (БД) награду — на сайте выглядело так, будто
    # правки из консоли не применяются вообще.
    import json as _json
    choice_levels: dict[tuple, list] = {}
    base_overrides: dict[tuple, dict] = {}
    async with db.execute(
        "SELECT level, track, mora, diamonds, items, theme_id, reward_options "
        "FROM battle_pass_reward_overrides WHERE season_id = ?",
        (season["id"],),
    ) as _c:
        for _r in await _c.fetchall():
            key = (_r[0], _r[1])
            raw_opts = _r[6]
            opts = None
            if raw_opts:
                try:
                    parsed = _json.loads(raw_opts)
                    if isinstance(parsed, list) and len(parsed) >= 2:
                        opts = parsed
                except Exception:
                    opts = None
            if opts is not None:
                choice_levels[key] = [
                    {**_reward_payload(_opt_to_reward(o), _r[0], _r[1], progress),
                     "text": reward_short_text(_opt_to_reward(o))}
                    for o in opts
                ]
            else:
                base_overrides[key] = {
                    "mora": _r[2] or 0, "diamonds": _r[3] or 0,
                    "items": tuple(tuple(x) for x in _json.loads(_r[4] or "[]")),
                    "theme": _r[5],
                }

    rewards = []
    for lv in range(1, progress["max_level"] + 1):
        r = BATTLE_PASS_REWARDS.get(lv, {})
        free_r = base_overrides.get((lv, "free")) or r.get("free", {})
        paid_r = base_overrides.get((lv, "paid")) or r.get("paid", {})
        free_p = _reward_payload(free_r, lv, "free", progress)
        paid_p = _reward_payload(paid_r, lv, "paid", progress)
        if (lv, "free") in choice_levels:
            free_p["options"] = choice_levels[(lv, "free")]
        if (lv, "paid") in choice_levels:
            paid_p["options"] = choice_levels[(lv, "paid")]
        rewards.append({"level": lv, "free": free_p, "paid": paid_p})

    xp_guide = []
    _frozen = await is_bp_frozen(db)   # ШАГ3: заморозка сезона

    return {
        "active": True,
        "retired": True,
        "retired_message": "Прогресс и покупка уровней закрыты. Уже заработанные награды можно забрать.",
        "frozen": _frozen,
        "season_label": season["label"],
        "season_starts": season.get("starts_at"),
        "season_ends": season.get("ends_at"),
        "buy_next": None,
        "weekend_boost": {"active": False, "pct": 0},
        "level": progress["level"],
        "xp": progress["xp"],
        "xp_in_level": progress["xp_in_level"],
        "xp_to_next": progress["xp_to_next"],
        "xp_per_level": BATTLE_PASS_XP_PER_LEVEL,
        "max_level": progress["max_level"],
        "paid_track_open": progress["paid_track_open"],
        "rewards": rewards,
        "xp_guide": xp_guide,
    }


class ClaimRequest(BaseModel):
    level: int
    track: str
    choice_index: int | None = None


@router.post("/claim")
async def battle_pass_claim(body: ClaimRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, message = await claim_reward(db, user["id"], body.level, body.track, body.choice_index)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    await db.commit()
    return {"ok": True, "message": message}


@router.post("/claim-all")
async def battle_pass_claim_all(db=Depends(get_db), user=Depends(require_tg_user)):
    """C6: забрать все доступные награды одним запросом. Уровни-выбор (reward_options)
    пропускаются — их игрок забирает вручную (нужен выбор варианта)."""
    await refresh_seasons_cache(db)
    season = get_active_season()
    if not season:
        raise HTTPException(status_code=400, detail="Сейчас нет активного сезона.")
    progress = await get_progress(db, user["id"])
    if not progress:
        raise HTTPException(status_code=400, detail="Сейчас нет активного сезона.")

    import json as _json
    choice_set: set[tuple] = set()
    async with db.execute(
        "SELECT level, track, reward_options FROM battle_pass_reward_overrides "
        "WHERE season_id = ? AND reward_options IS NOT NULL",
        (season["id"],),
    ) as _c:
        for _r in await _c.fetchall():
            try:
                _o = _json.loads(_r[2])
            except Exception:
                continue
            if isinstance(_o, list) and len(_o) >= 2:
                choice_set.add((_r[0], _r[1]))

    tracks = ["free"] + (["paid"] if progress["paid_track_open"] else [])
    claimed = 0
    pending_choices = 0
    for lv in range(1, progress["level"] + 1):
        for track in tracks:
            already = progress["claimed_free"] if track == "free" else progress["claimed_paid"]
            if lv in already:
                continue
            if (lv, track) in choice_set:
                pending_choices += 1
                continue
            ok, _msg = await claim_reward(db, user["id"], lv, track)
            if ok:
                claimed += 1
    await db.commit()
    return {"ok": True, "claimed": claimed, "pending_choices": pending_choices}


@router.post("/buy-level")
async def battle_pass_buy_level(db=Depends(get_db), user=Depends(require_tg_user)):
    raise HTTPException(410, "Покупка уровней закрыта: Алмазы не покупают прогресс.")
