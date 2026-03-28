"""
Mini App views — serve the Telegram Mini App from Django.

Routes:
  GET /app          → index.html (Mini App entry point)
  GET /api/user_data  → JSON user profile from bot DB (auth via X-Telegram-Init-Data header)
"""

import hashlib
import hmac
import html
import json
import logging
import math
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

# Path to the bot's web/index.html (relative to this file's location)
_BOT_DIR = Path(__file__).resolve().parent.parent.parent / "PredvestnikBot"

# Import shared price catalogue from the bot package
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))
from shared_prices import (  # noqa: E402
    GACHA_SINGLE_PRICE as _GACHA_SINGLE_PRICE,
    GACHA_MULTI_PRICE as _GACHA_MULTI_PRICE,
    GACHA_SINGLES_SINGLE as _GACHA_SINGLES_SINGLE,
    GACHA_SINGLES_MULTI as _GACHA_SINGLES_MULTI,
    GACHA_PITY_MAX as _GACHA_PITY_MAX,
    PRICE_VIP as _PRICE_VIP,
    FRAMES_CATALOG as _FRAMES_CATALOG,
    COSMETICS_CATALOG as _COSMETICS_CATALOG,
    FOOD_ITEMS as _FOOD_ITEMS,
    POTIONS_CATALOG as _POTIONS_CATALOG,
    BOND_DEFAULTS as _BOND_DEFAULTS_SYNC,
    BANK_PLANS as _BANK_PLANS_SYNC,
    BANK_MIN_DEPOSIT as _BANK_MIN_DEPOSIT,
    BANK_MAX_DEPOSIT as _BANK_MAX_DEPOSIT,
    BANK_EARLY_PENALTY_PCT as _BANK_EARLY_PENALTY_PCT,
    CHECKIN_REWARDS as _CHECKIN_REWARDS_SYNC,
    CHECKIN_CHECKPOINTS as _CHECKIN_CHECKPOINTS_SYNC,
    ITEM_METADATA as _ITEM_METADATA,
    CUSTOM_TITLE_PRICE as _CUSTOM_TITLE_PRICE,
)
_INDEX_HTML = _BOT_DIR / "web" / "index.html"
_BOT_DB_URL = os.environ.get("PREDVESTNIK_DATABASE_URL", "")
_BOT_TOKEN = os.environ.get("PREDVESTNIK_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")


def _xp_for_level(level: int) -> int:
    return level * (level - 1) * 100


def _level_for_xp(xp: int) -> int:
    if xp < 200:
        return 1
    return max(1, int((1 + math.sqrt(1 + xp / 25)) / 2))


def _validate_init_data(init_data: str) -> int | None:
    """Validate Telegram WebApp initData HMAC. Returns user_id (int) if valid, else None."""
    if not _BOT_TOKEN or not init_data:
        return None
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = params.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(sorted(f"{k}={v}" for k, v in params.items()))
    secret_key = hmac.new(b"WebAppData", _BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        return None
    user_str = params.get("user", "{}")
    try:
        user_data = json.loads(user_str)
        uid = user_data.get("id")
        return int(uid) if uid else None
    except (json.JSONDecodeError, AttributeError, ValueError):
        return None


def _get_bot_db_connection():
    """Return a DB connection to the bot's database (psycopg2 or sqlite3)."""
    url = _BOT_DB_URL
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        import psycopg2
        return psycopg2.connect(url), "pg"
    # Fallback: SQLite bot.db next to this file
    db_path = _BOT_DIR / "bot.db"
    return sqlite3.connect(str(db_path)), "sqlite"


@require_GET
def miniapp_index(request):
    """Serve the Mini App HTML."""
    if not _INDEX_HTML.exists():
        return HttpResponse(
            "<h1>Mini App not found</h1><p>web/index.html is missing.</p>",
            status=404,
            content_type="text/html",
        )
    content = _INDEX_HTML.read_text(encoding="utf-8")
    return HttpResponse(content, content_type="text/html")


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "X-Telegram-Init-Data, X-Init-Data, Content-Type",
        "Cache-Control": "no-cache",
    }


def _get_init_data(request) -> str:
    """Return initData from supported headers (and URL fallback for webview edge cases)."""
    return (
        request.headers.get("X-Telegram-Init-Data", "")
        or request.headers.get("X-Init-Data", "")
        or request.GET.get("initData", "")
        or request.GET.get("tgWebAppData", "")
    ).strip()


@csrf_exempt
def miniapp_user_data(request):
    """Return JSON profile data for a Telegram user from the bot's database.

    Auth: X-Telegram-Init-Data header (validated HMAC).
    Fallback for development: ?user_id=N query param (only if no bot token configured).
    """
    headers = _cors_headers()

    # Handle CORS preflight
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)

    if request.method != "GET":
        return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)

    # ── Auth: validate initData from header ─────────────────────────────
    init_data = _get_init_data(request)
    uid: int | None = None

    if init_data:
        uid = _validate_init_data(init_data)
        if uid is None:
            return JsonResponse({"error": "invalid or expired initData"}, status=401, headers=headers)
    else:
        # Dev fallback: plain user_id param (only allowed if bot token not set)
        if _BOT_TOKEN:
            return JsonResponse({"error": "initData required"}, status=401, headers=headers)
        uid_str = request.GET.get("user_id", "")
        if not uid_str.isdigit():
            return JsonResponse({"error": "missing or invalid user_id"}, status=400, headers=headers)
        uid = int(uid_str)

    # ── Optional chat_id to scope data to a specific chat ────────────────
    chat_id_str = request.GET.get("chat_id", "").lstrip()
    specific_chat_id: int | None = None
    if chat_id_str.lstrip("-").isdigit():
        specific_chat_id = int(chat_id_str)
    # Fallback: parse chat from signed initData (contains "chat" field for group contexts)
    if not specific_chat_id and init_data:
        try:
            _iparams = dict(parse_qsl(init_data, keep_blank_values=True))
            _chat_raw = _iparams.get("chat", "")
            if _chat_raw:
                _chat_data = json.loads(_chat_raw)
                _cid = _chat_data.get("id")
                if _cid:
                    specific_chat_id = int(_cid)
        except Exception:
            pass

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception:
        logger.exception("miniapp: DB connection failed")
        return JsonResponse({"error": "Сервис временно недоступен"}, status=503,
                            headers=headers)

    try:
        if db_type == "pg":
            cur = conn.cursor()
            ph = "%s"
        else:
            cur = conn.cursor()
            ph = "?"

        # User full_name
        cur.execute(f"SELECT full_name FROM users WHERE user_id={ph}", (uid,))
        user_row = cur.fetchone()
        full_name = user_row[0] if user_row else str(uid)

        # Mora row: use specific chat if provided, otherwise best (highest balance)
        if specific_chat_id:
            cur.execute(
                f"SELECT chat_id, balance, vip, top_frame, active_theme FROM user_mora "
                f"WHERE user_id={ph} AND chat_id={ph}",
                (uid, specific_chat_id),
            )
        else:
            cur.execute(
                f"SELECT chat_id, balance, vip, top_frame, active_theme FROM user_mora "
                f"WHERE user_id={ph} ORDER BY balance DESC LIMIT 1",
                (uid,),
            )
        mora_row = cur.fetchone()
        if mora_row:
            chat_id, balance, vip, top_frame, active_theme = mora_row
        else:
            chat_id, balance, vip, top_frame, active_theme = 0, 0, 0, None, None

        # XP + level: scope to same chat when possible
        if specific_chat_id or chat_id:
            effective_cid = specific_chat_id or chat_id
            cur.execute(
                f"SELECT xp, COALESCE(level, 1), custom_title, COALESCE(rank,'user'), first_active, last_active, COALESCE(warns,0), COALESCE(message_count,0), newbie_shield_until FROM user_stats WHERE user_id={ph} AND chat_id={ph}",
                (uid, effective_cid),
            )
        else:
            cur.execute(
                f"SELECT xp, COALESCE(level, 1), custom_title, COALESCE(rank,'user'), first_active, last_active, COALESCE(warns,0), COALESCE(message_count,0), newbie_shield_until FROM user_stats WHERE user_id={ph} ORDER BY xp DESC LIMIT 1",
                (uid,),
            )
        xp_row = cur.fetchone()
        xp = xp_row[0] if xp_row else 0
        db_level = xp_row[1] if xp_row else 1
        custom_title = xp_row[2] if xp_row else None
        user_rank = xp_row[3] if xp_row else 'user'
        first_active = str(xp_row[4]) if xp_row and xp_row[4] else None
        last_active = str(xp_row[5]) if xp_row and xp_row[5] else None
        warns_count = xp_row[6] if xp_row else 0
        message_count = xp_row[7] if xp_row else 0
        newbie_shield_until = str(xp_row[8]) if xp_row and xp_row[8] else None
        # Developer ID always gets developer rank regardless of DB value
        if uid == _DEVELOPER_ID:
            user_rank = 'developer'

        # Bonds
        bonds_data = []
        if chat_id:
            cur.execute(
                f"SELECT b.bond_key, b.amount, COALESCE(p.price, 100) as price "
                f"FROM user_bonds b "
                f"LEFT JOIN bond_prices p ON p.bond_key=b.bond_key AND p.chat_id=b.chat_id "
                f"WHERE b.user_id={ph} AND b.chat_id={ph}",
                (uid, chat_id),
            )
            for row in cur.fetchall():
                bkey, amount, price = row
                bonds_data.append({
                    "name": bkey,
                    "amount": amount,
                    "value": amount * price,
                })

        # Inventory (gacha items)
        items: list[str] = []
        if chat_id:
            cur.execute(
                f"SELECT item_name, rarity, equipped FROM gacha_inventory "
                f"WHERE user_id={ph} AND chat_id={ph} LIMIT 20",
                (uid, chat_id),
            )
            for row in cur.fetchall():
                item_name, rarity, equipped = row
                label = f"{'★' if equipped else ''}{item_name} ({rarity})"
                items.append(label)

        # Pet
        pet_info = None
        if chat_id:
            cur.execute(
                f"SELECT pet_type, name, COALESCE(fatigue,0), walk_end_at, color_name FROM pets "
                f"WHERE user_id={ph} AND chat_id={ph}",
                (uid, chat_id),
            )
            pet_row = cur.fetchone()
            if pet_row:
                ptype, pname, pfatigue, pwalk_end, pcolor = pet_row
                emoji = {"cat": "🐱", "dog": "🐶"}.get(ptype, "🐾")
                on_walk = False
                walk_mins_left = 0
                if pwalk_end:
                    try:
                        from datetime import datetime as _dt, timezone as _tz
                        end_dt = _dt.fromisoformat(str(pwalk_end))
                        if end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=_tz.utc)
                        diff = (end_dt - _dt.now(_tz.utc)).total_seconds()
                        if diff > 0:
                            on_walk = True
                            walk_mins_left = int(diff / 60) + 1
                    except Exception:
                        pass
                pet_info = {
                    "type": ptype,
                    "name": pname or "безымянный",
                    "emoji": emoji,
                    "fatigue": pfatigue,
                    "on_walk": on_walk,
                    "walk_mins_left": walk_mins_left,
                    "walk_end_at": pwalk_end or None,
                    "color_name": pcolor,
                }

        # RPG stats
        rpg = {"hp": 100, "atk": 50, "def": 20, "crit": 0.05}
        if chat_id:
            cur.execute(
                f"SELECT base_hp, base_atk, base_def, base_crit, weapon_id, armor_id, artifact_id "
                f"FROM user_rpg_stats WHERE user_id={ph} AND chat_id={ph}",
                (uid, chat_id),
            )
            rpg_row = cur.fetchone()
            if rpg_row:
                rpg = {"hp": rpg_row[0], "atk": rpg_row[1], "def": rpg_row[2], "crit": rpg_row[3]}
                equip_ids = [eid for eid in [rpg_row[4], rpg_row[5], rpg_row[6]] if eid]
                if equip_ids:
                    placeholders = ",".join(ph for _ in equip_ids)
                    cur.execute(
                        f"SELECT COALESCE(atk,0),COALESCE(def_val,0),COALESCE(hp,0),COALESCE(crit_rate,0) "
                        f"FROM gacha_inventory WHERE id IN ({placeholders})", equip_ids)
                    for er in cur.fetchall():
                        rpg["atk"] += er[0]; rpg["def"] += er[1]
                        rpg["hp"] += er[2]; rpg["crit"] += er[3]

        # Family wallet (if married) — show total of both spouses
        family_balance = 0
        my_family_balance = 0
        partner_family_balance = 0
        has_partner = False
        partner_name = None
        partner_id_val = None
        if chat_id:
            cur.execute(
                f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}",
                (uid, chat_id),
            )
            m_row = cur.fetchone()
            has_partner = m_row is not None
            if has_partner:
                partner_id = m_row[0]
                partner_id_val = partner_id
                cur.execute(f"SELECT full_name FROM users WHERE user_id={ph}", (partner_id,))
                pn_row = cur.fetchone()
                partner_name = pn_row[0] if pn_row else None
                cur.execute(
                    f"SELECT COALESCE(balance,0) FROM family_wallet WHERE chat_id={ph} AND user_id={ph}",
                    (chat_id, uid),
                )
                fw_row = cur.fetchone()
                my_family_balance = fw_row[0] if fw_row else 0
                cur.execute(
                    f"SELECT COALESCE(balance,0) FROM family_wallet WHERE chat_id={ph} AND user_id={ph}",
                    (chat_id, partner_id),
                )
                fw_row2 = cur.fetchone()
                partner_family_balance = fw_row2[0] if fw_row2 else 0
                family_balance = my_family_balance + partner_family_balance

        # Gacha pity
        pity = 0
        if chat_id:
            cur.execute(
                f"SELECT COUNT(*) FROM gacha_inventory "
                f"WHERE user_id={ph} AND chat_id={ph} "
                f"AND id > COALESCE("
                f"  (SELECT MAX(id) FROM gacha_inventory "
                f"   WHERE user_id={ph} AND chat_id={ph} AND rarity='legendary'), 0)",
                (uid, chat_id, uid, chat_id),
            )
            pity = (cur.fetchone() or [0])[0]

        # Streak from daily_checkin
        streak = 0
        if chat_id:
            cur.execute(
                f"SELECT streak FROM daily_checkin WHERE user_id={ph} AND chat_id={ph}",
                (uid, chat_id),
            )
            str_row = cur.fetchone()
            streak = str_row[0] if str_row else 0

        conn.close()

        computed_level = db_level if db_level > 1 else _level_for_xp(xp)
        xp_max = _xp_for_level(computed_level + 1)
        
        payload = {
            "uid": uid,
            "chat_id": chat_id,
            "name": full_name,
            "balance": balance,
            "xp": xp,
            "level": computed_level,
            "xp_max": xp_max,
            "vip": bool(vip),
            "active_frame": top_frame or "default",
            "active_theme": active_theme or "default",
            "bonds": bonds_data,
            "items": items,
            "pet": pet_info,
            "rpg": rpg,
            "family_balance": family_balance,
            "my_family_balance": my_family_balance,
            "partner_family_balance": partner_family_balance,
            "has_partner": has_partner,
            "partner_name": partner_name,
            "partner_id": partner_id_val,
            "pity": pity,
            "streak": streak,
            "rank": user_rank,
            "is_dev": user_rank in ('developer', 'owner'),
            "custom_title": custom_title or "",
            "first_active": first_active,
            "last_active": last_active,
            "warns": warns_count,
            "message_count": message_count,
            "newbie_shield_until": newbie_shield_until,
        }
        return JsonResponse(payload, json_dumps_params={"ensure_ascii": False},
                            headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Leaderboard ──────────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_leaderboard(request):
    """GET /api/leaderboard?chat_id=X&type=xp|messages|boss"""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)
    lb_type = request.GET.get("type", "xp")

    uid_lb = None
    init_data_lb = _get_init_data(request)
    if init_data_lb:
        uid_lb = _validate_init_data(init_data_lb)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.user import get_leaderboard
        result = _a2s(get_leaderboard)(chat_id, lb_type, uid_lb)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Daily check-in ───────────────────────────────────────────────────────────
