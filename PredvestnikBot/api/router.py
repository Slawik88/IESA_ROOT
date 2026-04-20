"""
api/router.py — единый FastAPI APIRouter для всех /api/* эндпоинтов бота.

Вместо 28 строк @app.get/post в web_app.py — один include_router:
    from api.router import router as api_router
    app.include_router(api_router)

Инфраструктурные маршруты (webhook, health, SPA, static) остаются в web_app.py.
"""
from __future__ import annotations

import logging
import time as _time
import urllib.request as _ur
import hashlib as _hl

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response as _FaResponse

_log = logging.getLogger("api.router")

router = APIRouter()

# ─── Кэш аватарок ─────────────────────────────────────────────────────────────
_avatar_cache: dict[str, tuple[bytes, str, float]] = {}
_AVATAR_TTL = 86_400  # 24 h

# ─── Константы Solo Boss ──────────────────────────────────────────────────────
_BOSS_DAILY_LIMIT = 3
_BOSS_COUPON_PRICE_CRYSTALS = 7


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  User Data / Profile
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/user_data")
@router.get("/api/user_data/")
async def api_user_data(user_id: int = 0):
    if not user_id:
        return JSONResponse({"error": "missing user_id"}, status_code=400)

    from database.db import get_user
    from database.postgres import connect as postgres_connect

    user = await get_user(user_id)
    if not user:
        return JSONResponse({"error": "user not found"}, status_code=404)

    async with postgres_connect() as db:
        async with db.execute(
            """SELECT um.chat_id, COALESCE(u.balance, 0) AS balance,
                      COALESCE(u.total_earned, 0) AS total_earned,
                      um.vip, um.vip_expires_at, um.top_frame, um.mora_public
               FROM user_mora um
               JOIN users u ON u.user_id = um.user_id
               WHERE um.user_id=? ORDER BY um.balance DESC LIMIT 1""",
            (user_id,),
        ) as c:
            mora = await c.fetchone()
        async with db.execute(
            "SELECT xp FROM user_stats WHERE user_id=? ORDER BY xp DESC LIMIT 1",
            (user_id,),
        ) as c:
            xp_row = await c.fetchone()
        chat_id = mora["chat_id"] if mora else 0
        async with db.execute(
            "SELECT b.bond_key, b.amount, COALESCE(p.price,100) as price "
            "FROM user_bonds b "
            "LEFT JOIN bond_prices p ON p.bond_key=b.bond_key AND p.chat_id=b.chat_id "
            "WHERE b.user_id=? AND b.chat_id=?",
            (user_id, chat_id),
        ) as c:
            bond_rows = await c.fetchall()
        async with db.execute(
            "SELECT item_name, rarity, equipped FROM gacha_inventory "
            "WHERE user_id=? AND chat_id=? LIMIT 20",
            (user_id, chat_id),
        ) as c:
            inv_rows = await c.fetchall()
        async with db.execute(
            "SELECT pet_type, name, COALESCE(fatigue,0) FROM pets_global WHERE user_id=?",
            (user_id,),
        ) as c:
            pet_row = await c.fetchone()
        async with db.execute(
            "SELECT partner_id, married_at FROM marriages_global WHERE user_id=?",
            (user_id,),
        ) as c:
            marriage_row = await c.fetchone()

    balance = mora["balance"] if mora else 0
    vip = bool(mora and mora["vip"])
    active_frame = mora["top_frame"] if mora else None
    xp = xp_row["xp"] if xp_row else 0

    bonds_data = [
        {"name": r["bond_key"], "amount": r["amount"], "value": r["amount"] * r["price"]}
        for r in bond_rows
    ]
    items = [
        f"{'★' if r['equipped'] else ''}{r['item_name']} ({r['rarity']})"
        for r in inv_rows
    ]
    pet_info = None
    if pet_row:
        emoji = {"cat": "🐱", "dog": "🐶"}.get(pet_row[0], "🐾")
        pet_info = {"type": pet_row[0], "name": pet_row[1] or "безымянный",
                    "emoji": emoji, "fatigue": pet_row[2]}

    partner_info = None
    if marriage_row:
        from database.db import get_user as _gu
        partner_user = await _gu(marriage_row["partner_id"])
        _mat = marriage_row["married_at"]
        married_iso = _mat.isoformat() if hasattr(_mat, 'isoformat') else str(_mat or "")
        partner_info = {
            "partner_id": marriage_row["partner_id"],
            "partner_name": partner_user["full_name"] if partner_user else "?",
            "married_at": married_iso,
        }

    payload = {
        "name": user["full_name"],
        "balance": balance,
        "xp": xp,
        "vip": vip,
        "active_frame": active_frame or "default",
        "bonds": bonds_data,
        "items": items,
        "pet": pet_info,
        "partner": partner_info,
    }
    return JSONResponse(payload, headers={"Access-Control-Allow-Origin": "*"})


