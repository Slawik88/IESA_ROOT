"""
Mini App views — serve the Telegram Mini App from Django.

Routes:
  GET /app          → index.html (Mini App entry point)
  GET /api/user_data  → JSON user profile from bot DB (auth via X-Telegram-Init-Data header)
"""

import hashlib
import hmac
import json
import math
import os
import sqlite3
import sys
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
    BOND_DEFAULTS as _BOND_DEFAULTS_SYNC,
    CHECKIN_REWARDS as _CHECKIN_REWARDS_SYNC,
    CHECKIN_CHECKPOINTS as _CHECKIN_CHECKPOINTS_SYNC,
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
                f"SELECT xp, COALESCE(level, 1) FROM user_stats WHERE user_id={ph} AND chat_id={ph}",
                (uid, effective_cid),
            )
        else:
            cur.execute(
                f"SELECT xp, COALESCE(level, 1) FROM user_stats WHERE user_id={ph} ORDER BY xp DESC LIMIT 1",
                (uid,),
            )
        xp_row = cur.fetchone()
        xp = xp_row[0] if xp_row else 0
        db_level = xp_row[1] if xp_row else 1

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
                f"SELECT pet_type, name, COALESCE(fatigue,0) FROM pets "
                f"WHERE user_id={ph} AND chat_id={ph}",
                (uid, chat_id),
            )
            pet_row = cur.fetchone()
            if pet_row:
                ptype, pname, pfatigue = pet_row
                emoji = {"cat": "🐱", "dog": "🐶"}.get(ptype, "🐾")
                pet_info = {
                    "type": ptype,
                    "name": pname or "безымянный",
                    "emoji": emoji,
                    "fatigue": pfatigue,
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
        has_partner = False
        partner_name = None
        if chat_id:
            cur.execute(
                f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}",
                (uid, chat_id),
            )
            m_row = cur.fetchone()
            has_partner = m_row is not None
            if has_partner:
                partner_id = m_row[0]
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
            "has_partner": has_partner,
            "partner_name": partner_name,
            "pity": pity,
            "streak": streak,
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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        from datetime import datetime as _dt, timezone as _tz
        today = _dt.now(_tz.utc).strftime("%Y-%m-%d")
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"

        # Anti-cheat: per-user daily damage cap
        cur.execute(
            f"SELECT COALESCE(SUM(damage),0) FROM boss_damage_log "
            f"WHERE user_id={ph} AND chat_id={ph} AND session_date={ph}",
            (uid, chat_id, today),
        )
        today_total = (cur.fetchone() or [0])[0]
        if today_total + damage > _BOSS_DAILY_DAMAGE_LIMIT:
            conn.close()
            return JsonResponse({"error": "daily damage limit reached", "limit": _BOSS_DAILY_DAMAGE_LIMIT},
                                status=429, headers=headers)

        cur.execute(
            f"INSERT INTO boss_damage_log (user_id, chat_id, damage, session_date) "
            f"VALUES ({ph},{ph},{ph},{ph})",
            (uid, chat_id, damage, today),
        )

        mora_reward = max(5, damage // 20)
        if db_type == "pg":
            cur.execute(
                f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
                f"ON CONFLICT (user_id, chat_id) DO UPDATE SET balance=user_mora.balance+EXCLUDED.balance",
                (uid, chat_id, mora_reward),
            )
        else:
            cur.execute(
                "INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,?) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=user_mora.balance+excluded.balance",
                (uid, chat_id, mora_reward),
            )

        cur.execute(
            f"SELECT COALESCE(SUM(damage),0) FROM boss_damage_log WHERE chat_id={ph} AND session_date={ph}",
            (chat_id, today),
        )
        total_chat_damage = (cur.fetchone() or [0])[0]
        conn.commit()
        conn.close()

        return JsonResponse({
            "ok": True,
            "damage": damage,
            "mora_earned": mora_reward,
            "boss_hp_remaining": max(0, _BOSS_MAX_HP - total_chat_damage),
        }, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
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
    except Exception:
        return JsonResponse({"error": "invalid JSON"}, status=400, headers=headers)

    if not target_id:
        return JsonResponse({"error": "target_id required"}, status=400, headers=headers)

    return JsonResponse(
        {"message": f"Напиши в Telegram: бот брак @user (или ID: {target_id})"},
        json_dumps_params={"ensure_ascii": False},
        headers=headers,
    )


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

        # Price history (last 30 points per bond)
        _BOND_KEYS = ["mondstadt", "inazuma"]
        history = {}
        for bk in _BOND_KEYS:
            cur.execute(
                f"SELECT price, recorded_at FROM bond_price_history "
                f"WHERE chat_id={ph} AND bond_key={ph} ORDER BY id DESC LIMIT 30",
                (chat_id, bk),
            )
            rows = cur.fetchall()
            rows.reverse()
            history[bk] = [{"price": r[0], "ts": r[1]} for r in rows]

        conn.close()

        bonds_out = []
        for bk in _BOND_KEYS:
            current_price = price_map.get(bk, {}).get("price", 100)
            holding = holdings.get(bk, {"amount": 0, "invested": 0})
            bname = _BOND_DEFAULTS_SYNC.get(bk, {}).get("name", bk)
            bonds_out.append({
                "key": bk,
                "name": bname,
                "price": current_price,
                "amount": holding["amount"],
                "invested": holding["invested"],
                "value": holding["amount"] * current_price,
                "history": history.get(bk, []),
            })

        return JsonResponse({"bonds": bonds_out},
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
    """POST /api/equip — equip a gacha item into a slot."""
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
        conn, db_type = _get_bot_db_connection()
    except Exception as exc:
        return JsonResponse({"error": f"DB: {exc}"}, status=503, headers=headers)

    try:
        cur = conn.cursor()
        ph = "%s" if db_type == "pg" else "?"
        col = {"weapon": "weapon_id", "armor": "armor_id", "artifact": "artifact_id"}[slot]

        # Verify item belongs to user
        cur.execute(
            f"SELECT id, item_name, slot FROM gacha_inventory WHERE id={ph} AND user_id={ph} AND chat_id={ph}",
            (item_id, uid, chat_id),
        )
        irow = cur.fetchone()
        if not irow:
            conn.close()
            return JsonResponse({"error": "item not found or not yours"}, status=404, headers=headers)
        item_name = irow[1]

        # Upsert user_rpg_stats with new equipped slot
        if db_type == "pg":
            cur.execute(
                f"INSERT INTO user_rpg_stats (user_id, chat_id, {col}) VALUES ({ph},{ph},{ph}) "
                f"ON CONFLICT (user_id, chat_id) DO UPDATE SET {col}=EXCLUDED.{col}",
                (uid, chat_id, item_id),
            )
        else:
            cur.execute(
                f"INSERT INTO user_rpg_stats (user_id, chat_id, {col}) VALUES (?,?,?) "
                f"ON CONFLICT(user_id, chat_id) DO UPDATE SET {col}=excluded.{col}",
                (uid, chat_id, item_id),
            )
        conn.commit()
        conn.close()
        return JsonResponse({"ok": True, "equipped": item_name, "slot": slot}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
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
        if db_type == "pg":
            cur.execute(
                f"INSERT INTO user_stats (user_id, chat_id, xp) VALUES ({ph},{ph},{ph}) "
                f"ON CONFLICT (user_id, chat_id) DO UPDATE SET xp=GREATEST(0, user_stats.xp + EXCLUDED.xp)",
                (target_id, chat_id, amount),
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
        if not cur.fetchone():
            conn.close()
            return JsonResponse({"error": "Нет союза"}, status=400, headers=headers)

        cur.execute(
            f"SELECT balance FROM family_wallet WHERE chat_id={ph} AND user_id={ph}",
            (chat_id, uid),
        )
        row = cur.fetchone()
        family_bal = row[0] if row else 0
        if family_bal < amount:
            conn.close()
            return JsonResponse({"error": f"Недостаточно в семейном ({family_bal})"}, status=400, headers=headers)

        # Deduct family
        cur.execute(
            f"UPDATE family_wallet SET balance=balance-{ph} WHERE chat_id={ph} AND user_id={ph}",
            (amount, chat_id, uid),
        )
        # Add to personal
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
                f"SELECT id, item_name, rarity, equipped, "
                f"COALESCE(atk,0), COALESCE(def_val,0), COALESCE(hp,0), COALESCE(crit_rate,0), slot "
                f"FROM gacha_inventory WHERE user_id={ph} AND chat_id={ph} ORDER BY id DESC",
                (uid, chat_id),
            )
            items = []
            for r in cur.fetchall():
                items.append({
                    "id": r[0], "name": r[1], "rarity": r[2], "equipped": bool(r[3]),
                    "atk": r[4], "def": r[5], "hp": r[6], "crit": r[7], "slot": r[8],
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
                f"SELECT id, equipped FROM gacha_inventory WHERE id={ph} AND user_id={ph} AND chat_id={ph}",
                (item_id, uid, chat_id),
            )
            irow = cur.fetchone()
            if not irow:
                conn.close()
                return JsonResponse({"error": "item not found"}, status=404, headers=headers)

            currently_equipped = bool(irow[1])
            if currently_equipped:
                # Unequip
                cur.execute(f"UPDATE gacha_inventory SET equipped=0 WHERE id={ph}", (item_id,))
            else:
                # Unequip previous, equip this one
                cur.execute(
                    f"UPDATE gacha_inventory SET equipped=0 WHERE user_id={ph} AND chat_id={ph} AND equipped=1",
                    (uid, chat_id),
                )
                cur.execute(f"UPDATE gacha_inventory SET equipped=1 WHERE id={ph}", (item_id,))
            conn.commit()
            conn.close()
            return JsonResponse({"ok": True, "equipped": not currently_equipped}, headers=headers)
        except Exception as exc:
            try:
                conn.close()
            except Exception:
                pass
            return JsonResponse({"error": str(exc)}, status=500, headers=headers)

    return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)

import random as _random

_GACHA_POOL = {
    "junk":      [("junk_stone","\U0001faa8 Камень Маслоу"),("junk_stick","\U0001fab5 Палка путника"),("junk_dust","💨 Пыль забвения"),("junk_bone","🦴 Кость хиличурла"),("junk_mushroom","🍄 Сомнительный гриб")],
    "common":    [("cmn_sword","⚔️ Тупой клинок"),("cmn_bow","🏹 Кривой лук"),("cmn_book","📕 Потрёпанный дневник"),("cmn_ring","💍 Дешёвое кольцо"),("cmn_shield","🛡 Ржавый щит")],
    "rare":      [("rare_crown","👑 Серебряная корона"),("rare_catalyst","🔮 Магический катализатор"),("rare_cape","🧣 Алый плащ"),("rare_gem","💎 Сапфир полуночи")],
    "legendary": [("lego_gnosis","✨ Гнозис Балладеера"),("lego_scepter","🏛 Скипетр Дендро Архонта"),("lego_pantalone","🎩 Маска Панталоне"),("lego_abyss","🌀 Корона Бездны"),("lego_fatui","⚡ Перст Предвестника")],
}


def _gacha_roll_one_sync(pity: int):
    roll = _random.random()
    if pity >= _GACHA_PITY_MAX - 1 or roll < 0.02:
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
            cur.execute(
                f"INSERT INTO gacha_inventory (user_id, chat_id, item_key, item_name, rarity, obtained_at) "
                f"VALUES ({ph},{ph},{ph},{ph},{ph},{now_expr})",
                (uid, chat_id, item_key, item_name, rarity),
            )
            pity = 0 if rarity == "legendary" else pity + 1
            results.append({"key": item_key, "name": item_name, "rarity": rarity})

        conn.commit()
        cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        new_bal = (cur.fetchone() or [0])[0]
        conn.close()

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


# ─── Pet Walk & Feed ──────────────────────────────────────────────────────────

@csrf_exempt
def miniapp_pet_walk(request):
    """POST /api/pet/walk — walk pet (−15 fatigue, 60min cooldown)."""
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

        try:
            cur.execute(f"SELECT pet_type, name, COALESCE(fatigue,0), last_walked FROM pets WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            pet_row = cur.fetchone()
            last_walked = pet_row[3] if pet_row else None
        except Exception:
            cur.execute(f"SELECT pet_type, name, COALESCE(fatigue,0) FROM pets WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            pet_row = cur.fetchone()
            last_walked = None
            if pet_row:
                pet_row = (pet_row[0], pet_row[1], pet_row[2], None)

        if not pet_row:
            conn.close()
            return JsonResponse({"error": "У тебя нет питомца"}, status=400, headers=headers)

        ptype, pname, fatigue = pet_row[0], pet_row[1], pet_row[2]

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        if last_walked:
            try:
                lw = datetime.fromisoformat(str(last_walked).replace("Z", "+00:00"))
                if lw.tzinfo is None:
                    lw = lw.replace(tzinfo=timezone.utc)
                diff = (now - lw).total_seconds()
                if diff < 3600:
                    mins_left = int((3600 - diff) / 60) + 1
                    conn.close()
                    return JsonResponse({"error": f"Можно гулять раз в час. Ещё {mins_left} мин."}, status=429, headers=headers)
            except Exception:
                pass

        new_fatigue = max(0, fatigue - 15)
        now_iso = now.isoformat()
        try:
            cur.execute(f"UPDATE pets SET fatigue={ph}, last_walked={ph} WHERE user_id={ph} AND chat_id={ph}", (new_fatigue, now_iso, uid, chat_id))
        except Exception:
            cur.execute(f"UPDATE pets SET fatigue={ph} WHERE user_id={ph} AND chat_id={ph}", (new_fatigue, uid, chat_id))

        conn.commit()
        conn.close()
        emoji = {"cat": "🐱", "dog": "🐶"}.get(ptype, "🐾")
        return JsonResponse({"ok": True, "fatigue": new_fatigue, "reduced": 15, "pet_emoji": emoji, "pet_name": pname or "Питомец"},
                            json_dumps_params={"ensure_ascii": False}, headers=headers)
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


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

        emoji = {"cat": "🐱", "dog": "🐶"}.get(ptype, "🐾")
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
        return JsonResponse({
            "balance": balance, "frames": frames, "cosmetics": cosmetics,
            "food": food_list, "has_vip": has_vip, "active_frame": active_frame or "default",
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
