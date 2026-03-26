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
    except Exception as exc:
        return JsonResponse({"error": f"DB connection failed: {exc}"}, status=503,
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
                f"SELECT xp, COALESCE(level, 1), custom_title, COALESCE(rank,'user') FROM user_stats WHERE user_id={ph} AND chat_id={ph}",
                (uid, effective_cid),
            )
        else:
            cur.execute(
                f"SELECT xp, COALESCE(level, 1), custom_title, COALESCE(rank,'user') FROM user_stats WHERE user_id={ph} ORDER BY xp DESC LIMIT 1",
                (uid,),
            )
        xp_row = cur.fetchone()
        xp = xp_row[0] if xp_row else 0
        db_level = xp_row[1] if xp_row else 1
        custom_title = xp_row[2] if xp_row else None
        user_rank = xp_row[3] if xp_row else 'user'
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
                f"SELECT pet_type, name, COALESCE(fatigue,0), walk_end_at FROM pets "
                f"WHERE user_id={ph} AND chat_id={ph}",
                (uid, chat_id),
            )
            pet_row = cur.fetchone()
            if pet_row:
                ptype, pname, pfatigue, pwalk_end = pet_row
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
                for eid in [rpg_row[4], rpg_row[5], rpg_row[6]]:
                    if eid:
                        cur.execute(
                            f"SELECT COALESCE(atk,0),COALESCE(def_val,0),COALESCE(hp,0),COALESCE(crit_rate,0) "
                            f"FROM gacha_inventory WHERE id={ph}", (eid,))
                        er = cur.fetchone()
                        if er:
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
        }
        return JsonResponse(payload, json_dumps_params={"ensure_ascii": False},
                            headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        if lb_type == "messages":
            cur.execute(
                f"SELECT s.user_id, u.full_name, s.message_count "
                f"FROM user_stats s LEFT JOIN users u ON u.user_id=s.user_id "
                f"WHERE s.chat_id={ph} ORDER BY s.message_count DESC LIMIT 20",
                (chat_id,),
            )
        elif lb_type == "boss":
            cur.execute(
                f"SELECT b.user_id, u.full_name, SUM(b.damage) "
                f"FROM boss_damage_log b LEFT JOIN users u ON u.user_id=b.user_id "
                f"WHERE b.chat_id={ph} GROUP BY b.user_id ORDER BY SUM(b.damage) DESC LIMIT 20",
                (chat_id,),
            )
        elif lb_type == "mora":
            cur.execute(
                f"SELECT m.user_id, u.full_name, m.balance "
                f"FROM user_mora m LEFT JOIN users u ON u.user_id=m.user_id "
                f"WHERE m.chat_id={ph} ORDER BY m.balance DESC LIMIT 20",
                (chat_id,),
            )
        else:  # xp
            cur.execute(
                f"SELECT s.user_id, u.full_name, s.xp "
                f"FROM user_stats s LEFT JOIN users u ON u.user_id=s.user_id "
                f"WHERE s.chat_id={ph} ORDER BY s.xp DESC LIMIT 20",
                (chat_id,),
            )

        rows = cur.fetchall()

        # Check if requesting user is in top 20
        uid_lb = None
        init_data_lb = _get_init_data(request)
        if init_data_lb:
            uid_lb = _validate_init_data(init_data_lb)

        user_in_top = False
        user_rank_data = None
        if uid_lb:
            for i, r in enumerate(rows):
                if r[0] == uid_lb:
                    user_in_top = True
                    break
            if not user_in_top:
                # Query user's rank
                if lb_type == "messages":
                    cur.execute(
                        f"SELECT COUNT(*)+1 FROM user_stats WHERE chat_id={ph} AND message_count > "
                        f"  COALESCE((SELECT message_count FROM user_stats WHERE user_id={ph} AND chat_id={ph}),0)",
                        (chat_id, uid_lb, chat_id),
                    )
                    rank_row = cur.fetchone()
                    cur.execute(f"SELECT COALESCE(message_count,0) FROM user_stats WHERE user_id={ph} AND chat_id={ph}", (uid_lb, chat_id))
                    score_row = cur.fetchone()
                    user_rank_data = {"rank": rank_row[0] if rank_row else 0, "score": score_row[0] if score_row else 0}
                elif lb_type == "mora":
                    cur.execute(
                        f"SELECT COUNT(*)+1 FROM user_mora WHERE chat_id={ph} AND balance > "
                        f"  COALESCE((SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}),0)",
                        (chat_id, uid_lb, chat_id),
                    )
                    rank_row = cur.fetchone()
                    cur.execute(f"SELECT COALESCE(balance,0) FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid_lb, chat_id))
                    score_row = cur.fetchone()
                    user_rank_data = {"rank": rank_row[0] if rank_row else 0, "score": score_row[0] if score_row else 0}
                else:  # xp
                    cur.execute(
                        f"SELECT COUNT(*)+1 FROM user_stats WHERE chat_id={ph} AND xp > "
                        f"  COALESCE((SELECT xp FROM user_stats WHERE user_id={ph} AND chat_id={ph}),0)",
                        (chat_id, uid_lb, chat_id),
                    )
                    rank_row = cur.fetchone()
                    cur.execute(f"SELECT COALESCE(xp,0) FROM user_stats WHERE user_id={ph} AND chat_id={ph}", (uid_lb, chat_id))
                    score_row = cur.fetchone()
                    user_rank_data = {"rank": rank_row[0] if rank_row else 0, "score": score_row[0] if score_row else 0}

        conn.close()
        if lb_type == "mora":
            entries = [
                {"rank": i + 1, "user_id": r[0], "name": r[1] or f"user_{r[0]}",
                 "score": (r[2] or 0) if r[0] == uid_lb else None}
                for i, r in enumerate(rows)
            ]
        else:
            entries = [
                {"rank": i + 1, "user_id": r[0], "name": r[1] or f"user_{r[0]}", "score": r[2] or 0}
                for i, r in enumerate(rows)
            ]
        resp = {"type": lb_type, "entries": entries, "uid": uid_lb}
        if user_rank_data:
            resp["user_rank"] = user_rank_data
        return JsonResponse(resp,
                            json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        cur.execute(
            f"SELECT streak, total_days, last_checkin, checkpoint "
            f"FROM daily_checkin WHERE user_id={ph} AND chat_id={ph}",
            (uid, chat_id),
        )
        row = cur.fetchone()

        if request.method == "GET":
            from datetime import datetime as _dt, timezone as _tz
            today = _dt.now(_tz.utc).strftime("%Y-%m-%d")
            if not row:
                data = {"streak": 0, "total_days": 0, "last_checkin": None, "checkpoint": 0, "today_done": False}
            else:
                streak, total_days, last_checkin, checkpoint = row
                data = {
                    "streak": streak, "total_days": total_days,
                    "last_checkin": last_checkin, "checkpoint": checkpoint,
                    "today_done": last_checkin == today,
                }
            conn.close()
            return JsonResponse(data, headers=headers)

        # POST: perform check-in
        from datetime import datetime as _dt, date as _date, timezone as _tz
        today = _dt.now(_tz.utc).strftime("%Y-%m-%d")

        if row and row[2] == today:
            conn.close()
            return JsonResponse({"already_done": True, "streak": row[0], "total_days": row[1]},
                                headers=headers)

        streak = (row[0] if row else 0) + 1
        total_days = (row[1] if row else 0) + 1
        checkpoint = row[3] if row else 0

        if row and row[2]:
            try:
                diff = (_date.fromisoformat(today) - _date.fromisoformat(row[2])).days
                if diff > 1:
                    streak = min(streak - 1, checkpoint) if checkpoint else 1
            except (ValueError, TypeError):
                pass

        day_idx = min(streak, 20)
        mora_reward = _CHECKIN_REWARDS_SYNC.get(day_idx, 40)
        is_checkpoint = day_idx in _CHECKIN_CHECKPOINTS_SYNC
        if is_checkpoint:
            checkpoint = day_idx

        if db_type == "pg":
            cur.execute(
                f"INSERT INTO daily_checkin (user_id, chat_id, streak, total_days, last_checkin, checkpoint) "
                f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph}) "
                f"ON CONFLICT (user_id, chat_id) DO UPDATE SET "
                f"streak=EXCLUDED.streak, total_days=EXCLUDED.total_days, "
                f"last_checkin=EXCLUDED.last_checkin, checkpoint=EXCLUDED.checkpoint",
                (uid, chat_id, streak, total_days, today, checkpoint),
            )
            cur.execute(
                f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
                f"ON CONFLICT (user_id, chat_id) DO UPDATE SET balance=user_mora.balance+EXCLUDED.balance",
                (uid, chat_id, mora_reward),
            )
        else:
            cur.execute(
                "INSERT INTO daily_checkin (user_id, chat_id, streak, total_days, last_checkin, checkpoint) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET "
                "streak=excluded.streak, total_days=excluded.total_days, "
                "last_checkin=excluded.last_checkin, checkpoint=excluded.checkpoint",
                (uid, chat_id, streak, total_days, today, checkpoint),
            )
            cur.execute(
                "INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,?) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=user_mora.balance+excluded.balance",
                (uid, chat_id, mora_reward),
            )

        conn.commit()
        conn.close()
        
        # ➕ ЛОГИРУЕМ ДЕЙСТВИЕ В ЧАТ
        from asgiref.sync import async_to_sync as _a2s
        reward_text = f"+{mora_reward} 🪙"
        if is_checkpoint:
            reward_text += f" | День {day_idx} - ЧЕКПОИНТ! ✨"
        if day_idx == 20:
            reward_text += " | Бесплатная гача! 🎁"

        _a2s(log_action_to_chat)(
            uid, chat_id,
            f"Забрал ежедневную награду (день {streak})",
            reward_text
        )
        
        return JsonResponse({
            "ok": True, "already_done": False,
            "mora": mora_reward, "streak": streak,
            "total_days": total_days, "is_checkpoint": is_checkpoint,
            "free_gacha": day_idx == 20,
        }, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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


def _ensure_wallet_ledger_table(cur, db_type: str) -> None:
    if db_type == "pg":
        cur.execute(
            "CREATE TABLE IF NOT EXISTS wallet_ledger ("
            "id SERIAL PRIMARY KEY, "
            "chat_id BIGINT NOT NULL, user_id BIGINT NOT NULL, "
            "direction TEXT NOT NULL, amount INTEGER NOT NULL, source TEXT NOT NULL, "
            "description TEXT DEFAULT '', actor_id BIGINT DEFAULT NULL, "
            "created_at TIMESTAMPTZ NOT NULL)"
        )
    else:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS wallet_ledger ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
            "direction TEXT NOT NULL, amount INTEGER NOT NULL, source TEXT NOT NULL, "
            "description TEXT DEFAULT '', actor_id INTEGER DEFAULT NULL, "
            "created_at TEXT NOT NULL)"
        )


def _insert_wallet_ledger(cur, db_type: str, chat_id: int, user_id: int, direction: str,
                          amount: int, source: str, description: str = "",
                          actor_id: int | None = None) -> None:
    if amount <= 0:
        return
    _ensure_wallet_ledger_table(cur, db_type)
    ph = "%s" if db_type == "pg" else "?"
    created_at = datetime.now(timezone.utc).isoformat()
    cur.execute(
        f"INSERT INTO wallet_ledger (chat_id, user_id, direction, amount, source, description, actor_id, created_at) "
        f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})",
        (chat_id, user_id, direction, amount, source, description or "", actor_id, created_at),
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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Current marriage
        cur.execute(
            f"SELECT partner_id, married_at FROM marriages WHERE user_id={ph} AND chat_id={ph}",
            (uid, chat_id),
        )
        row = cur.fetchone()
        has_partner = row is not None
        partner_id = row[0] if row else None
        married_at = row[1] if row else None
        partner_name = None
        if partner_id:
            cur.execute(f"SELECT full_name FROM users WHERE user_id={ph}", (partner_id,))
            prow = cur.fetchone()
            partner_name = prow[0] if prow else f"user_{partner_id}"

        # Singles: users in this chat with no marriage row, ordered by xp desc
        cur.execute(
            f"SELECT s.user_id, u.full_name, COALESCE(s.xp, 0) as xp "
            f"FROM user_stats s LEFT JOIN users u ON u.user_id=s.user_id "
            f"WHERE s.chat_id={ph} AND s.user_id!={ph} "
            f"AND s.user_id NOT IN (SELECT user_id FROM marriages WHERE chat_id={ph}) "
            f"ORDER BY s.xp DESC LIMIT 20",
            (chat_id, uid, chat_id),
        )
        singles = [
            {"user_id": r[0], "name": r[1] or f"user_{r[0]}", "xp": r[2]}
            for r in cur.fetchall()
        ]

        conn.close()
        return JsonResponse({
            "has_partner": has_partner,
            "partner_id": partner_id,
            "partner_name": partner_name,
            "married_at": married_at,
            "singles": singles,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Check if requester is already married
        cur.execute(f"SELECT 1 FROM marriages WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        if cur.fetchone():
            conn.close()
            return JsonResponse({"error": "Ты уже в браке. Сначала разведись."}, status=400,
                                json_dumps_params={"ensure_ascii": False}, headers=headers)

        # Check if target is already married
        cur.execute(f"SELECT 1 FROM marriages WHERE user_id={ph} AND chat_id={ph}", (target_id, chat_id))
        if cur.fetchone():
            conn.close()
            return JsonResponse({"error": "Этот игрок уже состоит в браке."}, status=400,
                                json_dumps_params={"ensure_ascii": False}, headers=headers)

        # Get names
        cur.execute(f"SELECT full_name FROM users WHERE user_id={ph}", (uid,))
        from_name = (cur.fetchone() or [f"user_{uid}"])[0]
        cur.execute(f"SELECT full_name FROM users WHERE user_id={ph}", (target_id,))
        to_name = (cur.fetchone() or [f"user_{target_id}"])[0]
        conn.close()
    except Exception as exc:
        try: conn.close()
        except Exception: pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)

    # Create proposal in DB
    from database.db import create_marriage_proposal
    from asgiref.sync import async_to_sync
    proposal_id = async_to_sync(create_marriage_proposal)(uid, target_id, chat_id)

    # Send Telegram notification to target
    try:
        import asyncio
        from aiogram import Bot as _AiogramBot
        from config import BOT_TOKEN as _BOT_TOKEN

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
        "proposal_id": proposal_id,
        "message": f"Предложение отправлено игроку {html.escape(to_name)}!",
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
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)

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
            return JsonResponse({"error": str(exc)}, status=500, headers=headers)
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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Current prices
        cur.execute(
            f"SELECT bond_key, price, updated_at FROM bond_prices WHERE chat_id={ph}",
            (chat_id,),
        )
        price_map = {r[0]: {"price": r[1], "updated_at": r[2]} for r in cur.fetchall()}

        # User holdings
        cur.execute(
            f"SELECT bond_key, amount, invested FROM user_bonds WHERE user_id={ph} AND chat_id={ph}",
            (uid, chat_id),
        )
        holdings = {r[0]: {"amount": r[1], "invested": r[2]} for r in cur.fetchall()}

        # Price history (last 120 points per bond = ~15 days at 3h ticks)
        _BOND_KEYS = list(_BOND_DEFAULTS_SYNC.keys())
        history = {}
        for bk in _BOND_KEYS:
            cur.execute(
                f"SELECT price, recorded_at FROM bond_price_history "
                f"WHERE chat_id={ph} AND bond_key={ph} ORDER BY id DESC LIMIT 120",
                (chat_id, bk),
            )
            rows = cur.fetchall()
            rows.reverse()
            history[bk] = [{"price": r[0], "ts": r[1]} for r in rows]

        # Market trend state
        market_trend = "neutral"
        market_ticks = 0
        cur.execute(
            f"SELECT trend, ticks_left FROM market_state WHERE chat_id={ph}",
            (chat_id,)
        )
        trend_row = cur.fetchone()
        if trend_row:
            market_trend = trend_row[0]
            market_ticks = trend_row[1]

        conn.close()

        bonds_out = []
        for bk in _BOND_KEYS:
            current_price = price_map.get(bk, {}).get("price", 100)
            holding       = holdings.get(bk, {"amount": 0, "invested": 0})
            amount        = holding["amount"]
            invested      = holding["invested"]
            bname         = _BOND_DEFAULTS_SYNC.get(bk, {}).get("name", bk)
            avg_price     = round(invested / amount, 1) if amount > 0 else 0
            pnl_mora      = amount * current_price - invested if amount > 0 else 0
            pnl_pct       = round(pnl_mora / invested * 100, 1) if invested > 0 else 0
            bonds_out.append({
                "key":       bk,
                "name":      bname,
                "price":     current_price,
                "amount":    amount,
                "invested":  invested,
                "avg_price": avg_price,
                "pnl_mora":  pnl_mora,
                "pnl_pct":   pnl_pct,
                "value":     amount * current_price,
                "history":   history.get(bk, []),
            })

        return JsonResponse(
            {"bonds": bonds_out, "market_trend": market_trend, "market_ticks": market_ticks},
            json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Active chats (groups that have at least 1 user_stats entry)
        cur.execute(
            "SELECT cs.chat_id, cs.title, COUNT(DISTINCT s.user_id) as member_count "
            "FROM chats cs LEFT JOIN user_stats s ON s.chat_id=cs.chat_id "
            "GROUP BY cs.chat_id, cs.title ORDER BY member_count DESC LIMIT 50"
        )
        chats = [{"chat_id": r[0], "title": r[1] or f"chat_{r[0]}", "members": r[2]}
                 for r in cur.fetchall()]

        # Total users
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = (cur.fetchone() or [0])[0]

        # Recent boss damage (last 24h)
        if db_type == "sqlite":
            cur.execute(
                "SELECT COUNT(*) FROM boss_damage_log WHERE session_date >= date('now', '-1 day')"
            )
        else:
            cur.execute(
                "SELECT COUNT(*) FROM boss_damage_log WHERE session_date::date >= CURRENT_DATE - INTERVAL '1 day'"
            )
        boss_hits_today = (cur.fetchone() or [0])[0]

        conn.close()
        return JsonResponse({
            "total_users": total_users,
            "boss_hits_today": boss_hits_today,
            "chats": chats,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        _ensure_wallet_ledger_table(cur, db_type)
        cur.execute(
            f"SELECT COALESCE(balance,0) FROM user_mora WHERE user_id={ph} AND chat_id={ph}",
            (target_id, chat_id),
        )
        old_balance = (cur.fetchone() or [0])[0]
        if db_type == "pg":
            cur.execute(
                f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
                f"ON CONFLICT (user_id, chat_id) DO UPDATE SET balance=EXCLUDED.balance",
                (target_id, chat_id, balance),
            )
        else:
            cur.execute(
                "INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,?) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=excluded.balance",
                (target_id, chat_id, balance),
            )
        delta = balance - old_balance
        if delta > 0:
            _insert_wallet_ledger(
                cur, db_type, chat_id, target_id, "income", delta,
                "admin_setbalance", "CRM: установлен баланс", uid,
            )
        elif delta < 0:
            _insert_wallet_ledger(
                cur, db_type, chat_id, target_id, "expense", abs(delta),
                "admin_setbalance", "CRM: установлен баланс", uid,
            )
        conn.commit()
        conn.close()
        return JsonResponse({"ok": True, "target_id": target_id, "balance": balance}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        _ensure_wallet_ledger_table(cur, db_type)
        if db_type == "pg":
            cur.execute(
                f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},GREATEST(0,{ph})) "
                f"ON CONFLICT (user_id, chat_id) DO UPDATE SET balance=GREATEST(0, user_mora.balance + EXCLUDED.balance)",
                (target_id, chat_id, amount),
            )
        else:
            cur.execute(
                "INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,MAX(0,?)) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=MAX(0, user_mora.balance + ?)",
                (target_id, chat_id, amount, amount),
            )
        cur.execute(
            f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}",
            (target_id, chat_id),
        )
        new_bal = (cur.fetchone() or [0])[0]
        if amount > 0:
            _insert_wallet_ledger(
                cur, db_type, chat_id, target_id, "income", amount,
                "admin_adjustment", "Админская корректировка баланса", uid,
            )
        elif amount < 0:
            _insert_wallet_ledger(
                cur, db_type, chat_id, target_id, "expense", abs(amount),
                "admin_adjustment", "Админская корректировка баланса", uid,
            )
        conn.commit()
        conn.close()
        return JsonResponse({"ok": True, "target_id": target_id, "new_balance": new_bal}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        new_level = max(1, _level_for_xp(amount if set_mode else 0))
        if set_mode:
            new_level = _level_for_xp(max(0, amount))
        if db_type == "pg":
            if set_mode:
                cur.execute(
                    f"INSERT INTO user_stats (user_id, chat_id, xp, level) VALUES ({ph},{ph},{ph},{ph}) "
                    f"ON CONFLICT (user_id, chat_id) DO UPDATE SET xp=EXCLUDED.xp, level=EXCLUDED.level",
                    (target_id, chat_id, max(0, amount), new_level),
                )
            else:
                cur.execute(
                    f"INSERT INTO user_stats (user_id, chat_id, xp, level) VALUES ({ph},{ph},{ph},1) "
                    f"ON CONFLICT (user_id, chat_id) DO UPDATE SET xp=GREATEST(0, user_stats.xp + EXCLUDED.xp)",
                    (target_id, chat_id, amount),
                )
        else:
            if set_mode:
                cur.execute(
                    "INSERT INTO user_stats (user_id, chat_id, xp, level) VALUES (?,?,?,?) "
                    "ON CONFLICT(user_id, chat_id) DO UPDATE SET xp=excluded.xp, level=excluded.level",
                    (target_id, chat_id, max(0, amount), new_level),
                )
            else:
                cur.execute(
                    "INSERT INTO user_stats (user_id, chat_id, xp) VALUES (?,?,?) "
                    "ON CONFLICT(user_id, chat_id) DO UPDATE SET xp=MAX(0, user_stats.xp + ?)",
                    (target_id, chat_id, amount, amount),
                )
        cur.execute(
            f"SELECT xp, COALESCE(level, 1) FROM user_stats WHERE user_id={ph} AND chat_id={ph}",
            (target_id, chat_id),
        )
        row = cur.fetchone()
        new_xp = row[0] if row else 0
        new_level = row[1] if row else 1
        if new_level <= 1:
            new_level = _level_for_xp(new_xp)
        conn.commit()
        conn.close()
        return JsonResponse({"ok": True, "target_id": target_id, "xp": new_xp, "new_level": new_level}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        _ensure_wallet_ledger_table(cur, db_type)
        cur.execute(
            f"SELECT direction, amount, source, description, created_at "
            f"FROM wallet_ledger WHERE user_id={ph} AND chat_id={ph} "
            f"ORDER BY created_at DESC LIMIT 50",
            (uid, chat_id),
        )
        rows = cur.fetchall()
        conn.close()
        history = [
            {
                "direction": r[0],
                "amount": r[1],
                "source": r[2],
                "description": r[3] or "",
                "created_at": str(r[4]),
            }
            for r in rows
        ]
        return JsonResponse({"history": history}, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        _ensure_wallet_ledger_table(cur, db_type)
        cur.execute(
            f"SELECT COALESCE(balance,0) FROM user_mora WHERE user_id={ph} AND chat_id={ph}",
            (target_id, chat_id),
        )
        old_balance = (cur.fetchone() or [0])[0]
        new_level = _level_for_xp(xp)

        if db_type == "pg":
            cur.execute(
                f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
                f"ON CONFLICT (user_id, chat_id) DO UPDATE SET balance=EXCLUDED.balance",
                (target_id, chat_id, balance),
            )
            cur.execute(
                f"INSERT INTO user_stats (user_id, chat_id, xp, level, rank) VALUES ({ph},{ph},{ph},{ph},{ph}) "
                f"ON CONFLICT (user_id, chat_id) DO UPDATE SET xp=EXCLUDED.xp, level=EXCLUDED.level, rank=EXCLUDED.rank",
                (target_id, chat_id, xp, new_level, rank),
            )
        else:
            cur.execute(
                "INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,?) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=excluded.balance",
                (target_id, chat_id, balance),
            )
            cur.execute(
                "INSERT INTO user_stats (user_id, chat_id, xp, level, rank) VALUES (?,?,?,?,?) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET xp=excluded.xp, level=excluded.level, rank=excluded.rank",
                (target_id, chat_id, xp, new_level, rank),
            )

        delta = balance - old_balance
        if delta > 0:
            _insert_wallet_ledger(cur, db_type, chat_id, target_id, "income", delta,
                                  "crm_editor", "CRM: правка участника", uid)
        elif delta < 0:
            _insert_wallet_ledger(cur, db_type, chat_id, target_id, "expense", abs(delta),
                                  "crm_editor", "CRM: правка участника", uid)

        # Update message_count in user_stats if provided
        if msg_count is not None:
            cur.execute(
                f"UPDATE user_stats SET message_count={ph} WHERE user_id={ph} AND chat_id={ph}",
                (msg_count, target_id, chat_id),
            )

        # Update cleanup_counts (day/week/today/yesterday/last_week/total) if provided
        _cc_fields = (day_count, week_count, total_count, yesterday_count, last_week_count)
        if any(v is not None for v in _cc_fields):
            # Ensure row exists first
            cur.execute(
                f"INSERT INTO cleanup_counts (chat_id, user_id, count, week_count, day_count) "
                f"VALUES ({ph},{ph},0,0,0) "
                f"ON CONFLICT(chat_id, user_id) DO NOTHING",
                (chat_id, target_id),
            )
            if day_count is not None:
                cur.execute(
                    f"UPDATE cleanup_counts SET day_count={ph} WHERE user_id={ph} AND chat_id={ph}",
                    (day_count, target_id, chat_id),
                )
            if week_count is not None:
                cur.execute(
                    f"UPDATE cleanup_counts SET week_count={ph} WHERE user_id={ph} AND chat_id={ph}",
                    (week_count, target_id, chat_id),
                )
            if total_count is not None:
                cur.execute(
                    f"UPDATE cleanup_counts SET count={ph} WHERE user_id={ph} AND chat_id={ph}",
                    (total_count, target_id, chat_id),
                )
            if yesterday_count is not None:
                cur.execute(
                    f"UPDATE cleanup_counts SET yesterday_count={ph} WHERE user_id={ph} AND chat_id={ph}",
                    (yesterday_count, target_id, chat_id),
                )
            if last_week_count is not None:
                cur.execute(
                    f"UPDATE cleanup_counts SET last_week_count={ph} WHERE user_id={ph} AND chat_id={ph}",
                    (last_week_count, target_id, chat_id),
                )

        conn.commit()
        conn.close()
        return JsonResponse(
            {"ok": True, "target_id": target_id, "balance": balance, "xp": xp,
             "level": new_level, "rank": rank},
            headers=headers,
        )
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        _ensure_wallet_ledger_table(cur, db_type)
        cur.execute(f"SELECT COALESCE(full_name, '') FROM users WHERE user_id={ph}", (target_id,))
        name_row = cur.fetchone()
        target_name = (name_row or [""])[0] or f"Игрок {target_id}"

        if db_type == "pg":
            cur.execute(
                f"INSERT INTO user_mora (user_id, chat_id, balance, total_earned) VALUES ({ph},{ph},{ph},{ph}) "
                f"ON CONFLICT (user_id, chat_id) DO UPDATE SET "
                f"balance=user_mora.balance + EXCLUDED.balance, "
                f"total_earned=user_mora.total_earned + EXCLUDED.total_earned",
                (target_id, chat_id, amount, amount),
            )
        else:
            cur.execute(
                "INSERT INTO user_mora (user_id, chat_id, balance, total_earned) VALUES (?,?,?,?) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=user_mora.balance + excluded.balance, total_earned=user_mora.total_earned + excluded.total_earned",
                (target_id, chat_id, amount, amount),
            )

        desc = f"Зарплата за {days} дн."
        if reason:
            desc = f"{desc}: {reason}"
        _insert_wallet_ledger(cur, db_type, chat_id, target_id, "income", amount, "salary", desc, uid)

        cur.execute(
            f"SELECT COALESCE(balance,0) FROM user_mora WHERE user_id={ph} AND chat_id={ph}",
            (target_id, chat_id),
        )
        new_balance = (cur.fetchone() or [0])[0]
        conn.commit()
        conn.close()

        _send_salary_announcement(chat_id, target_name)

        return JsonResponse(
            {"ok": True, "target_id": target_id, "days": days, "amount": amount,
             "reason": reason, "new_balance": new_balance},
            json_dumps_params={"ensure_ascii": False},
            headers=headers,
        )
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        cur.execute(
            f"INSERT INTO gacha_inventory (user_id, chat_id, item_key, item_name, rarity, obtained_at) "
            f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph})",
            (target_id, chat_id, item_name.lower().replace(" ", "_"), item_name, rarity, now),
        )
        conn.commit()
        conn.close()
        return JsonResponse({"ok": True, "target_id": target_id, "item_name": item_name, "rarity": rarity},
                            json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        if q:
            like = f"%{q}%"
            cur.execute(
                f"SELECT s.user_id, u.full_name FROM user_stats s "
                f"LEFT JOIN users u ON u.user_id=s.user_id "
                f"WHERE s.chat_id={ph} AND (u.full_name LIKE {ph} OR CAST(s.user_id AS TEXT) LIKE {ph}) "
                f"ORDER BY s.xp DESC LIMIT 20",
                (chat_id, like, like),
            )
        else:
            cur.execute(
                f"SELECT s.user_id, u.full_name FROM user_stats s "
                f"LEFT JOIN users u ON u.user_id=s.user_id "
                f"WHERE s.chat_id={ph} ORDER BY s.xp DESC LIMIT 20",
                (chat_id,),
            )
        rows = cur.fetchall()
        conn.close()
        users = [{"user_id": r[0], "name": r[1] or f"user_{r[0]}"} for r in rows]
        return JsonResponse({"users": users}, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        # БАГ ИСПРАВЛЕН: Фильтруем только группы и каналы, исключаем личные чаты
        cur.execute(
            "SELECT c.chat_id, c.title, c.chat_type, COUNT(DISTINCT s.user_id) AS members "
            "FROM chats c LEFT JOIN user_stats s ON s.chat_id=c.chat_id "
            "WHERE c.chat_type IN ('group', 'supergroup', 'channel') "
            "GROUP BY c.chat_id, c.title, c.chat_type ORDER BY members DESC LIMIT 100"
        )
        rows = cur.fetchall()
        conn.close()
        groups, admin_chats = [], []
        for r in rows:
            ctype = (r[2] or "").lower()
            obj = {"chat_id": r[0], "title": r[1] or f"chat_{r[0]}", "chat_type": ctype, "members": r[3]}
            if ctype in ("group", "supergroup"):
                groups.append(obj)
            else:
                admin_chats.append(obj)
        return JsonResponse({"groups": groups, "admin_chats": admin_chats},
                            json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        cur.execute(
            f"SELECT s.user_id, u.full_name, COALESCE(s.rank,'user') AS rank, "
            f"COALESCE(s.level,1) AS level, COALESCE(s.xp,0) AS xp, "
            f"COALESCE(m.balance,0) AS balance, "
            f"COALESCE(s.message_count,0) AS message_count, "
            f"COALESCE(cc.count,0) AS total_count, "
            f"COALESCE(cc.week_count,0) AS week_count, "
            f"COALESCE(cc.day_count,0) AS day_count, "
            f"COALESCE(cc.yesterday_count,0) AS yesterday_count, "
            f"COALESCE(cc.last_week_count,0) AS last_week_count "
            f"FROM user_stats s "
            f"LEFT JOIN users u ON u.user_id=s.user_id "
            f"LEFT JOIN user_mora m ON m.user_id=s.user_id AND m.chat_id=s.chat_id "
            f"LEFT JOIN cleanup_counts cc ON cc.user_id=s.user_id AND cc.chat_id=s.chat_id "
            f"WHERE s.chat_id={ph} "
            f"ORDER BY s.xp DESC LIMIT 50",
            (chat_id,),
        )
        rows = cur.fetchall()
        conn.close()
        members = [
            {"user_id": r[0], "name": r[1] or f"user_{r[0]}", "rank": r[2],
             "level": r[3], "xp": r[4], "balance": r[5],
             "message_count": r[6], "total_count": r[7],
             "week_count": r[8], "day_count": r[9],
             "yesterday_count": r[10], "last_week_count": r[11]}
            for r in rows
        ]
        return JsonResponse({"members": members}, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    ph = "%s" if db_type == "pg" else "?"

    try:
        cur = conn.cursor()

        if request.method == "GET":
            cur.execute(
                "SELECT bl.user_id, u.full_name, bl.reason, bl.added_at "
                "FROM user_banlist bl "
                "LEFT JOIN users u ON u.user_id=bl.user_id "
                "WHERE bl.chat_id=0 ORDER BY bl.added_at DESC LIMIT 100"
            )
            rows = cur.fetchall()
            conn.close()
            banned = [
                {"user_id": r[0], "name": r[1] or f"user_{r[0]}", "reason": r[2] or "", "added_at": r[3]}
                for r in rows
            ]
            return JsonResponse({"banned": banned}, json_dumps_params={"ensure_ascii": False}, headers=headers)

        body = json.loads(request.body or b"{}")
        target_id = int(body.get("user_id", 0))
        if not target_id:
            conn.close()
            return JsonResponse({"error": "user_id required"}, status=400, headers=headers)

        if request.method == "POST":
            reason = str(body.get("reason", ""))[:200]
            import datetime as _dt
            now_iso = _dt.datetime.utcnow().isoformat()
            if db_type == "pg":
                cur.execute(
                    f"INSERT INTO user_banlist (chat_id,user_id,added_by,reason,added_at) "
                    f"VALUES ({ph},{ph},{ph},{ph},{ph}) "
                    f"ON CONFLICT (chat_id,user_id) DO UPDATE SET reason=EXCLUDED.reason",
                    (0, target_id, uid, reason, now_iso),
                )
            else:
                cur.execute(
                    "INSERT INTO user_banlist (chat_id,user_id,added_by,reason,added_at) "
                    "VALUES (?,?,?,?,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET reason=excluded.reason",
                    (0, target_id, uid, reason, now_iso),
                )
            conn.commit()
            conn.close()
            return JsonResponse({"ok": True, "banned": target_id}, headers=headers)

        if request.method == "DELETE":
            cur.execute(
                f"DELETE FROM user_banlist WHERE chat_id=0 AND user_id={ph}", (target_id,)
            )
            conn.commit()
            conn.close()
            return JsonResponse({"ok": True, "unbanned": target_id}, headers=headers)

        conn.close()
        return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Leave log (who left/was kicked)
        if chat_id:
            cur.execute(
                f"SELECT user_id, full_name, left_at FROM leave_log "
                f"WHERE chat_id={ph} ORDER BY left_at DESC LIMIT 20",
                (chat_id,),
            )
        else:
            cur.execute(
                "SELECT user_id, full_name, left_at FROM leave_log ORDER BY left_at DESC LIMIT 20"
            )
        leave_rows = cur.fetchall()
        leave_log = [{"user_id": r[0], "name": r[1] or f"user_{r[0]}", "left_at": r[2]} for r in leave_rows]

        # Server errors from log file
        import os, pathlib
        error_lines = []
        log_candidates = [
            pathlib.Path(__file__).parent.parent.parent / "logs" / "bot.log",
            pathlib.Path(__file__).parent.parent.parent / "logs" / "app.log",
            pathlib.Path(__file__).parent.parent.parent / "server_output.txt",
        ]
        for lp in log_candidates:
            if lp.exists() and lp.stat().st_size > 0:
                try:
                    with open(lp, "r", encoding="utf-8", errors="replace") as f:
                        all_lines = f.readlines()
                    errs = [l.strip() for l in all_lines if "error" in l.lower() or "exception" in l.lower() or "traceback" in l.lower()]
                    error_lines = errs[-5:]  # last 5 error lines
                    break
                except Exception:
                    pass

        conn.close()
        return JsonResponse({
            "leave_log": leave_log,
            "server_errors": error_lines,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    _SUPPORTED_EVENTS = {"chest", "сундук", "дилижанс", "diligence"}
    if event_type not in _SUPPORTED_EVENTS:
        return JsonResponse(
            {"error": f"Неизвестный тип события: '{event_type}'. "
                      f"Поддерживаются: сундук, дилижанс"},
            status=400, headers=headers,
        )

    # We enqueue the event request into a small DB table so the bot process can pick it up.
    # This avoids needing to share bot instance state with Django.
    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    ph = "%s" if db_type == "pg" else "?"
    try:
        cur = conn.cursor()
        # Ensure table exists (idempotent)
        if db_type == "pg":
            # PostgreSQL syntax
            cur.execute(
                "CREATE TABLE IF NOT EXISTS dev_event_queue ("
                "id SERIAL PRIMARY KEY, "
                "chat_id BIGINT NOT NULL, event_type TEXT NOT NULL, "
                "requested_by BIGINT NOT NULL, created_at TEXT NOT NULL, processed INTEGER DEFAULT 0)"
            )
        else:
            # SQLite syntax
            cur.execute(
                "CREATE TABLE IF NOT EXISTS dev_event_queue ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "chat_id INTEGER NOT NULL, event_type TEXT NOT NULL, "
                "requested_by INTEGER NOT NULL, created_at TEXT NOT NULL, processed INTEGER DEFAULT 0)"
            )
        import datetime as _dt
        cur.execute(
            f"INSERT INTO dev_event_queue (chat_id, event_type, requested_by, created_at) "
            f"VALUES ({ph},{ph},{ph},{ph})",
            (target_chat, event_type, uid, _dt.datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()
        return JsonResponse({"ok": True, "event_type": event_type, "chat_id": target_chat,
                             "note": "queued — bot will fire within ~30s"}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    # Build flat list from the pool defined lower in this file
    # We re-declare the mapping here to avoid forward-reference issues
    _pool = {
        "junk":      [("junk_stone", "🪨 Камень Маслоу"), ("junk_stick", "🪴 Палка путника"),
                      ("junk_dust", "💨 Пыль забвения"), ("junk_bone", "🦴 Кость хиличурла"),
                      ("junk_mushroom", "🍄 Сомнительный гриб")],
        "common":    [("cmn_sword", "⚔️ Тупой клинок"), ("cmn_bow", "🏹 Кривой лук"),
                      ("cmn_book", "📕 Потрёпанный дневник"), ("cmn_ring", "💍 Дешёвое кольцо"),
                      ("cmn_shield", "🛡 Ржавый щит")],
        "rare":      [("rare_crown", "👑 Серебряная корона"), ("rare_catalyst", "🔮 Магический катализатор"),
                      ("rare_cape", "🧣 Алый плащ"), ("rare_gem", "💎 Сапфир полуночи")],
        "legendary": [("lego_gnosis", "✨ Гнозис Балладеера"), ("lego_scepter", "🏛 Скипетр Дендро Архонта"),
                      ("lego_pantalone", "🎩 Маска Панталоне"), ("lego_abyss", "🌀 Корона Бездны"),
                      ("lego_fatui", "⚡ Перст Предвестника")],
    }
    items = []
    rarity_emoji = {"junk": "🪨", "common": "💙", "rare": "💜", "legendary": "⭐"}
    for rarity, pool in _pool.items():
        for key, name in pool:
            items.append({"key": key, "name": name, "rarity": rarity,
                          "rarity_emoji": rarity_emoji.get(rarity, "")})
    return JsonResponse({"items": items}, json_dumps_params={"ensure_ascii": False}, headers=headers)


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

    if amount <= 0:
        return JsonResponse({"error": "amount must be positive"}, status=400, headers=headers)

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Check marriage exists
        cur.execute(
            f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}",
            (uid, chat_id),
        )
        if not cur.fetchone():
            conn.close()
            return JsonResponse({"error": "Нет союза — семейный кошелёк недоступен"}, status=400, headers=headers)

        # Check personal balance
        cur.execute(
            f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}",
            (uid, chat_id),
        )
        row = cur.fetchone()
        personal = row[0] if row else 0
        if personal < amount:
            conn.close()
            return JsonResponse({"error": f"Недостаточно Моры ({personal})"}, status=400, headers=headers)

        # Deduct personal
        cur.execute(
            f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph}",
            (amount, uid, chat_id),
        )
        # Add to family wallet
        if db_type == "pg":
            cur.execute(
                f"INSERT INTO family_wallet (chat_id, user_id, balance) VALUES ({ph},{ph},{ph}) "
                f"ON CONFLICT (chat_id, user_id) DO UPDATE SET balance=family_wallet.balance+EXCLUDED.balance",
                (chat_id, uid, amount),
            )
        else:
            cur.execute(
                "INSERT INTO family_wallet (chat_id, user_id, balance) VALUES (?,?,?) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET balance=family_wallet.balance+excluded.balance",
                (chat_id, uid, amount),
            )
        # Log the transaction
        from datetime import datetime, timezone
        _now_iso = datetime.now(timezone.utc).isoformat()
        cur.execute(
            "INSERT INTO family_wallet_log (chat_id, user_id, action, amount, description, created_at) "
            "VALUES (?,?,?,?,?,?)" if db_type != "pg" else
            "INSERT INTO family_wallet_log (chat_id, user_id, action, amount, description, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (chat_id, uid, "deposit", amount, "Пополнение через Mini App", _now_iso),
        )
        # Read new balances
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_personal = (cur.fetchone() or [0])[0]
        cur.execute(f"SELECT balance FROM family_wallet WHERE chat_id={ph} AND user_id={ph}", (chat_id, uid))
        new_family = (cur.fetchone() or [0])[0]

        conn.commit()
        conn.close()
        return JsonResponse({"ok": True, "personal": new_personal, "family": new_family}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    if amount <= 0:
        return JsonResponse({"error": "amount must be positive"}, status=400, headers=headers)

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        cur.execute(
            f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}",
            (uid, chat_id),
        )
        marriage_row = cur.fetchone()
        if not marriage_row:
            conn.close()
            return JsonResponse({"error": "Нет союза"}, status=400, headers=headers)

        partner_id = marriage_row[0]

        # Проверяем СУММАРНЫЙ семейный баланс (вклад обоих партнёров)
        cur.execute(
            f"SELECT COALESCE(balance,0) FROM family_wallet WHERE chat_id={ph} AND user_id={ph}",
            (chat_id, uid),
        )
        my_bal = (cur.fetchone() or [0])[0]
        cur.execute(
            f"SELECT COALESCE(balance,0) FROM family_wallet WHERE chat_id={ph} AND user_id={ph}",
            (chat_id, partner_id),
        )
        partner_bal = (cur.fetchone() or [0])[0]
        total_bal = my_bal + partner_bal

        if total_bal < amount:
            conn.close()
            return JsonResponse(
                {"error": f"В семейном кошельке недостаточно средств ({total_bal} 🪙)"},
                status=400, headers=headers,
            )

        # Списываем из пула: сначала мой вклад, затем вклад партнёра
        if my_bal >= amount:
            cur.execute(
                f"UPDATE family_wallet SET balance=balance-{ph} WHERE chat_id={ph} AND user_id={ph}",
                (amount, chat_id, uid),
            )
        else:
            rest = amount - my_bal
            cur.execute(
                f"UPDATE family_wallet SET balance=0 WHERE chat_id={ph} AND user_id={ph}",
                (chat_id, uid),
            )
            cur.execute(
                f"UPDATE family_wallet SET balance=MAX(0,balance-{ph}) WHERE chat_id={ph} AND user_id={ph}",
                (rest, chat_id, partner_id),
            )

        # Добавляем на личный счёт
        if db_type == "pg":
            cur.execute(
                f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
                f"ON CONFLICT (user_id, chat_id) DO UPDATE SET balance=user_mora.balance+EXCLUDED.balance",
                (uid, chat_id, amount),
            )
        else:
            cur.execute(
                "INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,?) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=user_mora.balance+excluded.balance",
                (uid, chat_id, amount),
            )

        # Log the transaction
        from datetime import datetime, timezone
        _now_iso = datetime.now(timezone.utc).isoformat()
        cur.execute(
            "INSERT INTO family_wallet_log (chat_id, user_id, action, amount, description, created_at) "
            "VALUES (?,?,?,?,?,?)" if db_type != "pg" else
            "INSERT INTO family_wallet_log (chat_id, user_id, action, amount, description, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (chat_id, uid, "withdraw", amount, "Снятие через Mini App", _now_iso),
        )

        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_personal = (cur.fetchone() or [0])[0]
        cur.execute(f"SELECT COALESCE(balance,0) FROM family_wallet WHERE chat_id={ph} AND user_id={ph}", (chat_id, uid))
        new_my = (cur.fetchone() or [0])[0]
        cur.execute(f"SELECT COALESCE(balance,0) FROM family_wallet WHERE chat_id={ph} AND user_id={ph}", (chat_id, partner_id))
        new_partner = (cur.fetchone() or [0])[0]

        conn.commit()
        conn.close()
        return JsonResponse({"ok": True, "personal": new_personal, "family": new_my + new_partner}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        cur.execute(f"SELECT 1 FROM marriages WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        if not cur.fetchone():
            conn.close()
            return JsonResponse({"log": []}, headers=headers)

        # Auto-cleanup old records (> 60 days)
        if db_type == "pg":
            cur.execute(
                f"DELETE FROM family_wallet_log WHERE chat_id={ph} AND created_at < NOW() - INTERVAL '60 days'",
                (chat_id,),
            )
        else:
            cur.execute(
                "DELETE FROM family_wallet_log WHERE chat_id=? AND created_at < datetime('now', '-60 days')",
                (chat_id,),
            )

        cur.execute(
            f"SELECT fw.id, fw.user_id, fw.action, fw.amount, fw.description, fw.created_at, u.full_name "
            f"FROM family_wallet_log fw "
            f"LEFT JOIN users u ON u.user_id = fw.user_id "
            f"WHERE fw.chat_id={ph} "
            f"ORDER BY fw.created_at DESC LIMIT 30",
            (chat_id,),
        )
        rows = cur.fetchall()
        conn.commit()
        conn.close()

        log = [
            {
                "id": r[0], "user_id": r[1], "action": r[2],
                "amount": r[3], "description": r[4] or "",
                "created_at": r[5], "user_name": r[6] or str(r[1]),
            }
            for r in rows
        ]
        return JsonResponse({"ok": True, "log": log}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
                f"COALESCE(atk,0), COALESCE(def_val,0), COALESCE(hp,0), COALESCE(crit_rate,0), slot, COALESCE(enhancement_level,0) "
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
                equip_ids = [rpg_row[4], rpg_row[5], rpg_row[6]]
                for eid in equip_ids:
                    if eid:
                        cur.execute(
                            f"SELECT COALESCE(atk,0), COALESCE(def_val,0), COALESCE(hp,0), COALESCE(crit_rate,0) "
                            f"FROM gacha_inventory WHERE id={ph}",
                            (eid,),
                        )
                        er = cur.fetchone()
                        if er:
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
            return JsonResponse({"error": str(exc)}, status=500, headers=headers)

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
            return JsonResponse({"error": str(exc)}, status=500, headers=headers)

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
            f"SELECT id, item_key FROM gacha_inventory WHERE user_id={ph} AND chat_id={ph} AND rarity='junk'",
            (uid, chat_id),
        )
        junk_items = cur.fetchall()
        if not junk_items:
            cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            bal = (cur.fetchone() or [0])[0]
            conn.close()
            return JsonResponse({"ok": True, "sold": 0, "mora": 0, "balance": bal}, headers=headers)
        total_mora = 0
        ids_to_delete = []
        for row in junk_items:
            iid, ikey = row
            meta = _ITEM_METADATA.get(ikey, {})
            sell = meta.get("sell", 0)
            total_mora += max(1, sell // 2)
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
        return JsonResponse({"ok": True, "sold": len(ids_to_delete), "mora": total_mora, "balance": new_bal}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


import random as _random

_GACHA_POOL = {
    "junk":      [("junk_stone","\U0001faa8 Камень Маслоу"),("junk_stick","\U0001fab5 Палка путника"),("junk_dust","💨 Пыль забвения"),("junk_bone","🦴 Кость хиличурла"),("junk_mushroom","🍄 Сомнительный гриб")],
    "common":    [("cmn_sword","⚔️ Тупой клинок"),("cmn_bow","🏹 Кривой лук"),("cmn_book","📕 Потрёпанный дневник"),("cmn_ring","💍 Дешёвое кольцо"),("cmn_shield","🛡 Ржавый щит")],
    "rare":      [("rare_crown","👑 Серебряная корона"),("rare_catalyst","🔮 Магический катализатор"),("rare_cape","🧣 Алый плащ"),("rare_gem","💎 Сапфир полуночи")],
    "legendary": [("lego_gnosis","✨ Гнозис Балладеера"),("lego_scepter","🏛 Скипетр Дендро Архонта"),("lego_pantalone","🎩 Маска Панталоне"),("lego_abyss","🌀 Корона Бездны"),("lego_fatui","⚡ Перст Предвестника")],
}


def _gacha_roll_one_sync(pity: int):
    roll = _random.random()
    if pity >= _GACHA_PITY_MAX - 1 or roll < 0.03:  # РЕБАЛАНС: было 0.02
        key, name = _random.choice(_GACHA_POOL["legendary"])
        return key, name, "legendary"
    elif roll < 0.10:
        key, name = _random.choice(_GACHA_POOL["rare"])
        return key, name, "rare"
    elif roll < 0.30:
        key, name = _random.choice(_GACHA_POOL["common"])
        return key, name, "common"
    else:
        key, name = _random.choice(_GACHA_POOL["junk"])
        return key, name, "junk"


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
        body = json.loads(request.body)
        chat_id = int(str(body.get("chat_id", "0")))
        count = int(body.get("count", 1))
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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        cur.execute(f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        is_single = cur.fetchone() is None
        price = (_GACHA_SINGLES_SINGLE if count == 1 else _GACHA_SINGLES_MULTI) if is_single else (
            _GACHA_SINGLE_PRICE if count == 1 else _GACHA_MULTI_PRICE)

        if wallet_type == "family":
            cur.execute(f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            if not cur.fetchone():
                conn.close()
                return JsonResponse({"error": "Нет семейного кошелька"}, status=400, headers=headers)
            cur.execute(f"SELECT balance FROM family_wallet WHERE chat_id={ph} AND user_id={ph}", (chat_id, uid))
            fam_bal = (cur.fetchone() or [0])[0]
            if fam_bal < price:
                conn.close()
                return JsonResponse({"error": f"Недостаточно в семейном ({fam_bal}/{price} 🪙)"}, status=400, headers=headers)
            cur.execute(f"UPDATE family_wallet SET balance=balance-{ph} WHERE chat_id={ph} AND user_id={ph}", (price, chat_id, uid))
        else:
            cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            bal = (cur.fetchone() or [0])[0]
            if bal < price:
                conn.close()
                return JsonResponse({"error": f"Недостаточно Моры ({bal}/{price} 🪙)"}, status=400, headers=headers)
            cur.execute(f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph}", (price, uid, chat_id))

        cur.execute(
            f"SELECT COUNT(*) FROM gacha_inventory WHERE user_id={ph} AND chat_id={ph} "
            f"AND id > COALESCE((SELECT MAX(id) FROM gacha_inventory WHERE user_id={ph} AND chat_id={ph} AND rarity='legendary'),0)",
            (uid, chat_id, uid, chat_id),
        )
        pity = (cur.fetchone() or [0])[0]

        results = []
        for _ in range(count):
            item_key, item_name, rarity = _gacha_roll_one_sync(pity)
            now_expr = "NOW()" if db_type == "pg" else "datetime('now')"
            _meta = _ITEM_METADATA.get(item_key, {})
            cur.execute(
                f"INSERT INTO gacha_inventory "
                f"(user_id, chat_id, item_key, item_name, rarity, obtained_at, atk, def_val, hp, crit_rate, slot) "
                f"VALUES ({ph},{ph},{ph},{ph},{ph},{now_expr},{ph},{ph},{ph},{ph},{ph})",
                (uid, chat_id, item_key, item_name, rarity,
                 _meta.get("atk", 0), _meta.get("def_val", 0), _meta.get("hp", 0),
                 _meta.get("crit_rate", 0.0), _meta.get("slot")),
            )
            pity = 0 if rarity == "legendary" else pity + 1
            results.append({"key": item_key, "name": item_name, "rarity": rarity})

        conn.commit()
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_bal = (cur.fetchone() or [0])[0]
        conn.close()
        
        # ➕ ЛОГИРУЕМ КРУТКУ ГАЧИ В ЧАТ
        loot_text = ""
        for item in results:
            rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}
            emoji = rarity_emoji.get(item["rarity"], "⚪")
            loot_text += f"{emoji} {item['name']}"
        
        roll_type = f"{count}x крутка" if count > 1 else "Одиночная крутка"
        from asgiref.sync import async_to_sync as _a2s
        _a2s(log_action_to_chat)(
            uid, chat_id,
            f"🎲 {roll_type} гачи (-{price} 🪙)",
            f"Выпало:{loot_text}"
        )

        return JsonResponse({"ok": True, "items": results, "balance": new_bal, "pity": pity, "spent": price},
                            json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        cur.execute(f"SELECT price FROM bond_prices WHERE chat_id={ph} AND bond_key={ph}", (chat_id, bond_key))
        row = cur.fetchone()
        price_per = row[0] if row else _BOND_DEFAULTS_SYNC[bond_key]["base_price"]
        total_cost = price_per * amount

        if wallet == "family":
            cur.execute(f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            if not cur.fetchone():
                conn.close()
                return JsonResponse({"error": "Нет семейного кошелька"}, status=400, headers=headers)
            cur.execute(f"SELECT balance FROM family_wallet WHERE chat_id={ph} AND user_id={ph}", (chat_id, uid))
            fam_bal = (cur.fetchone() or [0])[0]
            if fam_bal < total_cost:
                conn.close()
                return JsonResponse({"error": f"Недостаточно в семейном ({fam_bal}/{total_cost})"}, status=400, headers=headers)
            cur.execute(f"UPDATE family_wallet SET balance=balance-{ph} WHERE chat_id={ph} AND user_id={ph}", (total_cost, chat_id, uid))
        else:
            cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            pers_bal = (cur.fetchone() or [0])[0]
            if pers_bal < total_cost:
                conn.close()
                return JsonResponse({"error": f"Недостаточно Моры ({pers_bal}/{total_cost})"}, status=400, headers=headers)
            cur.execute(f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph}", (total_cost, uid, chat_id))

        if db_type == "pg":
            cur.execute(
                "INSERT INTO user_bonds (user_id, chat_id, bond_key, amount, invested) VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT(user_id, chat_id, bond_key) DO UPDATE SET amount=user_bonds.amount+EXCLUDED.amount, invested=user_bonds.invested+EXCLUDED.invested",
                (uid, chat_id, bond_key, amount, total_cost),
            )
        else:
            cur.execute(
                "INSERT INTO user_bonds (user_id, chat_id, bond_key, amount, invested) VALUES (?,?,?,?,?) "
                "ON CONFLICT(user_id, chat_id, bond_key) DO UPDATE SET amount=user_bonds.amount+excluded.amount, invested=user_bonds.invested+excluded.invested",
                (uid, chat_id, bond_key, amount, total_cost),
            )

        conn.commit()
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_personal = (cur.fetchone() or [0])[0]
        cur.execute(f"SELECT balance FROM family_wallet WHERE chat_id={ph} AND user_id={ph}", (chat_id, uid))
        new_family = (cur.fetchone() or [0])[0]
        cur.execute(f"SELECT amount, invested FROM user_bonds WHERE user_id={ph} AND chat_id={ph} AND bond_key={ph}", (uid, chat_id, bond_key))
        bond_row = cur.fetchone()
        conn.close()

        return JsonResponse({
            "ok": True, "bond_key": bond_key, "price_per": price_per, "total_cost": total_cost,
            "holdings": bond_row[0] if bond_row else amount,
            "invested": bond_row[1] if bond_row else total_cost,
            "personal": new_personal, "family": new_family,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        cur.execute(f"SELECT amount, invested FROM user_bonds WHERE user_id={ph} AND chat_id={ph} AND bond_key={ph}", (uid, chat_id, bond_key))
        bond_row = cur.fetchone()
        if not bond_row or bond_row[0] < amount:
            conn.close()
            have = bond_row[0] if bond_row else 0
            return JsonResponse({"error": f"У тебя только {have} облигаций"}, status=400, headers=headers)

        cur.execute(f"SELECT price FROM bond_prices WHERE chat_id={ph} AND bond_key={ph}", (chat_id, bond_key))
        price_row = cur.fetchone()
        price_per = price_row[0] if price_row else _BOND_DEFAULTS_SYNC[bond_key]["base_price"]
        revenue = price_per * amount

        new_amount = bond_row[0] - amount
        new_invested = max(0, int(bond_row[1] * new_amount / bond_row[0])) if bond_row[0] > 0 else 0
        if new_amount <= 0:
            cur.execute(f"DELETE FROM user_bonds WHERE user_id={ph} AND chat_id={ph} AND bond_key={ph}", (uid, chat_id, bond_key))
        else:
            cur.execute(f"UPDATE user_bonds SET amount={ph}, invested={ph} WHERE user_id={ph} AND chat_id={ph} AND bond_key={ph}", (new_amount, new_invested, uid, chat_id, bond_key))

        if db_type == "pg":
            cur.execute(
                f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
                f"ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=user_mora.balance+EXCLUDED.balance",
                (uid, chat_id, revenue),
            )
        else:
            cur.execute(
                "INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,?) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=user_mora.balance+excluded.balance",
                (uid, chat_id, revenue),
            )

        conn.commit()
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_bal = (cur.fetchone() or [0])[0]
        conn.close()

        return JsonResponse({
            "ok": True, "bond_key": bond_key, "sold": amount, "price_per": price_per,
            "revenue": revenue, "remaining": new_amount, "balance": new_bal,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        cur.execute(
            f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}",
            (uid, chat_id),
        )
        balance_row = cur.fetchone()
        balance = balance_row[0] if balance_row else 0

        cur.execute(
            f"SELECT id, amount, rate, created_at, matures_at "
            f"FROM bank_deposits WHERE user_id={ph} AND chat_id={ph} AND withdrawn=0 ORDER BY id",
            (uid, chat_id),
        )
        rows = cur.fetchall()

        # Fetch family balance for display reference
        family_balance = 0
        try:
            cur.execute(f"SELECT balance FROM family_wallet WHERE chat_id={ph}", (chat_id,))
            frow = cur.fetchone()
            family_balance = frow[0] if frow else 0
        except Exception:
            family_balance = 0

        conn.close()

        now = datetime.now(timezone.utc)
        deposits = []
        for row in rows:
            dep_id, amount, rate, created_at, matures_at = row
            # Normalize str -> datetime
            if isinstance(matures_at, str):
                from datetime import datetime as _dt
                matures_at = _dt.fromisoformat(matures_at.replace("Z", "+00:00"))
            if isinstance(created_at, str):
                from datetime import datetime as _dt
                created_at = _dt.fromisoformat(created_at.replace("Z", "+00:00"))
            # Fix offset-naive vs offset-aware error: assume UTC for naive datetimes
            if matures_at is not None and getattr(matures_at, 'tzinfo', None) is None:
                matures_at = matures_at.replace(tzinfo=timezone.utc)
            if created_at is not None and getattr(created_at, 'tzinfo', None) is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            mature = now >= matures_at
            reward = int(amount * rate)
            time_left_secs = max(0, (matures_at - now).total_seconds()) if not mature else 0
            time_left_h = int(time_left_secs // 3600)
            time_left_m = int((time_left_secs % 3600) // 60)
            total_secs = max(1, (matures_at - created_at).total_seconds())
            elapsed_secs = (now - created_at).total_seconds()
            progress_pct = min(100, max(0, int(elapsed_secs / total_secs * 100)))
            plan_days = max(1, round(total_secs / 86400))
            deposits.append({
                "id": dep_id,
                "amount": amount,
                "rate": rate,
                "rate_pct": round(rate * 100, 1),
                "reward": reward,
                "mature": mature,
                "time_left_h": time_left_h,
                "time_left_m": time_left_m,
                "progress_pct": progress_pct,
                "plan_days": plan_days,
                "matures_at_iso": matures_at.strftime("%d.%m %H:%M"),
            })

        plans_out = []
        for key, p in _BANK_PLANS_SYNC.items():
            plans_out.append({
                "key": key,
                "days": p["days"],
                "rate_pct": round(p["rate"] * 100, 1),
                "label": p["label"],
                "amounts": [a for a in (100, 250, 500, 1_000, 2_500, 5_000, 10_000)
                            if _BANK_MIN_DEPOSIT <= a <= _BANK_MAX_DEPOSIT],
            })

        return JsonResponse({
            "balance": balance,
            "family_balance": family_balance,
            "deposits": deposits,
            "plans": plans_out,
            "min_deposit": _BANK_MIN_DEPOSIT,
            "max_deposit": _BANK_MAX_DEPOSIT,
            "early_penalty_pct": round(_BANK_EARLY_PENALTY_PCT * 100, 1),
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    plan = _BANK_PLANS_SYNC[plan_key]

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        if wallet == "family":
            cur.execute(
                f"SELECT balance FROM family_wallet WHERE chat_id={ph}",
                (chat_id,),
            )
            frow = cur.fetchone()
            fbal = frow[0] if frow else 0
            if fbal < amount:
                conn.close()
                return JsonResponse({"error": f"Недостаточно семейных средств ({fbal}/{amount} 🪙)"}, status=400, headers=headers)
            cur.execute(
                f"UPDATE family_wallet SET balance=balance-{ph} WHERE chat_id={ph}",
                (amount, chat_id),
            )
        else:
            cur.execute(
                f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}",
                (uid, chat_id),
            )
            brow = cur.fetchone()
            bal = brow[0] if brow else 0
            if bal < amount:
                conn.close()
                return JsonResponse({"error": f"Недостаточно Моры ({bal}/{amount} 🪙)"}, status=400, headers=headers)
            cur.execute(
                f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph}",
                (amount, uid, chat_id),
            )

        now = datetime.now(timezone.utc)
        matures = now + __import__("datetime").timedelta(days=plan["days"])

        if db_type == "pg":
            cur.execute(
                "INSERT INTO bank_deposits (user_id, chat_id, amount, rate, created_at, matures_at) "
                "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (uid, chat_id, amount, plan["rate"], now, matures),
            )
            dep_id = (cur.fetchone() or [None])[0]
        else:
            cur.execute(
                "INSERT INTO bank_deposits (user_id, chat_id, amount, rate, created_at, matures_at) "
                "VALUES (?,?,?,?,?,?)",
                (uid, chat_id, amount, plan["rate"], now, matures),
            )
            dep_id = cur.lastrowid

        conn.commit()

        # Fetch new balance
        if wallet == "family":
            cur.execute(f"SELECT balance FROM family_wallet WHERE chat_id={ph}", (chat_id,))
        else:
            cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        brow2 = cur.fetchone()
        new_balance = brow2[0] if brow2 else 0
        conn.close()

        return JsonResponse({
            "ok": True,
            "deposit_id": dep_id,
            "amount": amount,
            "rate_pct": round(plan["rate"] * 100, 1),
            "reward": int(amount * plan["rate"]),
            "days": plan["days"],
            "new_balance": new_balance,
            "wallet": wallet,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        cur.execute(
            f"SELECT id, user_id, amount, rate, matures_at FROM bank_deposits "
            f"WHERE id={ph} AND chat_id={ph} AND withdrawn=0",
            (deposit_id, chat_id),
        )
        dep = cur.fetchone()
        if not dep:
            conn.close()
            return JsonResponse({"error": "Вклад не найден или уже снят"}, status=404, headers=headers)

        dep_id, owner_id, amount, rate, matures_at = dep
        if owner_id != uid:
            conn.close()
            return JsonResponse({"error": "Это не твой вклад"}, status=403, headers=headers)

        if isinstance(matures_at, str):
            from datetime import datetime as _dt
            matures_at = _dt.fromisoformat(matures_at.replace("Z", "+00:00"))
        # Fix offset-naive vs offset-aware error
        if matures_at is not None and getattr(matures_at, 'tzinfo', None) is None:
            matures_at = matures_at.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        mature = now >= matures_at
        if mature:
            payout = amount + int(amount * rate)
            early = False
        else:
            penalty = int(amount * _BANK_EARLY_PENALTY_PCT)
            payout = max(0, amount - penalty)
            early = True

        cur.execute(f"UPDATE bank_deposits SET withdrawn=1 WHERE id={ph}", (deposit_id,))

        cur.execute(
            f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
            f"ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=user_mora.balance+excluded.balance",
            (uid, chat_id, payout),
        )
        conn.commit()

        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_balance = (cur.fetchone() or [0])[0]
        conn.close()

        return JsonResponse({
            "ok": True,
            "deposit_id": deposit_id,
            "payout": payout,
            "early": early,
            "new_balance": new_balance,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)

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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        cur.execute(f"SELECT pet_type, name, COALESCE(fatigue,0) FROM pets WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        pet_row = cur.fetchone()
        if not pet_row:
            conn.close()
            return JsonResponse({"error": "У тебя нет питомца"}, status=400, headers=headers)
        ptype, pname, fatigue = pet_row

        if wallet_type == "family":
            cur.execute(f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            if not cur.fetchone():
                conn.close()
                return JsonResponse({"error": "Нет семейного кошелька"}, status=400, headers=headers)
            cur.execute(f"SELECT balance FROM family_wallet WHERE chat_id={ph} AND user_id={ph}", (chat_id, uid))
            fam_bal = (cur.fetchone() or [0])[0]
            if fam_bal < food["price"]:
                conn.close()
                return JsonResponse({"error": f"Недостаточно в семейном ({fam_bal}/{food['price']})"}, status=400, headers=headers)
            cur.execute(f"UPDATE family_wallet SET balance=balance-{ph} WHERE chat_id={ph} AND user_id={ph}", (food["price"], chat_id, uid))
        else:
            cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            bal = (cur.fetchone() or [0])[0]
            if bal < food["price"]:
                conn.close()
                return JsonResponse({"error": f"Недостаточно Моры ({bal}/{food['price']})"}, status=400, headers=headers)
            cur.execute(f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph}", (food["price"], uid, chat_id))
        new_fatigue = max(0, fatigue - food["fatigue"])
        cur.execute(f"UPDATE pets SET fatigue={ph} WHERE user_id={ph} AND chat_id={ph}", (new_fatigue, uid, chat_id))
        conn.commit()
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_bal = (cur.fetchone() or [0])[0]
        conn.close()
        
        # ➕ ЛОГИРУЕМ КОРМЕЖКУ ПИТОМЦА В ЧАТ
        from asgiref.sync import async_to_sync as _a2s
        emoji = {"cat": "🐱", "dog": "🐶"}.get(ptype, "🐾")
        wallet_text = f" из {wallet_type} кошелька" if wallet_type == "family" else ""
        _a2s(log_action_to_chat)(
            uid, chat_id,
            f"{emoji} Покормил питомца {pname or 'Питомец'}",
            f"Еда: {food['name']} (-{food['price']} 🪙{wallet_text})\nУсталость: -{food['fatigue']}"
        )

        return JsonResponse({"ok": True, "fatigue": new_fatigue, "reduced": food["fatigue"], "balance": new_bal,
                             "pet_emoji": emoji, "pet_name": pname or "Питомец", "food_name": food["name"]},
                            json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        cur.execute(f"SELECT item_value FROM shop_items WHERE user_id={ph} AND chat_id={ph} AND item_type='frame'", (uid, chat_id))
        owned_frames = {r[0] for r in cur.fetchall()}

        cur.execute(f"SELECT item_value FROM shop_items WHERE user_id={ph} AND chat_id={ph} AND item_type='cosmetic'", (uid, chat_id))
        owned_cosmetics = {r[0] for r in cur.fetchall()}

        cur.execute(f"SELECT top_frame, vip, balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        mora_row = cur.fetchone()
        active_frame = mora_row[0] if mora_row else None
        has_vip = bool(mora_row[1]) if mora_row else False
        balance = mora_row[2] if mora_row else 0
        conn.close()

        frames = [
            {"key": key, "emoji": em, "name": name, "price": price,
             "owned": key in owned_frames or key == "default",
             "active": key == (active_frame or "default")}
            for key, em, name, price in _FRAMES_CATALOG
        ]
        cosmetics = [
            {"key": key, "emoji": em, "name": name, "price": price, "desc": desc, "owned": key in owned_cosmetics}
            for key, em, name, price, desc in _COSMETICS_CATALOG
        ]
        food_list = [
            {"key": k, "name": v["name"], "emoji": v["emoji"], "price": v["price"], "fatigue": v["fatigue"]}
            for k, v in _FOOD_ITEMS.items()
        ]
        potions_list = [
            {"key": k, "name": v["name"], "emoji": v["emoji"], "price": v["price"], 
             "buff_type": v["buff_type"], "buff_amount": v["buff_amount"], 
             "duration": v["duration"], "desc": v["desc"]}
            for k, v in _POTIONS_CATALOG.items()
            if v["price"] > 0  # Only show purchasable potions (not gacha-only)
        ]
        return JsonResponse({
            "balance": balance, "frames": frames, "cosmetics": cosmetics,
            "food": food_list, "potions": potions_list, "has_vip": has_vip, "active_frame": active_frame or "default",
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    # Validate and get price
    price = 0
    if item_type == "frame":
        frame_map = {f[0]: f for f in _FRAMES_CATALOG}
        frame = frame_map.get(item_key)
        if not frame:
            return JsonResponse({"error": "Unknown frame"}, status=400, headers=headers)
        price = frame[3]
        if price == 0:
            return JsonResponse({"error": "Default frame is free"}, status=400, headers=headers)
    elif item_type == "cosmetic":
        cosm_map = {c[0]: c for c in _COSMETICS_CATALOG}
        cosm = cosm_map.get(item_key)
        if not cosm:
            return JsonResponse({"error": "Unknown cosmetic"}, status=400, headers=headers)
        price = cosm[3]
    elif item_type == "vip":
        price = _PRICE_VIP
    else:
        return JsonResponse({"error": "item_type must be frame/cosmetic/vip"}, status=400, headers=headers)

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        if item_type in ("frame", "cosmetic"):
            cur.execute(
                f"SELECT 1 FROM shop_items WHERE user_id={ph} AND chat_id={ph} AND item_type={ph} AND item_value={ph}",
                (uid, chat_id, item_type, item_key),
            )
            if cur.fetchone():
                if item_type == "frame" and equip:
                    cur.execute(f"UPDATE user_mora SET top_frame={ph} WHERE user_id={ph} AND chat_id={ph}", (item_key, uid, chat_id))
                    conn.commit()
                conn.close()
                return JsonResponse({"ok": True, "already_owned": True, "equipped": item_type == "frame" and equip}, headers=headers)

        if wallet_type == "family":
            cur.execute(f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            if not cur.fetchone():
                conn.close()
                return JsonResponse({"error": "Нет семейного кошелька"}, status=400, headers=headers)
            cur.execute(f"SELECT balance FROM family_wallet WHERE chat_id={ph} AND user_id={ph}", (chat_id, uid))
            fam_bal = (cur.fetchone() or [0])[0]
            if fam_bal < price:
                conn.close()
                return JsonResponse({"error": f"Недостаточно в семейном ({fam_bal}/{price})"}, status=400, headers=headers)
            cur.execute(f"UPDATE family_wallet SET balance=balance-{ph} WHERE chat_id={ph} AND user_id={ph}", (price, chat_id, uid))
        else:
            cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            bal = (cur.fetchone() or [0])[0]
            if bal < price:
                conn.close()
                return JsonResponse({"error": f"Недостаточно Моры ({bal}/{price})"}, status=400, headers=headers)
            cur.execute(f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph}", (price, uid, chat_id))

        now_expr = "NOW()" if db_type == "pg" else "datetime('now')"
        if item_type in ("frame", "cosmetic"):
            cur.execute(
                f"INSERT INTO shop_items (user_id, chat_id, item_type, item_value, purchased_at) VALUES ({ph},{ph},{ph},{ph},{now_expr})",
                (uid, chat_id, item_type, item_key),
            )
            if item_type == "frame" and equip:
                cur.execute(f"UPDATE user_mora SET top_frame={ph} WHERE user_id={ph} AND chat_id={ph}", (item_key, uid, chat_id))
        elif item_type == "vip":
            cur.execute(f"UPDATE user_mora SET vip=1 WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))

        conn.commit()
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_bal = (cur.fetchone() or [0])[0]
        conn.close()

        return JsonResponse({"ok": True, "item_type": item_type, "item_key": item_key,
                             "price": price, "balance": new_bal, "equipped": item_type == "frame" and equip},
                            json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
            return JsonResponse({"error": str(exc)}, status=500, headers=headers)

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
            return JsonResponse({"error": str(exc)}, status=500, headers=headers)

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

        # Stats (level, xp, rank, custom_title)
        cur.execute(
            f"SELECT xp, COALESCE(level,1), COALESCE(rank,'user'), custom_title "
            f"FROM user_stats WHERE user_id={ph} AND chat_id={ph}",
            (target_id, chat_id),
        )
        stats_row = cur.fetchone()
        xp = stats_row[0] if stats_row else 0
        level = stats_row[1] if stats_row else 1
        rank = stats_row[2] if stats_row else "user"
        custom_title = stats_row[3] if stats_row else None

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
            for eid in [rpg_row[4], rpg_row[5], rpg_row[6]]:
                if eid:
                    cur.execute(
                        f"SELECT item_name, rarity, slot, COALESCE(atk,0), COALESCE(def_val,0), "
                        f"COALESCE(hp,0), COALESCE(crit_rate,0) FROM gacha_inventory WHERE id={ph}",
                        (eid,),
                    )
                    er = cur.fetchone()
                    if er:
                        rpg["atk"] += er[3]
                        rpg["def"] += er[4]
                        rpg["hp"] += er[5]
                        rpg["crit"] += er[6]
                        equipped_items.append({"name": er[0], "rarity": er[1], "slot": er[2] or "gear"})
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
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        from database.db import enhance_item
        from asgiref.sync import async_to_sync as _a2s

        success, message, new_level = _a2s(enhance_item)(uid, chat_id, item_id)

        # ➕ ЛОГИРУЕМ ЗАТОЧКУ В ЧАТ
        if success:
            _a2s(log_action_to_chat)(
                uid, chat_id,
                f"✨ Заточил предмет до +{new_level}",
                message
            )
        
        # Get updated balance
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        balance = (cur.fetchone() or [0])[0]
        conn.close()

        return JsonResponse({
            "success": success,
            "message": message,
            "enhancement_level": new_level,
            "balance": balance,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    item_ids = data.get("item_ids", [])
    chat_id = data.get("chat_id")

    if not chat_id:
        return JsonResponse({"error": "chat_id required"}, status=400, headers=headers)

    if not isinstance(item_ids, list):
        return JsonResponse({"error": "item_ids must be array"}, status=400, headers=headers)

    try:
        from database.db import batch_sell_items
        from asgiref.sync import async_to_sync as _a2s

        sold_count, total_mora = _a2s(batch_sell_items)(uid, chat_id, item_ids)

        # ➕ ЛОГИРУЕМ ПРОДАЖУ ВЕЩЕЙ В ЧАТ
        if sold_count > 0:
            _a2s(log_action_to_chat)(
                uid, chat_id,
                f"💰 Продал {sold_count} предметов",
                f"Получено: +{total_mora} 🪙"
            )

        # Get updated balance
        try:
            conn, db_type = _get_bot_db_connection()
            cur = conn.cursor()
            ph = "%s" if db_type == "pg" else "?"
            cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            balance = (cur.fetchone() or [0])[0]
            conn.close()
        except Exception:
            balance = 0

        return JsonResponse({
            "sold": sold_count,
            "mora": total_mora,
            "balance": balance,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
            "is_repeat", "is_completed", "session_date"
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
            from database.db import get_couple_boss_rewards
            rewards = async_to_sync(get_couple_boss_rewards)(session_data)
            
            # Give rewards to both players
            try:
                conn, db_type = _get_bot_db_connection()
                cur = conn.cursor()
                ph = "%s" if db_type == "pg" else "?"
                
                # Add mora and XP to both users
                for player_id in [user_a_id, user_b_id]:
                    if db_type == "pg":
                        cur.execute(
                            f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
                            f"ON CONFLICT (user_id, chat_id) DO UPDATE SET balance = user_mora.balance + EXCLUDED.balance",
                            (player_id, chat_id, rewards["mora_each"]),
                        )
                        cur.execute(
                            f"INSERT INTO user_stats (user_id, chat_id, xp) VALUES ({ph},{ph},{ph}) "
                            f"ON CONFLICT (user_id, chat_id) DO UPDATE SET xp = user_stats.xp + EXCLUDED.xp",
                            (player_id, chat_id, rewards["xp_each"]),
                        )
                    else:
                        cur.execute(
                            "INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,?) "
                            "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance = user_mora.balance + excluded.balance",
                            (player_id, chat_id, rewards["mora_each"]),
                        )
                        cur.execute(
                            "INSERT INTO user_stats (user_id, chat_id, xp) VALUES (?,?,?) "
                            "ON CONFLICT(user_id, chat_id) DO UPDATE SET xp = user_stats.xp + excluded.xp",
                            (player_id, chat_id, rewards["xp_each"]),
                        )
                
                conn.commit()
                conn.close()
                
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
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
            conn, db_type = _get_bot_db_connection()
            cur = conn.cursor()
            ph = "%s" if db_type == "pg" else "?"
            if db_type == "pg":
                cur.execute(
                    f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
                    f"ON CONFLICT (user_id, chat_id) DO UPDATE SET balance = user_mora.balance + EXCLUDED.balance",
                    (uid, chat_id, mora_reward),
                )
                cur.execute(
                    f"INSERT INTO user_stats (user_id, chat_id, xp) VALUES ({ph},{ph},{ph}) "
                    f"ON CONFLICT (user_id, chat_id) DO UPDATE SET xp = user_stats.xp + EXCLUDED.xp",
                    (uid, chat_id, xp_reward),
                )
            else:
                cur.execute(
                    "INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,?) "
                    "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance = user_mora.balance + excluded.balance",
                    (uid, chat_id, mora_reward),
                )
                cur.execute(
                    "INSERT INTO user_stats (user_id, chat_id, xp) VALUES (?,?,?) "
                    "ON CONFLICT(user_id, chat_id) DO UPDATE SET xp = user_stats.xp + excluded.xp",
                    (uid, chat_id, xp_reward),
                )
            conn.commit()
            conn.close()
            response["rewards"] = {"mora": mora_reward, "xp": xp_reward}
        except Exception as e:
            try: conn.close()
            except Exception: pass
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

    user_id_str = request.GET.get("user_id", "")
    if not user_id_str.isdigit():
        return JsonResponse({"error": "user_id required"}, status=400, headers=headers)
    
    user_id = int(user_id_str)
    avatar_url = get_telegram_avatar_url(user_id)
    
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

def _quest_today() -> str:
    """Return today's date string matching bot_today() (UTC or BOT_TIMEZONE)."""
    try:
        from zoneinfo import ZoneInfo
        from config import BOT_TIMEZONE
        tz = ZoneInfo(BOT_TIMEZONE)
        return datetime.now(tz).date().isoformat()
    except Exception:
        return datetime.now(timezone.utc).date().isoformat()


def _quest_default_for_date(today_str: str) -> dict:
    """Compute the rotation quest for a given date without DB lookup."""
    from datetime import date as _date
    try:
        from database.db import DAILY_QUESTS
    except Exception:
        return {"type": "messages", "goal": 10, "xp": 30, "mora": 3, "desc": "✍️ Написать 10 сообщений в чате"}
    d = _date.fromisoformat(today_str)
    idx = d.toordinal() % len(DAILY_QUESTS)
    return DAILY_QUESTS[idx]


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
    today = _quest_today()

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        cur.execute(
            f"SELECT quest_type, goal, progress, completed, rewarded "
            f"FROM user_quests WHERE user_id={ph} AND chat_id={ph} AND quest_date={ph}",
            (uid, chat_id, today),
        )
        row = cur.fetchone()
        conn.close()

        if row:
            quest_type, goal, progress, completed, rewarded = row
            # Find matching quest in DAILY_QUESTS
            try:
                from database.db import DAILY_QUESTS
                quest = next(
                    (q for q in DAILY_QUESTS if q["type"] == quest_type and q["goal"] == goal),
                    None,
                )
                if not quest:
                    quest = {"type": quest_type, "goal": goal, "xp": 50, "mora": 5, "desc": f"Задание: {quest_type}"}
            except Exception:
                quest = {"type": quest_type, "goal": goal, "xp": 50, "mora": 5, "desc": f"Задание: {quest_type}"}
        else:
            quest = _quest_default_for_date(today)
            progress = 0
            completed = 0
            rewarded = 0

        return JsonResponse({
            "ok": True,
            "quest": {
                "type": quest["type"],
                "goal": quest["goal"],
                "desc": quest["desc"],
                "xp": quest["xp"],
                "mora": quest.get("mora", 5),
            },
            "progress": progress,
            "completed": bool(completed),
            "rewarded": bool(rewarded),
            "today": today,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
    today = _quest_today()

    try:
        from config import QUEST_REROLL_PRICE
    except Exception:
        QUEST_REROLL_PRICE = 25

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Check if already completed
        cur.execute(
            f"SELECT completed FROM user_quests WHERE user_id={ph} AND chat_id={ph} AND quest_date={ph}",
            (uid, chat_id, today),
        )
        row = cur.fetchone()
        if row and row[0]:
            conn.close()
            return JsonResponse({"error": "Задание уже выполнено — переброс не нужен"}, status=400, headers=headers)

        # Check balance
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        bal_row = cur.fetchone()
        balance = bal_row[0] if bal_row else 0
        if balance < QUEST_REROLL_PRICE:
            conn.close()
            return JsonResponse({"error": f"Недостаточно Моры. Нужно {QUEST_REROLL_PRICE} 🪙"}, status=400, headers=headers)

        # Deduct mora
        cur.execute(
            f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph} AND balance>={ph}",
            (QUEST_REROLL_PRICE, uid, chat_id, QUEST_REROLL_PRICE),
        )
        if cur.rowcount == 0:
            conn.close()
            return JsonResponse({"error": "Не удалось списать Мору"}, status=400, headers=headers)

        # Pick new quest
        try:
            from database.db import DAILY_QUESTS
            import random as _random
            # Get old quest to avoid repeating it
            cur.execute(
                f"SELECT quest_type, goal FROM user_quests WHERE user_id={ph} AND chat_id={ph} AND quest_date={ph}",
                (uid, chat_id, today),
            )
            old_row = cur.fetchone()
            if old_row:
                old_type, old_goal = old_row
                candidates = [q for q in DAILY_QUESTS if not (q["type"] == old_type and q["goal"] == old_goal)]
                if not candidates:
                    candidates = DAILY_QUESTS
            else:
                old_quest = _quest_default_for_date(today)
                candidates = [q for q in DAILY_QUESTS if not (q["type"] == old_quest["type"] and q["goal"] == old_quest["goal"])]
                if not candidates:
                    candidates = DAILY_QUESTS
            new_quest = _random.choice(candidates)
        except Exception:
            new_quest = _quest_default_for_date(today)

        # Delete old row and insert new
        cur.execute(
            f"DELETE FROM user_quests WHERE user_id={ph} AND chat_id={ph} AND quest_date={ph}",
            (uid, chat_id, today),
        )
        cur.execute(
            f"INSERT INTO user_quests (user_id, chat_id, quest_date, quest_type, goal, progress, completed, rewarded) "
            f"VALUES ({ph},{ph},{ph},{ph},{ph},0,0,0)",
            (uid, chat_id, today, new_quest["type"], new_quest["goal"]),
        )
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_balance = (cur.fetchone() or [balance])[0]
        conn.commit()
        conn.close()

        return JsonResponse({
            "ok": True,
            "quest": {
                "type": new_quest["type"],
                "goal": new_quest["goal"],
                "desc": new_quest["desc"],
                "xp": new_quest["xp"],
                "mora": new_quest.get("mora", 5),
            },
            "cost": QUEST_REROLL_PRICE,
            "new_balance": new_balance,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    if target_id == uid:
        return JsonResponse({"error": "Нельзя шпионить за собой"}, status=400, headers=headers)

    SPY_COST = 50

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        import random as _random
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        now_utc = datetime.now(timezone.utc)
        cooldown_sec = 3600

        # Check cooldown
        if db_type == "pg":
            cur.execute(
                "SELECT COUNT(*) FROM espionage_log WHERE spy_id=%s AND target_id=%s AND chat_id=%s "
                "AND attempted_at > NOW() - INTERVAL '3600 seconds'",
                (uid, target_id, chat_id),
            )
        else:
            since_iso = (now_utc.replace(tzinfo=None) - __import__("datetime").timedelta(seconds=cooldown_sec)).isoformat()
            cur.execute(
                "SELECT COUNT(*) FROM espionage_log WHERE spy_id=? AND target_id=? AND chat_id=? AND attempted_at > ?",
                (uid, target_id, chat_id, since_iso),
            )
        count = (cur.fetchone() or [0])[0]
        if count > 0:
            # Get remaining cooldown
            cur.execute(
                f"SELECT attempted_at FROM espionage_log WHERE spy_id={ph} AND target_id={ph} AND chat_id={ph} "
                f"ORDER BY id DESC LIMIT 1",
                (uid, target_id, chat_id),
            )
            row = cur.fetchone()
            remaining = 0
            if row:
                last = row[0]
                if isinstance(last, str):
                    last = datetime.fromisoformat(last.replace("Z", "+00:00"))
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                elapsed = (now_utc - last).total_seconds()
                remaining = max(0, int(cooldown_sec - elapsed))
            conn.close()
            mins = remaining // 60
            secs = remaining % 60
            return JsonResponse({"error": f"Кулдаун: {mins} мин. {secs} сек."}, status=429, headers=headers)

        # Check own balance
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        bal_row = cur.fetchone()
        balance = bal_row[0] if bal_row else 0
        if balance < SPY_COST:
            conn.close()
            return JsonResponse({"error": f"Недостаточно Моры. Нужно {SPY_COST} 🪙"}, status=400, headers=headers)

        # Deduct cost
        cur.execute(
            f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph} AND balance>={ph}",
            (SPY_COST, uid, chat_id, SPY_COST),
        )
        if cur.rowcount == 0:
            conn.close()
            return JsonResponse({"error": "Не удалось списать Мору"}, status=400, headers=headers)

        # 30% fail
        failed = _random.random() < 0.30
        success_int = 0 if failed else 1

        # Log espionage
        now_iso = now_utc.isoformat()
        cur.execute(
            f"INSERT INTO espionage_log (spy_id, target_id, chat_id, success, attempted_at) VALUES ({ph},{ph},{ph},{ph},{ph})",
            (uid, target_id, chat_id, success_int, now_iso),
        )
        conn.commit()

        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_balance = (cur.fetchone() or [0])[0]

        if failed:
            conn.close()
            return JsonResponse({
                "ok": True,
                "success": False,
                "cost": SPY_COST,
                "new_balance": new_balance,
                "message": "💥 Провал! Агент обнаружен.",
            }, json_dumps_params={"ensure_ascii": False}, headers=headers)

        # Success — get target info
        cur.execute(f"SELECT balance, vip FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (target_id, chat_id))
        t_row = cur.fetchone()
        t_balance = t_row[0] if t_row else 0
        t_vip = bool(t_row[1]) if t_row else False

        # Get target name
        cur.execute(f"SELECT full_name, username FROM users WHERE user_id={ph}", (target_id,))
        u_row = cur.fetchone()
        t_name = u_row[0] if u_row else f"Игрок {target_id}"
        t_username = u_row[1] if u_row else None

        conn.close()
        return JsonResponse({
            "ok": True,
            "success": True,
            "cost": SPY_COST,
            "new_balance": new_balance,
            "target": {
                "id": target_id,
                "name": t_name,
                "username": t_username,
                "balance": t_balance,
                "vip": t_vip,
            },
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Check sender balance
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        bal_row = cur.fetchone()
        balance = bal_row[0] if bal_row else 0
        tax = max(1, int(amount * 0.005))
        total_needed = amount + tax
        if balance < total_needed:
            conn.close()
            return JsonResponse({"error": f"Недостаточно Моры. Нужно {total_needed} 🪙 (сумма + налог {tax})"}, status=400, headers=headers)

        # Deduct from sender (amount + tax)
        cur.execute(
            f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph} AND balance>={ph}",
            (total_needed, uid, chat_id, total_needed),
        )
        if cur.rowcount == 0:
            conn.close()
            return JsonResponse({"error": "Не удалось списать Мору"}, status=400, headers=headers)

        # Add to receiver
        cur.execute(
            f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
            f"ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=user_mora.balance+excluded.balance",
            (target_id, chat_id, amount),
        )
        # Tax to treasury
        cur.execute(
            f"INSERT INTO chat_treasury (chat_id, balance) VALUES ({ph},{ph}) "
            f"ON CONFLICT(chat_id) DO UPDATE SET balance=chat_treasury.balance+excluded.balance",
            (chat_id, tax),
        )
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_balance = (cur.fetchone() or [0])[0]
        conn.commit()
        conn.close()

        return JsonResponse({
            "ok": True,
            "amount": amount,
            "tax": tax,
            "new_balance": new_balance,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        def _get_name(user_id: int) -> str:
            cur.execute(f"SELECT full_name FROM users WHERE user_id={ph}", (user_id,))
            r = cur.fetchone()
            return r[0] if r else f"Игрок {user_id}"

        # Loans I borrowed (accepted)
        cur.execute(
            f"SELECT id, lender_id, amount, loaned_at FROM mora_loans "
            f"WHERE borrower_id={ph} AND chat_id={ph} AND repaid_at IS NULL "
            f"AND COALESCE(status,'accepted')='accepted' ORDER BY id",
            (uid, chat_id),
        )
        borrowed = []
        for row in cur.fetchall():
            loan_id, lender_id, amount, loaned_at = row
            loaned_at_str = loaned_at.isoformat() if hasattr(loaned_at, "isoformat") else str(loaned_at)
            borrowed.append({
                "id": loan_id,
                "lender_id": lender_id,
                "lender_name": _get_name(lender_id),
                "amount": amount,
                "loaned_at": loaned_at_str,
            })

        # Pending incoming requests (someone wants to lend me money)
        cur.execute(
            f"SELECT id, lender_id, amount, loaned_at FROM mora_loans "
            f"WHERE borrower_id={ph} AND chat_id={ph} AND repaid_at IS NULL "
            f"AND status='pending' ORDER BY id",
            (uid, chat_id),
        )
        pending_incoming = []
        for row in cur.fetchall():
            loan_id, lender_id, amount, loaned_at = row
            loaned_at_str = loaned_at.isoformat() if hasattr(loaned_at, "isoformat") else str(loaned_at)
            pending_incoming.append({
                "id": loan_id,
                "lender_id": lender_id,
                "lender_name": _get_name(lender_id),
                "amount": amount,
                "loaned_at": loaned_at_str,
            })

        # Loans I gave (accepted)
        cur.execute(
            f"SELECT id, borrower_id, amount, loaned_at FROM mora_loans "
            f"WHERE lender_id={ph} AND chat_id={ph} AND repaid_at IS NULL "
            f"AND COALESCE(status,'accepted')='accepted' ORDER BY id",
            (uid, chat_id),
        )
        lent = []
        for row in cur.fetchall():
            loan_id, borrower_id, amount, loaned_at = row
            loaned_at_str = loaned_at.isoformat() if hasattr(loaned_at, "isoformat") else str(loaned_at)
            lent.append({
                "id": loan_id,
                "borrower_id": borrower_id,
                "borrower_name": _get_name(borrower_id),
                "amount": amount,
                "loaned_at": loaned_at_str,
            })

        # Pending outgoing requests (I'm waiting for the borrower to accept)
        cur.execute(
            f"SELECT id, borrower_id, amount, loaned_at FROM mora_loans "
            f"WHERE lender_id={ph} AND chat_id={ph} AND repaid_at IS NULL "
            f"AND status='pending' ORDER BY id",
            (uid, chat_id),
        )
        pending_outgoing = []
        for row in cur.fetchall():
            loan_id, borrower_id, amount, loaned_at = row
            loaned_at_str = loaned_at.isoformat() if hasattr(loaned_at, "isoformat") else str(loaned_at)
            pending_outgoing.append({
                "id": loan_id,
                "borrower_id": borrower_id,
                "borrower_name": _get_name(borrower_id),
                "amount": amount,
                "loaned_at": loaned_at_str,
            })

        conn.close()
        return JsonResponse({
            "ok": True,
            "borrowed": borrowed,
            "lent": lent,
            "pending_incoming": pending_incoming,
            "pending_outgoing": pending_outgoing,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    if target_id == uid:
        return JsonResponse({"error": "Нельзя давать в долг самому себе"}, status=400, headers=headers)

    try:
        from config import LOAN_MAX_AMOUNT, LOAN_MAX_ACTIVE
    except Exception:
        LOAN_MAX_AMOUNT, LOAN_MAX_ACTIVE = 2000, 5

    if amount <= 0 or amount > LOAN_MAX_AMOUNT:
        return JsonResponse({"error": f"Сумма: 1–{LOAN_MAX_AMOUNT} 🪙"}, status=400, headers=headers)

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Check borrower's active loan count
        cur.execute(
            f"SELECT COUNT(*) FROM mora_loans WHERE borrower_id={ph} AND chat_id={ph} AND repaid_at IS NULL",
            (target_id, chat_id),
        )
        active = (cur.fetchone() or [0])[0]
        if active >= LOAN_MAX_ACTIVE:
            conn.close()
            return JsonResponse({"error": f"У заёмщика уже {active} активных долгов (максимум {LOAN_MAX_ACTIVE})"}, status=400, headers=headers)

        # Check lender has enough balance to "reserve"
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        bal_row = cur.fetchone()
        balance = bal_row[0] if bal_row else 0
        if balance < amount:
            conn.close()
            return JsonResponse({"error": f"Недостаточно Моры. У тебя {balance} 🪙"}, status=400, headers=headers)

        # Ensure status column exists (migration-safe)
        try:
            cur.execute("ALTER TABLE mora_loans ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'accepted'")
        except Exception:
            pass

        # Create PENDING loan request (money NOT transferred until borrower accepts)
        now_iso = datetime.now(timezone.utc).isoformat()
        if db_type == "pg":
            cur.execute(
                "INSERT INTO mora_loans (lender_id, borrower_id, chat_id, amount, loaned_at, status) "
                "VALUES (%s,%s,%s,%s,%s,'pending') RETURNING id",
                (uid, target_id, chat_id, amount, now_iso),
            )
            loan_id = cur.fetchone()[0]
        else:
            cur.execute(
                "INSERT INTO mora_loans (lender_id, borrower_id, chat_id, amount, loaned_at, status) VALUES (?,?,?,?,?,'pending')",
                (uid, target_id, chat_id, amount, now_iso),
            )
            loan_id = cur.lastrowid

        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_balance = (cur.fetchone() or [0])[0]
        conn.commit()
        conn.close()

        return JsonResponse({
            "ok": True,
            "loan_id": loan_id,
            "amount": amount,
            "new_balance": new_balance,
            "pending": True,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Find loan
        cur.execute(
            f"SELECT id, lender_id, amount FROM mora_loans "
            f"WHERE id={ph} AND borrower_id={ph} AND chat_id={ph} AND repaid_at IS NULL",
            (loan_id, uid, chat_id),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return JsonResponse({"error": "Долг не найден или уже погашен"}, status=404, headers=headers)

        _, lender_id, amount = row

        # Check borrower balance
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        bal_row = cur.fetchone()
        balance = bal_row[0] if bal_row else 0
        if balance < amount:
            conn.close()
            return JsonResponse({"error": f"Недостаточно Моры. Нужно {amount} 🪙, у тебя {balance}"}, status=400, headers=headers)

        # Deduct from borrower
        cur.execute(
            f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph} AND balance>={ph}",
            (amount, uid, chat_id, amount),
        )
        if cur.rowcount == 0:
            conn.close()
            return JsonResponse({"error": "Не удалось списать Мору"}, status=400, headers=headers)

        # Add to lender
        cur.execute(
            f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
            f"ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=user_mora.balance+excluded.balance",
            (lender_id, chat_id, amount),
        )

        # Mark repaid
        now_iso = datetime.now(timezone.utc).isoformat()
        cur.execute(
            f"UPDATE mora_loans SET repaid_at={ph} WHERE id={ph}",
            (now_iso, loan_id),
        )

        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_balance = (cur.fetchone() or [0])[0]
        conn.commit()
        conn.close()

        return JsonResponse({
            "ok": True,
            "loan_id": loan_id,
            "amount": amount,
            "new_balance": new_balance,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    if action not in ("accept", "reject"):
        return JsonResponse({"error": "action must be accept or reject"}, status=400, headers=headers)

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Find the pending loan for this borrower
        cur.execute(
            f"SELECT id, lender_id, amount FROM mora_loans "
            f"WHERE id={ph} AND borrower_id={ph} AND chat_id={ph} AND status='pending' AND repaid_at IS NULL",
            (loan_id, uid, chat_id),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return JsonResponse({"error": "Заявка не найдена или уже обработана"}, status=404, headers=headers)

        _, lender_id, amount = row

        if action == "reject":
            # Just mark status as rejected (no money moved)
            cur.execute(f"UPDATE mora_loans SET status='rejected', repaid_at=NOW() WHERE id={ph}", (loan_id,))
            conn.commit()
            conn.close()
            return JsonResponse({"ok": True, "action": "rejected"}, json_dumps_params={"ensure_ascii": False}, headers=headers)

        # Accept: transfer money from lender to borrower
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (lender_id, chat_id))
        lender_bal = (cur.fetchone() or [0])[0]
        if lender_bal < amount:
            conn.close()
            return JsonResponse({"error": f"У кредитора недостаточно Моры ({lender_bal}/{amount} 🪙)"}, status=400, headers=headers)

        # Deduct from lender
        cur.execute(
            f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph} AND balance>={ph}",
            (amount, lender_id, chat_id, amount),
        )
        if cur.rowcount == 0:
            conn.close()
            return JsonResponse({"error": "Не удалось списать Мору с кредитора"}, status=400, headers=headers)

        # Add to borrower
        cur.execute(
            f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
            f"ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=user_mora.balance+excluded.balance",
            (uid, chat_id, amount),
        )

        # Mark loan as accepted
        cur.execute(f"UPDATE mora_loans SET status='accepted' WHERE id={ph}", (loan_id,))

        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_balance = (cur.fetchone() or [0])[0]
        conn.commit()
        conn.close()

        return JsonResponse({
            "ok": True,
            "action": "accepted",
            "loan_id": loan_id,
            "amount": amount,
            "new_balance": new_balance,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


# =============================================================================
# CASINO / КАЗИНО
# =============================================================================

@csrf_exempt
def miniapp_casino_coin(request):
    """POST /api/casino/coin {chat_id, amount} — 30% win x2, 70% lose."""
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
    amount = int(data.get("amount", 0))

    try:
        from config import COIN_MAX_BET
    except Exception:
        COIN_MAX_BET = 5000

    if amount <= 0:
        return JsonResponse({"error": "Укажи ставку > 0"}, status=400, headers=headers)
    if amount > COIN_MAX_BET:
        return JsonResponse({"error": f"Максимальная ставка: {COIN_MAX_BET} 🪙"}, status=400, headers=headers)

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        import random as _random
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Check balance
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        bal_row = cur.fetchone()
        balance = bal_row[0] if bal_row else 0
        if balance < amount:
            conn.close()
            return JsonResponse({"error": f"Недостаточно Моры. У тебя {balance} 🪙"}, status=400, headers=headers)

        # Deduct bet
        cur.execute(
            f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph} AND balance>={ph}",
            (amount, uid, chat_id, amount),
        )
        if cur.rowcount == 0:
            conn.close()
            return JsonResponse({"error": "Не удалось списать ставку"}, status=400, headers=headers)

        win = _random.random() < 0.30
        if win:
            prize = amount * 2
            cur.execute(
                f"UPDATE user_mora SET balance=balance+{ph} WHERE user_id={ph} AND chat_id={ph}",
                (prize, uid, chat_id),
            )
        else:
            # 1% of bet goes to treasury
            tax = max(1, int(amount * 0.01))
            cur.execute(
                f"INSERT INTO chat_treasury (chat_id, balance) VALUES ({ph},{ph}) "
                f"ON CONFLICT(chat_id) DO UPDATE SET balance=chat_treasury.balance+excluded.balance",
                (chat_id, tax),
            )

        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_balance = (cur.fetchone() or [0])[0]
        conn.commit()
        conn.close()

        return JsonResponse({
            "ok": True,
            "win": win,
            "bet": amount,
            "prize": amount * 2 if win else 0,
            "new_balance": new_balance,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        from config import LOTTERY_TICKET_PRICE
    except Exception:
        LOTTERY_TICKET_PRICE = 10

    from datetime import date as _date

    def _week_key() -> str:
        today = _date.today()
        iso = today.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    week = _week_key()

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        if request.method == "GET":
            chat_id_str = request.GET.get("chat_id", "0")
            chat_id = int(chat_id_str)
            cur.execute(
                f"SELECT tickets FROM casino_lottery WHERE user_id={ph} AND chat_id={ph} AND week_key={ph}",
                (uid, chat_id, week),
            )
            row = cur.fetchone()
            tickets = row[0] if row else 0
            conn.close()
            return JsonResponse({
                "ok": True,
                "tickets": tickets,
                "week": week,
                "ticket_price": LOTTERY_TICKET_PRICE,
            }, json_dumps_params={"ensure_ascii": False}, headers=headers)

        elif request.method == "POST":
            try:
                data = json.loads(request.body)
            except Exception:
                conn.close()
                return JsonResponse({"error": "bad JSON"}, status=400, headers=headers)
            chat_id = int(data.get("chat_id", 0))

            # Check balance
            cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            bal_row = cur.fetchone()
            balance = bal_row[0] if bal_row else 0
            if balance < LOTTERY_TICKET_PRICE:
                conn.close()
                return JsonResponse({"error": f"Нужно {LOTTERY_TICKET_PRICE} 🪙"}, status=400, headers=headers)

            cur.execute(
                f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph} AND balance>={ph}",
                (LOTTERY_TICKET_PRICE, uid, chat_id, LOTTERY_TICKET_PRICE),
            )
            if cur.rowcount == 0:
                conn.close()
                return JsonResponse({"error": "Не удалось списать Мору"}, status=400, headers=headers)

            # Upsert ticket
            if db_type == "pg":
                cur.execute(
                    "INSERT INTO casino_lottery (chat_id, user_id, week_key, tickets) VALUES (%s,%s,%s,1) "
                    "ON CONFLICT(chat_id, user_id, week_key) DO UPDATE SET tickets=casino_lottery.tickets+1",
                    (chat_id, uid, week),
                )
            else:
                cur.execute(
                    "INSERT INTO casino_lottery (chat_id, user_id, week_key, tickets) VALUES (?,?,?,1) "
                    "ON CONFLICT(chat_id, user_id, week_key) DO UPDATE SET tickets=casino_lottery.tickets+1",
                    (chat_id, uid, week),
                )

            cur.execute(
                f"SELECT tickets FROM casino_lottery WHERE user_id={ph} AND chat_id={ph} AND week_key={ph}",
                (uid, chat_id, week),
            )
            tickets = (cur.fetchone() or [0])[0]
            cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            new_balance = (cur.fetchone() or [0])[0]
            conn.commit()
            conn.close()
            return JsonResponse({
                "ok": True,
                "tickets": tickets,
                "ticket_price": LOTTERY_TICKET_PRICE,
                "new_balance": new_balance,
            }, json_dumps_params={"ensure_ascii": False}, headers=headers)

        conn.close()
        return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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
        from config import EXPEDITION_OPTIONS
    except Exception:
        EXPEDITION_OPTIONS = {
            "short":  {"hours": 2, "cost": 0,  "reward_min": 10,  "reward_max": 15,  "label": "2ч (бесплатно)"},
            "medium": {"hours": 4, "cost": 5,  "reward_min": 35,  "reward_max": 40,  "label": "4ч (5 🪙)"},
            "long":   {"hours": 8, "cost": 10, "reward_min": 55,  "reward_max": 60,  "label": "8ч (10 🪙)"},
        }

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Pet info
        cur.execute(
            f"SELECT pet_type, name, COALESCE(fatigue,0) FROM pets WHERE user_id={ph} AND chat_id={ph}",
            (uid, chat_id),
        )
        pet_row = cur.fetchone()
        pet = None
        if pet_row:
            pet = {"type": pet_row[0], "name": pet_row[1], "fatigue": pet_row[2]}
            # Check if currently walking
            walk_end = pet_row[3] if len(pet_row) > 3 else None
            if walk_end:
                try:
                    we = walk_end if hasattr(walk_end, 'tzinfo') else datetime.fromisoformat(str(walk_end).replace('Z','+00:00'))
                    if we.tzinfo is None:
                        we = we.replace(tzinfo=timezone.utc)
                    now_utc = datetime.now(timezone.utc)
                    if we > now_utc:
                        secs = (we - now_utc).total_seconds()
                        pet["walking"] = True
                        pet["walk_mins_left"] = int(secs / 60) + 1
                except Exception:
                    pass

        # Active expedition
        cur.execute(
            f"SELECT started_at, duration_h, reward_min, reward_max FROM pet_expeditions "
            f"WHERE user_id={ph} AND chat_id={ph} AND finished=0",
            (uid, chat_id),
        )
        exp_row = cur.fetchone()
        expedition = None
        if exp_row:
            started_at, duration_h, reward_min, reward_max = exp_row
            if isinstance(started_at, str):
                started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            end_at = started_at + __import__("datetime").timedelta(hours=duration_h)
            done = now >= end_at
            secs_left = max(0, (end_at - now).total_seconds())
            h_left = int(secs_left // 3600)
            m_left = int((secs_left % 3600) // 60)
            expedition = {
                "started_at": started_at.isoformat(),
                "duration_h": duration_h,
                "reward_min": reward_min,
                "reward_max": reward_max,
                "done": done,
                "time_left_h": h_left,
                "time_left_m": m_left,
            }

        # Mora balance
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        bal_row = cur.fetchone()
        balance = bal_row[0] if bal_row else 0

        conn.close()
        return JsonResponse({
            "ok": True,
            "pet": pet,
            "expedition": expedition,
            "balance": balance,
            "options": {k: {"hours": v["hours"], "cost": v["cost"], "reward_min": v["reward_min"],
                            "reward_max": v["reward_max"], "label": v["label"]}
                        for k, v in EXPEDITION_OPTIONS.items()},
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    try:
        from config import EXPEDITION_OPTIONS
    except Exception:
        EXPEDITION_OPTIONS = {
            "short":  {"hours": 2, "cost": 0,  "reward_min": 10,  "reward_max": 15,  "label": "2ч (бесплатно)"},
            "medium": {"hours": 4, "cost": 5,  "reward_min": 35,  "reward_max": 40,  "label": "4ч (5 🪙)"},
            "long":   {"hours": 8, "cost": 10, "reward_min": 55,  "reward_max": 60,  "label": "8ч (10 🪙)"},
        }

    opt = EXPEDITION_OPTIONS.get(option_key)
    if not opt:
        return JsonResponse({"error": "Неизвестный тип экспедиции"}, status=400, headers=headers)

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Pet must exist
        cur.execute(f"SELECT pet_type, name, COALESCE(fatigue,0), walk_end_at FROM pets WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        pet_row = cur.fetchone()
        if not pet_row:
            conn.close()
            return JsonResponse({"error": "У тебя нет питомца"}, status=400, headers=headers)
        pet_type, pet_name, fatigue, walk_end_at = pet_row

        if fatigue >= 100:
            conn.close()
            return JsonResponse({"error": "Питомец слишком устал (100/100). Покорми его!"}, status=400, headers=headers)

        # Check pet is not currently walking
        if walk_end_at:
            try:
                walk_end_dt = walk_end_at if hasattr(walk_end_at, 'tzinfo') else datetime.fromisoformat(str(walk_end_at).replace('Z', '+00:00'))
                if walk_end_dt.tzinfo is None:
                    walk_end_dt = walk_end_dt.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                if walk_end_dt > now_utc:
                    mins = int((walk_end_dt - now_utc).total_seconds() / 60) + 1
                    conn.close()
                    return JsonResponse({"error": f"Питомец ещё на прогулке! Осталось {mins} мин."}, status=400, headers=headers)
            except Exception:
                pass

        # Check no active expedition
        cur.execute(f"SELECT 1 FROM pet_expeditions WHERE user_id={ph} AND chat_id={ph} AND finished=0", (uid, chat_id))
        if cur.fetchone():
            conn.close()
            return JsonResponse({"error": "Питомец уже в экспедиции"}, status=400, headers=headers)

        # Check cost
        cost = opt["cost"]
        if cost > 0:
            cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            bal_row = cur.fetchone()
            balance = bal_row[0] if bal_row else 0
            if balance < cost:
                conn.close()
                return JsonResponse({"error": f"Недостаточно Моры. Нужно {cost} 🪙"}, status=400, headers=headers)
            cur.execute(
                f"UPDATE user_mora SET balance=balance-{ph} WHERE user_id={ph} AND chat_id={ph} AND balance>={ph}",
                (cost, uid, chat_id, cost),
            )
            if cur.rowcount == 0:
                conn.close()
                return JsonResponse({"error": "Не удалось списать Мору"}, status=400, headers=headers)

        now_iso = datetime.now(timezone.utc).isoformat()
        # Insert/replace expedition (UPSERT)
        if db_type == "pg":
            cur.execute(
                "INSERT INTO pet_expeditions (user_id, chat_id, started_at, duration_h, reward_min, reward_max, finished) "
                "VALUES (%s,%s,%s,%s,%s,%s,0) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET started_at=excluded.started_at, "
                "duration_h=excluded.duration_h, reward_min=excluded.reward_min, "
                "reward_max=excluded.reward_max, finished=0",
                (uid, chat_id, now_iso, opt["hours"], opt["reward_min"], opt["reward_max"]),
            )
        else:
            cur.execute(
                "INSERT INTO pet_expeditions (user_id, chat_id, started_at, duration_h, reward_min, reward_max, finished) "
                "VALUES (?,?,?,?,?,?,0) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET started_at=excluded.started_at, "
                "duration_h=excluded.duration_h, reward_min=excluded.reward_min, "
                "reward_max=excluded.reward_max, finished=0",
                (uid, chat_id, now_iso, opt["hours"], opt["reward_min"], opt["reward_max"]),
            )

        # Add +20 fatigue
        cur.execute(
            f"UPDATE pets SET fatigue=LEAST(100, COALESCE(fatigue,0)+20) WHERE user_id={ph} AND chat_id={ph}",
            (uid, chat_id),
        )

        conn.commit()
        conn.close()
        return JsonResponse({
            "ok": True,
            "option": option_key,
            "duration_h": opt["hours"],
            "reward_min": opt["reward_min"],
            "reward_max": opt["reward_max"],
            "cost": cost,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

    try:
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        import random as _random
        import datetime as _dt_mod
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        cur.execute(
            f"SELECT started_at, duration_h, reward_min, reward_max "
            f"FROM pet_expeditions WHERE user_id={ph} AND chat_id={ph} AND finished=0",
            (uid, chat_id),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return JsonResponse({"error": "Нет активной экспедиции"}, status=404, headers=headers)

        started_at, duration_h, reward_min, reward_max = row
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        end_at = started_at + _dt_mod.timedelta(hours=duration_h)
        if now < end_at:
            secs_left = int((end_at - now).total_seconds())
            h_left = secs_left // 3600
            m_left = (secs_left % 3600) // 60
            conn.close()
            return JsonResponse({"error": f"Экспедиция ещё не завершена. Осталось: {h_left}ч {m_left}мин"}, status=400, headers=headers)

        reward = _random.randint(reward_min, reward_max)

        # Mark finished
        cur.execute(f"UPDATE pet_expeditions SET finished=1 WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))

        # Add mora
        cur.execute(
            f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
            f"ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=user_mora.balance+excluded.balance",
            (uid, chat_id, reward),
        )
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_balance = (cur.fetchone() or [0])[0]
        conn.commit()
        conn.close()

        return JsonResponse({
            "ok": True,
            "reward": reward,
            "new_balance": new_balance,
        }, json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)

