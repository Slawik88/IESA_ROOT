"""
api/admin.py — developer / CRM panel operations.

All functions are async; the mini app wraps them with async_to_sync.
Auth (developer-only check) is handled by the miniapp view layer.
"""
from datetime import datetime, timezone

_SUPPORTED_EVENTS = frozenset({"chest", "сундук", "дилижанс", "diligence"})

_GACHA_POOL = {
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


# ─── Internal helpers ─────────────────────────────────────────────────────────

async def _write_ledger(db, chat_id: int, user_id: int, direction: str, amount: int,
                        source: str, description: str = "", actor_id: int | None = None) -> None:
    """Insert one wallet_ledger row inside an open postgres_connect() context."""
    if amount <= 0:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO wallet_ledger "
        "(chat_id, user_id, direction, amount, source, description, actor_id, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (chat_id, user_id, direction, amount, source, description or "", actor_id, now_iso),
    )


# ─── Stats ────────────────────────────────────────────────────────────────────

async def get_stats() -> dict:
    """Return global bot stats: chats, total users, boss hits today."""
    from database.postgres import connect as postgres_connect

    async with postgres_connect() as db:
        async with db.execute(
            "SELECT cs.chat_id, cs.title, COUNT(DISTINCT s.user_id) AS member_count "
            "FROM chats cs LEFT JOIN user_stats s ON s.chat_id=cs.chat_id "
            "GROUP BY cs.chat_id, cs.title ORDER BY member_count DESC LIMIT 50"
        ) as c:
            chats = [
                {"chat_id": r[0], "title": r[1] or f"chat_{r[0]}", "members": r[2]}
                for r in await c.fetchall()
            ]
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            row = await c.fetchone()
        total_users = row[0] if row else 0

        async with db.execute(
            "SELECT COUNT(*) FROM boss_damage_log "
            "WHERE session_date::date >= CURRENT_DATE - INTERVAL '1 day'"
        ) as c:
            row = await c.fetchone()
        boss_hits_today = row[0] if row else 0

    return {"total_users": total_users, "boss_hits_today": boss_hits_today, "chats": chats}


# ─── Balance management ───────────────────────────────────────────────────────

async def set_balance(actor_id: int, target_id: int, chat_id: int, balance: int) -> dict:
    """Set a user's mora balance directly. Writes wallet_ledger entry for the delta."""
    from database.postgres import connect as postgres_connect

    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COALESCE(balance, 0) FROM user_mora WHERE user_id=? AND chat_id=?",
            (target_id, chat_id),
        ) as c:
            row = await c.fetchone()
        old_balance = row[0] if row else 0

        await db.execute(
            "INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,?) "
            "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=excluded.balance",
            (target_id, chat_id, balance),
        )
        delta = balance - old_balance
        if delta > 0:
            await _write_ledger(db, chat_id, target_id, "income", delta,
                                "admin_setbalance", "CRM: установлен баланс", actor_id)
        elif delta < 0:
            await _write_ledger(db, chat_id, target_id, "expense", abs(delta),
                                "admin_setbalance", "CRM: установлен баланс", actor_id)
        await db.commit()

    return {"ok": True, "target_id": target_id, "balance": balance}


async def admin_add_mora(actor_id: int, target_id: int, chat_id: int, amount: int) -> dict:
    """Add (positive) or subtract (negative) mora for a user. Writes ledger. Returns new balance."""
    from database.postgres import connect as postgres_connect

    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO user_mora (user_id, chat_id, balance) "
            "VALUES (?,?,GREATEST(0,?)) "
            "ON CONFLICT(user_id, chat_id) DO UPDATE SET "
            "balance=GREATEST(0, user_mora.balance + ?)",
            (target_id, chat_id, amount, amount),
        )
        async with db.execute(
            "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?",
            (target_id, chat_id),
        ) as c:
            row = await c.fetchone()
        new_bal = row[0] if row else 0

        if amount > 0:
            await _write_ledger(db, chat_id, target_id, "income", amount,
                                "admin_adjustment", "Админская корректировка баланса", actor_id)
        elif amount < 0:
            await _write_ledger(db, chat_id, target_id, "expense", abs(amount),
                                "admin_adjustment", "Админская корректировка баланса", actor_id)
        await db.commit()

    return {"ok": True, "target_id": target_id, "new_balance": new_bal}


