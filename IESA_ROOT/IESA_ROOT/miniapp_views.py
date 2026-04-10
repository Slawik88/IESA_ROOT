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
import time
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
    GACHA_PITY_MAX as _GACHA_PITY_MAX,
    PRICE_VIP as _PRICE_VIP,
    FRAMES_CATALOG as _FRAMES_CATALOG,
    COSMETICS_CATALOG as _COSMETICS_CATALOG,
    FOOD_ITEMS as _FOOD_ITEMS,
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


_INIT_DATA_MAX_AGE = 86400  # 24 hours — reject replayed/captured initData


def _validate_init_data(init_data: str) -> int | None:
    """Validate Telegram WebApp initData HMAC and freshness. Returns user_id (int) if valid, else None."""
    if not _BOT_TOKEN or not init_data:
        return None
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = params.pop("hash", None)
    if not received_hash:
        return None
    # Reject initData older than 24 h to prevent replay attacks
    try:
        auth_date = int(params.get("auth_date", 0))
        if abs(time.time() - auth_date) > _INIT_DATA_MAX_AGE:
            return None
    except (ValueError, TypeError):
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


def _log_error_to_db(context: str, tb_text: str, uid=None, cid=None):
    """Write an error entry to app_error_logs. Fire-and-forget, never raises."""
    try:
        url = _BOT_DB_URL
        if not (url.startswith("postgresql://") or url.startswith("postgres://")):
            return
        import psycopg2
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        error_line = (tb_text.strip().splitlines() or [""])[-1][:500]
        cur.execute(
            "INSERT INTO app_error_logs (source, context, error_msg, traceback, user_id, chat_id) "
            "VALUES ('backend', %s, %s, %s, %s, %s)",
            (context[:200], error_line, tb_text[:8000], uid, cid),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


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

    # ── feat_website gate: check if miniapp is enabled for this chat ─────
    if specific_chat_id:
        try:
            _cur_fw = conn.cursor()
            _ph_fw = "%s" if db_type == "pg" else "?"
            _cur_fw.execute(
                f"SELECT COALESCE(feat_website, 1) FROM chat_settings WHERE chat_id={_ph_fw}",
                (specific_chat_id,),
            )
            _fw_row = _cur_fw.fetchone()
            if _fw_row is not None and _fw_row[0] == 0:
                conn.close()
                return JsonResponse(
                    {"error": "miniapp_disabled", "message": "Мини-приложение отключено администрацией чата."},
                    status=403, headers=headers,
                )
        except Exception:
            pass  # if we can't check, allow access (fail open)

    try:
        if db_type == "pg":
            cur = conn.cursor()
            ph = "%s"
        else:
            cur = conn.cursor()
            ph = "?"

        # User full_name — sync from initData if available (picks up TG renames)
        _tg_name: str | None = None
        if init_data:
            try:
                _ip = dict(parse_qsl(init_data, keep_blank_values=True))
                _ud = json.loads(_ip.get("user", "{}"))
                _fn = (_ud.get("first_name") or "").strip()
                _ln = (_ud.get("last_name") or "").strip()
                if _fn:
                    _tg_name = (_fn + (" " + _ln if _ln else "")).strip()
            except Exception:
                pass
        if _tg_name:
            try:
                cur.execute(f"UPDATE users SET full_name={ph} WHERE user_id={ph}", (_tg_name, uid))
                conn.commit()
            except Exception:
                conn.rollback()
        cur.execute(f"SELECT full_name, COALESCE(bio,'') FROM users WHERE user_id={ph}", (uid,))
        user_row = cur.fetchone()
        full_name = _tg_name or (user_row[0] if user_row else str(uid))
        user_bio = user_row[1] if user_row else ''

        # Mora row: use specific chat if provided, otherwise any chat row
        if specific_chat_id:
            cur.execute(
                f"SELECT um.chat_id, COALESCE(u.balance,0) AS balance, COALESCE(um.vip,0), um.top_frame, um.active_theme, um.vip_expires_at "
                f"FROM users u LEFT JOIN user_mora um ON um.user_id=u.user_id AND um.chat_id={ph} "
                f"WHERE u.user_id={ph}",
                (specific_chat_id, uid),
            )
        else:
            cur.execute(
                f"SELECT um.chat_id, COALESCE(u.balance,0) AS balance, COALESCE(um.vip,0), um.top_frame, um.active_theme, um.vip_expires_at "
                f"FROM users u LEFT JOIN user_mora um ON um.user_id=u.user_id "
                f"WHERE u.user_id={ph} ORDER BY um.chat_id LIMIT 1",
                (uid,),
            )
        mora_row = cur.fetchone()
        if mora_row:
            chat_id, balance, vip, top_frame, active_theme, vip_expires_at = mora_row
            # VIP expiry check
            if vip and vip_expires_at:
                from datetime import timezone as _tz
                import datetime as _dt
                exp = vip_expires_at
                if isinstance(exp, str):
                    try:
                        exp = _dt.datetime.fromisoformat(exp)
                    except Exception:
                        exp = None
                if exp and exp.tzinfo is None:
                    exp = exp.replace(tzinfo=_tz.utc)
                if exp and _dt.datetime.now(_tz.utc) > exp:
                    vip = 0
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
                f"SELECT pet_type, name, COALESCE(fatigue,0), walk_end_at, color_name FROM pets_global "
                f"WHERE user_id={ph}",
                (uid,),
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
                f"SELECT partner_id FROM marriages_global WHERE user_id={ph}",
                (uid,),
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
                    f"SELECT COALESCE(balance,0) FROM family_wallet WHERE chat_id=0 AND user_id={ph}",
                    (uid,),
                )
                fw_row = cur.fetchone()
                my_family_balance = fw_row[0] if fw_row else 0
                cur.execute(
                    f"SELECT COALESCE(balance,0) FROM family_wallet WHERE chat_id=0 AND user_id={ph}",
                    (partner_id,),
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

        # Crystals balance (global, not chat-scoped)
        try:
            cur.execute(
                f"SELECT COALESCE(balance,0) FROM user_crystals WHERE user_id={ph}", (uid,)
            )
            crystals_row = cur.fetchone()
            crystals_balance = crystals_row[0] if crystals_row else 0
        except Exception:
            conn.rollback()
            crystals_balance = 0

        # Block 3: crystal items (global)
        transfer_passes = enhancement_stones = guarantee_scrolls = 0
        avatar_unlocked = False
        chat_role = None
        try:
            # Transfer passes
            cur.execute(f"SELECT COALESCE(passes,0) FROM crystal_transfer_passes WHERE user_id={ph}", (uid,))
            tp_row = cur.fetchone()
            transfer_passes = tp_row[0] if tp_row else 0
            
            # Enhancement stones
            cur.execute(f"SELECT COALESCE(stones,0) FROM crystal_enhancement_stones WHERE user_id={ph}", (uid,))
            es_row = cur.fetchone()
            enhancement_stones = es_row[0] if es_row else 0
            
            # Guarantee scrolls
            cur.execute(f"SELECT COALESCE(scrolls,0) FROM crystal_guarantee_scrolls WHERE user_id={ph}", (uid,))
            gs_row = cur.fetchone()
            guarantee_scrolls = gs_row[0] if gs_row else 0
            
            # Avatar unlocked
            cur.execute(f"SELECT user_id FROM crystal_avatar_unlocks WHERE user_id={ph}", (uid,))
            avatar_unlocked = cur.fetchone() is not None
            
            # Chat role (if scoped to a specific chat)
            if chat_id:
                cur.execute(f"SELECT role_text FROM crystal_chat_roles WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
                cr_row = cur.fetchone()
                chat_role = cr_row[0] if cr_row else None
                
        except Exception:
            conn.rollback()

        # Crystal cosmetics owned (rainbow_title, crystal_aura, stealth_mode, etc.)
        crystal_cosmetics_owned = []
        has_rainbow_title = False
        try:
            cur.execute(f"SELECT item_value FROM shop_items WHERE user_id={ph} AND item_type='cosmetic'", (uid,))
            crystal_cosmetics_owned = [row[0] for row in cur.fetchall()]
            has_rainbow_title = 'rainbow_title' in crystal_cosmetics_owned
        except Exception:
            conn.rollback()

        computed_level = db_level if db_level > 1 else _level_for_xp(xp)
        xp_max = _xp_for_level(computed_level + 1)

        payload = {
            "uid": uid,
            "chat_id": chat_id,
            "name": full_name,
            "balance": balance,
            "crystals": crystals_balance,
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
            "is_dev": user_rank == 'developer',
            "custom_title": custom_title or "",
            "bio": user_bio,
            "first_active": first_active,
            "last_active": last_active,
            "warns": warns_count,
            "message_count": message_count,
            "newbie_shield_until": newbie_shield_until,
            # Block 3: crystal items
            "transfer_passes": transfer_passes,
            "enhancement_stones": enhancement_stones,
            "guarantee_scrolls": guarantee_scrolls,
            "avatar_unlocked": avatar_unlocked,
            "chat_role": chat_role,
            "crystal_cosmetics_owned": crystal_cosmetics_owned,
            "has_rainbow_title": has_rainbow_title,
        }

        # ── Heartbeat: update mini app online status ─────────────────────
        try:
            _hb_cur = conn.cursor()
            _hb_ph = "%s" if db_type == "pg" else "?"
            _hb_cur.execute(
                f"INSERT INTO miniapp_online (user_id, last_seen) VALUES ({_hb_ph}, NOW()) "
                f"ON CONFLICT(user_id) DO UPDATE SET last_seen = NOW()",
                (uid,),
            )
            conn.commit()
            _hb_cur.close()
        except Exception:
            pass  # non-critical

        conn.close()

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
        if result.get("error") == "isolated_chat":
            return JsonResponse({"error": "Чекин недоступен в этом чате"}, status=403, headers=headers)
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

# ─── Rank levels (single source of truth for miniapp) ────────────────────────
_RANK_LEVELS = {
    "user": 0, "moderator": 1, "admin_junior": 2, "admin_senior": 3,
    "co_owner": 4, "owner": 5, "developer": 6,
    # Backward compat
    "helper": 1, "vip": 0, "admin": 2,
}

_RANK_NAMES_RU = {
    "user": "👤 Участник", "moderator": "🛡 Модератор",
    "admin_junior": "⚡ Админ Младший", "admin_senior": "💎 Админ Старший",
    "co_owner": "👑 Совладелец", "owner": "🔱 Владелец", "developer": "🛠 Разработчик",
}


def _check_rank(uid, chat_id, min_rank, headers):
    """Check if user has at least min_rank in chat. Returns (rank_str, None) or (None, JsonResponse)."""
    if uid == _DEVELOPER_ID:
        return "developer", None
    try:
        conn, db_type = _get_bot_db_connection()
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        cur.execute(f"SELECT rank FROM user_stats WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        row = cur.fetchone()
        conn.close()
        rank = row[0] if row else "user"
        if _RANK_LEVELS.get(rank, 0) < _RANK_LEVELS.get(min_rank, 0):
            return None, JsonResponse(
                {"error": "forbidden", "required_rank": min_rank,
                 "required_rank_name": _RANK_NAMES_RU.get(min_rank, min_rank)},
                status=403, headers=headers,
            )
        return rank, None
    except Exception:
        return None, JsonResponse({"error": "DB error"}, status=503, headers=headers)


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
        import traceback as _tb
        _log_error_to_db("miniapp_marriage_respond/db_update", _tb.format_exc(), uid=uid)
        logger.exception("miniapp_marriage_respond db error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

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
    db_chat_id = row[3]  # chat_id from the proposal row (authoritative)

    if accept:
        from database.db import create_marriage
        from asgiref.sync import async_to_sync
        try:
            async_to_sync(create_marriage)(from_id, uid, db_chat_id)
        except Exception as exc:
            import traceback as _tb
            _tb_text = _tb.format_exc()
            logger.exception("miniapp_marriage_respond: create_marriage failed")
            _log_error_to_db("miniapp_marriage_respond/create_marriage", _tb_text, uid=uid, cid=db_chat_id)
            return JsonResponse({"error": "Внутренняя ошибка сервера"},
                                status=500, json_dumps_params={"ensure_ascii": False}, headers=headers)
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


# ─── Dev: wallet history for any user ────────────────────────────────────────

@csrf_exempt
def miniapp_dev_wallet_user(request):
    """GET /api/dev/wallet_user?user_id=X&chat_id=Y&days=N — developer: wallet history for any user."""
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

    user_id_str = request.GET.get("user_id", "")
    chat_id_str = request.GET.get("chat_id", "0")
    days_str    = request.GET.get("days", "7")

    if not user_id_str.lstrip("-").isdigit():
        return JsonResponse({"error": "user_id required"}, status=400, headers=headers)
    target_uid = int(user_id_str)
    chat_id    = int(chat_id_str) if chat_id_str.lstrip("-").isdigit() else 0
    days       = max(1, min(int(days_str) if days_str.isdigit() else 7, 90))

    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.economy import wallet_history as _wallet_history
        history = _a2s(_wallet_history)(target_uid, chat_id, days)
        return JsonResponse(
            {"history": history, "user_id": target_uid, "chat_id": chat_id, "days": days},
            json_dumps_params={"ensure_ascii": False},
            headers=headers,
        )
    except Exception:
        logger.exception("miniapp view error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


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
                f"COALESCE(stack_count,1), obtained_at "
                f"FROM gacha_inventory WHERE user_id={ph} ORDER BY id DESC",
                (uid,),
            )
            items = []
            for r in cur.fetchall():
                meta = _ITEM_METADATA.get(r[1], {})
                acquired = r[12]
                # 3-day auction eligibility
                days_owned = None
                can_auction = True
                hours_until_auctionable = None
                if acquired:
                    import datetime as _dt
                    if hasattr(acquired, 'date'):  # datetime object
                        age_days = (_dt.datetime.now(_dt.timezone.utc) - acquired.replace(tzinfo=acquired.tzinfo or _dt.timezone.utc)).total_seconds() / 86400
                    else:
                        try:
                            acq_dt = _dt.datetime.fromisoformat(str(acquired).replace('Z', '+00:00'))
                            age_days = (_dt.datetime.now(_dt.timezone.utc) - acq_dt).total_seconds() / 86400
                        except Exception:
                            age_days = 999
                    if age_days < 3:
                        hours_left = max(0.0, 72.0 - age_days * 24)
                        days_owned = max(0, int(hours_left / 24) + (1 if hours_left % 24 > 0 else 0))
                        hours_until_auctionable = int(hours_left) + (1 if hours_left % 1 > 0 else 0)
                        can_auction = False
                items.append({
                    "id": r[0], "key": r[1], "name": r[2], "rarity": r[3], "equipped": bool(r[4]),
                    "atk": r[5], "def_val": r[6], "hp": r[7], "crit_rate": r[8], "slot": r[9] or meta.get("slot"),
                    "enhancement_level": r[10],
                    "stack_count": r[11],
                    "is_cosmetic": meta.get("slot") == "flair",
                    "desc": meta.get("desc", ""),
                    "sell_price": meta.get("sell", 0),
                    "can_auction": can_auction,
                    "days_until_auctionable": days_owned,
                    "hours_until_auctionable": hours_until_auctionable,
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
                f"SELECT id, equipped, slot FROM gacha_inventory WHERE id={ph} AND user_id={ph}",
                (item_id, uid),
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
                        f"UPDATE gacha_inventory SET equipped=0 WHERE user_id={ph} AND slot={ph} AND equipped=1",
                        (uid, slot),
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
            f"SELECT id, item_key, COALESCE(stack_count, 1) FROM gacha_inventory WHERE user_id={ph} AND rarity='junk'",
            (uid,),
        )
        junk_items = cur.fetchall()
        if not junk_items:
            cur.execute(f"SELECT COALESCE(balance, 0) FROM users WHERE user_id={ph}", (uid,))
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
                f"UPDATE users SET balance=COALESCE(balance,0)+{ph} WHERE user_id={ph}",
                (total_mora, uid),
            )
        else:
            cur.execute(
                "UPDATE users SET balance=COALESCE(balance,0)+? WHERE user_id=?",
                (total_mora, uid),
            )
        conn.commit()
        cur.execute(f"SELECT COALESCE(balance, 0) FROM users WHERE user_id={ph}", (uid,))
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
            cur.execute(f"SELECT partner_id FROM marriages_global WHERE user_id={ph}", (uid,))
            marriage_row = cur.fetchone()
            if not marriage_row:
                conn.close()
                return JsonResponse({"error": "Нет семейного кошелька"}, status=400, headers=headers)
            partner_id = marriage_row[0]
            # Total family balance = user contribution + partner contribution (chat_id=0 — global)
            cur.execute(
                f"SELECT COALESCE(SUM(balance), 0) FROM family_wallet WHERE chat_id=0 AND user_id IN ({ph},{ph})",
                (uid, partner_id),
            )
            total_fam_bal = (cur.fetchone() or [0])[0]
            if total_fam_bal < _CUSTOM_TITLE_PRICE:
                conn.close()
                return JsonResponse({"error": f"Недостаточно моры в семейном кошельке. Нужно {_CUSTOM_TITLE_PRICE} 🪙, есть {total_fam_bal} 🪙"}, status=400, headers=headers)
            # Atomic deduction: deduct from user's contribution first, then partner's
            from asgiref.sync import async_to_sync as _a2s
            from database.db import deduct_family_pool
            try:
                _a2s(deduct_family_pool)(0, uid, partner_id, _CUSTOM_TITLE_PRICE)
            except ValueError:
                conn.close()
                return JsonResponse({"error": f"Недостаточно моры в семейном кошельке (race)"}, status=400, headers=headers)
        else:
            cur.execute(
                f"UPDATE users SET balance=balance-{ph} WHERE user_id={ph} AND COALESCE(balance,0)>={ph}",
                (_CUSTOM_TITLE_PRICE, uid, _CUSTOM_TITLE_PRICE),
            )
            if cur.rowcount == 0:
                conn.close()
                return JsonResponse({"error": f"Недостаточно моры. Нужно {_CUSTOM_TITLE_PRICE} 🪙"}, status=400, headers=headers)
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
        cur.execute(f"SELECT COALESCE(balance, 0) FROM users WHERE user_id={ph}", (uid,))
        new_bal = (cur.fetchone() or [0])[0]
        conn.close()
        return JsonResponse({"ok": True, "title": title, "balance": new_bal}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Profile Bio ──────────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_set_bio(request):
    """POST /api/profile/bio — update the user's 'О себе' bio text."""
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
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400, headers=headers)

    bio = str(body.get("bio", "")).strip()
    if len(bio) > 200:
        return JsonResponse({"error": "Биография не должна превышать 200 символов"}, status=400, headers=headers)

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        cur.execute(f"UPDATE users SET bio={ph} WHERE user_id={ph}", (bio or None, uid))
        cur.execute(f"UPDATE user_stats SET bio={ph} WHERE user_id={ph}", (bio or None, uid))
        conn.commit()
        conn.close()
        return JsonResponse({"ok": True, "bio": bio}, headers=headers)
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

    if count not in (1, 10, 50):
        return JsonResponse({"error": "count must be 1, 10 or 50"}, status=400, headers=headers)
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
            "family_balance": result.get("new_family_bal"),
            "pity":       result["pity"],
            "spent":      result["spent"],
            "quest_done": result["quest_done"],
            "quest_xp":   result.get("quest_xp", 0),
            "quest_mora": result.get("quest_mora", 0),
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
    if item_type not in ("frame", "cosmetic", "vip", "potion", "pet_color", "profile_theme"):
        return JsonResponse({"error": "item_type must be frame/cosmetic/vip/potion/pet_color/profile_theme"}, status=400, headers=headers)

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
                f"SELECT theme_key FROM user_themes WHERE user_id={ph}",
                (uid,),
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
                    f"SELECT 1 FROM user_themes WHERE user_id={ph} AND theme_key={ph}",
                    (uid, theme_key),
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
        cur.execute(f"SELECT full_name, COALESCE(bio,'') FROM users WHERE user_id={ph}", (target_id,))
        user_row = cur.fetchone()
        if not user_row:
            conn.close()
            return JsonResponse({"error": "User not found"}, status=404, headers=headers)
        full_name = user_row[0]
        pub_bio = user_row[1]

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
            f"SELECT partner_id FROM marriages_global WHERE user_id={ph}",
            (target_id,),
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

        # Online status indicator
        online_status = "offline"
        try:
            cur.execute(
                f"SELECT last_seen FROM miniapp_online WHERE user_id={ph}",
                (target_id,),
            )
            _ol_row = cur.fetchone()
            if _ol_row and _ol_row[0]:
                from datetime import datetime as _dt_ol, timezone as _tz_ol
                _ls = _ol_row[0]
                if hasattr(_ls, 'tzinfo') and _ls.tzinfo is None:
                    _ls = _ls.replace(tzinfo=_tz_ol.utc)
                _diff = (_dt_ol.now(_tz_ol.utc) - _ls).total_seconds()
                if _diff < 90:
                    online_status = "online"
                elif _diff < 300:
                    online_status = "recently"
        except Exception:
            pass

        # Avatar URL for public display
        avatar_url = None
        try:
            cur.execute(
                f"SELECT avatar_path FROM crystal_avatar_unlocks WHERE user_id={ph}",
                (target_id,),
            )
            av_row = cur.fetchone()
            if av_row and av_row[0]:
                avatar_url = f"/api/user_avatar/{target_id}/"
        except Exception:
            pass

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
            "bio": pub_bio,
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
            "online_status": online_status,
            "avatar_url": avatar_url,
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
    use_stone = data.get("use_stone")  # True=use stone (100%), False=use mora, None=auto

    if not item_id or not chat_id:
        return JsonResponse({"error": "item_id and chat_id required"}, status=400, headers=headers)

    try:
        from database.db import enhance_item
        from api.economy import get_balance
        from asgiref.sync import async_to_sync as _a2s

        success, message, new_level = _a2s(enhance_item)(uid, chat_id, item_id, use_stone=use_stone)

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
        
        # Check if user is married (global)
        cur.execute(f"SELECT partner_id FROM marriages_global WHERE user_id={ph}", (uid,))
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
        cur.execute(f"SELECT partner_id FROM marriages_global WHERE user_id={ph}", (uid,))
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
        
        # Check if user is married (global)
        cur.execute(f"SELECT partner_id FROM marriages_global WHERE user_id={ph}", (uid,))
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
                # Return attacker's new balance for frontend sync
                try:
                    new_bal = async_to_sync(get_mora)(uid, chat_id)
                    response["new_balance"] = new_bal["balance"] if new_bal else 0
                except Exception:
                    pass
                
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
            from database.db import add_mora, add_xp_in_chat, get_mora
            async_to_sync(add_mora)(uid, chat_id, mora_reward)
            async_to_sync(add_xp_in_chat)(uid, chat_id, xp_reward)
            response["rewards"] = {"mora": mora_reward, "xp": xp_reward}
            # Return new balance for frontend sync
            try:
                new_bal = async_to_sync(get_mora)(uid, chat_id)
                response["new_balance"] = new_bal["balance"] if new_bal else 0
            except Exception:
                pass
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
    # Return the server-side proxy URL instead of the raw Telegram URL
    return JsonResponse({
        "user_id": user_id,
        "avatar_url": f"/api/user_avatar/{user_id}/"
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
            f"WHERE s.chat_id={ph} "
            f"ORDER BY s.xp DESC LIMIT 60",
            (chat_id,),
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


# ─── Admin roster (combined moderation overview) ──────────────────────────────
@csrf_exempt
def miniapp_admin_roster(request):
    """GET /api/admin/roster?chat_id=X — full moderation roster: stats, warns, userbans, bans, voluntary leavers."""
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

    ph = "%s" if db_type == "pg" else "?"

    try:
        cur = conn.cursor()

        # ── Auth: moderator+ or developer ─────────────────────────────────────
        if uid != _DEVELOPER_ID:
            cur.execute(
                f"SELECT rank FROM user_stats WHERE user_id={ph} AND chat_id={ph}",
                (uid, chat_id),
            )
            row = cur.fetchone()
            caller_rank = row[0] if row else "user"
            if _RANK_LEVELS.get(caller_rank, 0) < _RANK_LEVELS["moderator"]:
                conn.close()
                return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

        # ── 1. General stats ──────────────────────────────────────────────────
        cur.execute(f"SELECT COUNT(*) FROM user_stats WHERE chat_id={ph}", (chat_id,))
        total_members = (cur.fetchone() or [0])[0]

        if db_type == "pg":
            cur.execute(
                "SELECT COUNT(*) FROM user_stats WHERE chat_id=%s "
                "AND last_active >= NOW() - INTERVAL '1 day'", (chat_id,)
            )
        else:
            cur.execute(
                "SELECT COUNT(*) FROM user_stats WHERE chat_id=? "
                "AND last_active >= datetime('now', '-1 day')", (chat_id,)
            )
        active_today = (cur.fetchone() or [0])[0]

        cur.execute(
            f"SELECT COUNT(*), COALESCE(SUM(warns), 0) FROM user_stats "
            f"WHERE chat_id={ph} AND warns > 0", (chat_id,)
        )
        row = cur.fetchone() or (0, 0)
        warned_count, total_warns = row[0], int(row[1])

        try:
            if db_type == "pg":
                cur.execute(
                    "SELECT COUNT(*) FROM user_stats WHERE chat_id=%s "
                    "AND restrict_until IS NOT NULL AND restrict_until > NOW()", (chat_id,)
                )
            else:
                cur.execute(
                    "SELECT COUNT(*) FROM user_stats WHERE chat_id=? "
                    "AND restrict_until IS NOT NULL", (chat_id,)
                )
            muted_count = (cur.fetchone() or [0])[0]
        except Exception:
            try: conn.rollback()
            except Exception: pass
            muted_count = 0

        cur.execute(
            f"SELECT rank, COUNT(*) FROM user_stats WHERE chat_id={ph} "
            f"GROUP BY rank ORDER BY COUNT(*) DESC", (chat_id,)
        )
        rank_breakdown = [{"rank": r[0], "count": r[1]} for r in cur.fetchall()]

        # ── 2. Users with warns ───────────────────────────────────────────────
        cur.execute(
            f"SELECT s.user_id, COALESCE(u.full_name, CAST(s.user_id AS TEXT)) AS name, "
            f"u.username, s.warns "
            f"FROM user_stats s LEFT JOIN users u ON u.user_id=s.user_id "
            f"WHERE s.chat_id={ph} AND s.warns > 0 ORDER BY s.warns DESC LIMIT 100",
            (chat_id,),
        )
        warned = [{"user_id": r[0], "name": r[1], "username": r[2], "warns": r[3]}
                  for r in cur.fetchall()]

        # ── 3. Bot-level userbans (user_banlist table) ────────────────────────
        try:
            cur.execute(
                f"SELECT ub.user_id, COALESCE(u.full_name, CAST(ub.user_id AS TEXT)) AS name, "
                f"u.username, ub.reason, ub.added_at "
                f"FROM user_banlist ub LEFT JOIN users u ON u.user_id=ub.user_id "
                f"WHERE ub.chat_id={ph} ORDER BY ub.added_at DESC LIMIT 100",
                (chat_id,),
            )
            userbans = [{"user_id": r[0], "name": r[1], "username": r[2],
                         "reason": r[3] or "", "added_at": str(r[4] or "")[:10]}
                        for r in cur.fetchall()]
        except Exception:
            try: conn.rollback()
            except Exception: pass
            userbans = []

        # ── 4. Telegram-banned / kicked (user_stats restrict_type='ban') ──────
        try:
            cur.execute(
                f"SELECT s.user_id, COALESCE(u.full_name, CAST(s.user_id AS TEXT)) AS name, "
                f"u.username, s.restrict_until "
                f"FROM user_stats s LEFT JOIN users u ON u.user_id=s.user_id "
                f"WHERE s.chat_id={ph} AND s.restrict_type = 'ban' "
                f"ORDER BY s.restrict_until DESC NULLS LAST LIMIT 100",
                (chat_id,),
            )
            tg_banned = [{"user_id": r[0], "name": r[1], "username": r[2],
                          "until": str(r[3] or "")[:19] if r[3] else None}
                         for r in cur.fetchall()]
        except Exception:
            try: conn.rollback()
            except Exception: pass
            tg_banned = []

        # ── 5. Voluntary leavers (leave_log) ─────────────────────────────────
        try:
            cur.execute(
                f"SELECT user_id, COALESCE(full_name, CAST(user_id AS TEXT)) AS name, "
                f"username, left_at "
                f"FROM leave_log WHERE chat_id={ph} "
                f"ORDER BY left_at DESC LIMIT 100",
                (chat_id,),
            )
            left_chat = [{"user_id": r[0], "name": r[1], "username": r[2],
                          "left_at": str(r[3] or "")[:10]}
                         for r in cur.fetchall()]
        except Exception:
            try: conn.rollback()
            except Exception: pass
            left_chat = []

        conn.close()
        return JsonResponse({
            "stats": {
                "total_members": total_members,
                "active_today": active_today,
                "warned_count": warned_count,
                "total_warns": total_warns,
                "muted_count": muted_count,
                "rank_breakdown": rank_breakdown,
            },
            "warned": warned,
            "userbans": userbans,
            "tg_banned": tg_banned,
            "left_chat": left_chat,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception:
        try: conn.close()
        except Exception: pass
        logger.exception("miniapp_admin_roster error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


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
        chat_id = int(data.get("chat_id", 0))
        target_id = int(data.get("target_id", 0))
        amount = int(data.get("amount", 0))
        cover_vat = bool(data.get("cover_vat", True))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({"error": "invalid JSON or params"}, status=400, headers=headers)

    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    if not target_id:
        return JsonResponse({"error": "target_id required"}, status=400, headers=headers)
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


@csrf_exempt
def miniapp_crystals_transfer(request):
    """POST /api/crystals/transfer {target_id, amount} — send crystals to another user. No VAT."""
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

    try:
        target_id = int(data.get("target_id", 0))
        amount = int(data.get("amount", 0))
    except (TypeError, ValueError):
        return JsonResponse({"error": "invalid params"}, status=400, headers=headers)

    if target_id == uid:
        return JsonResponse({"error": "Нельзя переводить самому себе"}, status=400, headers=headers)
    if target_id <= 0:
        return JsonResponse({"error": "Укажи получателя"}, status=400, headers=headers)

    from api.economy import transfer_crystals as _api_tc
    from asgiref.sync import async_to_sync as _a2s
    try:
        result = _a2s(_api_tc)(uid, target_id, amount)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp crystals_transfer error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)
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
        chat_id = int(data.get("chat_id", 0))
        target_id = int(data.get("target_id", 0))
        amount = int(data.get("amount", 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({"error": "invalid JSON or params"}, status=400, headers=headers)

    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    if not target_id:
        return JsonResponse({"error": "target_id required"}, status=400, headers=headers)
    if amount <= 0:
        return JsonResponse({"error": "amount must be positive"}, status=400, headers=headers)

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
        chat_id  = int(data.get("chat_id", 0))
        bet_type = str(data.get("bet_type", ""))
        amount   = int(data.get("amount", 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({"error": "invalid JSON or params"}, status=400, headers=headers)

    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)

    # Check feat_roulette toggle
    try:
        from database.db import get_chat_settings as _gcs
        from asgiref.sync import async_to_sync as _a2s_set
        _r_settings = _a2s_set(_gcs)(chat_id)
        if _r_settings and _r_settings.get("feat_roulette") == 0:
            return JsonResponse({"error": "Рулетка отключена в этом чате"}, status=403, headers=headers)
    except Exception:
        pass

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
            if _BOT_TOKEN and amount >= 200:  # Only announce bets ≥200🪙 to avoid spam
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
        chat_id = int(data.get("chat_id", 0))
        amount  = int(data.get("amount", 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({"error": "invalid JSON or params"}, status=400, headers=headers)

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
    wallet_type = str(data.get("wallet_type", "personal")).lower()
    if wallet_type not in ("personal", "family"):
        wallet_type = "personal"

    from api.expeditions import start_expedition as _api_start
    from asgiref.sync import async_to_sync as _a2s
    try:
        result = _a2s(_api_start)(uid, chat_id, option_key, wallet_type)
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
    return rank in ("owner", "co_owner", "developer")


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
            else:
                return JsonResponse({"active": False}, headers=headers)
        except Exception as exc:
            logger.exception("miniapp view error")
            return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    elif request.method == "POST":
        try:
            body = json.loads(request.body or "{}")
        except ValueError:
            return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

        chat_id = int(str(body.get("chat_id", "0")))
        buff_type = str(body.get("buff_type", "xp_plus10"))  # default to XP +10 buff

        if not chat_id:
            return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)

        try:
            from asgiref.sync import async_to_sync as _a2s
            from database.db import buy_chat_buff as _buy_buff
            result = _a2s(_buy_buff)(uid, chat_id, buff_type)
            return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
        except ValueError as ve:
            return JsonResponse({"error": str(ve)}, status=400, json_dumps_params={"ensure_ascii": False}, headers=headers)
        except Exception as exc:
            logger.exception("miniapp view error")
            return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)


# ── Block 3: Crystal-Mora conversion ──────────────────────────────────────────

@csrf_exempt
def miniapp_convert_crystals(request):
    """POST /api/convert_crystals {amount} — convert crystals to mora at 1:30 rate."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        body = json.loads(request.body or "{}")
        amount = int(body.get("amount", 0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({"error": "invalid JSON or amount"}, status=400, headers=headers)

    if amount <= 0 or amount > 1000:
        return JsonResponse({"error": "Amount must be 1-1000 crystals"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import spend_crystals, get_crystals, add_mora
        
        # Spend crystals first
        ok = _a2s(spend_crystals)(uid, amount)
        if not ok:
            return JsonResponse({"error": "Недостаточно кристаллов"}, status=400, headers=headers)
        
        # Add 30x mora globally (1 crystal = 30 mora)
        mora_added = amount * 30
        _a2s(add_mora)(uid, 0, mora_added)
        
        new_crystals = _a2s(get_crystals)(uid)
        
        return JsonResponse({
            "ok": True,
            "crystals_spent": amount,
            "mora_added": mora_added,
            "crystals_balance": new_crystals,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
        
    except Exception as exc:
        logger.exception("convert_crystals error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ── Block 3: Avatar serving ──────────────────────────────────────────────────

@csrf_exempt
def miniapp_user_avatar(request, user_id):
    """GET /api/user_avatar/<user_id>/ — serve user's avatar image or redirect to URL."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    try:
        uid_int = int(user_id)
    except ValueError:
        return JsonResponse({"error": "invalid user_id"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import get_avatar_path
        
        avatar_path = _a2s(get_avatar_path)(uid_int)
        if not avatar_path:
            return JsonResponse({"error": "Avatar not found"}, status=404, headers=headers)
        
        # If avatar_path is a URL, redirect to it (whitelist Telegram CDN domains)
        if avatar_path.startswith("http://") or avatar_path.startswith("https://"):
            from urllib.parse import urlparse
            _allowed_avatar_hosts = {"t.me", "telegram.org", "cdn4.telegram-cdn.org", "cdn5.telegram-cdn.org"}
            parsed = urlparse(avatar_path)
            if parsed.hostname not in _allowed_avatar_hosts:
                return JsonResponse({"error": "Avatar URL domain not allowed"}, status=400, headers=headers)
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(avatar_path)
        
        # Otherwise serve as file
        from django.http import FileResponse
        from pathlib import Path
        file_path = Path(avatar_path)
        if not file_path.exists():
            return JsonResponse({"error": "Avatar file not found"}, status=404, headers=headers)
        
        return FileResponse(
            open(file_path, 'rb'),
            content_type='image/jpeg',
            headers=headers
        )
        
    except Exception as exc:
        logger.exception("user_avatar error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


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
        from config import MARRIAGE_GIFTS

        marriage = _a2s(get_marriage)(uid, chat_id)
        if not marriage:
            return JsonResponse({"ok": True, "married": False, "catalog": [], "summary": None}, headers=headers)

        partner_id = marriage["partner_id"]
        count, total = _a2s(get_gifts_summary)(uid, partner_id, chat_id)
        received = _a2s(get_received_gifts)(uid, chat_id)

        from database.db import get_mora
        mora = _a2s(get_mora)(uid, chat_id)
        balance = mora["balance"] if mora else 0

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
            "balance":        balance,
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
        from config import MARRIAGE_GIFTS

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
                        "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
                        (price, uid, price),
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

        # Quest tick: gift
        try:
            from database.db import get_user_quest, quest_tick, mark_quest_rewarded, add_xp_in_chat, add_mora
            from utils.helpers import bot_today
            today = bot_today()
            quest = _a2s(get_user_quest)(uid, chat_id, today)
            if quest and quest["type"] == "gift":
                new_p, goal, just_done = _a2s(quest_tick)(uid, chat_id, today, quest["type"], quest["goal"])
                if just_done:
                    _mr = quest.get("mora", 5)
                    _a2s(add_xp_in_chat)(uid, chat_id, quest["xp"])
                    _a2s(add_mora)(uid, chat_id, _mr)
                    _a2s(mark_quest_rewarded)(uid, chat_id, today)
        except Exception:
            pass

        return JsonResponse(resp, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Аукцион ─────────────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_auction_list(request):
    """GET /api/auction/list?chat_id=X — активные лоты."""
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
        from api.auction import get_active_auctions, get_user_auctions
        lots = _a2s(get_active_auctions)()          # global — no chat_id filter
        my   = _a2s(get_user_auctions)(uid, chat_id)  # user's lots/bids globally
        for lot in lots:
            for k, v in lot.items():
                if hasattr(v, 'isoformat'):
                    lot[k] = v.isoformat()
        for lst in (my.get("my_lots", []), my.get("my_bids", [])):
            for item in lst:
                for k, v in item.items():
                    if hasattr(v, 'isoformat'):
                        item[k] = v.isoformat()
        return JsonResponse({
            "lots": lots,
            "my_lots": my.get("my_lots", []),
            "my_bids": my.get("my_bids", []),
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_auction_create(request):
    """POST /api/auction/create — выставить предмет."""
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
        chat_id     = int(str(body.get("chat_id", "0")))
        start_price = int(str(body.get("start_price", "0")))
        buyout      = body.get("buyout_price")
        if buyout is not None:
            buyout = int(str(buyout))
        item_source = str(body.get("item_source", "gacha"))
        item_key_str = str(body.get("item_key", ""))
        item_name_str = str(body.get("item_name", item_key_str))
        item_id     = int(str(body.get("item_id", "0")))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)
    if not chat_id or start_price <= 0:
        return JsonResponse({"error": "chat_id, start_price required"}, status=400, headers=headers)
    try:
        from asgiref.sync import async_to_sync as _a2s
        if item_source == "shop":
            if not item_key_str:
                return JsonResponse({"error": "item_key required for shop items"}, status=400, headers=headers)
            from api.auction import create_cosmetic_auction
            result = _a2s(create_cosmetic_auction)(uid, chat_id, item_key_str, item_name_str, start_price, buyout)
        else:
            if not item_id:
                return JsonResponse({"error": "item_id required"}, status=400, headers=headers)
            from api.auction import create_auction
            result = _a2s(create_auction)(uid, chat_id, item_id, start_price, buyout)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_auction_bid(request):
    """POST /api/auction/bid — сделать ставку."""
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
        chat_id    = int(str(body.get("chat_id", "0")))
        auction_id = int(str(body.get("auction_id", "0")))
        amount     = int(str(body.get("amount", "0")))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)
    if not chat_id or not auction_id or amount <= 0:
        return JsonResponse({"error": "chat_id, auction_id, amount required"}, status=400, headers=headers)
    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.auction import place_bid
        result = _a2s(place_bid)(uid, chat_id, auction_id, amount)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_auction_buyout(request):
    """POST /api/auction/buyout — мгновенный выкуп."""
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
        chat_id    = int(str(body.get("chat_id", "0")))
        auction_id = int(str(body.get("auction_id", "0")))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)
    if not chat_id or not auction_id:
        return JsonResponse({"error": "chat_id, auction_id required"}, status=400, headers=headers)
    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.auction import buyout_auction
        result = _a2s(buyout_auction)(uid, chat_id, auction_id)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_auction_cancel(request):
    """POST /api/auction/cancel — отменить лот."""
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
        chat_id    = int(str(body.get("chat_id", "0")))
        auction_id = int(str(body.get("auction_id", "0")))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)
    if not chat_id or not auction_id:
        return JsonResponse({"error": "chat_id, auction_id required"}, status=400, headers=headers)
    try:
        from asgiref.sync import async_to_sync as _a2s
        from api.auction import cancel_auction
        result = _a2s(cancel_auction)(uid, chat_id, auction_id)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Достижения ───────────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_achievements(request):
    """GET /api/achievements?chat_id=X — все достижения с флагом unlocked.
       GET /api/achievements?chat_id=X&mode=leaderboard — топ по достижениям в чате.
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
    mode = request.GET.get("mode", "")
    try:
        from asgiref.sync import async_to_sync as _a2s
        if mode == "leaderboard":
            from api.achievements import get_global_achievements_leaderboard
            data = _a2s(get_global_achievements_leaderboard)(chat_id)
            return JsonResponse({"ok": True, "leaderboard": data}, json_dumps_params={"ensure_ascii": False}, headers=headers)
        from api.achievements import get_all_achievements_with_status
        data = _a2s(get_all_achievements_with_status)(uid, chat_id)
        return JsonResponse(
            data,
            json_dumps_params={"ensure_ascii": False},
            headers=headers
        )
    except Exception as exc:
        logger.exception("miniapp view error"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Crystals spend (POST /api/crystals/spend) ────────────────────────────────
@csrf_exempt
def miniapp_crystals_spend(request):
    """POST /api/crystals/spend {item_key, price} — spend crystals on cosmetic."""
    from shared_prices import CRYSTAL_COSMETICS
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)
    uid, err = _require_auth(request, headers)
    if err:
        return err
    try:
        body = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"error": "Invalid JSON"}, status=400, headers=headers)

    item_key = str(body.get("item_key", "")).strip()
    price_raw = body.get("price", 0)
    chat_id = int(str(body.get("chat_id", "0")))  # Для chat_role
    role_text = str(body.get("role_text", "")).strip()  # Для chat_role
    
    if not item_key:
        return JsonResponse({"error": "item_key required"}, status=400, headers=headers)
    try:
        price = int(price_raw)
    except (TypeError, ValueError):
        return JsonResponse({"error": "invalid price"}, status=400, headers=headers)

    # Validate item exists in catalog
    valid_items = {c[0]: {"price": c[3], "name": c[2]} for c in CRYSTAL_COSMETICS}
    if item_key not in valid_items:
        return JsonResponse({"error": "Товар не найден"}, status=404, headers=headers)
    
    # Server-side price verification
    expected_price = valid_items[item_key]["price"]
    if price != expected_price:
        return JsonResponse({"error": "Некорректная цена"}, status=400, headers=headers)

    # Handle special item requirements
    if item_key == "chat_role":
        if not chat_id:
            return JsonResponse({"error": "chat_id required for chat_role"}, status=400, headers=headers)
        if not role_text or len(role_text) > 50:
            return JsonResponse({"error": "Роль должна быть от 1 до 50 символов"}, status=400, headers=headers)
    
    if item_key == "telegram_avatar":
        # Check if already unlocked (one-time purchase)
        try:
            from asgiref.sync import async_to_sync as _a2s
            from database.db import is_avatar_unlocked
            if _a2s(is_avatar_unlocked)(uid):
                return JsonResponse({"error": "Аватар уже разблокирован"}, status=400, headers=headers)
        except Exception:
            pass

    # Block cosmetic/frame items in isolated test chats
    _COSMETIC_CRYSTAL_ITEMS = {
        "crystal_aura", "dark_matter_frame", "herald_frame", "rainbow_title",
        "crystal_pet_skin", "stealth_mode",
    }
    if item_key in _COSMETIC_CRYSTAL_ITEMS and chat_id:
        from database.db import is_isolated_chat
        if is_isolated_chat(chat_id):
            return JsonResponse(
                {"error": "В тестовых чатах нельзя покупать косметику и рамки"},
                status=403,
                headers=headers,
            )

    try:
        import asyncpg
        from asgiref.sync import async_to_sync as _a2s
        from database.db import spend_crystals, get_crystals
        
        # Spend crystals first
        ok = _a2s(spend_crystals)(uid, price)
        if not ok:
            return JsonResponse({"error": "Недостаточно кристаллов"}, status=400, headers=headers)
        
        # Apply item effects
        if item_key == "transfer_pass":
            from database.db import add_transfer_passes
            _a2s(add_transfer_passes)(uid, 1)
            
        elif item_key == "shard_chest":
            # Add 3 rare-grade frame shards to gacha inventory
            from database.db import add_gacha_item
            frame_shards = [
                ("shard_warrior", "🗡️ Осколок Воина", "rare"),
                ("shard_king", "👑 Осколок Короля", "rare"),
                ("shard_moon", "🌙 Лунный осколок", "rare"),
            ]
            for key, name, rarity in frame_shards:
                _a2s(add_gacha_item)(uid, chat_id or 0, key, name, rarity)
                
        elif item_key == "guarantee_scroll":
            from database.db import add_guarantee_scrolls
            _a2s(add_guarantee_scrolls)(uid, 1)
            
        elif item_key == "chat_role":
            from database.db import set_crystal_chat_role
            _a2s(set_crystal_chat_role)(uid, chat_id, role_text)
            
        elif item_key == "telegram_avatar":
            from database.db import unlock_avatar
            # TODO: Download avatar from Telegram and save path
            _a2s(unlock_avatar)(uid, None)
            
        elif item_key == "enhancement_stones_5":
            from database.db import add_enhancement_stones
            _a2s(add_enhancement_stones)(uid, 5)

        # ── Crystal-exclusive cosmetics / frames ──────────────────────────────
        elif item_key in ("crystal_aura", "rainbow_title", "stealth_mode", "crystal_pet_skin"):
            from database.db import add_shop_item, has_active_cosmetic
            if _a2s(has_active_cosmetic)(uid, item_key):
                # Already owned — refund crystals and return error
                from database.db import add_crystals
                _a2s(add_crystals)(uid, price)
                return JsonResponse(
                    {"error": "Этот предмет у вас уже есть"},
                    status=400,
                    headers=headers,
                )
            _a2s(add_shop_item)(uid, "cosmetic", item_key)

        elif item_key in ("dark_matter_frame", "herald_frame"):
            from database.db import add_shop_item, get_user_owned_frames
            owned = _a2s(get_user_owned_frames)(uid, 0)
            if item_key in owned:
                from database.db import add_crystals
                _a2s(add_crystals)(uid, price)
                return JsonResponse(
                    {"error": "Эта рамка у вас уже есть"},
                    status=400,
                    headers=headers,
                )
            _a2s(add_shop_item)(uid, "frame", item_key)

        elif item_key == "double_pity":
            import time
            expires_ts = int(time.time()) + 7 * 86400
            from database.db import add_shop_item
            _a2s(add_shop_item)(uid, "cosmetic", f"double_pity_{expires_ts}")

        elif item_key == "vip_week":
            if not chat_id:
                from database.db import add_crystals
                _a2s(add_crystals)(uid, price)
                return JsonResponse(
                    {"error": "chat_id required для VIP"},
                    status=400,
                    headers=headers,
                )
            from database.db import add_vip_days
            _a2s(add_vip_days)(uid, chat_id, 7)

        new_balance = _a2s(get_crystals)(uid)
        
        return JsonResponse(
            {"ok": True, "item_key": item_key, "crystals_balance": new_balance},
            json_dumps_params={"ensure_ascii": False},
            headers=headers,
        )
    except Exception as exc:
        logger.exception("crystals_spend error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)



# ──────────────────────────────────────────────────────────────────────────────
#  Dev: error log endpoints
# ──────────────────────────────────────────────────────────────────────────────
#  Dev: give crystals (developer-only)
# ──────────────────────────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_dev_give_crystals(request):
    """POST /api/dev/give_crystals {target_id, amount} — manually grant crystals (developer only)."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "Forbidden"}, status=403, headers=headers)

    try:
        body = json.loads(request.body or b"{}")
        target_id = int(body.get("target_id", 0))
        amount = int(body.get("amount", 0))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not target_id:
        return JsonResponse({"error": "target_id required"}, status=400, headers=headers)
    if amount < 1 or amount > 100000:
        return JsonResponse({"error": "amount must be 1-100000"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import add_crystals
        new_balance = _a2s(add_crystals)(target_id, amount)
        return JsonResponse({"ok": True, "target_id": target_id, "amount": amount, "new_balance": new_balance},
                            json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("miniapp_dev_give_crystals error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ──────────────────────────────────────────────────────────────────────────────
#  Chat ban list (admin view — users banned in a specific chat)
# ──────────────────────────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_chat_banlist(request):
    """GET /api/chat_banlist?chat_id=X — list users banned in this chat (admin_junior+)."""
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

        # Check caller rank
        if uid != _DEVELOPER_ID:
            cur.execute(f"SELECT rank FROM user_stats WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            row = cur.fetchone()
            rank = row[0] if row else "user"
            if _RANK_LEVELS.get(rank, 0) < _RANK_LEVELS["admin_junior"]:
                conn.close()
                return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

        # Fetch users with restrict_until in the future (banned = not None and far future)
        # Also check user_stats for restrict_type = 'ban' if that column exists
        try:
            cur.execute(
                f"SELECT s.user_id, COALESCE(u.full_name, CAST(s.user_id AS TEXT)) AS full_name, "
                f"u.username, s.restrict_until, s.restrict_type "
                f"FROM user_stats s LEFT JOIN users u ON u.user_id=s.user_id "
                f"WHERE s.chat_id={ph} AND s.restrict_type = 'ban' "
                f"ORDER BY s.restrict_until DESC LIMIT 100",
                (chat_id,),
            )
            rows = cur.fetchall()
            banned = [{"user_id": r[0], "name": r[1], "username": r[2],
                       "reason": "бан", "until": str(r[3]) if r[3] else None} for r in rows]
        except Exception:
            conn.rollback()
            # Fallback: users with restrict_until far in the future
            if db_type == "pg":
                cur.execute(
                    "SELECT s.user_id, COALESCE(u.full_name, CAST(s.user_id AS TEXT)), u.username, s.restrict_until "
                    "FROM user_stats s LEFT JOIN users u ON u.user_id=s.user_id "
                    "WHERE s.chat_id=%s AND s.restrict_until IS NOT NULL AND s.restrict_until > NOW() + INTERVAL '365 days' "
                    "ORDER BY s.restrict_until DESC LIMIT 100",
                    (chat_id,),
                )
            else:
                cur.execute(
                    "SELECT s.user_id, COALESCE(u.full_name, CAST(s.user_id AS TEXT)), u.username, s.restrict_until "
                    "FROM user_stats s LEFT JOIN users u ON u.user_id=s.user_id "
                    "WHERE s.chat_id=? AND s.restrict_until IS NOT NULL "
                    "ORDER BY s.restrict_until DESC LIMIT 100",
                    (chat_id,),
                )
            rows = cur.fetchall()
            banned = [{"user_id": r[0], "name": r[1], "username": r[2],
                       "reason": "бан", "until": str(r[3]) if r[3] else None} for r in rows]

        conn.close()
        return JsonResponse({"banned": banned}, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        logger.exception("miniapp_chat_banlist error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ──────────────────────────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_dev_error_logs(request):
    """GET /api/dev/error_logs  — list DB error logs (developer only).
       DELETE /api/dev/error_logs — clear all DB error logs (developer only)."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "Forbidden"}, status=403, headers=headers)

    from asgiref.sync import async_to_sync as _a2s

    if request.method == "GET":
        try:
            from database.db import get_app_error_logs
            logs = _a2s(get_app_error_logs)(1000)
            # Convert datetime objects to ISO strings for JSON serialisation
            for entry in logs:
                for k, v in entry.items():
                    if hasattr(v, "isoformat"):
                        entry[k] = v.isoformat()
            return JsonResponse({"ok": True, "logs": logs}, json_dumps_params={"ensure_ascii": False}, headers=headers)
        except Exception as exc:
            logger.exception("miniapp_dev_error_logs GET error")
            return JsonResponse({"error": str(exc)}, status=500, headers=headers)

    if request.method == "DELETE":
        try:
            from database.db import clear_app_error_logs
            _a2s(clear_app_error_logs)()
            return JsonResponse({"ok": True}, headers=headers)
        except Exception as exc:
            logger.exception("miniapp_dev_error_logs DELETE error")
            return JsonResponse({"error": str(exc)}, status=500, headers=headers)

    return JsonResponse({"error": "Method not allowed"}, status=405, headers=headers)


# ─── AF2 dynamic config ──────────────────────────────────────────────────────

# Mapping: miniapp key → (config constant name, min, max)
_AF2_KEYS = {
    "af2_enabled":            ("AF2_ENABLED",              0, 1),
    "antispam_enabled":       ("AF2_ANTISPAM_ENABLED",     0, 1),
    "newcomer_text_limit":    ("AF2_NEWCOMER_TEXT_LIMIT",    0, 30),
    "newcomer_text_window":   ("AF2_NEWCOMER_TEXT_WINDOW",   0.5, 30.0),
    "newcomer_text_mute":     ("AF2_NEWCOMER_TEXT_MUTE",     0, 86400),
    "newcomer_media_limit":   ("AF2_NEWCOMER_MEDIA_LIMIT",   0, 20),
    "newcomer_media_window":  ("AF2_NEWCOMER_MEDIA_WINDOW",  0.5, 30.0),
    "newcomer_media_mute":    ("AF2_NEWCOMER_MEDIA_MUTE",    0, 86400),
    "newcomer_sticker_limit": ("AF2_NEWCOMER_STICKER_LIMIT", 0, 20),
    "newcomer_sticker_window":("AF2_NEWCOMER_STICKER_WINDOW",0.5, 30.0),
    "newcomer_sticker_mute":  ("AF2_NEWCOMER_STICKER_MUTE",  0, 86400),
    "newcomer_mixed_limit":   ("AF2_NEWCOMER_MIXED_LIMIT",   0, 30),
    "newcomer_mixed_window":  ("AF2_NEWCOMER_MIXED_WINDOW",  0.5, 30.0),
    "newcomer_mixed_mute":    ("AF2_NEWCOMER_MIXED_MUTE",    0, 86400),
    "trusted_sticker_limit":  ("AF2_TRUSTED_STICKER_LIMIT",  0, 30),
    "trusted_sticker_window": ("AF2_TRUSTED_STICKER_WINDOW", 0.5, 60.0),
    "trusted_sticker_mute":   ("AF2_TRUSTED_STICKER_MUTE",   0, 86400),
    "trusted_media_limit":    ("AF2_TRUSTED_MEDIA_LIMIT",    0, 20),
    "trusted_media_window":   ("AF2_TRUSTED_MEDIA_WINDOW",   0.5, 30.0),
    "trusted_media_mute":     ("AF2_TRUSTED_MEDIA_MUTE",     0, 86400),
    "regular_sticker_limit":  ("AF2_REGULAR_STICKER_LIMIT",  0, 30),
    "regular_sticker_window": ("AF2_REGULAR_STICKER_WINDOW", 0.5, 60.0),
    "regular_sticker_mute":   ("AF2_REGULAR_STICKER_MUTE",   0, 86400),
    "regular_text_limit":     ("AF2_REGULAR_TEXT_LIMIT",      0, 30),
    "regular_text_window":    ("AF2_REGULAR_TEXT_WINDOW",     0.5, 60.0),
    "regular_text_mute":      ("AF2_REGULAR_TEXT_MUTE",       0, 86400),
    "trusted_text_limit":     ("AF2_TRUSTED_TEXT_LIMIT",      0, 30),
    "trusted_text_window":    ("AF2_TRUSTED_TEXT_WINDOW",     0.5, 60.0),
    "trusted_text_mute":      ("AF2_TRUSTED_TEXT_MUTE",       0, 86400),
    "newcomer_rate_limit":    ("AF2_NEWCOMER_RATE_LIMIT",     0, 50),
    "newcomer_rate_window":   ("AF2_NEWCOMER_RATE_WINDOW",    1.0, 120.0),
    "newcomer_rate_mute":     ("AF2_NEWCOMER_RATE_MUTE",      0, 86400),
    "antispam_limit":         ("AF2_ANTISPAM_LIMIT",          1, 50),
    "delete_window":          ("AF2_DELETE_WINDOW",           60, 86400 * 30),
    "newcomer_threshold":     ("TRUST_NEWCOMER_THRESHOLD",    10, 5000),
    "trusted_threshold":      ("TRUST_TRUSTED_THRESHOLD",     100, 50000),
}


@csrf_exempt
def miniapp_dev_af2_config(request):
    """GET /api/dev/af2_config  — read current AF2 config (developer or owner).
       POST /api/dev/af2_config — update AF2 config key(s) (developer or owner)."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    # Developer has unrestricted access (including chat_id=0 global config).
    # Owner/co_owner can only configure their OWN chat — global config is dev-only.
    if uid != _DEVELOPER_ID:
        try:
            import json as _jt
            if request.method in ("GET", "OPTIONS"):
                _cc = request.GET.get("chat_id", "0")
                _req_cid = int(_cc) if _cc.lstrip("-").isdigit() else 0
            else:
                # request.body is cached in Django, safe to read here
                _req_cid = int(_jt.loads(request.body or b"{}").get("chat_id", 0) or 0)
        except Exception:
            _req_cid = 0
        if _req_cid == 0:
            return JsonResponse({"error": "Forbidden"}, status=403, headers=headers)
        try:
            conn, db_type = _get_bot_db_connection()
            cur = conn.cursor()
            ph = "%s" if db_type == "pg" else "?"
            cur.execute(
                f"SELECT rank FROM user_stats WHERE user_id={ph} AND chat_id={ph} AND rank IN ('owner', 'co_owner')",
                (uid, _req_cid),
            )
            row = cur.fetchone()
            conn.close()
            is_privileged = bool(row)
        except Exception:
            is_privileged = False
        if not is_privileged:
            return JsonResponse({"error": "Forbidden"}, status=403, headers=headers)

    from asgiref.sync import async_to_sync as _a2s

    if request.method == "GET":
        try:
            chat_id_param = request.GET.get("chat_id", "0")
            req_chat_id = int(chat_id_param) if chat_id_param.lstrip("-").isdigit() else 0
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'PredvestnikBot'))
            import importlib
            cfg_mod = importlib.import_module("config")
            db_mod = importlib.import_module("database.db")

            # Load defaults from config constants
            defaults = {}
            for key, (const_name, _mn, _mx) in _AF2_KEYS.items():
                defaults[key] = getattr(cfg_mod, const_name, None)

            # Load DB overrides for the specific chat
            overrides = _a2s(db_mod.get_af2_config)(req_chat_id)

            # Merge: DB value wins over default
            merged = {k: overrides.get(k, defaults[k]) for k in _AF2_KEYS}
            return JsonResponse(
                {"ok": True, "config": merged, "defaults": defaults},
                json_dumps_params={"ensure_ascii": False},
                headers=headers,
            )
        except Exception:
            logger.exception("miniapp_dev_af2_config GET error")
            return JsonResponse({"error": "Internal error"}, status=500, headers=headers)

    if request.method == "POST":
        try:
            import json as _json, sys, os
            body = _json.loads(request.body)
            if not isinstance(body, dict):
                return JsonResponse({"error": "JSON object required"}, status=400, headers=headers)

            req_chat_id = int(body.pop("chat_id", 0) or 0)

            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'PredvestnikBot'))
            import importlib
            db_mod = importlib.import_module("database.db")

            validated = {}
            for key, raw_value in body.items():
                if key not in _AF2_KEYS:
                    return JsonResponse({"error": f"Unknown key: {key}"}, status=400, headers=headers)
                _, mn, mx = _AF2_KEYS[key]
                try:
                    v = float(raw_value)
                except (TypeError, ValueError):
                    return JsonResponse({"error": f"Value for {key} must be a number"}, status=400, headers=headers)
                if v < mn or v > mx:
                    return JsonResponse({"error": f"{key} must be between {mn} and {mx}"}, status=400, headers=headers)
                validated[key] = v

            _a2s(db_mod.set_af2_config)(validated, req_chat_id)
            return JsonResponse({"ok": True, "saved": list(validated.keys())}, headers=headers)
        except Exception:
            logger.exception("miniapp_dev_af2_config POST error")
            return JsonResponse({"error": "Internal error"}, status=500, headers=headers)

    return JsonResponse({"error": "Method not allowed"}, status=405, headers=headers)


@csrf_exempt
# =============================================================================
# SEASON PASS
# =============================================================================

@csrf_exempt
def miniapp_season_data(request):
    """GET /api/season/data — season pass info + user progress."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import get_active_season, get_season_progress, get_season_rewards

        season = _a2s(get_active_season)()
        if not season:
            return JsonResponse({"error": "No active season"}, status=404, headers=headers)

        season_id = season["id"]
        progress = _a2s(get_season_progress)(uid, season_id)
        rewards = _a2s(get_season_rewards)(season_id)

        season_out = {
            "id": season["id"],
            "name": season["name"],
            "start_date": season["start_date"].isoformat() if season.get("start_date") else None,
            "end_date": season["end_date"].isoformat() if season.get("end_date") else None,
            "active": season["active"],
        }

        return JsonResponse(
            {"season": season_out, "progress": progress, "rewards": rewards},
            json_dumps_params={"ensure_ascii": False},
            headers=headers,
        )
    except Exception:
        logger.exception("miniapp_season_data error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_season_claim(request):
    """POST /api/season/claim {season_id, level, is_premium} — claim a season reward."""
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

    season_id = int(data.get("season_id", 0))
    level = int(data.get("level", 0))
    is_premium = bool(data.get("is_premium", False))

    if not season_id or not level:
        return JsonResponse({"error": "season_id and level required"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import claim_season_reward

        result = _a2s(claim_season_reward)(uid, season_id, level, is_premium)
        if result.get("ok"):
            return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
        else:
            return JsonResponse(result, status=400, headers=headers)
    except Exception:
        logger.exception("miniapp_season_claim error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_season_premium(request):
    """POST /api/season/premium {season_id} — buy season premium pass."""
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

    season_id = int(data.get("season_id", 0))
    if not season_id:
        return JsonResponse({"error": "season_id required"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import buy_season_premium

        ok = _a2s(buy_season_premium)(uid, season_id)
        if ok:
            return JsonResponse({"ok": True}, headers=headers)
        else:
            return JsonResponse({"error": "Purchase failed"}, status=400, headers=headers)
    except Exception:
        logger.exception("miniapp_season_premium error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Cleanup pass shop (пропуск чистки) ──────────────────────────────────────────

def _send_tg_notification(chat_id_or_user: int, text: str, reply_markup: dict | None = None) -> None:
    """Fire-and-forget Telegram message from Django using the bot token."""
    if not _BOT_TOKEN:
        return
    try:
        import requests as _req
        payload: dict = {"chat_id": chat_id_or_user, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        _req.post(
            f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=5,
        )
    except Exception:
        pass


@csrf_exempt
def miniapp_cleanup_pass(request):
    """
    GET  /api/cleanup_pass?chat_id=X  → {status, pass_id, price, created_at}
    POST /api/cleanup_pass {chat_id}  → buy pass: deduct mora, create pending, notify admins
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
        try:
            from shared_prices import CLEANUP_PASS_COOLDOWN_DAYS
            conn, db_type = _get_bot_db_connection()
            ph = "%s" if db_type == "pg" else "?"
            cur = conn.cursor()
            # Active/pending pass
            cur.execute(
                f"SELECT id, status, price, created_at FROM cleanup_passes "
                f"WHERE user_id={ph} AND chat_id={ph} AND status IN ('pending','approved') "
                f"ORDER BY created_at DESC LIMIT 1",
                (uid, chat_id),
            )
            row = cur.fetchone()
            if row:
                conn.close()
                return JsonResponse(
                    {"exists": True, "pass_id": row[0], "status": row[1],
                     "price": row[2], "created_at": str(row[3])},
                    headers=headers,
                )
            # Check cooldown (last purchase of any status)
            cur.execute(
                f"SELECT created_at FROM cleanup_passes WHERE user_id={ph} AND chat_id={ph} "
                f"ORDER BY created_at DESC LIMIT 1",
                (uid, chat_id),
            )
            last_row = cur.fetchone()
            conn.close()
            if last_row:
                from datetime import datetime as _dt, timezone as _tz, timedelta as _td
                last_dt = last_row[0]
                if isinstance(last_dt, str):
                    last_dt = _dt.fromisoformat(last_dt.replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=_tz.utc)
                cooldown_until = last_dt + _td(days=CLEANUP_PASS_COOLDOWN_DAYS)
                now_utc = _dt.now(_tz.utc)
                if cooldown_until > now_utc:
                    remaining = cooldown_until - now_utc
                    remaining_days = remaining.days + (1 if remaining.seconds > 0 else 0)
                    return JsonResponse(
                        {"exists": False, "on_cooldown": True, "cooldown_days": remaining_days},
                        headers=headers,
                    )
            return JsonResponse({"exists": False, "on_cooldown": False}, headers=headers)
        except Exception:
            logger.exception("miniapp_cleanup_pass GET error")
            return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

        chat_id_raw = body.get("chat_id")
        if not chat_id_raw:
            return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
        chat_id = int(str(chat_id_raw))

        from shared_prices import CLEANUP_PASS_PRICE as _PASS_PRICE

        try:
            from asgiref.sync import async_to_sync as _a2s
            from database.db import (
                deduct_mora as _deduct,
                buy_cleanup_pass as _buy_pass,
                get_admin_groups as _get_admin_groups,
                get_staff_in_chat as _get_staff,
            )
            from database.db import get_mora as _get_mora

            # Check current balance
            mora = _a2s(_get_mora)(uid, chat_id)
            bal = mora["balance"] if mora else 0
            if bal < _PASS_PRICE:
                return JsonResponse(
                    {"error": f"Недостаточно моры. Нужно {_PASS_PRICE} 🪙, у тебя {bal} 🪙"},
                    status=400,
                    headers=headers,
                )

            # Check existing pass
            conn2, db_type2 = _get_bot_db_connection()
            ph2 = "%s" if db_type2 == "pg" else "?"
            cur2 = conn2.cursor()
            cur2.execute(
                f"SELECT id FROM cleanup_passes WHERE user_id={ph2} AND chat_id={ph2} "
                f"AND status IN ('pending','approved')",
                (uid, chat_id),
            )
            existing = cur2.fetchone()
            if not existing:
                # Check 12-day cooldown
                from shared_prices import CLEANUP_PASS_COOLDOWN_DAYS
                cur2.execute(
                    f"SELECT created_at FROM cleanup_passes WHERE user_id={ph2} AND chat_id={ph2} "
                    f"ORDER BY created_at DESC LIMIT 1",
                    (uid, chat_id),
                )
                last_pur = cur2.fetchone()
                if last_pur:
                    from datetime import datetime as _dt2, timezone as _tz2, timedelta as _td2
                    ld = last_pur[0]
                    if isinstance(ld, str):
                        ld = _dt2.fromisoformat(ld.replace("Z", "+00:00"))
                    if ld.tzinfo is None:
                        ld = ld.replace(tzinfo=_tz2.utc)
                    cooldown_until = ld + _td2(days=CLEANUP_PASS_COOLDOWN_DAYS)
                    now_check = _dt2.now(_tz2.utc)
                    if cooldown_until > now_check:
                        conn2.close()
                        rem = cooldown_until - now_check
                        rem_days = rem.days + (1 if rem.seconds > 0 else 0)
                        return JsonResponse(
                            {"error": f"Пропуск на кулдауне: следующая покупка через {rem_days} дн."},
                            status=400,
                            headers=headers,
                        )
            conn2.close()
            if existing:
                return JsonResponse(
                    {"error": "У тебя уже есть активный или ожидающий пропуск чистки"},
                    status=400,
                    headers=headers,
                )

            # Deduct mora
            ok, new_bal = _a2s(_deduct)(uid, chat_id, _PASS_PRICE)
            if not ok:
                return JsonResponse({"error": "Не удалось списать мору"}, status=400, headers=headers)

            # Create pass record
            pass_id = _a2s(_buy_pass)(uid, chat_id, _PASS_PRICE)

            # Get buyer name for notification
            conn3, db_type3 = _get_bot_db_connection()
            ph3 = "%s" if db_type3 == "pg" else "?"
            cur3 = conn3.cursor()
            cur3.execute(f"SELECT full_name FROM users WHERE user_id={ph3}", (uid,))
            urow = cur3.fetchone()
            user_name = html.escape(urow[0] if urow else str(uid))
            # Get chat title
            cur3.execute(f"SELECT title FROM chats WHERE chat_id={ph3}", (chat_id,))
            crow = cur3.fetchone()
            chat_title = html.escape(str(crow[0]) if crow and crow[0] else str(chat_id))
            conn3.close()

            # Notification markup
            kb = {
                "inline_keyboard": [[
                    {"text": "✅ Одобрить", "callback_data": f"cpass:approve:{pass_id}:{uid}:{chat_id}"},
                    {"text": "❌ Отклонить", "callback_data": f"cpass:reject:{pass_id}:{uid}:{chat_id}"},
                ]]
            }
            notify_text = (
                f"🎫 <b>Заявка на пропуск чистки</b>\n\n"
                f"👤 {user_name} (<code>{uid}</code>)\n"
                f"💬 {chat_title}\n"
                f"💰 Оплачено: <b>{_PASS_PRICE} 🪙</b>\n"
                f"📋 Заявка #{pass_id}"
            )

            # Notify admin groups
            admin_groups = _a2s(_get_admin_groups)()
            for ag in admin_groups:
                _send_tg_notification(ag, notify_text, kb)

            # Notify owner/developer in this chat + global developer
            notified: set = set(admin_groups)
            staff = _a2s(_get_staff)(chat_id)
            for s in staff:
                if s["rank"] in ("owner",) and s["user_id"] not in notified:
                    _send_tg_notification(s["user_id"], notify_text, kb)
                    notified.add(s["user_id"])
            if _DEVELOPER_ID not in notified:
                _send_tg_notification(_DEVELOPER_ID, notify_text, kb)

            return JsonResponse(
                {"ok": True, "pass_id": pass_id, "new_balance": new_bal, "price": _PASS_PRICE},
                headers=headers,
            )
        except Exception:
            logger.exception("miniapp_cleanup_pass POST error")
            return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)

    return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)


# ─── Bot timezone management ──────────────────────────────────────────────────

@csrf_exempt
def miniapp_timezone(request):
    """
    GET  /api/timezone         → {timezone}
    POST /api/timezone {tz}    → set timezone (developer only)
    """
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    if request.method == "GET":
        try:
            import pathlib, re as _re
            cfg_path = pathlib.Path(__file__).resolve().parent.parent.parent / "PredvestnikBot" / "config.py"
            content = cfg_path.read_text(encoding="utf-8")
            m = _re.search(r'BOT_TIMEZONE\s*=\s*"([^"]+)"', content)
            tz_val = m.group(1) if m else "Europe/Zurich"
            return JsonResponse({"timezone": tz_val}, headers=headers)
        except Exception:
            return JsonResponse({"timezone": "Europe/Zurich"}, headers=headers)

    if request.method == "POST":
        # Only developer can change timezone
        if uid != _DEVELOPER_ID:
            return JsonResponse({"error": "forbidden"}, status=403, headers=headers)

        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

        tz_name = str(body.get("tz", "")).strip()
        if not tz_name:
            return JsonResponse({"error": "tz required"}, status=400, headers=headers)

        # Validate IANA timezone name
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(tz_name)
        except Exception:
            return JsonResponse({"error": f"Неизвестный часовой пояс: {tz_name}"}, status=400, headers=headers)

        # Write to config.py
        try:
            import pathlib, re as _re
            cfg_path = pathlib.Path(__file__).resolve().parent.parent.parent / "PredvestnikBot" / "config.py"
            content = cfg_path.read_text(encoding="utf-8")
            new_content, n = _re.subn(
                r'BOT_TIMEZONE\s*=\s*"[^"]*"',
                f'BOT_TIMEZONE = "{tz_name}"',
                content,
            )
            if n == 0:
                return JsonResponse({"error": "Не удалось найти BOT_TIMEZONE в config.py"}, status=500, headers=headers)
            cfg_path.write_text(new_content, encoding="utf-8")
            return JsonResponse({"ok": True, "timezone": tz_name}, headers=headers)
        except Exception:
            logger.exception("miniapp_timezone POST error")
            return JsonResponse({"error": "Не удалось записать настройку"}, status=500, headers=headers)

    return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)


def miniapp_frontend_error_log(request):
    """POST /api/frontend_error_log — capture a JS error from the Mini App front-end."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    # Allow unauthenticated to not break boot errors, but still log uid if available
    if err:
        uid = None

    try:
        body = json.loads(request.body)
        context = str(body.get("context", "frontend"))[:200]
        message = str(body.get("message", ""))[:500]
        stack = str(body.get("stack", ""))[:8000]
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    _log_error_to_db_frontend(context, message, stack, uid)
    return JsonResponse({"ok": True}, headers=headers)


def _log_error_to_db_frontend(context: str, message: str, stack: str, uid=None):
    """Write a frontend error to app_error_logs. Never raises."""
    try:
        url = _BOT_DB_URL
        if not (url.startswith("postgresql://") or url.startswith("postgres://")):
            return
        import psycopg2
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO app_error_logs (source, context, error_msg, traceback, user_id) "
            "VALUES ('frontend', %s, %s, %s, %s)",
            (context, message, stack, uid),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ─── Dev: bulk import users from JSON ─────────────────────────────────────────

@csrf_exempt
def miniapp_dev_import_users(request):
    """POST /api/dev/import_users — import message-count records into a chat.
    Body: {chat_id: int, records: [{user_id?, username?, messages: int, full_name?}, ...]}
    Auth: developer or owner/co_owner.
    """
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    # Allow developer by UID, or any owner/co_owner rank
    if uid != _DEVELOPER_ID:
        try:
            conn, db_type = _get_bot_db_connection()
            cur = conn.cursor()
            ph = "%s" if db_type == "pg" else "?"
            cur.execute(
                f"SELECT rank FROM user_stats WHERE user_id={ph} AND rank IN ('owner', 'co_owner') LIMIT 1",
                (uid,),
            )
            row = cur.fetchone()
            conn.close()
            is_privileged = bool(row)
        except Exception:
            is_privileged = False
        if not is_privileged:
            return JsonResponse({"error": "Forbidden"}, status=403, headers=headers)

    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0") or "0"))
        records = body.get("records")
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400, headers=headers)

    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    if not isinstance(records, list) or not records:
        return JsonResponse({"error": "records must be a non-empty list"}, status=400, headers=headers)

    # Sanitise and cap records
    MAX_RECORDS = 10_000
    clean: list[dict] = []
    for rec in records[:MAX_RECORDS]:
        if not isinstance(rec, dict):
            continue
        entry: dict = {"messages": int(rec.get("messages") or rec.get("message_count") or 0)}
        raw_uid = rec.get("user_id")
        if raw_uid is not None:
            try:
                entry["user_id"] = int(raw_uid)
            except (ValueError, TypeError):
                pass
        raw_name = str(rec.get("full_name") or "").strip()
        if raw_name:
            entry["full_name"] = raw_name[:200]
        raw_uname = str(rec.get("username") or "").strip()
        if raw_uname:
            entry["username"] = raw_uname[:64]
        # Pass through per-period message counts from the JSON parser
        for _cnt_field in ("week_count", "day_count", "yesterday_count", "last_week_count"):
            _cnt_val = rec.get(_cnt_field)
            if _cnt_val is not None:
                try:
                    entry[_cnt_field] = max(0, int(_cnt_val))
                except (ValueError, TypeError):
                    pass
        if entry["messages"] > 0:
            clean.append(entry)

    if not clean:
        return JsonResponse({"error": "No valid records after sanitisation"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'PredvestnikBot'))
        from database.db import import_users_bulk as _import_users_bulk
        result = _a2s(_import_users_bulk)(clean, chat_id)
        return JsonResponse(
            {"ok": True, "ok_direct": result["ok_direct"], "ok_pending": result["ok_pending"],
             "errors": result["errors"][:50]},
            json_dumps_params={"ensure_ascii": False},
            headers=headers,
        )
    except Exception:
        logger.exception("miniapp_dev_import_users error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Dev: scan which user_ids are currently in a chat ─────────────────────────

@csrf_exempt
async def miniapp_dev_scan_members(request):
    """POST /api/dev/scan_members — check Telegram membership for a list of user_ids.
    Body: {chat_id: int, user_ids: [int, ...]}
    Returns: {active: [int, ...], inactive: [int, ...], errors: int}
    Auth: developer or owner/co_owner.
    Async view: uses httpx.AsyncClient + asyncio.gather so it never blocks Daphne.
    """
    import asyncio
    import httpx as _httpx

    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    # _require_auth is sync — run in thread to avoid blocking event loop
    auth_uid, err = await asyncio.to_thread(_require_auth, request, headers)
    if err:
        return err

    if auth_uid != _DEVELOPER_ID:
        def _check_priv():
            try:
                conn, db_type = _get_bot_db_connection()
                cur = conn.cursor()
                ph = "%s" if db_type == "pg" else "?"
                cur.execute(
                    f"SELECT rank FROM user_stats WHERE user_id={ph} AND rank IN ('owner', 'co_owner') LIMIT 1",
                    (auth_uid,),
                )
                row = cur.fetchone()
                conn.close()
                return bool(row)
            except Exception:
                return False
        is_privileged = await asyncio.to_thread(_check_priv)
        if not is_privileged:
            return JsonResponse({"error": "Forbidden"}, status=403, headers=headers)

    if not _BOT_TOKEN:
        return JsonResponse({"error": "Bot token not configured"}, status=500, headers=headers)

    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0") or "0"))
        raw_ids = body.get("user_ids", [])
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400, headers=headers)

    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    if not isinstance(raw_ids, list):
        return JsonResponse({"error": "user_ids must be a list"}, status=400, headers=headers)

    # Sanitise and cap
    user_ids = []
    for x in raw_ids[:2000]:
        try:
            user_ids.append(int(x))
        except (TypeError, ValueError):
            pass

    if not user_ids:
        return JsonResponse({"active": [], "inactive": [], "errors": 0}, headers=headers)

    _ACTIVE_STATUSES = {"member", "administrator", "creator", "restricted"}
    _tg_url = f"https://api.telegram.org/bot{_BOT_TOKEN}/getChatMember"
    # Semaphore limits concurrent Telegram API calls to avoid rate-limiting
    sem = asyncio.Semaphore(30)

    async def _check(client, uid):
        async with sem:
            try:
                resp = await client.get(
                    _tg_url,
                    params={"chat_id": str(chat_id), "user_id": str(uid)},
                    timeout=5.0,
                )
                data = resp.json()
                if data.get("ok"):
                    result = data["result"]
                    status = result.get("status", "left")
                    is_member = status in _ACTIVE_STATUSES
                    is_bot = result.get("user", {}).get("is_bot", False)
                    return uid, is_member, is_bot
                # Bot can't see this user — treat as inactive, not a bot
                return uid, False, False
            except Exception:
                return uid, None, False  # None = network/timeout error

    active = []
    inactive = []
    bots = []
    err_count = 0

    async with _httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_check(client, u) for u in user_ids])

    for uid, is_member, is_bot in results:
        if is_member is None:
            err_count += 1
        elif is_bot:
            bots.append(uid)
        elif is_member:
            active.append(uid)
        else:
            inactive.append(uid)

    return JsonResponse(
        {"active": active, "inactive": inactive, "bots": bots, "errors": err_count},
        headers=headers,
    )


# ─── Dev: purge non-members from bot DB for a specific chat ───────────────────

@csrf_exempt
async def miniapp_dev_purge_chat_nonmembers(request):
    """POST /api/dev/purge_chat_nonmembers — delete per-chat DB rows for users NOT in chat.
    Body: {chat_id: int, user_ids: [int, ...]}  ← the INACTIVE user_ids to remove
    Returns: {deleted: int}
    Auth: developer or owner/co_owner.
    """
    import asyncio

    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405, headers=headers)

    auth_uid, err = await asyncio.to_thread(_require_auth, request, headers)
    if err:
        return err

    if auth_uid != _DEVELOPER_ID:
        def _check_priv():
            try:
                conn, db_type = _get_bot_db_connection()
                cur = conn.cursor()
                ph = "%s" if db_type == "pg" else "?"
                cur.execute(
                    f"SELECT rank FROM user_stats WHERE user_id={ph} AND rank IN ('owner', 'co_owner') LIMIT 1",
                    (auth_uid,),
                )
                row = cur.fetchone()
                conn.close()
                return bool(row)
            except Exception:
                return False
        is_privileged = await asyncio.to_thread(_check_priv)
        if not is_privileged:
            return JsonResponse({"error": "Forbidden"}, status=403, headers=headers)

    try:
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0") or "0"))
        raw_ids = body.get("user_ids", [])
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400, headers=headers)

    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
    if not isinstance(raw_ids, list):
        return JsonResponse({"error": "user_ids must be a list"}, status=400, headers=headers)

    # Sanitise
    user_ids = []
    for x in raw_ids[:5000]:
        try:
            user_ids.append(int(x))
        except (TypeError, ValueError):
            pass

    if not user_ids:
        return JsonResponse({"deleted": 0}, headers=headers)

    # Tables with (user_id, chat_id) that hold per-chat data
    _PER_CHAT_TABLES = [
        "user_stats",
        "user_mora",
        "cleanup_counts",
        "user_quests",
    ]

    def _do_purge():
        try:
            conn, db_type = _get_bot_db_connection()
            cur = conn.cursor()
            if db_type == "pg":
                import psycopg2.extras
                # Use ANY() for efficient batch delete
                id_tuple = tuple(user_ids)
                for tbl in _PER_CHAT_TABLES:
                    cur.execute(
                        f"DELETE FROM {tbl} WHERE user_id = ANY(%s) AND chat_id = %s",
                        (list(id_tuple), chat_id),
                    )
            else:
                # SQLite: delete one by one (no ANY())
                ph = "?"
                for uid in user_ids:
                    for tbl in _PER_CHAT_TABLES:
                        cur.execute(
                            f"DELETE FROM {tbl} WHERE user_id={ph} AND chat_id={ph}",
                            (uid, chat_id),
                        )
            conn.commit()
            conn.close()
            return len(user_ids)
        except Exception as e:
            import traceback
            _log_error_to_db("purge_chat_nonmembers", traceback.format_exc())
            raise

    try:
        deleted = await asyncio.to_thread(_do_purge)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500, headers=headers)

    return JsonResponse({"deleted": deleted}, headers=headers)


# ─── Dev: user inventory viewer ───────────────────────────────────────────────

@csrf_exempt
def miniapp_dev_user_inventory(request):
    """GET /api/dev/user_inventory?user_id=X&chat_id=Y — developer only: list user inventory."""
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

    target_id = request.GET.get("user_id", "")
    chat_id_str = request.GET.get("chat_id", "")
    if not target_id.isdigit():
        return JsonResponse({"error": "user_id required"}, status=400, headers=headers)
    target_id = int(target_id)

    try:
        conn, db_type = _get_bot_db_connection()
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        cur.execute(
            f"SELECT id, item_key, item_name, rarity, equipped, "
            f"COALESCE(stack_count,1) AS stack_count, slot "
            f"FROM gacha_inventory WHERE user_id={ph} ORDER BY id DESC",
            (target_id,),
        )
        cols = [d[0] for d in cur.description]
        items = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()

        _RARITY_EMOJI = {"junk": "⚪", "common": "🔵", "rare": "🟣", "legendary": "🟡"}
        for it in items:
            it["emoji"] = _RARITY_EMOJI.get(it.get("rarity", ""), "📦")
            it["name"] = it.get("item_name") or it.get("item_key") or "❓"

        return JsonResponse({"items": items}, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        logger.exception("dev_user_inventory error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Dev: delete inventory item ───────────────────────────────────────────────

@csrf_exempt
def miniapp_dev_delete_inventory_item(request):
    """POST /api/dev/delete_inventory_item {item_id: int} — developer only: delete an item."""
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
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)
    item_id = body.get("item_id")
    if not item_id:
        return JsonResponse({"error": "item_id required"}, status=400, headers=headers)

    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "invalid item_id"}, status=400, headers=headers)

    try:
        conn, db_type = _get_bot_db_connection()
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        cur.execute(f"DELETE FROM gacha_inventory WHERE id={ph}", (item_id,))
        conn.commit()
        conn.close()
        return JsonResponse({"ok": True}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        logger.exception("dev_delete_inventory_item error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Dev: feature toggle per chat ────────────────────────────────────────────

_ALLOWED_FEATURE_KEYS = frozenset({
    "feat_website", "feat_antispam", "feat_marriages",
    "feat_pets", "feat_casino", "feat_random_events",
    "bot_disabled",
    # Granular toggles
    "feat_roulette", "feat_chest", "feat_coin_flip",
    "feat_xp_gain", "feat_auto_welcome", "antiflood_mode",
})

@csrf_exempt
def miniapp_dev_feature_toggle(request):
    """POST /api/dev/feature_toggle {chat_id, feature, enabled} — developer only."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method not in ("GET", "POST"):
        return JsonResponse({"error": "GET/POST required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err
    if uid != _DEVELOPER_ID:
        return JsonResponse({"error": "Forbidden"}, status=403, headers=headers)

    if request.method == "GET":
        # Return current feature flags for a chat
        try:
            chat_id = int(request.GET.get("chat_id", 0) or 0)
            conn, db_type = _get_bot_db_connection()
            cur = conn.cursor()
            ph = "%s" if db_type == "pg" else "?"
            cur.execute(
                f"SELECT feat_website, feat_antispam, feat_marriages, feat_pets, feat_casino, feat_random_events, bot_disabled "
                f"FROM chat_settings WHERE chat_id={ph}",
                (chat_id,),
            )
            row = cur.fetchone()
            conn.close()
            if row:
                keys = ["feat_website", "feat_antispam", "feat_marriages", "feat_pets", "feat_casino", "feat_random_events", "bot_disabled"]
                # For feat_* columns default is 1 (enabled); for bot_disabled default is 0 (not disabled)
                feat_defaults = {"bot_disabled": 0}
                flags = {k: bool(v if v is not None else feat_defaults.get(k, 1)) for k, v in zip(keys, row)}
            else:
                flags = {k: True for k in ["feat_website", "feat_antispam", "feat_marriages", "feat_pets", "feat_casino", "feat_random_events"]}
                flags["bot_disabled"] = False
            return JsonResponse({"ok": True, "flags": flags}, headers=headers)
        except Exception:
            logger.exception("miniapp_dev_feature_toggle GET error")
            return JsonResponse({"error": "Internal error"}, status=500, headers=headers)

    # POST
    try:
        body = json.loads(request.body)
        chat_id = int(body.get("chat_id") or 0)
        feature = str(body.get("feature") or "")
        enabled = bool(body.get("enabled", True))
        if feature not in _ALLOWED_FEATURE_KEYS:
            return JsonResponse({"error": f"Unknown feature: {feature!r}"}, status=400, headers=headers)
        import sys as _sys, os as _os
        _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', 'PredvestnikBot'))
        import importlib as _importlib
        _db = _importlib.import_module("database.db")
        from asgiref.sync import async_to_sync as _a2s
        _a2s(_db.set_chat_setting)(chat_id, feature, 1 if enabled else 0)
        return JsonResponse({"ok": True, "feature": feature, "enabled": enabled}, headers=headers)
    except Exception:
        logger.exception("miniapp_dev_feature_toggle POST error")
        return JsonResponse({"error": "Internal error"}, status=500, headers=headers)


# ═══════════════════════════════════════════════════════════════════════════════
#  SETTINGS: Local (per-chat) with rank-based access control
# ═══════════════════════════════════════════════════════════════════════════════

# Maps each setting key → minimum rank required to change it
_SETTING_RANK_MAP = {
    # Feature toggles — admin_senior (raised from junior: can affect whole chat economy/UX)
    "feat_roulette":     "admin_senior",
    "feat_chest":        "admin_senior",
    "feat_coin_flip":    "admin_senior",
    "feat_auto_welcome": "admin_senior",
    "feat_casino":       "admin_senior",
    "feat_random_events":"admin_senior",
    "feat_marriages":    "admin_senior",
    "feat_pets":         "admin_senior",
    "feat_website":      "admin_senior",
    "feat_antispam":     "admin_senior",
    # XP / economy — co_owner only (disabling XP gain is a chat-wide economic impact)
    "feat_xp_gain":      "co_owner",
    # Antiflood — on/off is junior; destructive settings (kick/limit) require senior
    "antiflood_enabled": "admin_junior",
    "antiflood_limit":   "admin_senior",
    "antiflood_action":  "admin_senior",
    "antiflood_window":  "admin_senior",
    "antiflood_mode":    "admin_senior",
    # Welcome — raised to senior to prevent phishing link injection
    "welcome_text":      "admin_senior",
    "farewell_text":     "admin_senior",
    "welcome_call":      "admin_junior",
    # Content
    "rules_text":        "admin_senior",
    "blacklist_enabled": "admin_junior",
    # Cleanup
    "cleanup_threshold":     "co_owner",
    "cleanup_message_norm":  "co_owner",
    "cleanup_warn_hours":    "co_owner",
    "inactivity_warn_enabled":"co_owner",
    "inactivity_warn_days":  "co_owner",
    # Full control
    "bot_disabled":      "owner",
}


@csrf_exempt
def miniapp_settings_local(request):
    """
    GET  /api/settings/local?chat_id=X  → returns all per-chat settings + user rank + rank map
    POST /api/settings/local  {chat_id, key, value}  → rank-checked update
    """
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    uid, err = _require_auth(request, headers)
    if err:
        return err

    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', 'PredvestnikBot'))
    import importlib as _importlib
    _db = _importlib.import_module("database.db")
    from asgiref.sync import async_to_sync as _a2s

    if request.method == "GET":
        try:
            chat_id = int(request.GET.get("chat_id", 0) or 0)
            if not chat_id:
                return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)

            # Get user rank
            caller_rank, rank_err = _check_rank(uid, chat_id, "user", headers)
            if rank_err:
                return rank_err

            settings_row = _a2s(_db.get_chat_settings)(chat_id)

            # Build settings dict
            _SETTING_KEYS = [
                "antiflood_enabled", "antiflood_limit", "antiflood_action", "antiflood_window",
                "antiflood_mode", "blacklist_enabled", "welcome_call",
                "feat_website", "feat_antispam", "feat_marriages", "feat_pets",
                "feat_casino", "feat_random_events", "bot_disabled",
                "feat_roulette", "feat_chest", "feat_coin_flip",
                "feat_xp_gain", "feat_auto_welcome",
                "cleanup_threshold", "cleanup_message_norm", "cleanup_warn_hours",
                "inactivity_warn_enabled", "inactivity_warn_days",
            ]
            settings = {}
            for k in _SETTING_KEYS:
                if settings_row:
                    val = settings_row.get(k) if hasattr(settings_row, 'get') else getattr(settings_row, k, None)
                    if val is None:
                        # Defaults for feat_* = 1, numeric = their default
                        val = 1 if k.startswith("feat_") else 0
                    settings[k] = val
                else:
                    settings[k] = 1 if k.startswith("feat_") else 0
            if settings_row and not settings.get("antiflood_mode"):
                settings["antiflood_mode"] = "soft"

            # Return rank map so frontend knows what's locked
            rank_map = {}
            for sk, sr in _SETTING_RANK_MAP.items():
                rank_map[sk] = {
                    "min_rank": sr,
                    "min_rank_level": _RANK_LEVELS.get(sr, 0),
                    "min_rank_name": _RANK_NAMES_RU.get(sr, sr),
                }

            return JsonResponse({
                "ok": True,
                "settings": settings,
                "user_rank": caller_rank,
                "user_rank_level": _RANK_LEVELS.get(caller_rank, 0),
                "rank_map": rank_map,
            }, headers=headers)
        except Exception:
            logger.exception("miniapp_settings_local GET error")
            return JsonResponse({"error": "Internal error"}, status=500, headers=headers)

    # POST — update a setting
    if request.method != "POST":
        return JsonResponse({"error": "GET/POST required"}, status=405, headers=headers)

    try:
        body = json.loads(request.body)
        chat_id = int(body.get("chat_id") or 0)
        key = str(body.get("key") or "")
        value = body.get("value")
        if not chat_id or not key:
            return JsonResponse({"error": "chat_id and key required"}, status=400, headers=headers)

        # Check required rank for this setting
        required_rank = _SETTING_RANK_MAP.get(key, "owner")
        caller_rank, rank_err = _check_rank(uid, chat_id, required_rank, headers)
        if rank_err:
            return rank_err

        _a2s(_db.set_chat_setting)(chat_id, key, value)
        return JsonResponse({"ok": True, "key": key, "value": value}, headers=headers)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400, headers=headers)
    except Exception:
        logger.exception("miniapp_settings_local POST error")
        return JsonResponse({"error": "Internal error"}, status=500, headers=headers)


# ═══════════════════════════════════════════════════════════════════════════════
#  SETTINGS: Global (bot-wide) — developer only (+ maintenance_mode for owner)
# ═══════════════════════════════════════════════════════════════════════════════

_GLOBAL_SETTING_KEYS = {
    "maintenance_mode":    "developer",  # 0/1
    "bond_limit_per_user": "developer",  # integer
    "shop_enabled":        "developer",  # 0/1
    "gacha_enabled":       "developer",  # 0/1
    "auction_enabled":     "developer",  # 0/1
}


@csrf_exempt
def miniapp_settings_global(request):
    """
    GET  /api/settings/global  → returns all global settings
    POST /api/settings/global  {key, value}  → developer only
    """
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    uid, err = _require_auth(request, headers)
    if err:
        return err

    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', 'PredvestnikBot'))
    import importlib as _importlib
    _db = _importlib.import_module("database.db")
    from asgiref.sync import async_to_sync as _a2s

    if request.method == "GET":
        try:
            all_settings = _a2s(_db.get_all_global_settings)()
            return JsonResponse({
                "ok": True,
                "settings": all_settings,
                "is_dev": uid == _DEVELOPER_ID,
            }, headers=headers)
        except Exception:
            logger.exception("miniapp_settings_global GET error")
            return JsonResponse({"error": "Internal error"}, status=500, headers=headers)

    if request.method != "POST":
        return JsonResponse({"error": "GET/POST required"}, status=405, headers=headers)

    try:
        body = json.loads(request.body)
        key = str(body.get("key") or "")
        value = str(body.get("value", ""))
        if key not in _GLOBAL_SETTING_KEYS:
            return JsonResponse({"error": f"Unknown global setting: {key!r}"}, status=400, headers=headers)

        required_rank = _GLOBAL_SETTING_KEYS[key]
        if uid != _DEVELOPER_ID:
            # For now, all global settings require developer
            return JsonResponse(
                {"error": "forbidden", "required_rank": required_rank,
                 "required_rank_name": _RANK_NAMES_RU.get(required_rank, required_rank)},
                status=403, headers=headers,
            )

        _a2s(_db.set_global_setting)(key, value, uid)
        return JsonResponse({"ok": True, "key": key, "value": value}, headers=headers)
    except Exception:
        logger.exception("miniapp_settings_global POST error")
        return JsonResponse({"error": "Internal error"}, status=500, headers=headers)


# ═══════════════════════════════════════════════════════════════════════════════
#  CHAT TAGS — per-user role labels in chat
# ═══════════════════════════════════════════════════════════════════════════════

@csrf_exempt
def miniapp_chat_tags(request):
    """
    GET    /api/chat_tags?chat_id=X          → list all tags
    POST   /api/chat_tags  {chat_id, user_id, tag}  → set tag (moderator+)
    DELETE /api/chat_tags  {chat_id, user_id}        → remove tag (moderator+)
    """
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    uid, err = _require_auth(request, headers)
    if err:
        return err

    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', 'PredvestnikBot'))
    import importlib as _importlib
    _db = _importlib.import_module("database.db")
    from asgiref.sync import async_to_sync as _a2s

    if request.method == "GET":
        try:
            chat_id = int(request.GET.get("chat_id", 0) or 0)
            if not chat_id:
                return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
            tags = _a2s(_db.get_all_chat_tags)(chat_id)
            return JsonResponse({"ok": True, "tags": tags}, headers=headers)
        except Exception:
            logger.exception("miniapp_chat_tags GET error")
            return JsonResponse({"error": "Internal error"}, status=500, headers=headers)

    if request.method in ("POST", "DELETE"):
        try:
            body = json.loads(request.body)
            chat_id = int(body.get("chat_id") or 0)
            target_uid = int(body.get("user_id") or 0)
            if not chat_id or not target_uid:
                return JsonResponse({"error": "chat_id and user_id required"}, status=400, headers=headers)

            # Require moderator+ rank
            caller_rank, rank_err = _check_rank(uid, chat_id, "moderator", headers)
            if rank_err:
                return rank_err

            if request.method == "DELETE" or body.get("_action") == "delete":
                removed = _a2s(_db.remove_chat_tag)(target_uid, chat_id)
                return JsonResponse({"ok": True, "removed": removed}, headers=headers)
            else:
                tag = str(body.get("tag") or "").strip()
                if not tag:
                    return JsonResponse({"error": "tag is required"}, status=400, headers=headers)
                if len(tag) > 50:
                    return JsonResponse({"error": "tag too long (max 50)"}, status=400, headers=headers)
                _a2s(_db.set_chat_tag)(target_uid, chat_id, tag, uid)
                return JsonResponse({"ok": True, "user_id": target_uid, "tag": tag}, headers=headers)
        except Exception:
            logger.exception("miniapp_chat_tags POST/DELETE error")
            return JsonResponse({"error": "Internal error"}, status=500, headers=headers)

    return JsonResponse({"error": "Method not allowed"}, status=405, headers=headers)


# ─── Tag Definitions ─────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_tag_definitions(request):
    """
    GET    /api/tag_definitions?chat_id=X       → list all tag definitions with holder info
    POST   /api/tag_definitions  {chat_id, name, description, color, emoji}  → create (co_owner+)
    PATCH  /api/tag_definitions  {chat_id, name, description, color, emoji}  → update (co_owner+)
    DELETE /api/tag_definitions  {chat_id, name}                             → delete (co_owner+)
    """
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    uid, err = _require_auth(request, headers)
    if err:
        return err

    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', 'PredvestnikBot'))
    import importlib as _importlib
    _db = _importlib.import_module("database.db")
    from asgiref.sync import async_to_sync as _a2s

    if request.method == "GET":
        try:
            chat_id = int(request.GET.get("chat_id", 0) or 0)
            if not chat_id:
                return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)
            defs = _a2s(_db.get_tag_definitions)(chat_id)
            return JsonResponse({"ok": True, "definitions": defs}, headers=headers)
        except Exception:
            logger.exception("miniapp_tag_definitions GET error")
            return JsonResponse({"error": "Internal error"}, status=500, headers=headers)

    if request.method in ("POST", "PATCH", "DELETE"):
        try:
            body = json.loads(request.body)
            chat_id = int(body.get("chat_id") or 0)
            if not chat_id:
                return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)

            # Require co_owner+ rank
            caller_rank, rank_err = _check_rank(uid, chat_id, "co_owner", headers)
            if rank_err:
                return rank_err

            if request.method == "DELETE":
                name = str(body.get("name") or "").strip()
                if not name:
                    return JsonResponse({"error": "name required"}, status=400, headers=headers)
                deleted = _a2s(_db.delete_tag_definition)(chat_id, name)
                return JsonResponse({"ok": True, "deleted": deleted}, headers=headers)

            name = str(body.get("name") or "").strip()
            if not name:
                return JsonResponse({"error": "name required"}, status=400, headers=headers)
            description = str(body.get("description") or "").strip()
            color = str(body.get("color") or "#7c6af7").strip()
            emoji = str(body.get("emoji") or "").strip()

            if request.method == "POST":
                new_id = _a2s(_db.create_tag_definition)(chat_id, name, description, color, emoji, uid)
                if new_id is None:
                    return JsonResponse({"error": "Тег с таким именем уже существует"}, status=409, headers=headers)
                return JsonResponse({"ok": True, "id": new_id, "name": name}, headers=headers)

            if request.method == "PATCH":
                updated = _a2s(_db.update_tag_definition)(chat_id, name, description, color, emoji)
                return JsonResponse({"ok": True, "updated": updated}, headers=headers)

        except Exception:
            logger.exception("miniapp_tag_definitions POST/PATCH/DELETE error")
            return JsonResponse({"error": "Internal error"}, status=500, headers=headers)

    return JsonResponse({"error": "Method not allowed"}, status=405, headers=headers)


# ─── Save avatar URL ──────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_save_avatar(request):
    """POST /api/save_avatar {photo_url: str} — save Telegram avatar URL for the user."""
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
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)
    photo_url = (body.get("photo_url") or "").strip()
    if not photo_url or not photo_url.startswith("https://"):
        return JsonResponse({"error": "valid https photo_url required"}, status=400, headers=headers)
    # Whitelist Telegram CDN domains to prevent storing arbitrary URLs
    from urllib.parse import urlparse as _urlparse
    _allowed_hosts = {"t.me", "telegram.org", "cdn4.telegram-cdn.org", "cdn5.telegram-cdn.org"}
    _parsed = _urlparse(photo_url)
    if _parsed.hostname not in _allowed_hosts:
        return JsonResponse({"error": "Only Telegram avatar URLs are allowed"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import is_avatar_unlocked, unlock_avatar
        if not _a2s(is_avatar_unlocked)(uid):
            return JsonResponse({"error": "Avatar not unlocked"}, status=403, headers=headers)
        _a2s(unlock_avatar)(uid, photo_url)
        return JsonResponse({"ok": True}, headers=headers)
    except Exception as exc:
        logger.exception("save_avatar error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_use_transfer_pass(request):
    """POST /api/transfer_pass/use {chat_id, item_id} — consume a transfer pass to unlock a locked inventory item."""
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
        item_id = int(str(body.get("item_id", "0")))
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not chat_id or not item_id:
        return JsonResponse({"error": "chat_id and item_id required"}, status=400, headers=headers)

    try:
        conn, db_type = _get_bot_db_connection()
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Atomic pass deduction: deduct 1 pass only if passes > 0
        cur.execute(
            f"UPDATE crystal_transfer_passes SET passes = passes - 1 WHERE user_id={ph} AND COALESCE(passes, 0) > 0",
            (uid,),
        )
        if cur.rowcount == 0:
            conn.close()
            return JsonResponse({"error": "У вас нет Пропусков переноса 🎫"}, status=400, headers=headers)

        # Check item belongs to user
        cur.execute(
            f"SELECT id FROM gacha_inventory WHERE id={ph} AND user_id={ph} AND chat_id={ph}",
            (item_id, uid, chat_id),
        )
        item_row = cur.fetchone()
        if not item_row:
            conn.rollback()
            conn.close()
            return JsonResponse({"error": "Предмет не найден в вашем инвентаре"}, status=404, headers=headers)

        # Unlock item by backdating obtained_at to 4 days ago
        if db_type == "pg":
            cur.execute(
                f"UPDATE gacha_inventory SET obtained_at = NOW() - INTERVAL '4 days' WHERE id={ph} AND user_id={ph}",
                (item_id, uid),
            )
        else:
            cur.execute(
                f"UPDATE gacha_inventory SET obtained_at = datetime('now', '-4 days') WHERE id={ph} AND user_id={ph}",
                (item_id, uid),
            )
        conn.commit()

        # Get remaining passes
        cur.execute(f"SELECT COALESCE(passes, 0) FROM crystal_transfer_passes WHERE user_id={ph}", (uid,))
        row2 = cur.fetchone()
        remaining = row2[0] if row2 else 0
        conn.close()

        return JsonResponse({"ok": True, "remaining_passes": remaining}, headers=headers)

    except Exception as exc:
        logger.exception("use_transfer_pass error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Shards — осколки предметов ──────────────────────────────────────────────

@csrf_exempt
def miniapp_shards(request):
    """GET /api/shards?chat_id=X — return shard stash + catalog."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import get_shard_stash
        from shared_prices import SHARD_CATALOG

        stash = _a2s(get_shard_stash)(uid)
        # Enrich catalog with current amounts
        catalog_out = {}
        for key, info in SHARD_CATALOG.items():
            catalog_out[key] = {
                "name": info["name"],
                "emoji": info["emoji"],
                "craft_into": info.get("craft_into"),
                "craft_frame": info.get("craft_frame"),
                "craft_amount": info["craft_amount"],
                "owned": stash.get(key, 0),
            }
        return JsonResponse(
            {"stash": stash, "catalog": catalog_out},
            json_dumps_params={"ensure_ascii": False},
            headers=headers,
        )
    except Exception:
        logger.exception("miniapp_shards error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_shards_craft(request):
    """POST /api/shards/craft {chat_id, shard_key} — craft item/frame from shards."""
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
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    shard_key = str(body.get("shard_key", "")).strip()
    chat_id_raw = body.get("chat_id")
    if not shard_key:
        return JsonResponse({"error": "shard_key required"}, status=400, headers=headers)
    chat_id = int(str(chat_id_raw)) if chat_id_raw else 0

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import craft_from_shards
        from shared_prices import SHARD_CATALOG

        if shard_key not in SHARD_CATALOG:
            return JsonResponse({"error": "Неизвестный тип осколка"}, status=400, headers=headers)

        result = _a2s(craft_from_shards)(uid, chat_id, shard_key)
        if result.get("ok"):
            return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
        return JsonResponse(result, status=400, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception:
        logger.exception("miniapp_shards_craft error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Talents — древо талантов ─────────────────────────────────────────────────

@csrf_exempt
def miniapp_talents(request):
    """GET /api/talents — return talent data + tree definition."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405, headers=headers)

    uid, err = _require_auth(request, headers)
    if err:
        return err

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import get_user_talents
        from shared_prices import TALENT_TREE

        data = _a2s(get_user_talents)(uid)
        return JsonResponse(
            {"talent_points": data["talent_points"], "talents": data["talents"], "tree": TALENT_TREE},
            json_dumps_params={"ensure_ascii": False},
            headers=headers,
        )
    except Exception:
        logger.exception("miniapp_talents error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


@csrf_exempt
def miniapp_talents_upgrade(request):
    """POST /api/talents/upgrade {talent_id} — spend a talent point to upgrade a talent."""
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
    except Exception:
        return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)

    talent_id = str(body.get("talent_id", "")).strip()
    if not talent_id:
        return JsonResponse({"error": "talent_id required"}, status=400, headers=headers)

    try:
        from asgiref.sync import async_to_sync as _a2s
        from database.db import upgrade_talent, get_user_talents

        result = _a2s(upgrade_talent)(uid, talent_id)
        if result.get("ok"):
            # Return updated points too
            data = _a2s(get_user_talents)(uid)
            result["talent_points"] = data["talent_points"]
            return JsonResponse(result, json_dumps_params={"ensure_ascii": False}, headers=headers)
        return JsonResponse(result, status=400, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception:
        logger.exception("miniapp_talents_upgrade error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)


# ─── Newbie quest status ──────────────────────────────────────────────────────

@csrf_exempt
def miniapp_newbie_quest(request):
    """GET /api/newbie_quest?chat_id=X — return newcomer quest status for the user."""
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
        from database.db import get_newbie_quest_status

        status = _a2s(get_newbie_quest_status)(uid, chat_id)
        if status is None:
            return JsonResponse({"active": False}, headers=headers)
        return JsonResponse({"active": True, **status}, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception:
        logger.exception("miniapp_newbie_quest error")
        return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500, headers=headers)