# _CHECKIN_REWARDS_SYNC and _CHECKIN_CHECKPOINTS_SYNC imported from shared_prices at top


@csrf_exempt
def miniapp_checkin(request):
    """GET or POST /api/checkin — check-in status or perform check-in."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method not in ("GET", "POST"):
        return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)

    # Auth
    init_data = _get_init_data(request)
    uid: int | None = None
    if init_data:
        uid = _validate_init_data(init_data)
        if uid is None:
            return JsonResponse({"error": "invalid initData"}, status=401, headers=headers)
    else:
        if _BOT_TOKEN:
            return JsonResponse({"error": "initData required"}, status=401, headers=headers)
        uid_str = request.GET.get("user_id", "")
        if not uid_str.isdigit():
            return JsonResponse({"error": "missing user_id"}, status=400, headers=headers)
        uid = int(uid_str)

    # chat_id
    if request.method == "GET":
        chat_id_str = request.GET.get("chat_id", "")
    else:
        try:
            body = json.loads(request.body)
            chat_id_str = str(body.get("chat_id", ""))
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    from asgiref.sync import async_to_sync as _a2s
    try:
        if request.method == "GET":
            from api.checkin import get_checkin_status
            data = _a2s(get_checkin_status)(uid, chat_id)
            return JsonResponse(data, headers=headers)

        # POST: perform check-in
        from api.checkin import do_checkin
        result = _a2s(do_checkin)(uid, chat_id)
        if result.get("already_done"):
            return JsonResponse(result, headers=headers)

        mora_reward = result["mora"]
        streak = result["streak"]
        day_idx = min(streak, 20)
        is_checkpoint = result.get("is_checkpoint", False)
        reward_text = f"+{mora_reward} 🪙"
        if is_checkpoint:
            reward_text += f" | День {day_idx} - ЧЕКПОИНТ! ✨"
        if day_idx == 20:
            reward_text += " | Бесплатная гача! 🎁"

        _a2s(log_action_to_chat)(
            uid, chat_id,
            f"Забрал ежедневную награду (день {streak})",
            reward_text,
        )

        return JsonResponse(result, headers=headers)

    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Boss damage ──────────────────────────────────────────────────────────────

_BOSS_MAX_HP = 500_000
_BOSS_DAILY_DAMAGE_LIMIT = 50_000


@csrf_exempt
def miniapp_boss_damage(request):
    """POST /api/boss/submit_damage — submit boss attack damage."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    init_data = _get_init_data(request)
    uid: int | None = None
    if init_data:
        uid = _validate_init_data(init_data)
        if uid is None:
            return JsonResponse({"error": "invalid initData"}, status=401, headers=headers)
    else:
        return JsonResponse({"error": "initData required"}, status=401, headers=headers)

    try:
        body = json.loads(request.body)
        chat_id_str = str(body.get("chat_id", ""))
        damage = int(body.get("damage", 0))
    except (json.JSONDecodeError, ValueError, AttributeError):
        return JsonResponse({"error": "invalid JSON body"}, status=400, headers=headers)

    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    if damage <= 0 or damage > _BOSS_DAILY_DAMAGE_LIMIT:
        return JsonResponse({"error": "damage out of valid range"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync
        from services.boss_service import record_miniapp_damage
        from services.exceptions import BossLimitError

        result = async_to_sync(record_miniapp_damage)(
            uid, chat_id, damage,
            daily_limit=_BOSS_DAILY_DAMAGE_LIMIT,
            boss_max_hp=_BOSS_MAX_HP,
        )
        return JsonResponse({"ok": True, **result}, headers=headers)

    except BossLimitError:
        return JsonResponse(
            {"error": "daily damage limit reached", "limit": _BOSS_DAILY_DAMAGE_LIMIT},
            status=429, headers=headers,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Developer ID ─────────────────────────────────────────────────────────────
_DEVELOPER_ID = 1460945748


def _require_auth(request, headers):
    """Validate initData. Returns uid (int) on success or a JsonResponse error."""
    init_data = _get_init_data(request)
    if not init_data:
        if _BOT_TOKEN:
            return None, JsonResponse({"error": "initData required"}, status=401, headers=headers)
        uid_str = request.GET.get("user_id", "") if request.method == "GET" else ""
        if uid_str.isdigit():
            return int(uid_str), None
        return None, JsonResponse({"error": "auth required"}, status=401, headers=headers)
    uid = _validate_init_data(init_data)
    if uid is None:
        return None, JsonResponse({"error": "invalid initData"}, status=401, headers=headers)
    return uid, None


_EDITABLE_RANKS = (
    "user",
    "moderator",
    "admin_junior",
    "admin_senior",
    "co_owner",
    "owner",
    "developer",
)


def _send_salary_announcement(chat_id: int, target_name: str) -> None:
    if not _BOT_TOKEN:
        return
    try:
        import requests
        url = f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage"
        requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": f"🎉 <b>{html.escape(target_name)}</b> получил зарплату от администрации!",
                "parse_mode": "HTML",
            },
            timeout=5,
        )
    except Exception:
        pass


# ─── Marriage ─────────────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_marriage(request):
    """GET /api/marriage?chat_id=X — marriage status + singles list."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.marriage import get_status
        data = _a2s(get_status)(uid, chat_id)
        return JsonResponse(data, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Marriage: propose ────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_marriage_propose(request):
    """POST /api/marriage/propose — returns bot command instruction."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body)
        target_id = int(body.get("target_id", 0))
        chat_id = int(body.get("chat_id", 0))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not target_id or not chat_id:
        return JsonResponse({"error": "target_id and chat_id required"}, status=400, headers=headers)

    if target_id == uid:
        return JsonResponse({"error": "Нельзя предложить руку самому себе"}, status=400,
                            json_dumps_params={"ensure_ascii": False}, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.marriage import propose as _propose
        result = _a2s(_propose)(uid, target_id, chat_id)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400,
                            json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    # Send Telegram notification to the target's chat
    try:
        from asgiref.sync import async_to_sync as _a2s2
        from database.db import get_user as _get_user
        import asyncio
        from aiogram import Bot as _AiogramBot
        from config import BOT_TOKEN as _BOT_TOKEN

        from_user = _a2s2(_get_user)(uid)
        from_name = from_user["full_name"] if from_user else f"user_{uid}"
        proposal_text = (
            f"💍 <b>{html.escape(from_name)}</b> делает тебе предложение руки и сердца!\n\n"
            f"Открой Mini App, вкладку 🤝 Узы, чтобы принять или отклонить."
        )

        async def _notify():
            bot = _AiogramBot(token=_BOT_TOKEN)
            try:
                await bot.send_message(chat_id, proposal_text, parse_mode="HTML")
            except Exception:
                pass
            finally:
                await bot.session.close()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_notify())
            else:
                loop.run_until_complete(_notify())
        except Exception:
            pass
    except Exception:
        pass

    return JsonResponse({
        "ok": True,
        "proposal_id": result["proposal_id"],
        "message": result["message"],
    }, json_dumps_params={"ensure_ascii": False}, headers=headers)


# ─── Marriage: list pending proposals ────────────────────────────────────────

@csrf_exempt
def miniapp_marriage_proposals_list(request):
    """GET /api/marriage/proposals?chat_id=X — list pending incoming proposals."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    from database.db import get_pending_proposals
    from asgiref.sync import async_to_sync
    proposals = async_to_sync(get_pending_proposals)(uid, chat_id)

    return JsonResponse({
        "proposals": [
            {"id": p["id"], "from_user_id": p["from_user_id"],
             "from_name": p["from_name"], "created_at": str(p.get("created_at", ""))}
            for p in proposals
        ]
    }, json_dumps_params={"ensure_ascii": False}, headers=headers)


# ─── Marriage: respond to proposal ───────────────────────────────────────────

@csrf_exempt
def miniapp_marriage_respond(request):
    """POST /api/marriage/respond — accept or decline a proposal."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body)
        proposal_id = int(body.get("proposal_id", 0))
        accept = bool(body.get("accept", False))
        chat_id = int(body.get("chat_id", 0))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not proposal_id or not chat_id:
        return JsonResponse({"error": "proposal_id and chat_id required"}, status=400, headers=headers)

    from database.db import create_marriage
    from asgiref.sync import async_to_sync

    new_status = "accepted" if accept else "declined"

    # ── Atomic update: flip status only if it is still 'pending' AND the
    #    target user matches the authenticated user.  This single statement
    #    in PostgreSQL prevents the TOCTOU race that caused "уже обработано"
    #    on rapid double-clicks or simultaneous requests.
    try:
        conn, db_type = _get_bot_db_connection()
        cur = conn.cursor()
        if db_type == "pg":
            cur.execute(
                """UPDATE marriage_proposals
                      SET status = %s
                    WHERE id = %s
                      AND to_user_id = %s
                      AND status = 'pending'
                    RETURNING id, from_user_id, to_user_id, chat_id, status""",
                (new_status, proposal_id, uid),
            )
            row = cur.fetchone()
        else:
            # SQLite path: UPDATE then check rowcount
            cur.execute(
                "UPDATE marriage_proposals SET status=? WHERE id=? AND to_user_id=? AND status='pending'",
                (new_status, proposal_id, uid),
            )
            if cur.rowcount == 1:
                cur.execute(
                    "SELECT id, from_user_id, to_user_id, chat_id, status FROM marriage_proposals WHERE id=?",
                    (proposal_id,),
                )
                row = cur.fetchone()
            else:
                row = None
        conn.commit()
        conn.close()
    except Exception as exc:
        try: conn.close()
        except Exception: pass
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    if not row:
        # Either the proposal doesn't exist, belongs to a different user,
        # or was already accepted/declined before this request landed.
        try:
            conn2, db_type2 = _get_bot_db_connection()
            cur2 = conn2.cursor()
            ph = "%s" if db_type2 == "pg" else "?"
            cur2.execute(
                f"SELECT status, to_user_id FROM marriage_proposals WHERE id={ph}",
                (proposal_id,),
            )
            check = cur2.fetchone()
            conn2.close()
        except Exception:
            try: conn2.close()
            except Exception: pass
            check = None
        if not check:
            return JsonResponse({"error": "Предложение не найдено"}, status=404,
                                json_dumps_params={"ensure_ascii": False}, headers=headers)
        if check[1] != uid:
            return JsonResponse({"error": "Forbidden"}, status=403, headers=headers)
        # check[0] is not 'pending' — already processed
        return JsonResponse({"error": "Предложение уже обработано"},
                            json_dumps_params={"ensure_ascii": False}, headers=headers)

    from_id = row[1]  # from_user_id

    if accept:
        from database.db import create_marriage
        from asgiref.sync import async_to_sync
        try:
            async_to_sync(create_marriage)(from_id, uid, chat_id)
        except Exception as exc:
            logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)
        return JsonResponse({"ok": True, "married": True,
                             "message": "Поздравляем! Вы теперь в браке! 💍"},
                            json_dumps_params={"ensure_ascii": False}, headers=headers)
    else:
        return JsonResponse({"ok": True, "married": False,
                             "message": "Предложение отклонено."},
                            json_dumps_params={"ensure_ascii": False}, headers=headers)


# ─── Bonds + price history ────────────────────────────────────────────────────