# ─── XP management ────────────────────────────────────────────────────────────

async def admin_add_xp(actor_id: int, target_id: int, chat_id: int,
                       amount: int, set_mode: bool = False) -> dict:
    """Add or set XP for a user. Recalculates level. Returns {ok, target_id, xp, new_level}."""
    from database.db import level_for_xp
    from database.postgres import connect as postgres_connect

    async with postgres_connect() as db:
        if set_mode:
            new_xp = max(0, amount)
            new_level = level_for_xp(new_xp)
            await db.execute(
                "INSERT INTO user_stats (user_id, chat_id, xp, level) VALUES (?,?,?,?) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET xp=excluded.xp, level=excluded.level",
                (target_id, chat_id, new_xp, new_level),
            )
        else:
            await db.execute(
                "INSERT INTO user_stats (user_id, chat_id, xp, level) VALUES (?,?,?,1) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET "
                "xp=GREATEST(0, user_stats.xp + ?)",
                (target_id, chat_id, amount, amount),
            )
            async with db.execute(
                "SELECT xp, COALESCE(level, 1) FROM user_stats WHERE user_id=? AND chat_id=?",
                (target_id, chat_id),
            ) as c:
                row = await c.fetchone()
            new_xp = row[0] if row else 0
            new_level = level_for_xp(new_xp)
            await db.execute(
                "UPDATE user_stats SET level=? WHERE user_id=? AND chat_id=?",
                (new_level, target_id, chat_id),
            )
        await db.commit()

    return {"ok": True, "target_id": target_id, "xp": new_xp if set_mode else new_xp,
            "new_level": new_level}


# ─── CRM member update ────────────────────────────────────────────────────────

async def member_update(
    actor_id: int, target_id: int, chat_id: int,
    balance: int, xp: int, rank: str,
    *,
    msg_count: int | None = None,
    day_count: int | None = None,
    week_count: int | None = None,
    total_count: int | None = None,
    yesterday_count: int | None = None,
    last_week_count: int | None = None,
) -> dict:
    """CRM combined update: balance, xp/level, rank, message counts."""
    from database.db import level_for_xp
    from database.postgres import connect as postgres_connect

    new_level = level_for_xp(xp)

    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COALESCE(balance, 0) FROM user_mora WHERE user_id=? AND chat_id=?",
            (target_id, chat_id),
        ) as c:
            row = await c.fetchone()
        old_balance = row[0] if row else 0

        await db.execute(
            "INSERT INTO user_mora (user_id, chat_id, balance) VALUES (?,?,?) "
            "ON CONFLICT(user_id, chat_id) DO UPDATE SET balance=excluded.balance",
            (target_id, chat_id, balance),
        )
        await db.execute(
            "INSERT INTO user_stats (user_id, chat_id, xp, level, rank) VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id, chat_id) DO UPDATE SET "
            "xp=excluded.xp, level=excluded.level, rank=excluded.rank",
            (target_id, chat_id, xp, new_level, rank),
        )

        delta = balance - old_balance
        if delta > 0:
            await _write_ledger(db, chat_id, target_id, "income", delta,
                                "crm_editor", "CRM: правка участника", actor_id)
        elif delta < 0:
            await _write_ledger(db, chat_id, target_id, "expense", abs(delta),
                                "crm_editor", "CRM: правка участника", actor_id)

        if msg_count is not None:
            await db.execute(
                "UPDATE user_stats SET message_count=? WHERE user_id=? AND chat_id=?",
                (msg_count, target_id, chat_id),
            )

        cc_fields = (day_count, week_count, total_count, yesterday_count, last_week_count)
        if any(v is not None for v in cc_fields):
            await db.execute(
                "INSERT INTO cleanup_counts (chat_id, user_id, count, week_count, day_count) "
                "VALUES (?,?,0,0,0) ON CONFLICT(chat_id, user_id) DO NOTHING",
                (chat_id, target_id),
            )
            if day_count is not None:
                await db.execute(
                    "UPDATE cleanup_counts SET day_count=? WHERE user_id=? AND chat_id=?",
                    (day_count, target_id, chat_id),
                )
            if week_count is not None:
                await db.execute(
                    "UPDATE cleanup_counts SET week_count=? WHERE user_id=? AND chat_id=?",
                    (week_count, target_id, chat_id),
                )
            if total_count is not None:
                await db.execute(
                    "UPDATE cleanup_counts SET count=? WHERE user_id=? AND chat_id=?",
                    (total_count, target_id, chat_id),
                )
            if yesterday_count is not None:
                await db.execute(
                    "UPDATE cleanup_counts SET yesterday_count=? WHERE user_id=? AND chat_id=?",
                    (yesterday_count, target_id, chat_id),
                )
            if last_week_count is not None:
                await db.execute(
                    "UPDATE cleanup_counts SET last_week_count=? WHERE user_id=? AND chat_id=?",
                    (last_week_count, target_id, chat_id),
                )

        await db.commit()

    return {
        "ok": True, "target_id": target_id,
        "balance": balance, "xp": xp, "level": new_level, "rank": rank,
    }


