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
    POTIONS_CATALOG as _POTIONS_CATALOG,
    BOND_DEFAULTS as _BOND_DEFAULTS_SYNC,
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
                f"SELECT xp, COALESCE(level, 1), custom_title FROM user_stats WHERE user_id={ph} AND chat_id={ph}",
                (uid, effective_cid),
            )
        else:
            cur.execute(
                f"SELECT xp, COALESCE(level, 1), custom_title FROM user_stats WHERE user_id={ph} ORDER BY xp DESC LIMIT 1",
                (uid,),
            )
        xp_row = cur.fetchone()
        xp = xp_row[0] if xp_row else 0
        db_level = xp_row[1] if xp_row else 1
        custom_title = xp_row[2] if xp_row else None

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
        
        # ➕ НОВАЯ ФУНКЦИЯ: Получаем аватарку из Telegram
        avatar_url = get_telegram_avatar_url(uid)

        payload = {
            "uid": uid,
            "chat_id": chat_id,
            "name": full_name,
            "balance": balance,
            "xp": xp,
            "level": computed_level,
            "xp_max": xp_max,
            "vip": bool(vip),
            "avatar_url": avatar_url,  # ➕ Добавляем аватарку
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
        import asyncio
        reward_text = f"+{mora_reward} 🪙"
        if is_checkpoint:
            reward_text += f" | День {day_idx} - ЧЕКПОИНТ! ✨"
        if day_idx == 20:
            reward_text += " | Бесплатная гача! 🎁"
            
        asyncio.create_task(log_action_to_chat(
            uid, chat_id, 
            f"Забрал ежедневную награду (день {streak})", 
            reward_text
        ))
        
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
            f"COALESCE(m.balance,0) AS balance "
            f"FROM user_stats s "
            f"LEFT JOIN users u ON u.user_id=s.user_id "
            f"LEFT JOIN user_mora m ON m.user_id=s.user_id AND m.chat_id=s.chat_id "
            f"WHERE s.chat_id={ph} "
            f"ORDER BY s.xp DESC LIMIT 50",
            (chat_id,),
        )
        rows = cur.fetchall()
        conn.close()
        members = [
            {"user_id": r[0], "name": r[1] or f"user_{r[0]}", "rank": r[2],
             "level": r[3], "xp": r[4], "balance": r[5]}
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
                             "note": "queued — bot will fire within ~60s"}, headers=headers)
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
        import asyncio
        loot_text = ""
        for item in results:
            rarity_emoji = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}
            emoji = rarity_emoji.get(item["rarity"], "⚪")
            loot_text += f"\\n{emoji} {item['name']}"
        
        roll_type = f"{count}x крутка" if count > 1 else "Одиночная крутка"
        asyncio.create_task(log_action_to_chat(
            uid, chat_id,
            f"🎲 {roll_type} гачи (-{price} 🪙)",
            f"Выпало:{loot_text}"
        ))

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
    """POST /api/pet/walk — start a 3-hour pet walk (−30 fatigue)."""
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
            cur.execute(f"SELECT pet_type, name, COALESCE(fatigue,0), walk_end_at FROM pets WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            pet_row = cur.fetchone()
            walk_end_at = pet_row[3] if pet_row else None
        except Exception:
            cur.execute(f"SELECT pet_type, name, COALESCE(fatigue,0) FROM pets WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
            pet_row = cur.fetchone()
            walk_end_at = None
            if pet_row:
                pet_row = (pet_row[0], pet_row[1], pet_row[2], None)

        if not pet_row:
            conn.close()
            return JsonResponse({"error": "У тебя нет питомца"}, status=400, headers=headers)

        ptype, pname, fatigue = pet_row[0], pet_row[1], pet_row[2]

        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)

        # Check if already on walk
        if walk_end_at:
            try:
                end_dt = datetime.fromisoformat(str(walk_end_at).replace("Z", "+00:00"))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                diff = (end_dt - now).total_seconds()
                if diff > 0:
                    mins_left = int(diff / 60) + 1
                    conn.close()
                    return JsonResponse({"error": f"Питомец уже на прогулке. Осталось {mins_left} мин."}, status=429, headers=headers)
            except Exception:
                pass

        new_fatigue = max(0, fatigue - 30)
        walk_end_iso = (now + timedelta(hours=3)).isoformat()
        try:
            cur.execute(f"UPDATE pets SET fatigue={ph}, walk_end_at={ph} WHERE user_id={ph} AND chat_id={ph}", (new_fatigue, walk_end_iso, uid, chat_id))
        except Exception:
            cur.execute(f"UPDATE pets SET fatigue={ph} WHERE user_id={ph} AND chat_id={ph}", (new_fatigue, uid, chat_id))

        # Mora reward for walk owner and partner (if married)
        WALK_REWARD = 20
        upsert_mora_sql = (
            f"INSERT INTO user_mora (user_id, chat_id, balance) VALUES ({ph},{ph},{ph}) "
            f"ON CONFLICT (user_id, chat_id) DO UPDATE SET balance=user_mora.balance+EXCLUDED.balance"
            if db_type == "pg" else
            "INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,?) "
            "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=user_mora.balance+excluded.balance"
        )
        cur.execute(upsert_mora_sql, (uid, chat_id, WALK_REWARD))
        cur.execute(f"SELECT partner_id FROM marriages WHERE user_id={ph} AND chat_id={ph}", (uid, chat_id))
        partner_walk_row = cur.fetchone()
        if partner_walk_row:
            cur.execute(upsert_mora_sql, (partner_walk_row[0], chat_id, WALK_REWARD))

        conn.commit()
        conn.close()
        
        # ➕ ЛОГИРУЕМ ВЫГУЛ ПИТОМЦА В ЧАТ
        import asyncio
        emoji = {"cat": "🐱", "dog": "🐶"}.get(ptype, "🐾")
        partner_text = f" (+{WALK_REWARD} 🪙 партнёру)" if partner_walk_row else ""
        asyncio.create_task(log_action_to_chat(
            uid, chat_id,
            f"{emoji} Выгулял питомца {pname or 'Питомец'} (3 часа)",
            f"Усталость: -{30}, награда: +{WALK_REWARD} 🪙{partner_text}"
        ))
        
        return JsonResponse(
            {"ok": True, "fatigue": new_fatigue, "reduced": 30, "pet_emoji": emoji,
             "pet_name": pname or "Питомец", "walk_mins": 180, "reward": WALK_REWARD},
            json_dumps_params={"ensure_ascii": False}, headers=headers,
        )
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
        import asyncio
        emoji = {"cat": "🐱", "dog": "🐶"}.get(ptype, "🐾")
        wallet_text = f" из {wallet} кошелька" if wallet == "family" else ""
        asyncio.create_task(log_action_to_chat(
            uid, chat_id,
            f"{emoji} Покормил питомца {pname or 'Питомец'}",
            f"Еда: {food['name']} (-{food['price']} 🪙{wallet_text})\\nУсталость: -{food['fatigue']}"
        ))

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
        import asyncio
        
        success, message, new_level = asyncio.run(enhance_item(uid, chat_id, item_id))
        
        # ➕ ЛОГИРУЕМ ЗАТОЧКУ В ЧАТ
        if success:
            import asyncio
            asyncio.create_task(log_action_to_chat(
                uid, chat_id,
                f"✨ Заточил предмет до +{new_level}",
                message
            ))
        
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
        import asyncio
        
        success, message = asyncio.run(consume_potion(uid, chat_id, item_id))
        
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
        import asyncio
        
        sold_count, total_mora = asyncio.run(batch_sell_items(uid, chat_id, item_ids))
        
        # ➕ ЛОГИРУЕМ ПРОДАЖУ ВЕЩЕЙ В ЧАТ
        if sold_count > 0:
            import asyncio
            asyncio.create_task(log_action_to_chat(
                uid, chat_id,
                f"💰 Продал {sold_count} предметов",
                f"Получено: +{total_mora} 🪙"
            ))

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
        cur.execute(f"SELECT full_name FROM users WHERE id={ph}", (uid,))
        user_name = (cur.fetchone() or ["Player"])[0]
        cur.execute(f"SELECT full_name FROM users WHERE id={ph}", (partner_id,))
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
                "is_repeat", "is_completed", "session_date"
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
        import asyncio
        
        session = asyncio.run(create_couple_boss_session(user_a_id, user_b_id, chat_id, boss_level))
        
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
        
        # Get user's combat stats
        cur.execute(f"""SELECT 
                     COALESCE(SUM(
                         CASE WHEN gi.slot = 'weapon' OR gi.slot = 'armor' THEN 
                             CASE WHEN m.atk IS NOT NULL THEN m.atk + (gi.enhancement_level * COALESCE(m.atk, 0) * 0.1) 
                                  ELSE COALESCE(m.atk, 0) END
                         ELSE COALESCE(m.atk, 0) END
                     ), 0) as total_atk,
                     COALESCE(SUM(
                         CASE WHEN gi.slot = 'weapon' OR gi.slot = 'armor' THEN 
                             CASE WHEN m.def_val IS NOT NULL THEN m.def_val + (gi.enhancement_level * COALESCE(m.def_val, 0) * 0.1)
                                  ELSE COALESCE(m.def_val, 0) END
                         ELSE COALESCE(m.def_val, 0) END
                     ), 0) as total_def,
                     COALESCE(SUM(
                         CASE WHEN gi.slot = 'weapon' OR gi.slot = 'armor' THEN 
                             CASE WHEN m.hp IS NOT NULL THEN m.hp + (gi.enhancement_level * COALESCE(m.hp, 0) * 0.1)
                                  ELSE COALESCE(m.hp, 0) END
                         ELSE COALESCE(m.hp, 0) END
                     ), 0) as total_hp,
                     COALESCE(SUM(COALESCE(m.crit_rate, 0)), 0) as total_crit
                 FROM gacha_inventory gi
                 LEFT JOIN item_metadata m ON gi.item_key = m.item_key
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
        import asyncio
        import random
        
        # Base damage calculation
        base_damage = random.randint(int(user_stats["atk"] * 0.8), int(user_stats["atk"] * 1.2)) + 50
        
        result = asyncio.run(apply_couple_boss_damage(uid, session_data, base_damage, user_stats))
        
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
            rewards = asyncio.run(get_couple_boss_rewards(session_data))
            
            # Give rewards to both players
            try:
                conn, db_type = _get_bot_db_connection()
                cur = conn.cursor()
                ph = "%s" if db_type == "pg" else "?"
                
                # Add mora and XP to both users
                for player_id in [user_a_id, user_b_id]:
                    cur.execute(f"INSERT OR REPLACE INTO user_mora (user_id, chat_id, balance) VALUES ({ph}, {ph}, COALESCE((SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}), 0) + {ph})", 
                               (player_id, chat_id, player_id, chat_id, rewards["mora_each"]))
                    cur.execute(f"INSERT OR REPLACE INTO user_stats (user_id, chat_id, xp) VALUES ({ph}, {ph}, COALESCE((SELECT xp FROM user_stats WHERE user_id={ph} AND chat_id={ph}), 0) + {ph})", 
                               (player_id, chat_id, player_id, chat_id, rewards["xp_each"]))
                
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
    """Отправить сообщение о действии пользователя в чат."""
    if not _BOT_TOKEN:
        return
        
    try:
        import requests
        from database.db import get_user_name
        
        # Получаем имя пользователя
        user_name = await get_user_name(user_id) or f"Игрок {user_id}"
        
        # Формируем сообщение
        message = f"🎮 <b>{user_name}</b> выполнил: {action}"
        if details:
            message += f"\\n{details}"
        
        # Отправляем в чат
        url = f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=5)
        
    except Exception:
        pass  # Не критично если не получилось отправить


