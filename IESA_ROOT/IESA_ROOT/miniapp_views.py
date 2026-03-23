"""
Mini App views — serve the Telegram Mini App from Django.

Routes:
  GET /app          → index.html (Mini App entry point)
  GET /api/user_data  → JSON user profile from bot DB (auth via X-Telegram-Init-Data header)
"""

import hashlib
import hmac
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import parse_qsl

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt

# Path to the bot's web/index.html (relative to this file's location)
_BOT_DIR = Path(__file__).resolve().parent.parent.parent / "PredvestnikBot"
_INDEX_HTML = _BOT_DIR / "web" / "index.html"
_BOT_DB_URL = os.environ.get("PREDVESTNIK_DATABASE_URL", "")
_BOT_TOKEN = os.environ.get("PREDVESTNIK_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")


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
        "Access-Control-Allow-Headers": "X-Telegram-Init-Data, Content-Type",
        "Cache-Control": "no-cache",
    }


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
    init_data = request.headers.get("X-Telegram-Init-Data", "").strip()
    uid: int | None = None

    if init_data:
        uid = _validate_init_data(init_data)
        if uid is None:
            return JsonResponse({"error": "invalid or expired initData"}, status=401, headers=headers)
    else:
        # Dev fallback: plain user_id param (only allowed if bot token not set)
        if _BOT_TOKEN:
            return JsonResponse({"error": "X-Telegram-Init-Data header required"}, status=401, headers=headers)
        uid_str = request.GET.get("user_id", "")
        if not uid_str.isdigit():
            return JsonResponse({"error": "missing or invalid user_id"}, status=400, headers=headers)
        uid = int(uid_str)

    # ── Optional chat_id to scope data to a specific chat ────────────────
    chat_id_str = request.GET.get("chat_id", "").lstrip()
    specific_chat_id: int | None = None
    if chat_id_str.lstrip("-").isdigit():
        specific_chat_id = int(chat_id_str)

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

        # XP: scope to same chat when possible
        if specific_chat_id or chat_id:
            effective_cid = specific_chat_id or chat_id
            cur.execute(
                f"SELECT xp FROM user_stats WHERE user_id={ph} AND chat_id={ph}",
                (uid, effective_cid),
            )
        else:
            cur.execute(
                f"SELECT xp FROM user_stats WHERE user_id={ph} ORDER BY xp DESC LIMIT 1",
                (uid,),
            )
        xp_row = cur.fetchone()
        xp = xp_row[0] if xp_row else 0

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

        conn.close()

        payload = {
            "name": full_name,
            "balance": balance,
            "xp": xp,
            "vip": bool(vip),
            "active_frame": top_frame or "default",
            "active_theme": active_theme or "default",
            "bonds": bonds_data,
            "items": items,
            "pet": pet_info,
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
                f"WHERE s.chat_id={ph} ORDER BY s.message_count DESC LIMIT 10",
                (chat_id,),
            )
        elif lb_type == "boss":
            cur.execute(
                f"SELECT b.user_id, u.full_name, SUM(b.damage) "
                f"FROM boss_damage_log b LEFT JOIN users u ON u.user_id=b.user_id "
                f"WHERE b.chat_id={ph} GROUP BY b.user_id ORDER BY SUM(b.damage) DESC LIMIT 10",
                (chat_id,),
            )
        else:  # xp
            cur.execute(
                f"SELECT s.user_id, u.full_name, s.xp "
                f"FROM user_stats s LEFT JOIN users u ON u.user_id=s.user_id "
                f"WHERE s.chat_id={ph} ORDER BY s.xp DESC LIMIT 10",
                (chat_id,),
            )

        rows = cur.fetchall()
        conn.close()
        entries = [
            {"rank": i + 1, "user_id": r[0], "name": r[1] or f"user_{r[0]}", "score": r[2] or 0}
            for i, r in enumerate(rows)
        ]
        return JsonResponse({"type": lb_type, "entries": entries},
                            json_dumps_params={"ensure_ascii": False}, headers=headers)

    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return JsonResponse({"error": str(exc)}, status=500, headers=headers)


# ─── Daily check-in ───────────────────────────────────────────────────────────

_CHECKIN_REWARDS_SYNC = {
    1: 30, 2: 30, 3: 35, 4: 35, 5: 60,
    6: 40, 7: 40, 8: 45, 9: 45, 10: 80,
    11: 50, 12: 50, 13: 55, 14: 55, 15: 100,
    16: 60, 17: 60, 18: 70, 19: 70, 20: 150,
}
_CHECKIN_CHECKPOINTS_SYNC = {5, 10, 15, 20}


@csrf_exempt
def miniapp_checkin(request):
    """GET or POST /api/checkin — check-in status or perform check-in."""
    headers = _cors_headers()
    if request.method == "OPTIONS":
        return HttpResponse("", status=204, headers=headers)
    if request.method not in ("GET", "POST"):
        return JsonResponse({"error": "method not allowed"}, status=405, headers=headers)

    # Auth
    init_data = request.headers.get("X-Telegram-Init-Data", "").strip()
    uid: int | None = None
    if init_data:
        uid = _validate_init_data(init_data)
        if uid is None:
            return JsonResponse({"error": "invalid initData"}, status=401, headers=headers)
    else:
        if _BOT_TOKEN:
            return JsonResponse({"error": "X-Telegram-Init-Data required"}, status=401, headers=headers)
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

    init_data = request.headers.get("X-Telegram-Init-Data", "").strip()
    uid: int | None = None
    if init_data:
        uid = _validate_init_data(init_data)
        if uid is None:
            return JsonResponse({"error": "invalid initData"}, status=401, headers=headers)
    else:
        return JsonResponse({"error": "X-Telegram-Init-Data required"}, status=401, headers=headers)

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