# ─── Salary ───────────────────────────────────────────────────────────────────

async def give_salary(actor_id: int, target_id: int, chat_id: int,
                      days: int, amount: int, reason: str = "") -> dict:
    """Grant salary mora to a user. Returns {ok, target_id, target_name, days, amount, new_balance}."""
    from database.postgres import connect as postgres_connect

    async with postgres_connect() as db:
        async with db.execute(
            "SELECT COALESCE(full_name, '') FROM users WHERE user_id=?", (target_id,)
        ) as c:
            row = await c.fetchone()
        target_name = (row[0] if row else "") or f"Игрок {target_id}"

        await db.execute(
            "INSERT INTO user_mora (user_id, chat_id, balance, total_earned) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id, chat_id) DO UPDATE SET "
            "balance=user_mora.balance + excluded.balance, "
            "total_earned=user_mora.total_earned + excluded.total_earned",
            (target_id, chat_id, amount, amount),
        )
        desc = f"Зарплата за {days} дн."
        if reason:
            desc = f"{desc}: {reason}"
        await _write_ledger(db, chat_id, target_id, "income", amount, "salary", desc, actor_id)

        async with db.execute(
            "SELECT COALESCE(balance, 0) FROM user_mora WHERE user_id=? AND chat_id=?",
            (target_id, chat_id),
        ) as c:
            row = await c.fetchone()
        new_balance = row[0] if row else 0
        await db.commit()

    return {
        "ok": True, "target_id": target_id, "target_name": target_name,
        "days": days, "amount": amount, "reason": reason, "new_balance": new_balance,
    }


# ─── Give item ────────────────────────────────────────────────────────────────

async def give_item(actor_id: int, target_id: int, chat_id: int,
                    item_name: str, rarity: str = "rare") -> dict:
    """Insert a gacha item directly into a user's inventory."""
    from database.postgres import connect as postgres_connect

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    item_key = item_name.lower().replace(" ", "_")

    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO gacha_inventory (user_id, chat_id, item_key, item_name, rarity, obtained_at) "
            "VALUES (?,?,?,?,?,?)",
            (target_id, chat_id, item_key, item_name, rarity, now),
        )
        await db.commit()

    return {"ok": True, "target_id": target_id, "item_name": item_name, "rarity": rarity}


# ─── User search ──────────────────────────────────────────────────────────────

async def search_users(chat_id: int, q: str = "") -> dict:
    """Search users in a chat by name or user_id. Returns {users}."""
    from database.postgres import connect as postgres_connect

    async with postgres_connect() as db:
        if q:
            like = f"%{q}%"
            async with db.execute(
                "SELECT s.user_id, u.full_name FROM user_stats s "
                "LEFT JOIN users u ON u.user_id=s.user_id "
                "WHERE s.chat_id=? AND (u.full_name LIKE ? OR CAST(s.user_id AS TEXT) LIKE ?) "
                "ORDER BY s.xp DESC LIMIT 20",
                (chat_id, like, like),
            ) as c:
                rows = await c.fetchall()
        else:
            async with db.execute(
                "SELECT s.user_id, u.full_name FROM user_stats s "
                "LEFT JOIN users u ON u.user_id=s.user_id "
                "WHERE s.chat_id=? ORDER BY s.xp DESC LIMIT 20",
                (chat_id,),
            ) as c:
                rows = await c.fetchall()

    return {"users": [{"user_id": r[0], "name": r[1] or f"user_{r[0]}"} for r in rows]}