@csrf_exempt
def miniapp_bonds(request):
    """GET /api/bonds?chat_id=X — bond prices, user holdings, price history."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.bonds import get_bonds_status
        result = _a2s(get_bonds_status)(uid, chat_id)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Equip item ───────────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_equip(request):
    """POST /api/equip — equip a gacha item into an RPG slot."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    init_data = _get_init_data(request)
    uid = _validate_init_data(init_data) if init_data else None
    if uid is None:
        return JsonResponse({"error": "initData required"}, status=401, headers=headers)

    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0")).lstrip())
        item_id = int(body.get("item_id", 0))
        slot = str(body.get("slot", "")).lower()
    except (json.JSONDecodeError, ValueError, AttributeError):
        return JsonResponse({"error": "invalid JSON body"}, status=400, headers=headers)

    if slot not in ("weapon", "armor", "artifact"):
        return JsonResponse({"error": "slot must be weapon/armor/artifact"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync
        from services.inventory_service import equip_rpg_slot
        from services.exceptions import ItemNotFoundError

        item_name = async_to_sync(equip_rpg_slot)(uid, chat_id, item_id, slot)
        return JsonResponse({"ok": True, "equipped": item_name, "slot": slot}, headers=headers)

    except ItemNotFoundError as exc:
        return JsonResponse({"error": str(exc)}, status=404, headers=headers)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Developer panel ──────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_dev_stats(request):
    """GET /api/dev/stats — developer only: active chats + recent error summary."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import get_stats as _get_stats
        result = _a2s(_get_stats)()
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_dev_setbalance(request):
    """POST /api/dev/setbalance — developer only: set a user's mora balance."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    init_data = _get_init_data(request)
    uid = _validate_init_data(init_data) if init_data else None
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    try:
        body = json.loads(request.body)
        target_id = int(body.get("target_id", 0) or body.get("target_uid", 0))
        chat_id = int(str(body.get("chat_id", "0")))
        balance = int(body.get("balance", 0) or body.get("amount", 0))
    except (json.JSONDecodeError, ValueError, AttributeError):
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if balance < 0 or balance > 10_000_000:
        return JsonResponse({"error": "balance out of range"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import set_balance as _set_balance
        result = _a2s(_set_balance)(uid, target_id, chat_id, balance)
        return JsonResponse(result, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Dev: add mora ────────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_dev_add_mora(request):
    """POST /api/dev/add_mora — add (or subtract) mora for a user."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    try:
        body = json.loads(request.body)
        target_id = int(body.get("target_id", 0) or body.get("target_uid", 0))
        chat_id = int(str(body.get("chat_id", "0")))
        amount = int(body.get("amount", 0))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not target_id or not chat_id:
        return JsonResponse({"error": "target_id and chat_id required"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import admin_add_mora as _admin_add_mora
        result = _a2s(_admin_add_mora)(uid, target_id, chat_id, amount)
        return JsonResponse(result, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Dev: add XP ──────────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_dev_add_xp(request):
    """POST /api/dev/add_xp — add XP for a user."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    try:
        body = json.loads(request.body)
        target_id = int(body.get("target_id", 0) or body.get("target_uid", 0))
        chat_id = int(str(body.get("chat_id", "0")))
        amount = int(body.get("amount", 0))
        set_mode = bool(body.get("set_mode", False))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not target_id or not chat_id:
        return JsonResponse({"error": "target_id and chat_id required"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import admin_add_xp as _admin_add_xp
        result = _a2s(_admin_add_xp)(uid, target_id, chat_id, amount, set_mode)
        return JsonResponse(result, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_wallet_history(request):
    """GET /api/wallet/history?chat_id=X — authenticated user's personal wallet ledger."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.economy import wallet_history
        history = _a2s(wallet_history)(uid, chat_id)
        return JsonResponse({"history": history}, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_dev_member_update(request):
    """POST /api/dev/member_update — developer CRM row save for balance/xp/rank."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    try:
        body = json.loads(request.body or b"{}")
        target_id = int(body.get("target_id", 0))
        chat_id = int(str(body.get("chat_id", "0")))
        balance = int(body.get("balance", 0))
        xp = int(body.get("xp", 0))
        rank = str(body.get("rank", "user")).strip().lower()
        # Message count fields (None means "not provided — don't update")
        msg_count        = body.get("message_count")     # user_stats.message_count
        day_count        = body.get("day_count")         # cleanup_counts.day_count
        week_count       = body.get("week_count")        # cleanup_counts.week_count
        total_count      = body.get("total_count")       # cleanup_counts.count
        yesterday_count  = body.get("yesterday_count")   # cleanup_counts.yesterday_count
        last_week_count  = body.get("last_week_count")   # cleanup_counts.last_week_count
        if msg_count        is not None: msg_count        = max(0, int(msg_count))
        if day_count        is not None: day_count        = max(0, int(day_count))
        if week_count       is not None: week_count       = max(0, int(week_count))
        if total_count      is not None: total_count      = max(0, int(total_count))
        if yesterday_count  is not None: yesterday_count  = max(0, int(yesterday_count))
        if last_week_count  is not None: last_week_count  = max(0, int(last_week_count))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not target_id or not chat_id:
        return JsonResponse({"error": "target_id and chat_id required"}, status=400, headers=headers)
    if balance < 0 or balance > 10_000_000:
        return JsonResponse({"error": "balance out of range"}, status=400, headers=headers)
    if xp < 0 or xp > 100_000_000:
        return JsonResponse({"error": "xp out of range"}, status=400, headers=headers)
    if rank not in _EDITABLE_RANKS:
        return JsonResponse({"error": "invalid rank"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import member_update as _member_update
        result = _a2s(_member_update)(
            uid, target_id, chat_id, balance, xp, rank,
            msg_count=msg_count, day_count=day_count, week_count=week_count,
            total_count=total_count, yesterday_count=yesterday_count,
            last_week_count=last_week_count,
        )
        return JsonResponse(result, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_dev_salary(request):
    """POST /api/dev/salary — grant salary privately, announce publicly without amount."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    try:
        body = json.loads(request.body or b"{}")
        target_id = int(body.get("target_id", 0))
        chat_id = int(str(body.get("chat_id", "0")))
        days = max(1, int(body.get("days", 1)))
        amount = int(body.get("amount", 0))
        reason = str(body.get("reason", "")).strip()
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not target_id or not chat_id or amount <= 0:
        return JsonResponse({"error": "target_id, chat_id and positive amount required"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import give_salary as _give_salary
        result = _a2s(_give_salary)(uid, target_id, chat_id, days, amount, reason)
        _send_salary_announcement(chat_id, result["target_name"])
        return JsonResponse(
            {"ok": True, "target_id": result["target_id"], "days": result["days"],
             "amount": result["amount"], "reason": result["reason"],
             "new_balance": result["new_balance"]},
            json_dumps_params={"ensure_ascii": False},
            headers=headers,
        )
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Dev: give item ───────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_dev_give_item(request):
    """POST /api/dev/give_item — give a gacha item to a user by item_key."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    try:
        body = json.loads(request.body)
        target_id = int(body.get("target_id", 0) or body.get("target_uid", 0))
        chat_id = int(str(body.get("chat_id", "0")))
        item_name = str(body.get("item_name", "")).strip()
        rarity = str(body.get("rarity", "rare")).strip().lower()
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not target_id or not chat_id or not item_name:
        return JsonResponse({"error": "target_id, chat_id, item_name required"}, status=400, headers=headers)

    if rarity not in ("common", "uncommon", "rare", "epic", "legendary"):
        rarity = "rare"

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import give_item as _give_item
        result = _a2s(_give_item)(uid, target_id, chat_id, item_name, rarity)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Dev: search users ────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_dev_users(request):
    """GET /api/dev/users?chat_id=X&q=search — search users in a chat."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)
    q = request.GET.get("q", "").strip()

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import search_users as _search_users
        result = _a2s(_search_users)(chat_id, q)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Dev: list all chats (grouped) ────────────────────────────────────────────

@csrf_exempt
def miniapp_dev_chats(request):
    """GET /api/dev/chats — developer only: all known chats split by type."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import get_chats as _get_chats
        result = _a2s(_get_chats)()
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Dev: chat admins with balances ───────────────────────────────────────────

@csrf_exempt
def miniapp_dev_chat_admins(request):
    """GET /api/dev/chat_admins?chat_id=X — developer only: members with rank/balance."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import get_chat_members as _get_chat_members
        result = _a2s(_get_chat_members)(chat_id)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Dev: blacklist (global ban by user_id) ────────────────────────────────────

@csrf_exempt
def miniapp_dev_banlist(request):
    """GET /api/dev/banlist — list banned users.
    POST /api/dev/banlist {user_id, reason} — add ban.
    DELETE /api/dev/banlist {user_id} — remove ban."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import get_banlist, ban_user, unban_user

        if request.method == "GET":
            result = _a2s(get_banlist)()
            return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)

        body = json.loads(request.body or b"{}")
        target_id = int(body.get("user_id", 0))
        if not target_id:
            return JsonResponse({"error": "user_id required"}, status=400, headers=headers)

        if request.method == "POST":
            reason = str(body.get("reason", ""))[:200]
            result = _a2s(ban_user)(uid, target_id, reason)
            return JsonResponse(result, headers=headers)

        if request.method == "DELETE":
            result = _a2s(unban_user)(target_id)
            return JsonResponse(result, headers=headers)

        return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Dev: activity logs ───────────────────────────────────────────────────────

@csrf_exempt
def miniapp_dev_logs(request):
    """GET /api/dev/logs?chat_id=X — last leave events + server error log."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    chat_id_str = request.GET.get("chat_id", "0")
    chat_id = int(chat_id_str) if chat_id_str.lstrip("-").isdigit() else 0

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import get_logs as _get_logs
        result = _a2s(_get_logs)(chat_id)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Dev: event trigger ───────────────────────────────────────────────────────

@csrf_exempt
def miniapp_dev_trigger_event(request):
    """POST /api/dev/trigger_event {event_type, chat_id} — fire an event in a chat."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    try:
        body = json.loads(request.body or b"{}")
        event_type = str(body.get("event_type", "")).strip().lower()
        target_chat = int(str(body.get("chat_id", "0")))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not event_type:
        return JsonResponse({"error": "event_type required"}, status=400, headers=headers)
    if not target_chat:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import trigger_event as _trigger_event
        result = _a2s(_trigger_event)(uid, target_chat, event_type)
        return JsonResponse(result, headers=headers)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Dev: list all available items ────────────────────────────────────────────

@csrf_exempt
def miniapp_dev_items(request):
    """GET /api/dev/items — developer only: all available gacha items."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    from api.admin import get_items as _get_items
    return JsonResponse(_get_items(), json_dumps_params={"ensure_ascii": False}, headers=headers)


# ─── Treasury / Казна + НДС-лог ───────────────────────────────────────────────

@csrf_exempt
def miniapp_treasury(request):
    """GET /api/treasury?chat_id=X — казна чата (только developer и owner)."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "0")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    # Allow developer by Telegram ID, or owner rank in this chat
    if uid != _DEVELOPER_ID:
        try:
            conn, db_type = _get_bot_db_connection()
            cur = conn.cursor()
            ph = "%s" if db_type == "pg" else "?"
            cur.execute(
                f"SELECT rank FROM user_stats WHERE user_id={ph} AND chat_id={ph}",
                (uid, chat_id),
            )
            row = cur.fetchone()
            conn.close()
            rank = row[0] if row else "user"
        except Exception:
            rank = "user"
        if rank not in ("owner", "developer"):
            return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import get_treasury as _get_treasury
        result = _a2s(_get_treasury)(chat_id)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_treasury_payout(request):
    """POST /api/treasury/payout — pay mora from treasury to a user (developer/owner only)."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0")))
        target_id = int(str(body.get("target_id", "0")))
        amount = int(body.get("amount", 0))
        reason = str(body.get("reason", ""))[:200]
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not chat_id or not target_id or amount <= 0:
        return JsonResponse({"error": "chat_id, target_id и amount обязательны"}, status=400, headers=headers)

    # Allow developer by Telegram ID, or owner rank in this chat
    if uid != _DEVELOPER_ID:
        try:
            conn, db_type = _get_bot_db_connection()
            cur = conn.cursor()
            ph = "%s" if db_type == "pg" else "?"
            cur.execute(
                f"SELECT rank FROM user_stats WHERE user_id={ph} AND chat_id={ph}",
                (uid, chat_id),
            )
            row = cur.fetchone()
            conn.close()
            rank = row[0] if row else "user"
        except Exception:
            rank = "user"
        if rank not in ("owner", "developer"):
            return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.admin import treasury_payout as _treasury_payout
        result = _a2s(_treasury_payout)(uid, target_id, chat_id, amount, reason)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Family wallet: deposit / withdraw ────────────────────────────────────────

@csrf_exempt
def miniapp_family_deposit(request):
    """POST /api/family/deposit — transfer mora from personal to family wallet."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0")))
        amount = int(body.get("amount", 0))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.marriage import family_deposit
        result = _a2s(family_deposit)(uid, chat_id, amount)
        return JsonResponse({
            "ok": True,
            "personal": result["personal_balance"],
            "family": result["family_balance"],
        }, headers=headers)
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_family_withdraw(request):
    """POST /api/family/withdraw — transfer from family wallet to personal."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0")))
        amount = int(body.get("amount", 0))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.marriage import family_withdraw
        result = _a2s(family_withdraw)(uid, chat_id, amount)
        return JsonResponse({
            "ok": True,
            "personal": result["personal_balance"],
            "family": result["family_balance"],
        }, headers=headers)
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Family wallet: transaction log ─────────────────────────────────────────

@csrf_exempt
def miniapp_family_log(request):
    """GET /api/family/log?chat_id=X — last 30 family transactions."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.marriage import get_family_log
        result = _a2s(get_family_log)(uid, chat_id)
        return JsonResponse(result, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Inventory (full, with equip/unequip) ─────────────────────────────────────

@csrf_exempt
def miniapp_inventory(request):
    """GET /api/inventory?chat_id=X — full inventory with details.
       POST /api/inventory — toggle equip on an item."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    if request.method == "GET":
        chat_id_str = request.GET.get("chat_id", "")
        if not chat_id_str.lstrip("-").isdigit():
            return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
        chat_id = int(chat_id_str)

        try:
            conn, db_type = _get_bot_db_connection()
        except Exception as exc:
            return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

        try:
            cur = conn.cursor()
            ph = "%s" if db_type == "pg" else "?"
            cur.execute(
                f"SELECT id, item_key, item_name, rarity, equipped, "
                f"COALESCE(atk,0), COALESCE(def_val,0), COALESCE(hp,0), COALESCE(crit_rate,0), slot, COALESCE(enhancement_level,0), "
                f"COALESCE(stack_count,1) "
                f"FROM gacha_inventory WHERE user_id={ph} AND chat_id={ph} ORDER BY id DESC",
                (uid, chat_id),
            )
            items = []
            for r in cur.fetchall():
                meta = _ITEM_METADATA.get(r[1], {})
                items.append({
                    "id": r[0], "key": r[1], "name": r[2], "rarity": r[3], "equipped": bool(r[4]),
                    "atk": r[5], "def": r[6], "hp": r[7], "crit": r[8], "slot": r[9],
                    "enhancement_level": r[10],
                    "stack_count": r[11],
                    "is_cosmetic": meta.get("slot") == "flair",
                    "desc": meta.get("desc", ""),
                    "sell_price": meta.get("sell", 0),
                })

            # RPG stats (base + equipped bonuses)
            cur.execute(
                f"SELECT base_hp, base_atk, base_def, base_crit, weapon_id, armor_id, artifact_id "
                f"FROM user_rpg_stats WHERE user_id={ph} AND chat_id={ph}",
                (uid, chat_id),
            )
            rpg_row = cur.fetchone()
            if rpg_row:
                rpg = {"hp": rpg_row[0], "atk": rpg_row[1], "def": rpg_row[2], "crit": rpg_row[3]}
                equip_ids = [eid for eid in [rpg_row[4], rpg_row[5], rpg_row[6]] if eid]
                if equip_ids:
                    placeholders = ",".join(ph for _ in equip_ids)
                    cur.execute(
                        f"SELECT COALESCE(atk,0), COALESCE(def_val,0), COALESCE(hp,0), COALESCE(crit_rate,0) "
                        f"FROM gacha_inventory WHERE id IN ({placeholders})",
                        equip_ids,
                    )
                    for er in cur.fetchall():
                        rpg["atk"] += er[0]; rpg["def"] += er[1]
                        rpg["hp"] += er[2]; rpg["crit"] += er[3]
            else:
                rpg = {"hp": 100, "atk": 50, "def": 20, "crit": 0.05}

            # Pity counter
            cur.execute(
                f"SELECT COUNT(*) FROM gacha_inventory "
                f"WHERE user_id={ph} AND chat_id={ph} "
                f"AND id > COALESCE("
                f"  (SELECT MAX(id) FROM gacha_inventory "
                f"   WHERE user_id={ph} AND chat_id={ph} AND rarity='legendary'), 0)",
                (uid, chat_id, uid, chat_id),
            )
            pity = (cur.fetchone() or [0])[0]

            conn.close()
            return JsonResponse({
                "items": items, "rpg": rpg, "pity": pity,
            }, json_dumps_params={"ensure_ascii": False}, headers=headers)
        except Exception as exc:
            try:
                conn.close()
            except Exception:
                pass
            logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    elif request.method == "POST":
        # Toggle equip
        try:
            body = json.loads(request.body)
            chat_id = int(str(body.get("chat_id", "0")))
            item_id = int(body.get("item_id", 0))
        except Exception:
            return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

        try:
            conn, db_type = _get_bot_db_connection()
        except Exception as exc:
            return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

        try:
            cur = conn.cursor()
            ph = "%s" if db_type == "pg" else "?"

            cur.execute(
                f"SELECT id, equipped, slot FROM gacha_inventory WHERE id={ph} AND user_id={ph} AND chat_id={ph}",
                (item_id, uid, chat_id),
            )
            irow = cur.fetchone()
            if not irow:
                conn.close()
                return JsonResponse({"error": "item not found"}, status=404, headers=headers)

            currently_equipped = bool(irow[1])
            slot = irow[2]  # "weapon"|"armor"|"artifact"|None
            slot_col = {"weapon": "weapon_id", "armor": "armor_id", "artifact": "artifact_id"}.get(slot or "")

            if currently_equipped:
                cur.execute(f"UPDATE gacha_inventory SET equipped=0 WHERE id={ph}", (item_id,))
                if slot_col:
                    cur.execute(
                        f"UPDATE user_rpg_stats SET {slot_col}=NULL WHERE user_id={ph} AND chat_id={ph}",
                        (uid, chat_id),
                    )
            else:
                # Unequip all items sharing this slot first
                if slot:
                    cur.execute(
                        f"UPDATE gacha_inventory SET equipped=0 WHERE user_id={ph} AND chat_id={ph} AND slot={ph} AND equipped=1",
                        (uid, chat_id, slot),
                    )
                cur.execute(f"UPDATE gacha_inventory SET equipped=1 WHERE id={ph}", (item_id,))
                if slot_col:
                    if db_type == "pg":
                        cur.execute(
                            f"INSERT INTO user_rpg_stats (user_id, chat_id, {slot_col}) VALUES ({ph},{ph},{ph}) "
                            f"ON CONFLICT (user_id, chat_id) DO UPDATE SET {slot_col}=EXCLUDED.{slot_col}",
                            (uid, chat_id, item_id),
                        )
                    else:
                        cur.execute(
                            f"INSERT INTO user_rpg_stats (user_id, chat_id, {slot_col}) VALUES (?,?,?) "
                            f"ON CONFLICT(user_id, chat_id) DO UPDATE SET {slot_col}=excluded.{slot_col}",
                            (uid, chat_id, item_id),
                        )
            conn.commit()
            conn.close()
            return JsonResponse({"ok": True, "equipped": not currently_equipped, "slot": slot}, headers=headers)
        except Exception as exc:
            try:
                conn.close()
            except Exception:
                pass
            logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)


@csrf_exempt
def miniapp_inventory_sell_junk(request):
    """POST /api/inventory/sell_junk — sell all junk-rarity items at 50% price."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)
    uid, err = _require_auth(request, headers)
    if err:
        return err
    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0")))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)
    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)
    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        cur.execute(
            f"SELECT id, item_key, COALESCE(stack_count, 1) FROM gacha_inventory WHERE user_id={ph} AND chat_id={ph} AND rarity='junk'",
            (uid, chat_id),
        )
        junk_items = cur.fetchall()
        if not junk_items:
            cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            bal = (cur.fetchone() or [0])[0]
            conn.close()
            return JsonResponse({"ok": True, "sold": 0, "mora": 0, "balance": bal}, headers=headers)
        total_mora = 0
        total_sold = 0
        ids_to_delete = []
        for row in junk_items:
            iid, ikey, sc = row[0], row[1], row[2]
            meta = _ITEM_METADATA.get(ikey, {})
            sell = meta.get("sell", 0)
            total_mora += max(1, sell // 2) * sc
            total_sold += sc
            ids_to_delete.append(iid)
        placeholders = ",".join([ph] * len(ids_to_delete))
        cur.execute(f"DELETE FROM gacha_inventory WHERE id IN ({placeholders})", ids_to_delete)
        if db_type == "pg":
            cur.execute(
                f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
                f"ON CONFLICT (user_id, chat_id) DO UPDATE SET balance=user_mora.balance+EXCLUDED.balance",
                (uid, chat_id, total_mora),
            )
        else:
            cur.execute(
                "INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,?) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=user_mora.balance+excluded.balance",
                (uid, chat_id, total_mora),
            )
        conn.commit()
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_bal = (cur.fetchone() or [0])[0]
        conn.close()
        return JsonResponse({"ok": True, "sold": total_sold, "mora": total_mora, "balance": new_bal}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_shop_set_title(request):
    """POST /api/shop/set_title — buy/update custom title for CUSTOM_TITLE_PRICE mora."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)
    uid, err = _require_auth(request, headers)
    if err:
        return err
    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0")))
        title = str(body.get("title", "")).strip()[:30]
        wallet_type = str(body.get("wallet_type", "personal")).lower()
        if wallet_type not in ("personal", "family"):
            wallet_type = "personal"
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)
    if not title:
        return JsonResponse({"error": "title cannot be empty"}, status=400, headers=headers)
    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)
    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        if wallet_type == "family":
            cur.execute(f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            if not cur.fetchone():
                conn.close()
                return JsonResponse({"error": "Нет семейного кошелька"}, status=400, headers=headers)
            cur.execute(f"SELECT balance FROM family_wallet WHERE chat_id={ph} AND user_id={ph}", (chat_id, uid))
            fam_bal = (cur.fetchone() or [0])[0]
            if fam_bal < _CUSTOM_TITLE_PRICE:
                conn.close()
                return JsonResponse({"error": f"Недостаточно моры. Нужно {_CUSTOM_TITLE_PRICE} 🪙"}, status=400, headers=headers)
            cur.execute(f"UPDATE family_wallet SET balance=balance-{ph} WHERE chat_id={ph} AND user_id={ph}", (_CUSTOM_TITLE_PRICE, chat_id, uid))
        else:
            cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            row = cur.fetchone()
            balance = row[0] if row else 0
            if balance < _CUSTOM_TITLE_PRICE:
                conn.close()
                return JsonResponse({"error": f"Недостаточно моры. Нужно {_CUSTOM_TITLE_PRICE} 🪙"}, status=400, headers=headers)
            cur.execute(
                f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph}",
                (_CUSTOM_TITLE_PRICE, uid, chat_id),
            )
        if db_type == "pg":
            cur.execute(
                f"INSERT INTO user_stats (user_id, chat_id, custom_title) VALUES ({ph},{ph},{ph}) "
                f"ON CONFLICT (user_id, chat_id) DO UPDATE SET custom_title=EXCLUDED.custom_title",
                (uid, chat_id, title),
            )
        else:
            cur.execute(
                "INSERT INTO user_stats (user_id, chat_id, custom_title) VALUES (?,?,?) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET custom_title=excluded.custom_title",
                (uid, chat_id, title),
            )
        conn.commit()
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_bal = (cur.fetchone() or [0])[0]
        conn.close()
        return JsonResponse({"ok": True, "title": title, "balance": new_bal}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Gacha Roll ───────────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_gacha_roll(request):
    """POST /api/gacha/roll — perform gacha roll(s) from mini app."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body        = json.loads(request.body)
        chat_id     = int(str(body.get("chat_id", "0")))
        count       = int(body.get("count", 1))
        wallet_type = str(body.get("wallet_type", "personal")).lower()
        if wallet_type not in ("personal", "family"):
            wallet_type = "personal"
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if count not in (1, 10):
        return JsonResponse({"error": "count must be 1 or 10"}, status=400, headers=headers)
    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)

    try:
        from api.gacha import gacha_roll as _bot_gacha_roll
        from asgiref.sync import async_to_sync as _a2s
        result = _a2s(_bot_gacha_roll)(uid, chat_id, count, wallet_type)

        # Log to chat
        try:
            _rarity_emoji = {"junk": "⚪", "common": "🟢", "rare": "🟣", "legendary": "🟡"}
            loot_text = " ".join(
                f"{_rarity_emoji.get(it['rarity'], '⚪')} {it['name']}"
                for it in result["items"]
            )
            roll_type = f"{count}x крутка" if count > 1 else "Одиночная крутка"
            _a2s(log_action_to_chat)(
                uid, chat_id,
                f"🎲 {roll_type} гачи (-{result['spent']} 🪙)",
                f"Выпало: {loot_text}",
            )
        except Exception:
            pass

        return JsonResponse({
            "ok":         True,
            "items":      result["items"],
            "balance":    result["new_balance"],
            "pity":       result["pity"],
            "spent":      result["spent"],
            "quest_done": result["quest_done"],
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Bonds Buy / Sell ─────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_bonds_buy(request):
    """POST /api/bonds/buy — buy bonds from mini app."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0")))
        bond_key = str(body.get("bond_key", "")).lower().strip()
        amount = int(body.get("amount", 0))
        wallet = str(body.get("wallet", "personal"))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if bond_key not in _BOND_DEFAULTS_SYNC:
        return JsonResponse({"error": f"Неизвестная облигация: {bond_key}"}, status=400, headers=headers)
    if amount <= 0:
        return JsonResponse({"error": "amount must be positive"}, status=400, headers=headers)
    if wallet not in ("personal", "family"):
        wallet = "personal"

    from api.bonds import buy_bond as _api_buy
    from asgiref.sync import async_to_sync as _a2s
    try:
        result = _a2s(_api_buy)(uid, chat_id, bond_key, amount, wallet)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)


@csrf_exempt
def miniapp_bonds_sell(request):
    """POST /api/bonds/sell — sell bonds from mini app."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0")))
        bond_key = str(body.get("bond_key", "")).lower().strip()
        amount = int(body.get("amount", 0))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if bond_key not in _BOND_DEFAULTS_SYNC:
        return JsonResponse({"error": "Неизвестная облигация"}, status=400, headers=headers)
    if amount <= 0:
        return JsonResponse({"error": "amount must be positive"}, status=400, headers=headers)

    from api.bonds import sell_bond as _api_sell
    from asgiref.sync import async_to_sync as _a2s
    try:
        result = _a2s(_api_sell)(uid, chat_id, bond_key, amount)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)


# ─── 🏦 Bank (deposits) ───────────────────────────────────────────────────────

@csrf_exempt
def miniapp_bank(request):
    """GET /api/bank?chat_id=X — returns user deposits + balance."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    from api.bank import get_bank_info as _api_bank_info
    from asgiref.sync import async_to_sync as _a2s
    try:
        result = _a2s(_api_bank_info)(uid, chat_id)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)


@csrf_exempt
def miniapp_bank_deposit(request):
    """POST /api/bank/deposit {chat_id, plan_key, amount, wallet} — open a deposit."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))
    plan_key = str(data.get("plan_key", ""))
    amount = int(data.get("amount", 0))
    wallet = str(data.get("wallet", "personal"))

    if plan_key not in _BANK_PLANS_SYNC:
        return JsonResponse({"error": "Invalid plan"}, status=400, headers=headers)
    if not (_BANK_MIN_DEPOSIT <= amount <= _BANK_MAX_DEPOSIT):
        return JsonResponse(
            {"error": f"Amount must be {_BANK_MIN_DEPOSIT}–{_BANK_MAX_DEPOSIT}"}, status=400, headers=headers
        )
    if wallet not in ("personal", "family"):
        wallet = "personal"

    from api.bank import deposit as _api_deposit
    from asgiref.sync import async_to_sync as _a2s
    try:
        result = _a2s(_api_deposit)(uid, chat_id, plan_key, amount, wallet)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)


@csrf_exempt
def miniapp_bank_withdraw(request):
    """POST /api/bank/withdraw {chat_id, deposit_id} — withdraw a deposit."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))
    deposit_id = int(data.get("deposit_id", 0))

    from api.bank import withdraw as _api_withdraw
    from asgiref.sync import async_to_sync as _a2s
    try:
        result = _a2s(_api_withdraw)(uid, chat_id, deposit_id)
    except ValueError as e:
        status_code = 404 if "не найден" in str(e).lower() else 400
        return JsonResponse({"error": str(e)}, status=status_code, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)


# ─── Pet Walk & Feed ──────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_pet_walk(request):
    """POST /api/pet/walk — start a 3-hour pet walk.

    ЕДИНЫЙ ИСТОЧНИК ПРАВДЫ: вся логика вынесена в start_pet_walk_full()
    в PredvestnikBot/database/db.py. Здесь — только HTTP-обёртка.
    """
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0")))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    try:
        from database.db import start_pet_walk_full
        from asgiref.sync import async_to_sync
        result = async_to_sync(start_pet_walk_full)(uid, chat_id)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    if not result["ok"]:
        status_code = 429 if result.get("mins_left") else 400
        return JsonResponse({"error": result["error"]}, status=status_code, headers=headers)

    emoji = {"cat": "🐱", "dog": "🐶"}.get(result.get("pet_type", ""), "🐾")
    return JsonResponse(
        {
            "ok": True,
            "fatigue": result["fatigue"],
            "reduced": result["fatigue_reduced"],
            "pet_emoji": emoji,
            "pet_name": result["pet_name"],
            "walk_mins": result["walk_mins"],
            "reward": result["reward"],
        },
        json_dumps_params={"ensure_ascii": False},
        headers=headers,
    )


@csrf_exempt
def miniapp_pet_feed(request):
    """POST /api/pet/feed — feed pet with food item."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0")))
        food_key = str(body.get("food_key", "")).strip()
        wallet_type = str(body.get("wallet_type", "personal")).lower()
        if wallet_type not in ("personal", "family"):
            wallet_type = "personal"
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    food = _FOOD_ITEMS.get(food_key)
    if not food:
        return JsonResponse({"error": f"Неизвестная еда: {food_key}"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.pets import feed_pet
        result = _a2s(feed_pet)(uid, chat_id, food_key, wallet_type)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400,
                            json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    # Log feeding action to chat
    from asgiref.sync import async_to_sync as _a2s
    wallet_text = f" из семейного кошелька" if wallet_type == "family" else ""
    _a2s(log_action_to_chat)(
        uid, chat_id,
        f"{result['pet_emoji']} Покормил питомца {result['pet_name']}",
        f"Еда: {result['food_name']} (-{food['price']} 🪙{wallet_text})\nУсталость: -{result['reduced']}",
    )

    return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)


# ─── Shop Catalog & Buy ───────────────────────────────────────────────────────

@csrf_exempt
def miniapp_shop_catalog(request):
    """GET /api/shop/catalog?chat_id=X — full shop catalog with ownership."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.shop import get_catalog
        data = _a2s(get_catalog)(uid, chat_id)
        return JsonResponse(data, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_shop_buy(request):
    """POST /api/shop/buy — buy frame/cosmetic/vip from mini app."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0")))
        item_type = str(body.get("item_type", "")).lower()
        item_key = str(body.get("item_key", "")).lower()
        equip = bool(body.get("equip", True))
        wallet_type = str(body.get("wallet_type", "personal")).lower()
        if wallet_type not in ("personal", "family"):
            wallet_type = "personal"
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    if item_type not in ("frame", "cosmetic", "vip", "potion", "pet_color"):
        return JsonResponse({"error": "item_type must be frame/cosmetic/vip/potion/pet_color"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.shop import buy_item
        result = _a2s(buy_item)(uid, chat_id, item_type, item_key, wallet_type, equip)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400,
                            json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Profile themes (list / set active) ──────────────────────────────────────

@csrf_exempt
def miniapp_themes(request):
    """GET /api/themes?chat_id=X — list all themes with ownership status.
       POST /api/themes — activate an owned theme {chat_id, theme_key}."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        from config import PROFILE_THEMES
    except ImportError:
        return JsonResponse({"error": "themes config unavailable"}, status=503, headers=headers)

    if request.method == "GET":
        chat_id_str = request.GET.get("chat_id", "")
        if not chat_id_str.lstrip("-").isdigit():
            return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
        chat_id = int(chat_id_str)
        try:
            conn, db_type = _get_bot_db_connection()
        except Exception as exc:
            return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)
        try:
            cur = conn.cursor()
            ph = "%s" if db_type == "pg" else "?"
            cur.execute(
                f"SELECT theme_key FROM user_themes WHERE user_id={ph} AND chat_id={ph}",
                (uid, chat_id),
            )
            owned_keys = {r[0] for r in cur.fetchall()}
            owned_keys.add("default")
            cur.execute(f"SELECT active_theme FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            mora_row = cur.fetchone()
            active = (mora_row[0] if mora_row else None) or "default"
            conn.close()
        except Exception as exc:
            try:
                conn.close()
            except Exception:
                pass
            logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

        themes_out = []
        for key, info in PROFILE_THEMES.items():
            themes_out.append({
                "key": key,
                "name": info["name"],
                "tier": info.get("tier", "common"),
                "source": info.get("source", "shop"),
                "price": info.get("price", 0),
                "header": info.get("header", ""),
                "separator": info.get("separator", ""),
                "footer": info.get("footer", ""),
                "owned": key in owned_keys,
                "active": key == active,
            })
        return JsonResponse({"themes": themes_out, "active": active},
                            json_dumps_params={"ensure_ascii": False}, headers=headers)

    if request.method == "POST":
        try:
            body = json.loads(request.body)
            chat_id = int(str(body.get("chat_id", "0")))
            theme_key = str(body.get("theme_key", "")).strip()
        except Exception:
            return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

        if not theme_key or theme_key not in PROFILE_THEMES:
            return JsonResponse({"error": "Unknown theme"}, status=400, headers=headers)
        try:
            conn, db_type = _get_bot_db_connection()
        except Exception as exc:
            return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)
        try:
            cur = conn.cursor()
            ph = "%s" if db_type == "pg" else "?"
            if theme_key != "default":
                cur.execute(
                    f"SELECT 1 FROM user_themes WHERE user_id={ph} AND chat_id={ph} AND theme_key={ph}",
                    (uid, chat_id, theme_key),
                )
                if not cur.fetchone():
                    conn.close()
                    return JsonResponse({"error": "Тема не куплена"}, status=403, headers=headers)
            cur.execute(
                f"UPDATE user_mora SET active_theme={ph} WHERE user_id={ph} AND chat_id={ph}",
                (theme_key, uid, chat_id),
            )
            conn.commit()
            conn.close()
            return JsonResponse({"ok": True, "active": theme_key}, headers=headers)
        except Exception as exc:
            try:
                conn.close()
            except Exception:
                pass
            logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)


# ─── Public profile (privacy-filtered view for other users) ──────────────────

@csrf_exempt
def miniapp_public_profile(request):
    """GET /api/public_profile?user_id=X&chat_id=Y
    Returns public data of another user.
    Shows: level, xp, vip, title, frame, theme + cosmetics, equipped items, rpg stats, marriage, pet.
    HIDES: mora balance, non-equipped inventory items."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    target_id_str = request.GET.get("user_id", "")
    chat_id_str = request.GET.get("chat_id", "")
    if not target_id_str.lstrip("-").isdigit() or not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "user_id and chat_id required"}, status=400, headers=headers)
    target_id = int(target_id_str)
    chat_id = int(chat_id_str)

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Basic user info
        cur.execute(f"SELECT full_name FROM users WHERE user_id={ph}", (target_id,))
        user_row = cur.fetchone()
        if not user_row:
            conn.close()
            return JsonResponse({"error": "User not found"}, status=404, headers=headers)
        full_name = user_row[0]

        # Stats (level, xp, rank, custom_title, activity, warns, messages)
        cur.execute(
            f"SELECT xp, COALESCE(level,1), COALESCE(rank,'user'), custom_title, "
            f"first_active, last_active, COALESCE(warns,0), COALESCE(message_count,0) "
            f"FROM user_stats WHERE user_id={ph} AND chat_id={ph}",
            (target_id, chat_id),
        )
        stats_row = cur.fetchone()
        xp = stats_row[0] if stats_row else 0
        level = stats_row[1] if stats_row else 1
        rank = stats_row[2] if stats_row else "user"
        custom_title = stats_row[3] if stats_row else None
        pub_first_active = str(stats_row[4]) if stats_row and stats_row[4] else None
        pub_last_active = str(stats_row[5]) if stats_row and stats_row[5] else None
        pub_warns = stats_row[6] if stats_row else 0
        pub_message_count = stats_row[7] if stats_row else 0

        # Mora row (vip, frame, theme)
        cur.execute(
            f"SELECT vip, top_frame, active_theme FROM user_mora WHERE user_id={ph} AND chat_id={ph}",
            (target_id, chat_id),
        )
        mora_r = cur.fetchone()
        vip = bool(mora_r[0]) if mora_r else False
        active_frame = (mora_r[1] if mora_r else None) or "default"
        active_theme = (mora_r[2] if mora_r else None) or "default"

        # Resolve theme visual data from config
        theme_header = "👤 <b>Профиль</b>"
        theme_separator = "━━━━━━━━━━━━━━━━━━━━"
        theme_footer = ""
        theme_name = "Стандарт"
        try:
            from config import PROFILE_THEMES
            t = PROFILE_THEMES.get(active_theme, PROFILE_THEMES.get("default", {}))
            theme_header = t.get("header", theme_header)
            theme_separator = t.get("separator", theme_separator)
            theme_footer = t.get("footer", theme_footer)
            theme_name = t.get("name", theme_name)
        except Exception:
            pass

        # RPG stats + equipped items
        rpg = {"hp": 100, "atk": 50, "def": 20, "crit": 0.05}
        equipped_items = []
        cur.execute(
            f"SELECT base_hp, base_atk, base_def, base_crit, weapon_id, armor_id, artifact_id "
            f"FROM user_rpg_stats WHERE user_id={ph} AND chat_id={ph}",
            (target_id, chat_id),
        )
        rpg_row = cur.fetchone()
        if rpg_row:
            rpg = {"hp": rpg_row[0], "atk": rpg_row[1], "def": rpg_row[2], "crit": rpg_row[3]}
            eq_ids = [eid for eid in [rpg_row[4], rpg_row[5], rpg_row[6]] if eid]
            if eq_ids:
                placeholders = ",".join([ph] * len(eq_ids))
                cur.execute(
                    f"SELECT id, item_name, rarity, slot, COALESCE(atk,0), COALESCE(def_val,0), "
                    f"COALESCE(hp,0), COALESCE(crit_rate,0) FROM gacha_inventory WHERE id IN ({placeholders})",
                    tuple(eq_ids),
                )
                for er in cur.fetchall():
                    rpg["atk"] += er[4]
                    rpg["def"] += er[5]
                    rpg["hp"] += er[6]
                    rpg["crit"] += er[7]
                    equipped_items.append({"name": er[1], "rarity": er[2], "slot": er[3] or "gear"})
        # Also grab equipped=1 items not already included via rpg_stats
        cur.execute(
            f"SELECT item_name, rarity, slot FROM gacha_inventory "
            f"WHERE user_id={ph} AND chat_id={ph} AND equipped=1",
            (target_id, chat_id),
        )
        for r in cur.fetchall():
            if not any(i["name"] == r[0] for i in equipped_items):
                equipped_items.append({"name": r[0], "rarity": r[1], "slot": r[2] or "gear"})

        # Marriage partner
        partner_name = None
        partner_id = None
        cur.execute(
            f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}",
            (target_id, chat_id),
        )
        m_row = cur.fetchone()
        if m_row:
            partner_id = m_row[0]
            cur.execute(f"SELECT full_name FROM users WHERE user_id={ph}", (partner_id,))
            pn = cur.fetchone()
            partner_name = pn[0] if pn else f"user_{partner_id}"

        # Pet (basic public info)
        pet_info = None
        cur.execute(
            f"SELECT pet_type, name, COALESCE(fatigue,0), walk_end_at FROM pets "
            f"WHERE user_id={ph} AND chat_id={ph}",
            (target_id, chat_id),
        )
        pet_row = cur.fetchone()
        if pet_row:
            from datetime import datetime as _dt2, timezone as _tz2
            ptype, pname, pfatigue, pwalk_end = pet_row
            emoji = {"cat": "🐱", "dog": "🐶"}.get(ptype, "🐾")
            on_walk = False
            if pwalk_end:
                try:
                    end_dt = _dt2.fromisoformat(str(pwalk_end))
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=_tz2.utc)
                    if (end_dt - _dt2.now(_tz2.utc)).total_seconds() > 0:
                        on_walk = True
                except Exception:
                    pass
            pet_info = {
                "type": ptype, "name": pname or "Питомец",
                "emoji": emoji, "fatigue": pfatigue, "on_walk": on_walk,
            }

        conn.close()
        return JsonResponse({
            "uid": target_id,
            "name": full_name,
            "level": level,
            "xp": xp,
            "xp_max": _xp_for_level(level + 1),
            "rank": rank,
            "vip": vip,
            "custom_title": custom_title or "",
            "active_frame": active_frame,
            "active_theme": active_theme,
            "theme_header": theme_header,
            "theme_separator": theme_separator,
            "theme_footer": theme_footer,
            "theme_name": theme_name,
            "rpg": rpg,
            "equipped_items": equipped_items,
            "partner_name": partner_name,
            "partner_id": partner_id,
            "pet": pet_info,
            "is_own": target_id == uid,
            "first_active": pub_first_active,
            "last_active": pub_last_active,
            "warns": pub_warns,
            "message_count": pub_message_count,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ===============================================================================
# -- ENHANCEMENT SYSTEM ---------------------------------------------------------
# ===============================================================================

@csrf_exempt
def miniapp_enhance_item(request):
    """POST /api/enhance - enhance an equipped RPG item."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    item_id = data.get("item_id")
    chat_id = data.get("chat_id")

    if not item_id or not chat_id:
        return JsonResponse({"error": "item_id and chat_id required"}, status=400, headers=headers)

    try:
        from database.db import enhance_item
        from api.economy import get_balance
        from asgiref.sync import async_to_sync as _a2s

        success, message, new_level = _a2s(enhance_item)(uid, chat_id, item_id)

        if success:
            _a2s(log_action_to_chat)(
                uid, chat_id,
                f"✨ Заточил предмет до +{new_level}",
                message
            )

        balance = _a2s(get_balance)(uid, chat_id)

        return JsonResponse({
            "success": success,
            "message": message,
            "enhancement_level": new_level,
            "balance": balance,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt  
def miniapp_consume_potion(request):
    """POST /api/consume_potion - consume a potion to gain buff."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    item_id = data.get("item_id")
    chat_id = data.get("chat_id")

    if not item_id or not chat_id:
        return JsonResponse({"error": "item_id and chat_id required"}, status=400, headers=headers)

    try:
        from database.db import consume_potion
        from asgiref.sync import async_to_sync
        
        success, message = async_to_sync(consume_potion)(uid, chat_id, item_id)
        
        return JsonResponse({
            "success": success,
            "message": message,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_batch_sell(request):
    """POST /api/batch_sell - sell multiple items at once."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)  
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    chat_id = data.get("chat_id")

    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)

    # Accept new format: items=[{id, qty}] or backward-compat item_ids=[int]
    items_list = data.get("items")
    item_ids_raw = data.get("item_ids", [])
    sell_qtys = None
    if items_list and isinstance(items_list, list):
        try:
            item_ids = [int(x["id"]) for x in items_list if isinstance(x, dict)]
            sell_qtys = {int(x["id"]): max(1, int(x.get("qty", 1))) for x in items_list if isinstance(x, dict)}
        except (ValueError, KeyError):
            return JsonResponse({"error": "invalid items format"}, status=400, headers=headers)
    elif isinstance(item_ids_raw, list):
        item_ids = item_ids_raw
    else:
        return JsonResponse({"error": "items or item_ids required"}, status=400, headers=headers)

    try:
        from database.db import batch_sell_items
        from api.economy import get_balance
        from asgiref.sync import async_to_sync as _a2s

        sold_count, total_mora = _a2s(batch_sell_items)(uid, chat_id, item_ids, sell_qtys)

        if sold_count > 0:
            _a2s(log_action_to_chat)(
                uid, chat_id,
                f"💰 Продал {sold_count} предметов",
                f"Получено: +{total_mora} 🪙"
            )

        balance = _a2s(get_balance)(uid, chat_id)

        return JsonResponse({
            "sold": sold_count,
            "mora": total_mora,
            "balance": balance,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# --- Couple Boss System (Married Pairs) --------------------------------------

@csrf_exempt
def miniapp_couple_boss_status(request):
    """GET /api/couple_boss/status?chat_id=X - get couple boss session status."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    try:
        conn, db_type = _get_bot_db_connection()
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        
        # Check if user is married
        cur.execute(f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        marriage_row = cur.fetchone()
        if not marriage_row:
            conn.close()
            return JsonResponse({"error": "No active marriage found in this chat"}, status=400, headers=headers)
        
        partner_id = marriage_row[0]
        user_a_id = min(uid, partner_id)
        user_b_id = max(uid, partner_id)
        
        # Get current session
        from datetime import timezone
        import datetime
        today = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        cur.execute(f"""SELECT * FROM couple_boss_sessions 
                     WHERE user_a_id={ph} AND user_b_id={ph} AND chat_id={ph} AND session_date={ph} AND is_completed=0""", 
                     (user_a_id, user_b_id, chat_id, today))
        session = cur.fetchone()
        
        # Get progress
        cur.execute(f"SELECT max_level FROM couple_boss_progress WHERE user_a_id={ph} AND user_b_id={ph} AND chat_id={ph}", 
                   (user_a_id, user_b_id, chat_id))
        progress_row = cur.fetchone()
        max_level = progress_row[0] if progress_row else 0
        
        # Get user names
        cur.execute(f"SELECT full_name FROM users WHERE user_id={ph}", (uid,))
        user_name = (cur.fetchone() or ["Player"])[0]
        cur.execute(f"SELECT full_name FROM users WHERE user_id={ph}", (partner_id,))
        partner_name = (cur.fetchone() or ["Partner"])[0]
        
        conn.close()
        
        result = {
            "married": True,
            "partner_id": partner_id,
            "partner_name": partner_name,
            "max_level_completed": max_level,
            "available_levels": list(range(1, max_level + 2)),  # Can challenge next level
        }
        
        if session:
            # Active session exists
            session_data = dict(zip([
                "id", "user_a_id", "user_b_id", "chat_id", "boss_level", "boss_max_hp", "boss_current_hp",
                "user_a_damage", "user_b_damage", "user_a_hits", "user_b_hits", "user_a_aggro", "user_b_aggro",
                "is_completed", "is_repeat", "session_date", "completed_at"
            ], session))
            
            hp_pct = (session_data["boss_current_hp"] / session_data["boss_max_hp"]) * 100
            
            # Determine which user is A/B
            if uid == user_a_id:
                my_damage = session_data["user_a_damage"]
                my_hits = session_data["user_a_hits"]
                partner_damage = session_data["user_b_damage"]
                partner_hits = session_data["user_b_hits"]
            else:
                my_damage = session_data["user_b_damage"]
                my_hits = session_data["user_b_hits"]
                partner_damage = session_data["user_a_damage"]
                partner_hits = session_data["user_a_hits"]
                
            result.update({
                "has_active_session": True,
                "boss_level": session_data["boss_level"],
                "boss_max_hp": session_data["boss_max_hp"],
                "boss_current_hp": session_data["boss_current_hp"],
                "boss_hp_percent": round(hp_pct, 1),
                "my_damage": my_damage,
                "my_hits": my_hits,
                "partner_damage": partner_damage,
                "partner_hits": partner_hits,
                "total_damage": my_damage + partner_damage,
                "is_repeat": session_data["is_repeat"],
                "resistance_active": session_data["user_a_hits"] > 0 and session_data["user_b_hits"] > 0,
            })
        else:
            result["has_active_session"] = False
        
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
        
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_couple_boss_start(request):
    """POST /api/couple_boss/start - start new couple boss session."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
        chat_id = int(data.get("chat_id", 0))
        boss_level = int(data.get("boss_level", 1))
    except Exception:
        return JsonResponse({"error": "invalid JSON or chat_id/boss_level"}, status=400, headers=headers)

    try:
        conn, db_type = _get_bot_db_connection()
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        
        # Check if user is married
        cur.execute(f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        marriage_row = cur.fetchone()
        if not marriage_row:
            conn.close()
            return JsonResponse({"error": "No active marriage found in this chat"}, status=400, headers=headers)
        
        partner_id = marriage_row[0]
        user_a_id = min(uid, partner_id)
        user_b_id = max(uid, partner_id)
        
        # Check if session already exists
        from datetime import timezone
        import datetime
        today = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        cur.execute(f"""SELECT 1 FROM couple_boss_sessions 
                     WHERE user_a_id={ph} AND user_b_id={ph} AND chat_id={ph} AND session_date={ph} AND is_completed=0""", 
                     (user_a_id, user_b_id, chat_id, today))
        if cur.fetchone():
            conn.close()
            return JsonResponse({"error": "Active boss session already exists for today"}, status=400, headers=headers)
        
        # Validate boss level
        if boss_level < 1 or boss_level > 50:  # Reasonable limit
            conn.close()
            return JsonResponse({"error": "Invalid boss level"}, status=400, headers=headers)
        
        # Check if level is available (can't skip levels)
        cur.execute(f"SELECT max_level FROM couple_boss_progress WHERE user_a_id={ph} AND user_b_id={ph} AND chat_id={ph}", 
                   (user_a_id, user_b_id, chat_id))
        progress_row = cur.fetchone()
        max_level = progress_row[0] if progress_row else 0
        
        if boss_level > max_level + 1:
            conn.close()
            return JsonResponse({"error": f"Can only challenge level {max_level + 1}"}, status=400, headers=headers)
        
        conn.close()
        
        # Create session using existing function
        from database.db import create_couple_boss_session
        from asgiref.sync import async_to_sync
        
        session = async_to_sync(create_couple_boss_session)(user_a_id, user_b_id, chat_id, boss_level)
        
        return JsonResponse({
            "ok": True,
            "session_id": session["id"],
            "boss_level": session["boss_level"],
            "boss_max_hp": session["boss_max_hp"],
            "is_repeat": session["is_repeat"],
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
        
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_couple_boss_attack(request):
    """POST /api/couple_boss/attack - attack couple boss."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
        chat_id = int(data.get("chat_id", 0))
    except Exception:
        return JsonResponse({"error": "invalid JSON or chat_id"}, status=400, headers=headers)

    try:
        conn, db_type = _get_bot_db_connection()
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        
        # Check if user is married
        cur.execute(f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        marriage_row = cur.fetchone()
        if not marriage_row:
            conn.close()
            return JsonResponse({"error": "No active marriage found in this chat"}, status=400, headers=headers)
        
        partner_id = marriage_row[0]
        user_a_id = min(uid, partner_id)
        user_b_id = max(uid, partner_id)
        
        # Get current session
        from datetime import timezone
        import datetime
        today = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        cur.execute(f"""SELECT * FROM couple_boss_sessions 
                     WHERE user_a_id={ph} AND user_b_id={ph} AND chat_id={ph} AND session_date={ph} AND is_completed=0""", 
                     (user_a_id, user_b_id, chat_id, today))
        session_row = cur.fetchone()
        if not session_row:
            conn.close()
            return JsonResponse({"error": "No active boss session"}, status=400, headers=headers)
        
        # Get user's combat stats (stats stored directly in gacha_inventory rows)
        cur.execute(f"""SELECT
                     COALESCE(SUM(COALESCE(gi.atk, 0) + gi.enhancement_level * COALESCE(gi.atk, 0) * 0.1), 0),
                     COALESCE(SUM(COALESCE(gi.def_val, 0) + gi.enhancement_level * COALESCE(gi.def_val, 0) * 0.1), 0),
                     COALESCE(SUM(COALESCE(gi.hp, 0) + gi.enhancement_level * COALESCE(gi.hp, 0) * 0.1), 0),
                     COALESCE(SUM(COALESCE(gi.crit_rate, 0)), 0)
                 FROM gacha_inventory gi
                 WHERE gi.user_id={ph} AND gi.chat_id={ph} AND gi.equipped=1""", (uid, chat_id))
        stats_row = cur.fetchone()
        user_stats = {
            "atk": int(stats_row[0]) if stats_row and stats_row[0] else 50,  # Base ATK
            "def": int(stats_row[1]) if stats_row and stats_row[1] else 20,  # Base DEF
            "hp": int(stats_row[2]) if stats_row and stats_row[2] else 100,   # Base HP
            "crit_rate": float(stats_row[3]) if stats_row and stats_row[3] else 0.05  # Base crit
        }
        
        conn.close()
        
        # Convert session row to dict
        session_data = dict(zip([
            "id", "user_a_id", "user_b_id", "chat_id", "boss_level", "boss_max_hp", "boss_current_hp",
            "user_a_damage", "user_b_damage", "user_a_hits", "user_b_hits", "user_a_aggro", "user_b_aggro",
            "is_completed", "is_repeat", "session_date", "completed_at"
        ], session_row))
        
        # Apply damage using existing function
        from database.db import apply_couple_boss_damage
        from asgiref.sync import async_to_sync
        import random
        
        # Base damage calculation
        base_damage = random.randint(int(user_stats["atk"] * 0.8), int(user_stats["atk"] * 1.2)) + 50
        
        result = async_to_sync(apply_couple_boss_damage)(uid, session_data, base_damage, user_stats)
        
        response = {
            "ok": True,
            "damage_dealt": result["damage_dealt"],
            "boss_hp": result["boss_hp"],
            "boss_defeated": result["boss_defeated"],
            "resistance_active": result["resistance_active"],
            "crit": result["crit"],
        }
        
        if result["boss_retaliation"]:
            response["boss_retaliation"] = result["boss_retaliation"]
            if result["boss_retaliation"]["target"] == uid:
                response["retaliation_message"] = f"Boss attacked you for {result['boss_retaliation']['damage']} HP!"
            else:
                response["retaliation_message"] = f"Boss attacked your partner for {result['boss_retaliation']['damage']} HP!"
        
        if result["boss_defeated"]:
            # Calculate rewards
            from database.db import get_couple_boss_rewards, add_mora, add_xp_in_chat
            rewards = async_to_sync(get_couple_boss_rewards)(session_data)
            
            # Give rewards to both players
            try:
                for player_id in [user_a_id, user_b_id]:
                    async_to_sync(add_mora)(player_id, chat_id, rewards["mora_each"])
                    async_to_sync(add_xp_in_chat)(player_id, chat_id, rewards["xp_each"])
                
                response["rewards"] = {
                    "mora": rewards["mora_each"],
                    "xp": rewards["xp_each"],
                    "is_repeat": rewards["is_repeat"],
                }
                
            except Exception as e:
                response["rewards_error"] = str(e)
        
        return JsonResponse(response, json_dumps_params={"ensure_ascii": False}, headers=headers)
        
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Solo Boss ────────────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_solo_boss_status(request):
    """GET /api/solo_boss/status?chat_id=X — current solo boss session for the user."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    from database.db import get_solo_boss_session, get_solo_boss_progress
    from asgiref.sync import async_to_sync

    session = async_to_sync(get_solo_boss_session)(uid, chat_id)
    progress = async_to_sync(get_solo_boss_progress)(uid, chat_id)

    next_level = (progress["max_level"] + 1) if progress else 1

    # Check if user completed a session today (get_solo_boss_session only returns incomplete)
    completed_today = None
    if not session:
        import datetime as _dt
        today_str = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
        try:
            conn, db_type = _get_bot_db_connection()
            cur = conn.cursor()
            ph = "%s" if db_type == "pg" else "?"
            cur.execute(
                f"SELECT * FROM solo_boss_sessions WHERE user_id={ph} AND chat_id={ph} AND session_date={ph} AND is_completed=1",
                (uid, chat_id, today_str))
            crow = cur.fetchone()
            conn.close()
            if crow:
                cols = [d[0] for d in cur.description]
                completed_today = dict(zip(cols, crow))
        except Exception:
            try: conn.close()
            except Exception: pass

    return JsonResponse({
        "session": session or completed_today,
        "progress": progress,
        "next_level": next_level,
    }, json_dumps_params={"ensure_ascii": False}, headers=headers)


@csrf_exempt
def miniapp_solo_boss_start(request):
    """POST /api/solo_boss/start — start a new solo boss session."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body)
        chat_id = int(body.get("chat_id", 0))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)

    from database.db import get_solo_boss_session, get_solo_boss_progress, create_solo_boss_session
    from asgiref.sync import async_to_sync

    # Check no active session today
    existing = async_to_sync(get_solo_boss_session)(uid, chat_id)
    if existing and not existing.get("is_completed"):
        return JsonResponse({"error": "У тебя уже есть активная битва с боссом сегодня!",
                             "session": existing},
                            status=400, json_dumps_params={"ensure_ascii": False}, headers=headers)

    progress = async_to_sync(get_solo_boss_progress)(uid, chat_id)
    boss_level = (progress["max_level"] + 1) if progress else 1

    session = async_to_sync(create_solo_boss_session)(uid, chat_id, boss_level)
    return JsonResponse({"ok": True, "session": session},
                        json_dumps_params={"ensure_ascii": False}, headers=headers)


@csrf_exempt
def miniapp_solo_boss_attack(request):
    """POST /api/solo_boss/attack — attack solo boss."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body)
        chat_id = int(body.get("chat_id", 0))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)

    from database.db import get_solo_boss_session, apply_solo_boss_damage
    from asgiref.sync import async_to_sync

    session = async_to_sync(get_solo_boss_session)(uid, chat_id)
    if not session:
        return JsonResponse({"error": "Нет активной битвы — сначала запусти босса!"},
                            status=400, json_dumps_params={"ensure_ascii": False}, headers=headers)
    if session.get("is_completed"):
        return JsonResponse({"error": "Эта битва уже завершена."},
                            status=400, json_dumps_params={"ensure_ascii": False}, headers=headers)

    # Get user attack stat from equipped items
    try:
        conn, db_type = _get_bot_db_connection()
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        # Stats stored directly in gacha_inventory (no item_metadata table needed)
        cur.execute(f"""SELECT COALESCE(SUM(COALESCE(gi.atk, 0) + gi.enhancement_level * COALESCE(gi.atk, 0) * 0.1), 50)
                    FROM gacha_inventory gi
                    WHERE gi.user_id={ph} AND gi.chat_id={ph} AND gi.equipped=1""", (uid, chat_id))
        atk_row = cur.fetchone()
        base_atk = int(atk_row[0]) if atk_row and atk_row[0] else 50
        conn.close()
    except Exception:
        try: conn.close()
        except Exception: pass
        base_atk = 50

    import random
    damage = random.randint(int(base_atk * 0.8), int(base_atk * 1.2)) + 50

    result = async_to_sync(apply_solo_boss_damage)(uid, session, damage)

    response = {
        "ok": True,
        "damage_dealt": result["damage_dealt"],
        "crit": result["crit"],
        "boss_hp": result["boss_hp"],
        "boss_defeated": result["boss_defeated"],
    }

    if result["boss_defeated"]:
        # Give rewards
        mora_reward = 500 + (session["boss_level"] - 1) * 200
        xp_reward = 300 + (session["boss_level"] - 1) * 100
        try:
            from database.db import add_mora, add_xp_in_chat
            async_to_sync(add_mora)(uid, chat_id, mora_reward)
            async_to_sync(add_xp_in_chat)(uid, chat_id, xp_reward)
            response["rewards"] = {"mora": mora_reward, "xp": xp_reward}
        except Exception as e:
            response["rewards_error"] = str(e)

    return JsonResponse(response, json_dumps_params={"ensure_ascii": False}, headers=headers)


# ─── НОВЫЕ ФУНКЦИИ: Аватарки из Telegram ─────────────────────────────────────

def get_telegram_avatar_url(user_id: int) -> str | None:
    """Получить URL аватарки пользователя из Telegram API."""
    if not _BOT_TOKEN:
        return None
    
    try:
        import requests
        url = f"https://api.telegram.org/bot{_BOT_TOKEN}/getUserProfilePhotos"
        response = requests.get(url, params={
            "user_id": user_id,
            "limit": 1
        }, timeout=5)
        
        data = response.json()
        if not data.get("ok") or not data["result"]["photos"]:
            return None
        
        # Берем самый большой размер фото
        photo = data["result"]["photos"][0][-1]  # Последний элемент = самый большой
        file_id = photo["file_id"]
        
        # Получаем file_path
        file_url = f"https://api.telegram.org/bot{_BOT_TOKEN}/getFile"
        file_response = requests.get(file_url, params={"file_id": file_id}, timeout=5)
        file_data = file_response.json()
        
        if not file_data.get("ok"):
            return None
            
        file_path = file_data["result"]["file_path"]
        return f"https://api.telegram.org/file/bot{_BOT_TOKEN}/{file_path}"
        
    except Exception:
        return None


@csrf_exempt
def miniapp_get_avatar(request):
    """GET /api/get_avatar?user_id=X - получить аватарку пользователя из Telegram."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    user_id_str = request.GET.get("user_id", "")
    if not user_id_str.isdigit():
        return JsonResponse({"error": "user_id required"}, status=400, headers=headers)
    
    user_id = int(user_id_str)
    avatar_url = get_telegram_avatar_url(user_id)
    if not avatar_url:
        return JsonResponse({"user_id": user_id, "avatar_url": None}, headers=headers)

    # Proxy through our server to avoid leaking bot token
    return JsonResponse({
        "user_id": user_id,
        "avatar_url": avatar_url
    }, headers=headers)


# ─── НОВАЯ ФУНКЦИЯ: Логирование действий в чат ──────────────────────────────

async def log_action_to_chat(user_id: int, chat_id: int, action: str, details: str = ""):
    """Отправить сообщение о действии пользователя в чат.
    
    PHASE 3 — social hub filter: только важные события попадают в общий чат.
    Обычные действия (чекин, кормёжка питомца, мелкие покупки) не публикуются.
    """
    if not _BOT_TOKEN:
        return

    # ── Фильтр социального хаба ─────────────────────────────────────────────
    # Пропускаем шумные/рутинные события
    _SKIP_KEYWORDS = (
        "ежедневную награду",   # ежедневный чекин
        "Покормил питомца",     # кормёжка питомца
        "Продал ",              # продажа предметов
    )
    if any(kw in action for kw in _SKIP_KEYWORDS):
        return

    # Гача: публикуем только легендарные (🟡) или эпические (🟣) дропы
    if "гачи" in action.lower():
        if "🟡" not in (details or "") and "🟣" not in (details or ""):
            return
    # ────────────────────────────────────────────────────────────────────────
        
    try:
        import requests
        from database.db import get_user_name
        
        # Получаем имя пользователя
        user_name = await get_user_name(user_id) or f"Игрок {user_id}"
        
        # Формируем сообщение
        message = f"🎮 <b>{user_name}</b> выполнил: {action}"
        if details:
            message += f"{details}"
        
        # Отправляем в чат
        url = f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=5)
        
    except Exception:
        pass  # Не критично если не получилось отправить


# =============================================================================
# QUEST / ЗАДАНИЯ
# =============================================================================

@csrf_exempt
def miniapp_quest(request):
    """GET /api/quest?chat_id=X — current daily quest + progress."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "0")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)
    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.quests import get_quest as _get_quest
        result = _a2s(_get_quest)(uid, chat_id)
        return JsonResponse({"ok": True, **result}, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_quest_reroll(request):
    """POST /api/quest/reroll {chat_id} — spend QUEST_REROLL_PRICE mora to get a new quest."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))
    use_coupon = bool(data.get("use_coupon", False))
    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.quests import reroll_quest as _reroll_quest
        result = _a2s(_reroll_quest)(uid, chat_id, use_coupon=use_coupon)
        return JsonResponse({"ok": True, **result}, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# =============================================================================
# MEMBERS LIST
# =============================================================================

@csrf_exempt
def miniapp_members(request):
    """GET /api/members?chat_id=X — return chat member list for user picker."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        cur.execute(
            f"SELECT s.user_id, u.full_name "
            f"FROM user_stats s LEFT JOIN users u ON u.user_id=s.user_id "
            f"WHERE s.chat_id={ph} AND s.user_id != {ph} "
            f"ORDER BY s.xp DESC LIMIT 60",
            (chat_id, uid),
        )
        rows = cur.fetchall()
        conn.close()
        members = [{"user_id": r[0], "name": r[1] or f"user_{r[0]}"} for r in rows]
        return JsonResponse({"members": members}, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_warnlist(request):
    """GET /api/warnlist?chat_id=X — return users with warns > 0."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        cur.execute(
            f"SELECT s.user_id, COALESCE(u.full_name, CAST(s.user_id AS TEXT)) AS full_name, "
            f"u.username, s.warns "
            f"FROM user_stats s LEFT JOIN users u ON u.user_id=s.user_id "
            f"WHERE s.chat_id={ph} AND s.warns > 0 "
            f"ORDER BY s.warns DESC, s.user_id",
            (chat_id,),
        )
        rows = cur.fetchall()
        conn.close()
        warned = [{"user_id": r[0], "name": r[1], "username": r[2], "warns": r[3]} for r in rows]
        return JsonResponse({"warned": warned}, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ADMIN CHAT SUMMARY
# =============================================================================

@csrf_exempt
def miniapp_admin_chat_summary(request):
    """GET /api/admin/chat_summary?chat_id=X — moderation overview for admin_junior+."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    # Verify caller has at least admin_junior rank in the target chat
    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    _RANK_LEVELS = {
        "user": 0, "moderator": 1, "admin_junior": 2, "admin_senior": 3,
        "co_owner": 4, "owner": 5, "developer": 6, "helper": 1,
    }

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        # Check caller rank
        cur.execute(
            f"SELECT rank FROM user_stats WHERE user_id={ph} AND chat_id={ph}",
            (uid, chat_id),
        )
        row = cur.fetchone()
        caller_rank = row[0] if row else "user"
        if _RANK_LEVELS.get(caller_rank, 0) < _RANK_LEVELS["admin_junior"] and uid != _DEVELOPER_ID:
            conn.close()
            return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

        # Total members
        cur.execute(
            f"SELECT COUNT(*) FROM user_stats WHERE chat_id={ph}",
            (chat_id,),
        )
        total_members = (cur.fetchone() or [0])[0]

        # Active today (message in last 24h via last_active)
        if db_type == "pg":
            cur.execute(
                "SELECT COUNT(*) FROM user_stats WHERE chat_id=%s "
                "AND last_active >= NOW() - INTERVAL '1 day'",
                (chat_id,),
            )
        else:
            cur.execute(
                "SELECT COUNT(*) FROM user_stats WHERE chat_id=? "
                "AND last_active >= datetime('now', '-1 day')",
                (chat_id,),
            )
        active_today = (cur.fetchone() or [0])[0]

        # Total warns outstanding
        cur.execute(
            f"SELECT COUNT(*), COALESCE(SUM(warns), 0) FROM user_stats WHERE chat_id={ph} AND warns > 0",
            (chat_id,),
        )
        row = cur.fetchone() or (0, 0)
        warned_count, total_warns = row[0], int(row[1])

        # Currently muted (restrict_until > now)
        try:
            if db_type == "pg":
                cur.execute(
                    "SELECT COUNT(*) FROM user_stats WHERE chat_id=%s AND restrict_until IS NOT NULL "
                    "AND restrict_until > NOW()",
                    (chat_id,),
                )
            else:
                cur.execute(
                    "SELECT COUNT(*) FROM user_stats WHERE chat_id=? AND restrict_until IS NOT NULL "
                    "AND restrict_until > datetime('now')",
                    (chat_id,),
                )
            muted_count = (cur.fetchone() or [0])[0]
        except Exception:
            conn.rollback()  # prevent "current transaction is aborted" on subsequent queries
            muted_count = 0

        # Rank breakdown
        cur.execute(
            f"SELECT rank, COUNT(*) FROM user_stats WHERE chat_id={ph} GROUP BY rank ORDER BY COUNT(*) DESC",
            (chat_id,),
        )
        rank_rows = cur.fetchall()
        rank_breakdown = [{"rank": r[0], "count": r[1]} for r in rank_rows]

        # Top warned users (up to 5)
        cur.execute(
            f"SELECT s.user_id, COALESCE(u.full_name, CAST(s.user_id AS TEXT)), s.warns "
            f"FROM user_stats s LEFT JOIN users u ON u.user_id=s.user_id "
            f"WHERE s.chat_id={ph} AND s.warns > 0 ORDER BY s.warns DESC LIMIT 5",
            (chat_id,),
        )
        top_warned = [{"user_id": r[0], "name": r[1], "warns": r[2]} for r in cur.fetchall()]

        conn.close()
        return JsonResponse({
            "total_members": total_members,
            "active_today": active_today,
            "warned_count": warned_count,
            "total_warns": total_warns,
            "muted_count": muted_count,
            "rank_breakdown": rank_breakdown,
            "top_warned": top_warned,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# SPY / ШПИОНАЖ
# =============================================================================

@csrf_exempt
def miniapp_spy(request):
    """POST /api/spy {chat_id, target_id} — spy on another user's balance."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))
    target_id_raw = data.get("target_id")
    if not target_id_raw:
        return JsonResponse({"error": "target_id required"}, status=400, headers=headers)
    target_id = int(target_id_raw)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.spy import spy as spy_action
        result = _a2s(spy_action)(uid, chat_id, target_id)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as ve:
        # Cooldown errors → 429, balance errors → 400
        msg = str(ve)
        status_code = 429 if "Кулдаун" in msg else 400
        return JsonResponse({"error": msg}, status=status_code, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# =============================================================================
# TRANSFERS / ПЕРЕВОДЫ
# =============================================================================

@csrf_exempt
def miniapp_transfer(request):
    """POST /api/transfer {chat_id, target_id, amount} — send mora to another user."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))
    target_id = int(data.get("target_id", 0))
    amount = int(data.get("amount", 0))
    cover_vat = bool(data.get("cover_vat", True))

    if target_id == uid:
        return JsonResponse({"error": "Нельзя переводить самому себе"}, status=400, headers=headers)

    try:
        from config import MORA_TRANSFER_MIN, MORA_TRANSFER_MAX
    except Exception:
        MORA_TRANSFER_MIN, MORA_TRANSFER_MAX = 1, 5000

    if amount < MORA_TRANSFER_MIN:
        return JsonResponse({"error": f"Минимальная сумма: {MORA_TRANSFER_MIN} 🪙"}, status=400, headers=headers)
    if amount > MORA_TRANSFER_MAX:
        return JsonResponse({"error": f"Максимальная сумма: {MORA_TRANSFER_MAX} 🪙"}, status=400, headers=headers)

    from api.economy import transfer_mora as _api_tr
    from asgiref.sync import async_to_sync as _a2s
    try:
        result = _a2s(_api_tr)(uid, target_id, chat_id, amount, cover_vat=cover_vat)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)


# =============================================================================
# LOANS / ДОЛГИ
# =============================================================================

@csrf_exempt
def miniapp_loans(request):
    """GET /api/loans?chat_id=X — list active loans (as borrower and as lender)."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "0")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.loans import get_loans
        result = _a2s(get_loans)(uid, chat_id)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_loans_create(request):
    """POST /api/loans/create {chat_id, target_id, amount} — give a loan."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))
    target_id = int(data.get("target_id", 0))
    amount = int(data.get("amount", 0))

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.loans import create_loan
        result = _a2s(create_loan)(uid, target_id, chat_id, amount)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_loans_repay(request):
    """POST /api/loans/repay {chat_id, loan_id} — repay a loan."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))
    loan_id = int(data.get("loan_id", 0))

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.loans import repay_loan
        result = _a2s(repay_loan)(uid, chat_id, loan_id)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_loans_respond(request):
    """POST /api/loans/respond {chat_id, loan_id, action: accept|reject} — borrower accepts or rejects a pending loan."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))
    loan_id = int(data.get("loan_id", 0))
    action = str(data.get("action", "")).lower()

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.loans import respond_to_loan
        result = _a2s(respond_to_loan)(uid, chat_id, loan_id, action)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# =============================================================================
# CASINO / КАЗИНО
# =============================================================================

@csrf_exempt
def miniapp_loans_cancel(request):
    """POST /api/loans/cancel {chat_id, loan_id} — lender cancels a pending outgoing loan request."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))
    loan_id = int(data.get("loan_id", 0))

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.loans import cancel_loan
        result = _a2s(cancel_loan)(uid, chat_id, loan_id)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# =============================================================================
# CASINO / КАЗИНО
# =============================================================================

@csrf_exempt
def miniapp_casino_roulette(request):
    """POST /api/casino/roulette {chat_id, bet_type, amount} — European roulette spin."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id  = int(data.get("chat_id", 0))
    bet_type = str(data.get("bet_type", ""))
    amount   = int(data.get("amount", 0))

    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)

    try:
        from api.roulette import roulette_spin
        from asgiref.sync import async_to_sync as _a2s
        result = _a2s(roulette_spin)(uid, chat_id, bet_type, amount)

        # ── Mandatory public chat notification ────────────────────────────────
        try:
            import requests as _requests
            init_data_str = _get_init_data(request)
            try:
                _params = dict(parse_qsl(init_data_str, keep_blank_values=True))
                _udata  = json.loads(_params.get("user", "{}"))
                _uname  = (
                    (_udata.get("first_name", "") + " " + _udata.get("last_name", "")).strip()
                    or f"user_{uid}"
                )
            except Exception:
                _uname = f"user_{uid}"
            _bet_labels = {
                "red": "🔴 Красное", "black": "⚫ Чёрное",
                "even": "Чётное", "odd": "Нечётное",
                "low": "Малое 1–18", "high": "Большое 19–36",
                "zero": "🟢 Зеро",
            }
            _bet_label = _bet_labels.get(bet_type, (
                f"Номер {bet_type[7:]}" if bet_type.startswith("number_") else bet_type
            ))
            if result["win"]:
                _notif = (
                    f"🎡 <b>{html.escape(_uname)}</b> крутил рулетку "
                    f"({_bet_label}, ставка {amount} 🪙)\n"
                    f"🎉 Победа! +{result['net_prize']} 🪙"
                )
            else:
                _notif = (
                    f"🎡 <b>{html.escape(_uname)}</b> крутил рулетку "
                    f"({_bet_label}, ставка {amount} 🪙)\n"
                    f"💸 Проигрыш"
                )
            if _BOT_TOKEN:
                _requests.post(
                    f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": _notif, "parse_mode": "HTML"},
                    timeout=5,
                )
        except Exception:
            pass

        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400, headers=headers)
    except Exception:
        logger.exception("miniapp view error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_casino_coin(request):
    """POST /api/casino/coin {chat_id, amount} — 40% win x2, 60% lose."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))
    amount  = int(data.get("amount", 0))

    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)

    try:
        from api.casino import coin_flip as _bot_coin_flip
        from asgiref.sync import async_to_sync as _a2s
        result = _a2s(_bot_coin_flip)(uid, chat_id, amount)
        return JsonResponse({
            "ok":          True,
            "win":         result["win"],
            "bet":         result["bet"],
            "prize":       result["prize"],
            "win_tax":     result.get("win_tax", 0),
            "new_balance": result["new_balance"],
            "quest_done":  result["quest_done"],
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_casino_lottery(request):
    """GET /api/casino/lottery?chat_id=X — ticket count this week.
       POST /api/casino/lottery {chat_id} — buy one ticket."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        from asgiref.sync import async_to_sync as _a2s

        if request.method == "GET":
            chat_id_str = request.GET.get("chat_id", "0")
            chat_id = int(chat_id_str)
            from api.casino import get_lottery_status
            result = _a2s(get_lottery_status)(uid, chat_id)
            return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)

        elif request.method == "POST":
            try:
                data = json.loads(request.body)
            except Exception:
                return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)
            chat_id = int(data.get("chat_id", 0))
            from api.casino import buy_lottery_ticket
            result = _a2s(buy_lottery_ticket)(uid, chat_id)
            return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)

        return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)

    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# =============================================================================
# EXPEDITIONS / ЭКСПЕДИЦИИ
# =============================================================================

@csrf_exempt
def miniapp_expeditions(request):
    """GET /api/expeditions?chat_id=X — current expedition status + pet info."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "0")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.expeditions import get_expedition_status
        result = _a2s(get_expedition_status)(uid, chat_id)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_expeditions_start(request):
    """POST /api/expeditions/start {chat_id, option_key} — start expedition."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))
    option_key = str(data.get("option_key", ""))

    from api.expeditions import start_expedition as _api_start
    from asgiref.sync import async_to_sync as _a2s
    try:
        result = _a2s(_api_start)(uid, chat_id, option_key)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)


@csrf_exempt
def miniapp_expeditions_collect(request):
    """POST /api/expeditions/collect {chat_id} — collect finished expedition reward."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))

    from api.expeditions import claim_expedition as _api_collect
    from asgiref.sync import async_to_sync as _a2s
    try:
        result = _a2s(_api_collect)(uid, chat_id)
    except ValueError as e:
        status_code = 404 if "нет актив" in str(e).lower() else 400
        return JsonResponse({"error": str(e)}, status=status_code, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)


@csrf_exempt
def miniapp_expeditions_boost(request):
    """POST /api/expeditions/boost {chat_id, item_id} — apply expedition boost coupon."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))
    item_id = int(data.get("item_id", 0))
    if not chat_id or not item_id:
        return JsonResponse({"error": "chat_id and item_id required"}, status=400, headers=headers)

    try:
        from api.expeditions import boost_expedition as _boost
        from asgiref.sync import async_to_sync as _a2s
        result = _a2s(_boost)(uid, chat_id, item_id)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_pets_rename(request):
    """POST /api/pets/rename {chat_id, name, use_coupon?} — rename pet (coupon=free, else PET_RENAME_PRICE)."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    chat_id = int(data.get("chat_id", 0))
    name = str(data.get("name", "")).strip()[:20]
    use_coupon = bool(data.get("use_coupon", False))
    if not chat_id or not name:
        return JsonResponse({"error": "chat_id and name required"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import deduct_mora, get_mora, rename_pet

        async def _do_rename():
            if use_coupon:
                from database.postgres import connect as _pg
                async with _pg() as db:
                    async with db.execute(
                        "SELECT id, COALESCE(stack_count, 1) FROM gacha_inventory "
                        "WHERE user_id=? AND chat_id=? AND item_key='pet_rename' LIMIT 1",
                        (uid, chat_id),
                    ) as c:
                        row = await c.fetchone()
                    if not row:
                        raise ValueError("Купон переименования не найден в инвентаре")
                    cid, csc = row[0], row[1]
                    if csc <= 1:
                        await db.execute("DELETE FROM gacha_inventory WHERE id=?", (cid,))
                    else:
                        await db.execute(
                            "UPDATE gacha_inventory SET stack_count = stack_count - 1 WHERE id=?", (cid,)
                        )
                    await db.commit()
                cost = 0
            else:
                from config import PET_RENAME_PRICE
                mora = await get_mora(uid, chat_id)
                bal = mora["balance"] if mora else 0
                if bal < PET_RENAME_PRICE:
                    raise ValueError(f"Недостаточно Моры: {bal}/{PET_RENAME_PRICE} 🪙")
                ok, _ = await deduct_mora(uid, chat_id, PET_RENAME_PRICE)
                if not ok:
                    raise ValueError("Не удалось списать Мору")
                cost = PET_RENAME_PRICE
            found = await rename_pet(uid, chat_id, name)
            if not found:
                raise ValueError("Питомец не найден")
            return {"ok": True, "name": name, "cost": cost}

        result = _a2s(_do_rename)()
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Cleanup config ───────────────────────────────────────────────────────────

def _check_owner_or_dev(uid: int, chat_id: int) -> bool:
    """Check if uid has 'owner' or 'developer' rank in the given chat."""
    if uid == _DEVELOPER_ID:
        return True
    try:
        conn, db_type = _get_bot_db_connection()
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        cur.execute(
            f"SELECT rank FROM user_stats WHERE user_id={ph} AND chat_id={ph}",
            (uid, chat_id),
        )
        row = cur.fetchone()
        conn.close()
        rank = row[0] if row else "user"
    except Exception:
        rank = "user"
    return rank in ("owner", "developer")


@csrf_exempt
def miniapp_cleanup_config(request):
    """
    GET  /api/cleanup_config?chat_id=X — current cleanup settings (owner/dev only)
    POST /api/cleanup_config {chat_id, next_cleanup_at?, cleanup_message_norm?, cleanup_warn_hours?}
    """
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    if request.method == "GET":
        chat_id_str = request.GET.get("chat_id", "")
        if not chat_id_str.lstrip("-").isdigit():
            return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
        chat_id = int(chat_id_str)

        if not _check_owner_or_dev(uid, chat_id):
            return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

        try:
            from asgiref.sync import async_to_sync as _a2s
            from api.admin import get_cleanup_settings as _get_cfg
            result = _a2s(_get_cfg)(chat_id)
            return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
        except Exception as exc:
            logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

        chat_id_raw = body.get("chat_id")
        if not chat_id_raw:
            return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
        chat_id = int(str(chat_id_raw))

        if not _check_owner_or_dev(uid, chat_id):
            return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

        next_cleanup_at = body.get("next_cleanup_at")  # ISO string or null
        norm_raw = body.get("cleanup_message_norm")
        warn_raw = body.get("cleanup_warn_hours")

        cleanup_message_norm = int(norm_raw) if norm_raw is not None else None
        cleanup_warn_hours   = int(warn_raw) if warn_raw is not None else None

        # Validate norm / warn ranges
        if cleanup_message_norm is not None and not (1 <= cleanup_message_norm <= 10000):
            return JsonResponse({"error": "cleanup_message_norm out of range"}, status=400, headers=headers)
        if cleanup_warn_hours is not None and not (1 <= cleanup_warn_hours <= 720):
            return JsonResponse({"error": "cleanup_warn_hours out of range"}, status=400, headers=headers)

        try:
            from asgiref.sync import async_to_sync as _a2s
            from api.admin import set_cleanup_settings as _set_cfg
            result = _a2s(_set_cfg)(
                chat_id,
                next_cleanup_at=next_cleanup_at,
                cleanup_message_norm=cleanup_message_norm,
                cleanup_warn_hours=cleanup_warn_hours,
            )
            return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
        except Exception as exc:
            logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)


# ─── Chat buff (Block 8) ───────────────────────────────────────────────────────

@csrf_exempt
def miniapp_chat_buff(request):
    """
    GET  /api/chat_buff?chat_id=X&buff_type=xp_plus10
         → {active, buff_type, expires_at, seconds_left} or {active: false}
    POST /api/chat_buff {chat_id, buff_type?}
         → buy buff for CHAT_BUFF_PRICE Mora; returns {ok, expires_at, cost, new_balance}
    """
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    if request.method == "GET":
        chat_id_str = request.GET.get("chat_id", "")
        if not chat_id_str.lstrip("-").isdigit():
            return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
        chat_id = int(chat_id_str)
        buff_type = request.GET.get("buff_type", "xp_plus10")

        try:
            from asgiref.sync import async_to_sync as _a2s
            from database.db import get_active_chat_buff as _get_buff
            buff = _a2s(_get_buff)(chat_id, buff_type)
            if buff:
                from datetime import datetime, timezone
                exp = buff["expires_at"]
                if hasattr(exp, "isoformat"):
                    exp_iso = exp.isoformat()
                    secs = max(0, int((exp - datetime.now(timezone.utc)).total_seconds()))
                else:
                    exp_iso = str(exp)
                    secs = 0
                return JsonResponse({
                    "active": True, "buff_type": buff_type,
                    "expires_at": exp_iso, "seconds_left": secs,
                }, headers=headers)
            return JsonResponse({"active": False, "buff_type": buff_type}, headers=headers)
        except Exception as exc:
            logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except Exception:
            return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

        chat_id_raw = body.get("chat_id")
        if not chat_id_raw:
            return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
        chat_id = int(str(chat_id_raw))
        buff_type = str(body.get("buff_type", "xp_plus10"))

        try:
            from asgiref.sync import async_to_sync as _a2s
            from api.economy import buy_chat_buff as _buy_buff
            result = _a2s(_buy_buff)(uid, chat_id, buff_type)
            return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
        except ValueError as ve:
            return JsonResponse({"error": str(ve)}, status=400, headers=headers)
        except Exception as exc:
            logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)


# ─── Gifts / Подарки партнёру ─────────────────────────────────────────────────

@csrf_exempt
def miniapp_gifts_catalog(request):
    """GET /api/gifts/catalog?chat_id=X
    Returns catalog of marriage gifts + summary of gifts sent/received in this pair.
    """
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    chat_id_str = request.GET.get("chat_id", "")
    if not chat_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    chat_id = int(chat_id_str)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import get_marriage, get_gifts_summary, get_received_gifts
        from shared_prices import MARRIAGE_GIFTS

        marriage = _a2s(get_marriage)(uid, chat_id)
        if not marriage:
            return JsonResponse({"ok": True, "married": False, "catalog": [], "summary": None}, headers=headers)

        partner_id = marriage["partner_id"]
        count, total = _a2s(get_gifts_summary)(uid, partner_id, chat_id)
        received = _a2s(get_received_gifts)(uid, chat_id)

        catalog = []
        for key, gift in MARRIAGE_GIFTS.items():
            buff = gift.get("buff")
            catalog.append({
                "key":   key,
                "name":  gift["name"],
                "price": gift["price"],
                "buff":  {"pct": buff["type"].replace("mora_boost_", ""), "hours": buff["hours"]} if buff else None,
            })

        return JsonResponse({
            "ok":             True,
            "married":        True,
            "partner_id":     partner_id,
            "catalog":        catalog,
            "summary":        {"count": count, "total": total},
            "received":       received,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_gifts_send(request):
    """POST /api/gifts/send {chat_id, gift_key, wallet}
    Deducts mora and records a gift to partner.
    Returns {ok, gift_name, price, new_balance, buff?}.
    """
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body or b"{}")
        chat_id  = int(str(body.get("chat_id", "0")))
        gift_key = str(body.get("gift_key", "")).strip()
        wallet   = str(body.get("wallet", "personal")).lower()
        if wallet not in ("personal", "family"):
            wallet = "personal"
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not gift_key:
        return JsonResponse({"error": "gift_key required"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import (get_marriage, give_gift, add_buff, get_mora)
        from shared_prices import MARRIAGE_GIFTS

        gift_info = MARRIAGE_GIFTS.get(gift_key)
        if not gift_info:
            return JsonResponse({"error": "Неизвестный подарок"}, status=400, headers=headers)

        marriage = _a2s(get_marriage)(uid, chat_id)
        if not marriage:
            return JsonResponse({"error": "Ты не в браке — некому дарить подарок"}, status=400, headers=headers)

        partner_id = marriage["partner_id"]
        price      = gift_info["price"]

        # Deduct payment
        if wallet == "family":
            from database.db import deduct_family_pool, get_total_family_balance
            total_fbal, _my, _pid = _a2s(get_total_family_balance)(chat_id, uid)
            if total_fbal < price:
                return JsonResponse({"error": f"Недостаточно в семейном кошельке ({total_fbal}/{price} 🪙)"}, status=400, headers=headers)
            _a2s(deduct_family_pool)(chat_id, uid, partner_id, price)
        else:
            from database.postgres import connect as postgres_connect
            from asgiref.sync import async_to_sync as _a2s2
            async def _deduct():
                async with postgres_connect() as db:
                    cursor = await db.execute(
                        "UPDATE user_mora SET balance=balance-? WHERE user_id=? AND chat_id=? AND balance>=?",
                        (price, uid, chat_id, price),
                    )
                    if cursor.rowcount == 0:
                        from database.db import get_mora as _gm
                        m = await _gm(uid, chat_id)
                        bal = m["balance"] if m else 0
                        raise ValueError(f"Недостаточно Моры ({bal}/{price} 🪙)")
                    await db.commit()
            _a2s2(_deduct)()

        # Record gift
        _a2s(give_gift)(uid, partner_id, chat_id, gift_key, gift_info["name"], price)

        # Apply buff if any
        buff_info = gift_info.get("buff")
        if buff_info:
            _a2s(add_buff)(uid, chat_id, buff_info["type"], buff_info["hours"], f"gift:{gift_key}")
            _a2s(add_buff)(partner_id, chat_id, buff_info["type"], buff_info["hours"], f"gift:{gift_key}")

        mora_row = _a2s(get_mora)(uid, chat_id)
        new_bal  = mora_row["balance"] if mora_row else 0

        resp = {
            "ok":          True,
            "gift_name":   gift_info["name"],
            "price":       price,
            "new_balance": new_bal,
        }
        if buff_info:
            pct = buff_info["type"].replace("mora_boost_", "")
            resp["buff"] = {"pct": pct, "hours": buff_info["hours"]}

        # Log to wallet ledger
        try:
            from api.economy import log_wallet_tx
            _a2s(log_wallet_tx)(uid, chat_id, "expense", price, "shop_buy",
                                f"Подарок: {gift_info['name']}")
        except Exception:
            pass

        return JsonResponse(resp, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)