@router.get("/api/profile/{user_id}")
async def api_profile(user_id: int):
    return await api_user_data(user_id=user_id)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Season Pass
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/season/data")
async def season_data_route(user_id: int = 0):
    if not user_id:
        return JSONResponse({"error": "user_id required"}, status_code=400)
    from database.db import get_active_season, get_season_progress, get_season_rewards
    try:
        season = await get_active_season()
        if not season:
            return JSONResponse({"error": "No active season"}, status_code=404)
        season_id = season["id"]
        progress = await get_season_progress(user_id, season_id)
        rewards = await get_season_rewards(season_id)
        return JSONResponse({
            "season": {
                "id": season["id"],
                "name": season["name"],
                "start_date": season["start_date"].isoformat() if season["start_date"] else None,
                "end_date": season["end_date"].isoformat() if season["end_date"] else None,
                "active": season["active"],
            },
            "progress": progress,
            "rewards": rewards,
        })
    except Exception as exc:
        _log.exception("season_data error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/api/season/claim")
async def season_claim_route(request: Request):
    from database.db import claim_season_reward
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        season_id = int(data.get("season_id", 0))
        level = int(data.get("level", 0))
        is_premium = bool(data.get("is_premium", False))
        if not all([user_id, season_id, level]):
            return JSONResponse({"error": "user_id, season_id, and level required"}, status_code=400)
        result = await claim_season_reward(user_id, season_id, level, is_premium)
        if result["ok"]:
            return JSONResponse(result)
        return JSONResponse(result, status_code=400)
    except Exception as exc:
        _log.exception("season_claim error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/api/season/premium")