# ─── Chat list ────────────────────────────────────────────────────────────────

async def get_chats() -> dict:
    """Return all group/channel chats with member counts."""
    from database.postgres import connect as postgres_connect

    async with postgres_connect() as db:
        async with db.execute(
            "SELECT c.chat_id, c.title, c.chat_type, COUNT(DISTINCT s.user_id) AS members "
            "FROM chats c LEFT JOIN user_stats s ON s.chat_id=c.chat_id "
            "WHERE c.chat_type IN ('group', 'supergroup', 'channel') "
            "GROUP BY c.chat_id, c.title, c.chat_type ORDER BY members DESC LIMIT 100"
        ) as c:
            rows = await c.fetchall()

    groups, admin_chats = [], []
    for r in rows:
        ctype = (r[2] or "").lower()
        obj = {"chat_id": r[0], "title": r[1] or f"chat_{r[0]}", "chat_type": ctype, "members": r[3]}
        if ctype in ("group", "supergroup"):
            groups.append(obj)
        else:
            admin_chats.append(obj)
    return {"groups": groups, "admin_chats": admin_chats}


# ─── Chat members ─────────────────────────────────────────────────────────────

async def get_chat_members(chat_id: int) -> dict:
    """Return members with full stats (xp, level, balance, message counts)."""
    from database.postgres import connect as postgres_connect

    async with postgres_connect() as db:
        async with db.execute(
            "SELECT s.user_id, u.full_name, COALESCE(s.rank,'user'), "
            "COALESCE(s.level,1), COALESCE(s.xp,0), COALESCE(m.balance,0), "
            "COALESCE(s.message_count,0), COALESCE(cc.count,0), "
            "COALESCE(cc.week_count,0), COALESCE(cc.day_count,0), "
            "COALESCE(cc.yesterday_count,0), COALESCE(cc.last_week_count,0) "
            "FROM user_stats s "
            "LEFT JOIN users u ON u.user_id=s.user_id "
            "LEFT JOIN user_mora m ON m.user_id=s.user_id AND m.chat_id=s.chat_id "
            "LEFT JOIN cleanup_counts cc ON cc.user_id=s.user_id AND cc.chat_id=s.chat_id "
            "WHERE s.chat_id=? ORDER BY s.xp DESC LIMIT 50",
            (chat_id,),
        ) as c:
            rows = await c.fetchall()

    members = [
        {
            "user_id": r[0], "name": r[1] or f"user_{r[0]}", "rank": r[2],
            "level": r[3], "xp": r[4], "balance": r[5],
            "message_count": r[6], "total_count": r[7],
            "week_count": r[8], "day_count": r[9],
            "yesterday_count": r[10], "last_week_count": r[11],
        }
        for r in rows
    ]
    return {"members": members}


# ─── Banlist ──────────────────────────────────────────────────────────────────

async def get_banlist() -> dict:
    """Return globally banned users."""
    from database.postgres import connect as postgres_connect

    async with postgres_connect() as db:
        async with db.execute(
            "SELECT bl.user_id, u.full_name, bl.reason, bl.added_at "
            "FROM user_banlist bl LEFT JOIN users u ON u.user_id=bl.user_id "
            "WHERE bl.chat_id=0 ORDER BY bl.added_at DESC LIMIT 100"
        ) as c:
            rows = await c.fetchall()

    banned = [
        {"user_id": r[0], "name": r[1] or f"user_{r[0]}", "reason": r[2] or "", "added_at": str(r[3])}
        for r in rows
    ]
    return {"banned": banned}


async def ban_user(actor_id: int, target_id: int, reason: str = "") -> dict:
    """Add a global ban entry. Idempotent (upserts reason)."""
    from database.postgres import connect as postgres_connect

    now_iso = datetime.now(timezone.utc).isoformat()
    async with postgres_connect() as db:
        await db.execute(
            "INSERT INTO user_banlist (chat_id, user_id, added_by, reason, added_at) "
            "VALUES (0,?,?,?,?) ON CONFLICT(chat_id, user_id) DO UPDATE SET reason=excluded.reason",
            (target_id, actor_id, reason[:200], now_iso),
        )
        await db.commit()
    return {"ok": True, "banned": target_id}


async def unban_user(target_id: int) -> dict:
    """Remove a global ban entry."""
    from database.postgres import connect as postgres_connect

    async with postgres_connect() as db:
        await db.execute(
            "DELETE FROM user_banlist WHERE chat_id=0 AND user_id=?", (target_id,)
        )
        await db.commit()
    return {"ok": True, "unbanned": target_id}


# ─── Logs ─────────────────────────────────────────────────────────────────────

async def get_logs(chat_id: int = 0) -> dict:
    """Return recent leave events and last server error lines."""
    import pathlib
    from database.postgres import connect as postgres_connect

    async with postgres_connect() as db:
        if chat_id:
            async with db.execute(
                "SELECT user_id, full_name, left_at FROM leave_log "
                "WHERE chat_id=? ORDER BY left_at DESC LIMIT 20",
                (chat_id,),
            ) as c:
                rows = await c.fetchall()
        else:
            async with db.execute(
                "SELECT user_id, full_name, left_at FROM leave_log ORDER BY left_at DESC LIMIT 20"
            ) as c:
                rows = await c.fetchall()

    leave_log = [{"user_id": r[0], "name": r[1] or f"user_{r[0]}", "left_at": str(r[2])} for r in rows]

    error_lines: list[str] = []
    base = pathlib.Path(__file__).resolve().parent.parent.parent
    for candidate in ("logs/bot.log", "logs/app.log", "server_output.txt"):
        lp = base / candidate
        if lp.exists() and lp.stat().st_size > 0:
            try:
                with open(lp, "r", encoding="utf-8", errors="replace") as f:
                    all_lines = f.readlines()
                error_lines = [
                    l.strip() for l in all_lines
                    if any(kw in l.lower() for kw in ("error", "exception", "traceback"))
                ][-5:]
                break
            except Exception:
                pass

    return {"leave_log": leave_log, "server_errors": error_lines}


# ─── Event trigger ────────────────────────────────────────────────────────────

async def trigger_event(actor_id: int, chat_id: int, event_type: str) -> dict:
    """Enqueue a bot event. The bot process polls dev_event_queue every ~30s."""
    if event_type not in _SUPPORTED_EVENTS:
        raise ValueError(
            f"Неизвестный тип события: '{event_type}'. Поддерживаются: сундук, дилижанс"
        )

    from database.postgres import connect as postgres_connect

    now_iso = datetime.now(timezone.utc).isoformat()
    async with postgres_connect() as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS dev_event_queue ("
            "id SERIAL PRIMARY KEY, "
            "chat_id BIGINT NOT NULL, event_type TEXT NOT NULL, "
            "requested_by BIGINT NOT NULL, created_at TEXT NOT NULL, processed INTEGER DEFAULT 0)"
        )
        await db.execute(
            "INSERT INTO dev_event_queue (chat_id, event_type, requested_by, created_at) "
            "VALUES (?,?,?,?)",
            (chat_id, event_type, actor_id, now_iso),
        )
        await db.commit()

    return {"ok": True, "event_type": event_type, "chat_id": chat_id,
            "note": "queued — bot will fire within ~30s"}


# ─── Items catalogue ──────────────────────────────────────────────────────────

def get_items() -> dict:
    """Return the static list of all available gacha items."""
    _rarity_emoji = {"junk": "🪨", "common": "💙", "rare": "💜", "legendary": "⭐"}
    items = []
    for rarity, pool in _GACHA_POOL.items():
        for key, name in pool:
            items.append({"key": key, "name": name, "rarity": rarity,
                          "rarity_emoji": _rarity_emoji.get(rarity, "")})
    return {"items": items}