async def season_premium_route(request: Request):
    from database.db import buy_season_premium
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        season_id = int(data.get("season_id", 0))
        if not all([user_id, season_id]):
            return JSONResponse({"error": "user_id and season_id required"}, status_code=400)
        success = await buy_season_premium(user_id, season_id)
        if success:
            return JSONResponse({"ok": True})
        return JSONResponse({"error": "Purchase failed"}, status_code=400)
    except Exception as exc:
        _log.exception("season_premium error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Achievements
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/achievements")
async def achievements_route(user_id: int = 0, chat_id: int = 0, mode: str = ""):
    from services.achievements import get_user_achievements, get_leaderboard, get_global_leaderboard
    try:
        if mode == "global_leaderboard":
            data = await get_global_leaderboard(limit=100)
            return JSONResponse({"leaderboard": data})
        if mode == "leaderboard":
            if not chat_id:
                return JSONResponse({"error": "chat_id required"}, status_code=400)
            data = await get_leaderboard(chat_id)
            return JSONResponse({"leaderboard": data})
        if not user_id or not chat_id:
            return JSONResponse({"error": "user_id and chat_id required"}, status_code=400)
        data = await get_user_achievements(user_id, chat_id)
        return JSONResponse(data)
    except Exception as exc:
        _log.exception("achievements error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/achievements/badges")
async def badges_route(user_id: int = 0, chat_id: int = 0):
    from services.achievements import get_user_badge_keys
    if not user_id or not chat_id:
        return JSONResponse({"error": "user_id and chat_id required"}, status_code=400)
    try:
        keys = await get_user_badge_keys(user_id, chat_id)
        return JSONResponse({"badges": keys})
    except Exception as exc:
        _log.exception("badges error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Telemetry & Error Logging
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/api/telemetry")
async def api_telemetry(request: Request):
    try:
        data = await request.json()
        events = data.get("events", [])
        if not isinstance(events, list) or len(events) > 200:
            return JSONResponse({"ok": False, "error": "invalid"}, status_code=400)
        from database.db import upsert_telemetry_batch
        await upsert_telemetry_batch(events)
        return JSONResponse({"ok": True})
    except Exception as exc:
        _log.warning("api_telemetry error: %s", exc)
        return JSONResponse({"ok": False}, status_code=500)


@router.post("/api/frontend_error_log")
async def api_frontend_error_log(request: Request):
    try:
        data = await request.json()
        error_msg = str(data.get("error", ""))[:500]
        stack = str(data.get("stack", ""))[:2000]
        _log.error("FRONTEND ERROR: %s | STACK: %s", error_msg, stack)
        return JSONResponse({"ok": True})
    except Exception as exc:
        _log.warning("api_frontend_error_log: %s", exc)
        return JSONResponse({"ok": False}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Avatar Proxy — кэшируем аватарки Telegram на 24 часа
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/proxy/avatar")
async def proxy_avatar(url: str = ""):
    if not url:
        return _FaResponse(status_code=400)
    import urllib.parse as _up
    parsed = _up.urlparse(url)
    allowed_hosts = (
        "t.me", "telegram.org",
        "cdn4.telegram-cdn.org", "cdn1.telegram-cdn.org",
        "cdn2.telegram-cdn.org", "cdn3.telegram-cdn.org",
        "cdn5.telegram-cdn.org", "api.telegram.org",
    )
    if parsed.scheme not in ("http", "https") or not any(parsed.netloc.endswith(h) for h in allowed_hosts):
        return _FaResponse(status_code=403)

    cache_key = _hl.md5(url.encode()).hexdigest()
    now = _time.time()
    if cache_key in _avatar_cache:
        data, ctype, expires = _avatar_cache[cache_key]
        if now < expires:
            return _FaResponse(content=data, media_type=ctype,
                               headers={"Cache-Control": "public, max-age=86400"})
    try:
        req = _ur.Request(url, headers={"User-Agent": "TelegramBot"})
        with _ur.urlopen(req, timeout=8) as resp:
            ctype = resp.headers.get_content_type() or "image/jpeg"
            data = resp.read(2 * 1024 * 1024)
        _avatar_cache[cache_key] = (data, ctype, now + _AVATAR_TTL)
        if len(_avatar_cache) > 5000:
            oldest = sorted(_avatar_cache, key=lambda k: _avatar_cache[k][2])[:500]
            for k in oldest:
                del _avatar_cache[k]
        return _FaResponse(content=data, media_type=ctype,
                           headers={"Cache-Control": "public, max-age=86400"})
    except Exception as exc:
        _log.debug("proxy_avatar fetch error: %s", exc)
        return _FaResponse(status_code=502)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Leaderboard
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/leaderboard")
async def leaderboard_route(request: Request, chat_id: int = 0, type: str = "xp"):
    """Leaderboard по типу: xp | messages | boss | mora"""
    try:
        from api.user import get_leaderboard
        uid_raw = request.headers.get("X-User-Id", "0")
        try:
            uid = int(uid_raw)
        except ValueError:
            uid = 0
        result = await get_leaderboard(chat_id=chat_id, lb_type=type, uid=uid)
        return JSONResponse(result)
    except Exception as exc:
        _log.exception("leaderboard_route error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Solo Boss
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/solo_boss/status")
async def solo_boss_status(user_id: int = 0, chat_id: int = 0):
    if not user_id or not chat_id:
        return JSONResponse({"error": "user_id and chat_id required"}, status_code=400)
    try:
        from database.db import (
            get_solo_boss_session, get_solo_boss_progress, get_boss_coupons,
        )
        from database.postgres import connect as postgres_connect
        from datetime import datetime, timezone, timedelta

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        session = await get_solo_boss_session(user_id, chat_id)
        progress = await get_solo_boss_progress(user_id, chat_id)
        coupons, next_regen = await get_boss_coupons(user_id)

        async with postgres_connect() as db:
            async with db.execute(
                "SELECT COUNT(*) AS c FROM solo_boss_sessions "
                "WHERE user_id=? AND chat_id=? AND session_date=?",
                (user_id, chat_id, today),
            ) as cur:
                cnt_row = await cur.fetchone()
        daily_used = int(cnt_row["c"] or 0) if cnt_row else 0

        now_utc = datetime.now(timezone.utc)
        tomorrow = (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        reset_in_sec = int((tomorrow - now_utc).total_seconds())
        hrs, rem = divmod(reset_in_sec, 3600)
        mins = rem // 60

        next_level = (progress["max_level"] + 1) if progress else 1
        return JSONResponse({
            "session": session,
            "progress": progress,
            "next_level": next_level,
            "daily_limit": _BOSS_DAILY_LIMIT,
            "daily_used": daily_used,
            "daily_remaining": max(0, _BOSS_DAILY_LIMIT - daily_used),
            "reset_at": tomorrow.isoformat(),
            "reset_in_seconds": reset_in_sec,
            "reset_in_text": f"{hrs}ч {mins}м",
            "boss_coupons": coupons,
            "next_coupon_regen_at": next_regen,
        })
    except Exception as exc:
        _log.exception("solo_boss_status error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/api/solo_boss/start")
async def solo_boss_start(request: Request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        chat_id = int(data.get("chat_id", 0))
        boss_level = int(data.get("boss_level", 0))
        if not user_id or not chat_id:
            return JSONResponse({"ok": False, "error": "user_id and chat_id required"}, status_code=400)

        from database.db import (
            get_solo_boss_session, get_solo_boss_progress,
            create_solo_boss_session, get_boss_coupons, use_boss_coupon,
        )
        from database.postgres import connect as postgres_connect
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        existing = await get_solo_boss_session(user_id, chat_id)
        if existing and not existing.get("is_completed"):
            return JSONResponse({"ok": True, "session": existing})

        async with postgres_connect() as db:
            async with db.execute(
                "SELECT COUNT(*) AS c FROM solo_boss_sessions "
                "WHERE user_id=? AND chat_id=? AND session_date=?",
                (user_id, chat_id, today),
            ) as cur:
                cnt_row = await cur.fetchone()
        daily_used = int(cnt_row["c"] or 0) if cnt_row else 0
        used_coupon = False
        coupons, next_coupon_regen_at = await get_boss_coupons(user_id)
        if daily_used >= _BOSS_DAILY_LIMIT:
            used_coupon = await use_boss_coupon(user_id)
            if not used_coupon:
                return JSONResponse({
                    "ok": False,
                    "error": "Дневной лимит исчерпан. Купи купон (7💎) или подожди завтра.",
                    "boss_coupons": coupons,
                    "next_coupon_regen_at": next_coupon_regen_at,
                })
            coupons = max(0, coupons - 1)

        progress = await get_solo_boss_progress(user_id, chat_id)
        if not boss_level:
            boss_level = (progress["max_level"] + 1) if progress else 1
        session = await create_solo_boss_session(user_id, chat_id, boss_level)
        return JSONResponse({
            "ok": True,
            "session": session,
            "used_coupon": used_coupon,
            "boss_coupons": coupons,
            "next_coupon_regen_at": next_coupon_regen_at,
        })
    except Exception as exc:
        _log.exception("solo_boss_start error: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.post("/api/solo_boss/attack")
async def solo_boss_attack(request: Request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        chat_id = int(data.get("chat_id", 0))
        if not user_id or not chat_id:
            return JSONResponse({"ok": False, "error": "user_id and chat_id required"}, status_code=400)

        from database.db import get_solo_boss_session, apply_solo_boss_damage, get_player_combat_stats
        import random as _rnd

        session = await get_solo_boss_session(user_id, chat_id)
        if not session:
            return JSONResponse({"ok": False, "error": "Нет активного боя. Начни сначала."})
        if session.get("is_completed"):
            return JSONResponse({"ok": False, "error": "Бой уже завершён."})

        combat = await get_player_combat_stats(user_id, chat_id)
        base_damage = _rnd.randint(120, 220) + combat["atk"]
        result = await apply_solo_boss_damage(user_id, session, base_damage, crit_rate=combat["crit_rate"])

        rewards = None
        if result["boss_defeated"]:
            boss_level = session["boss_level"]
            mora_reward = 300 + boss_level * 200
            xp_reward   = 50  + boss_level * 30
            is_repeat = bool(session.get("is_repeat"))
            if not is_repeat:
                from database.db import add_mora, add_user_xp
                await add_mora(user_id, chat_id, mora_reward, source="solo_boss_win")
                try:
                    await add_user_xp(user_id, chat_id, xp_reward)
                except Exception:
                    pass
            rewards = {
                "mora": mora_reward if not is_repeat else 0,
                "xp": xp_reward if not is_repeat else 0,
            }

        return JSONResponse({"ok": True, **result, "rewards": rewards})
    except Exception as exc:
        _log.exception("solo_boss_attack error: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.post("/api/solo_boss/forfeit")
async def solo_boss_forfeit(request: Request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        chat_id = int(data.get("chat_id", 0))
        if not user_id or not chat_id:
            return JSONResponse({"ok": False, "error": "user_id and chat_id required"}, status_code=400)

        from database.postgres import connect as postgres_connect
        from database.db import get_solo_boss_session

        session = await get_solo_boss_session(user_id, chat_id)
        if not session:
            return JSONResponse({"ok": True, "forfeited": False})

        async with postgres_connect() as db:
            await db.execute(
                "UPDATE solo_boss_sessions SET is_completed=1 WHERE id=?",
                (session["id"],),
            )
            await db.commit()
        return JSONResponse({"ok": True, "forfeited": True})
    except Exception as exc:
        _log.exception("solo_boss_forfeit error: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Boss Coupon Purchase
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/api/boss/buy_coupon")
async def boss_buy_coupon(request: Request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id", 0))
        if not user_id:
            return JSONResponse({"ok": False, "error": "user_id required"}, status_code=400)

        from database.db import get_boss_coupons, add_boss_coupons, BOSS_COUPONS_MAX
        from database.postgres import connect as postgres_connect

        coupons, _ = await get_boss_coupons(user_id)
        if coupons >= BOSS_COUPONS_MAX:
            return JSONResponse({"ok": False, "error": "Купоны уже заполнены (макс. 5)."})

        async with postgres_connect() as db:
            async with db.execute(
                "SELECT COALESCE(crystals, 0) AS c FROM users WHERE user_id=?",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
            if not row or int(row["c"]) < _BOSS_COUPON_PRICE_CRYSTALS:
                return JSONResponse({"ok": False, "error": f"Недостаточно 💎 (нужно {_BOSS_COUPON_PRICE_CRYSTALS})"})
            await db.execute(
                "UPDATE users SET crystals = crystals - ? WHERE user_id=? AND crystals >= ?",
                (_BOSS_COUPON_PRICE_CRYSTALS, user_id, _BOSS_COUPON_PRICE_CRYSTALS),
            )
            await db.commit()

        new_count = await add_boss_coupons(user_id, 1)
        return JSONResponse({"ok": True, "coupons": new_count})
    except Exception as exc:
        _log.exception("boss_buy_coupon error: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Inventory
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/inventory")
async def api_inventory(request: Request, chat_id: int):
    """Get user's inventory with enhanced metadata (categories, emojis)."""
    try:
        init_data_header = request.headers.get("X-Telegram-Init-Data", "")
        if not init_data_header:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        from utils.tg_auth import validate_init_data
        user_info = validate_init_data(init_data_header)
        if not user_info:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        user_id = int(user_info["id"])
        from database.postgres import connect as postgres_connect
        from shared_prices import get_item_display_info, FRAMES_CATALOG

        async with postgres_connect() as db:
            async with db.execute(
                "SELECT id, item_name, rarity, equipped, atk, def_val, hp, crit_rate, "
                "enhancement_level, stack_count, is_cosmetic, sell_price, "
                "can_auction, days_until_auctionable, hours_until_auctionable "
                "FROM gacha_inventory WHERE user_id=? AND chat_id=? ORDER BY id",
                (user_id, chat_id),
            ) as cur:
                gacha_rows = await cur.fetchall()

            async with db.execute(
                "SELECT item_key FROM shop_items "
                "WHERE user_id=? AND item_type='frame' AND (chat_id=? OR chat_id=0) "
                "GROUP BY item_key",
                (user_id, chat_id),
            ) as cur:
                owned_frame_rows = await cur.fetchall()

            async with db.execute(
                "SELECT top_frame FROM user_mora WHERE user_id=? AND chat_id=?",
                (user_id, chat_id),
            ) as cur:
                mora_row = await cur.fetchone()

            async with db.execute(
                "SELECT item_key FROM shop_items "
                "WHERE user_id=? AND item_type='theme' AND (chat_id=? OR chat_id=0) "
                "GROUP BY item_key",
                (user_id, chat_id),
            ) as cur:
                owned_theme_rows = await cur.fetchall()

            async with db.execute(
                "SELECT hp, atk, def_val, crit_rate FROM users WHERE user_id=?",
                (user_id,),
            ) as cur:
                user_stats = await cur.fetchone()

        active_frame = mora_row["top_frame"] if mora_row else "default"

        items = []
        for row in gacha_rows:
            item_key = row["item_name"]
            display_info = get_item_display_info(item_key)
            items.append({
                "id": row["id"],
                "key": item_key,
                "name": item_key,
                "rarity": row["rarity"],
                "equipped": bool(row["equipped"]),
                "atk": row.get("atk", 0),
                "def_val": row.get("def_val", 0),
                "hp": row.get("hp", 0),
                "crit_rate": row.get("crit_rate", 0),
                "slot": None,
                "enhancement_level": row.get("enhancement_level", 0),
                "stack_count": row.get("stack_count", 1),
                "is_cosmetic": bool(row.get("is_cosmetic", False)),
                "desc": display_info["desc"],
                "sell_price": row.get("sell_price", 0),
                "can_auction": bool(row.get("can_auction", False)),
                "days_until_auctionable": row.get("days_until_auctionable"),
                "hours_until_auctionable": row.get("hours_until_auctionable"),
                "category": display_info["category"],
                "emoji": display_info["emoji"],
                "readable_category": display_info["readable_category"],
            })

        owned_frame_keys = {r["item_key"] for r in owned_frame_rows}
        _frame_id_counter = 900000
        for frame_key in owned_frame_keys:
            if frame_key == "default":
                continue
            frame_info = FRAMES_CATALOG.get(frame_key, {})
            _frame_id_counter += 1
            items.append({
                "id": _frame_id_counter,
                "key": f"frame_{frame_key}",
                "name": frame_info.get("name", frame_key) if isinstance(frame_info, dict) else frame_key,
                "rarity": "rare",
                "equipped": frame_key == active_frame,
                "atk": 0, "def_val": 0, "hp": 0, "crit_rate": 0,
                "slot": "frame",
                "enhancement_level": 0,
                "stack_count": 1,
                "is_cosmetic": True,
                "desc": "Рамка профиля — свечение вокруг аватарки",
                "sell_price": 0,
                "can_auction": False,
                "days_until_auctionable": None,
                "hours_until_auctionable": None,
                "category": "cosmetic",
                "emoji": frame_info.get("emoji", "🖼️") if isinstance(frame_info, dict) else "🖼️",
                "readable_category": "Рамка профиля",
            })

        _theme_id_counter = 800000
        for row in owned_theme_rows:
            _theme_id_counter += 1
            items.append({
                "id": _theme_id_counter,
                "key": f"theme_{row['item_key']}",
                "name": row["item_key"],
                "rarity": "legendary",
                "equipped": False,
                "atk": 0, "def_val": 0, "hp": 0, "crit_rate": 0,
                "slot": "flair",
                "enhancement_level": 0,
                "stack_count": 1,
                "is_cosmetic": True,
                "desc": "Премиум тема оформления профиля",
                "sell_price": 0,
                "can_auction": False,
                "days_until_auctionable": None,
                "hours_until_auctionable": None,
                "category": "cosmetic",
                "emoji": "🎨",
                "readable_category": "Тема профиля",
            })

        rpg = {
            "hp": user_stats.get("hp", 100) if user_stats else 100,
            "atk": user_stats.get("atk", 10) if user_stats else 10,
            "def": user_stats.get("def_val", 5) if user_stats else 5,
            "crit": user_stats.get("crit_rate", 5) if user_stats else 5,
        }

        return JSONResponse({"items": items, "rpg": rpg, "pity": 0})

    except Exception as exc:
        _log.exception("api_inventory error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/api/equip")
async def api_equip(request: Request):
    """Equip/unequip an inventory item."""
    try:
        init_data_header = request.headers.get("X-Telegram-Init-Data", "")
        if not init_data_header:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        from utils.tg_auth import validate_init_data
        user_info = validate_init_data(init_data_header)
        if not user_info:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        data = await request.json()
        user_id = int(user_info["id"])
        item_id = int(data.get("item_id", 0))
        slot = data.get("slot", "")
        chat_id = int(data.get("chat_id", 0))

        if not item_id or not chat_id:
            return JSONResponse({"ok": False, "error": "item_id and chat_id required"}, status_code=400)

        from database.postgres import connect as postgres_connect

        async with postgres_connect() as db:
            async with db.execute(
                "UPDATE gacha_inventory SET equipped = NOT equipped "
                "WHERE id=? AND user_id=? AND chat_id=? RETURNING equipped, item_name",
                (item_id, user_id, chat_id),
            ) as cur:
                updated_row = await cur.fetchone()
            await db.commit()

        if not updated_row:
            return JSONResponse({"ok": False, "error": "Item not found"}, status_code=404)

        return JSONResponse({"ok": True, "equipped": updated_row["item_name"], "slot": slot})

    except Exception as exc:
        _log.exception("api_equip error: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Shards
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/shards")
async def api_shards(request: Request, chat_id: int):
    """Get user's shard inventory and catalog with enhanced metadata."""
    try:
        init_data_header = request.headers.get("X-Telegram-Init-Data", "")
        if not init_data_header:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        from utils.tg_auth import validate_init_data
        user_info = validate_init_data(init_data_header)
        if not user_info:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        user_id = int(user_info["id"])
        from database.postgres import connect as postgres_connect
        from shared_prices import SHARD_CATALOG, get_item_display_info

        async with postgres_connect() as db:
            async with db.execute(
                "SELECT shard_key, amount FROM user_shards "
                "WHERE user_id=? AND chat_id=? AND amount > 0",
                (user_id, chat_id),
            ) as cur:
                shard_rows = await cur.fetchall()

        stash = {row["shard_key"]: row["amount"] for row in shard_rows}

        catalog = {}
        for shard_key, shard_info in SHARD_CATALOG.items():
            owned = stash.get(shard_key, 0)
            craft_into = shard_info.get("craft_into")
            craft_frame = shard_info.get("craft_frame")

            readable_target = None
            if craft_into:
                item_info = get_item_display_info(craft_into)
                readable_target = f"{item_info['emoji']} {item_info['readable_category']}"
            elif craft_frame:
                readable_target = f"🖼️ Рамка «{craft_frame}»"

            catalog[shard_key] = {
                "name": shard_info.get("name", shard_key),
                "emoji": shard_info.get("emoji", "🔷"),
                "craft_into": craft_into,
                "craft_frame": craft_frame,
                "craft_amount": shard_info.get("craft_amount", 10),
                "owned": owned,
                "readable_target": readable_target,
            }

        return JSONResponse({"stash": stash, "catalog": catalog})

    except Exception as exc:
        _log.exception("api_shards error: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/api/shards/craft")
async def api_shards_craft(request: Request):
    """Craft an item from shards."""
    try:
        init_data_header = request.headers.get("X-Telegram-Init-Data", "")
        if not init_data_header:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        from utils.tg_auth import validate_init_data
        user_info = validate_init_data(init_data_header)
        if not user_info:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        data = await request.json()
        user_id = int(user_info["id"])
        chat_id = int(data.get("chat_id", 0))
        shard_key = data.get("shard_key", "")

        if not chat_id or not shard_key:
            return JSONResponse({"ok": False, "error": "chat_id and shard_key required"}, status_code=400)

        from shared_prices import SHARD_CATALOG
        from database.postgres import connect as postgres_connect

        if shard_key not in SHARD_CATALOG:
            return JSONResponse({"ok": False, "error": "Unknown shard type"}, status_code=400)

        shard_info = SHARD_CATALOG[shard_key]
        required_amount = shard_info.get("craft_amount", 10)

        async with postgres_connect() as db:
            async with db.execute(
                "SELECT amount FROM user_shards WHERE user_id=? AND chat_id=? AND shard_key=?",
                (user_id, chat_id, shard_key),
            ) as cur:
                shard_row = await cur.fetchone()

            owned = shard_row["amount"] if shard_row else 0
            if owned < required_amount:
                return JSONResponse({
                    "ok": False,
                    "error": f"Недостаточно осколков ({owned}/{required_amount})",
                })

            await db.execute(
                "UPDATE user_shards SET amount = amount - ? "
                "WHERE user_id=? AND chat_id=? AND shard_key=?",
                (required_amount, user_id, chat_id, shard_key),
            )

            craft_into = shard_info.get("craft_into")
            craft_frame = shard_info.get("craft_frame")

            if craft_into:
                await db.execute(
                    "INSERT INTO gacha_inventory "
                    "(user_id, chat_id, item_name, rarity, equipped, "
                    "atk, def_val, hp, crit_rate, enhancement_level, stack_count, is_cosmetic, sell_price) "
                    "VALUES (?, ?, ?, 'rare', 0, 0, 0, 0, 0, 0, 1, 0, 100)",
                    (user_id, chat_id, craft_into),
                )
                result_msg = f"Создан предмет: {craft_into}"
            elif craft_frame:
                await db.execute(
                    "INSERT OR REPLACE INTO user_frames (user_id, frame_key, acquired_at) "
                    "VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (user_id, craft_frame),
                )
                result_msg = f"Получена рамка: {craft_frame}"
            else:
                result_msg = "Что-то создано!"

            await db.commit()

        return JSONResponse({"ok": True, "message": result_msg})

    except Exception as exc:
        _log.exception("api_shards_craft error: %s", exc)
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Dev Analytics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/api/dev/analytics")
async def api_dev_analytics(request: Request, period: str = "week"):
    init_data_header = request.headers.get("X-Telegram-Init-Data", "")
    if not init_data_header:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from utils.tg_auth import validate_init_data
        user_info = validate_init_data(init_data_header)
        if not user_info:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        from utils.ranks import is_developer
        if not is_developer(user_info.get("id", 0)):
            return JSONResponse({"error": "forbidden"}, status_code=403)
    except Exception:
        pass  # allow in dev/no-auth setups
    if period not in ("day", "week", "month"):
        period = "week"
    from database.db import get_telemetry_analytics
    result = await get_telemetry_analytics(period)
    return JSONResponse(result)
