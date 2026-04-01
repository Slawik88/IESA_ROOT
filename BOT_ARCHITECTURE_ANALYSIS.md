# PredvestnikBot — Full Architecture Analysis for AI Review
## Purpose: Bug hunt — mora accrual commands & inventory issues

---

## 1. System Architecture (Two Processes, One DB)

```
┌─────────────────────────────────────────────────────────────────┐
│                     Production Server                           │
│                                                                 │
│  ┌──────────────────────────────┐  ┌───────────────────────┐   │
│  │   Django / Daphne ASGI       │  │   PredvestnikBot      │   │
│  │   Port 8080                  │  │   (aiogram 3, aiohttp)│   │
│  │                              │  │   Port 8081           │   │
│  │  IESA_ROOT/IESA_ROOT/        │  │                       │   │
│  │   miniapp_views.py  ←──┐     │  │  database/db.py       │   │
│  │   urls.py               │    │  │  database/postgres.py │   │
│  │                         │    │  │  handlers/            │   │
│  │  Auth: psycopg2 (sync)  │    │  │  api/                 │   │
│  │  Economy: async_to_sync │    │  │                       │   │
│  └──────────────────────────────┘  └───────────────────────┘   │
│              │                                │                  │
│              └──────────┬────────────────────┘                  │
│                         │                                        │
│                  ┌──────▼──────┐                                │
│                  │  PostgreSQL  │                                │
│                  │  (asyncpg   │                                │
│                  │  + psycopg2)│                                │
│                  └─────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

**Key fact**: Django is NOT a separate service — it lives in the same Heroku/DO dyno as the bot.
The bot is started as a background PID from Django's startup script (`start.sh`).

---

## 2. Database Connection — Two Parallel Approaches

### 2a. Bot side (asyncpg with compat layer)
File: `PredvestnikBot/database/postgres.py`

```python
# postgres.py has a compatibility shim that converts ? → $1, $2
def _convert_placeholders(sql, params):
    # Replaces every '?' with '$1', '$2', etc.
    # Also converts ISO datetime strings to datetime objects for asyncpg
    counter = [0]
    def replacer(m):
        counter[0] += 1
        return f'${counter[0]}'
    converted = re.sub(r'\?', replacer, sql)
    return converted, params_list
```

ALL code in `database/db.py` and `api/*.py` uses `?` placeholders.
The compat layer auto-converts them to asyncpg `$N` style.
**This is correct and works.**

Per-loop pool management: each asyncio event loop (bot loop, Django ASGI loop) gets its own `asyncpg.Pool`. So Django's `async_to_sync` calls create a SEPARATE pool from the bot's pool. Both connect to the same PostgreSQL database.

### 2b. Django side (psycopg2, synchronous)
File: `IESA_ROOT/IESA_ROOT/miniapp_views.py`

```python
def _get_bot_db_connection():
    url = _BOT_DB_URL  # env: PREDVESTNIK_DATABASE_URL
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        import psycopg2
        return psycopg2.connect(url), "pg"
    # FALLBACK: reads local bot.db SQLite file if env var not set!
    db_path = _BOT_DIR / "bot.db"
    return sqlite3.connect(str(db_path)), "sqlite"
```

Used by: `miniapp_user_data`, `miniapp_inventory`, `miniapp_inventory_sell_junk`, `miniapp_leaderboard`, etc.

**⚠️ RISK**: If `PREDVESTNIK_DATABASE_URL` env var is not set in the Django process, all these endpoints silently read from an EMPTY local bot.db SQLite file instead of PostgreSQL.

---

## 3. Mora (Currency) System

### 3a. Mora is GLOBAL, not per-chat

```sql
-- GLOBAL balance (one per user, all chats share it)
TABLE users (
    user_id    BIGINT PRIMARY KEY,
    balance    BIGINT DEFAULT 0,   -- ← THE ACTUAL MORA BALANCE
    total_earned BIGINT DEFAULT 0,
    ...
)

-- PER-CHAT metadata (streak, VIP, XP boost, etc.)
TABLE user_mora (
    user_id    BIGINT,
    chat_id    BIGINT,
    mora_public  INT DEFAULT 1,
    vip          INT DEFAULT 0,
    vip_expires_at TIMESTAMPTZ,
    xp_boost_until TIMESTAMPTZ,
    streak_days  INT DEFAULT 0,
    last_daily   TEXT,
    ...
    PRIMARY KEY (user_id, chat_id)
)
```

**Critical design fact**: `users.balance` is a SINGLE number per user across ALL chats.
When a user earns mora in Chat A, their balance also goes up in Chat B.
`user_mora` row contains only per-chat decorations (streak, theme, VIP) — NOT the balance.

### 3b. `add_mora` — the core function

File: `PredvestnikBot/database/db.py` line ~3313

```python
async def add_mora(user_id: int, chat_id: int, amount: int) -> int:
    if chat_id and is_isolated_chat(chat_id):
        # ⚠️ SILENT NO-OP — still returns "current balance" as if it succeeded
        _log.debug("add_mora BLOCKED uid=%s chat=%s amount=%s (isolated)", ...)
        async with postgres_connect() as db:
            async with db.execute("SELECT COALESCE(balance,0) FROM users WHERE user_id=?", (user_id,)) as c:
                row = await c.fetchone()
                return row[0] if row else 0  # returns OLD balance, NOT new balance

    # Happy path
    async with postgres_connect() as db:
        await db.execute(
            """UPDATE users SET
                   balance      = GREATEST(0, COALESCE(balance, 0) + ?),
                   total_earned = COALESCE(total_earned, 0) + CASE WHEN ? > 0 THEN ? ELSE 0 END
               WHERE user_id = ?""",
            (amount, amount, amount, user_id),
        )
        await db.commit()
        # ... returns new balance
```

### 3c. `is_isolated_chat` — in-memory, NOT shared with Django

```python
_admin_groups: set[int] = set()   # loaded into bot's memory at startup
_test_chats:   set[int] = set()   # loaded at startup

def is_isolated_chat(chat_id: int) -> bool:
    return chat_id in _admin_groups or chat_id in _test_chats
```

**⚠️ CRITICAL BUG SOURCE**: When Django imports `database.db` (via `async_to_sync`), 
`_admin_groups` and `_test_chats` are EMPTY (they were never populated on the Django side).
`load_admin_groups()` is called only during bot startup, NOT during Django startup.

**Consequence for Django context**: `is_isolated_chat()` always returns `False` → 
Django-side `add_mora` calls always succeed (isolation check is bypassed).

**Consequence for Bot context**: `is_isolated_chat()` works correctly — blocks economy in admin/test chats.

---

## 4. ⚠️ BUG: "Mora Commands Return 200 but Don't Work"

### Bot commands for mora (in `handlers/owner.py`)

```
бот выдать [amount] @user [reason]   → cmd_emit_mora  → add_mora(uid, message.chat.id, amount)
бот сетюзер @user мора +200          → cmd_setuser    → add_mora(uid, message.chat.id, delta)
```

### Why it fails silently:

**Scenario**: Admin types `бот выдать 500 @user` in the ADMIN GROUP chat.
1. `cmd_emit_mora` runs → calls `add_mora(uid, message.chat.id=ADMIN_CHAT, 500)`
2. `is_isolated_chat(ADMIN_CHAT)` returns `True` (bot memory has admin groups loaded)
3. `add_mora` silently does NOTHING, returns the CURRENT balance (e.g., 1000)
4. The handler replies: `✅ +500 🪙 → 1000 🪙` ← **shows OLD balance as if it's the new one**
5. Admin thinks it worked (balance "went to 1000"). In reality, nothing changed.

**The correct fix**: Admin must run mora commands from a MAIN CHAT, not from the admin group.
Or: the bot should detect `is_isolated_chat` before showing the success message and report the block.

### Mini App API mora endpoints

| Endpoint | Django view | Calls | DB method |
|---|---|---|---|
| `POST /api/dev/add_mora` | `miniapp_dev_add_mora` | `api.admin.admin_add_mora()` | Direct `UPDATE users SET balance=...` |
| `POST /api/transfer` | `miniapp_transfer` | `api.economy.transfer_mora()` | Direct atomic SQL |
| `GET /api/wallet/history` | `miniapp_wallet_history` | `api.economy.wallet_history()` | `SELECT FROM wallet_ledger` |

`admin_add_mora` in `api/admin.py` does NOT check `is_isolated_chat` — it updates balance unconditionally.
So `/api/dev/add_mora` **always** works (bypasses isolation). Returns `{"ok": True, "new_balance": N}`.

**⚠️ If the endpoint returns 200 but balance seemingly doesn't change**, possible causes:
1. Frontend is reading balance from a stale cache and not re-fetching after the POST
2. `PREDVESTNIK_DATABASE_URL` is not set → Django reads SQLite fallback → update goes to wrong DB
3. `target_id` in the POST body is 0 or wrong (WHERE clause doesn't match any row)

---

## 5. ⚠️ BUG: Inventory Inconsistency (Global vs Per-Chat)

### The table

```sql
TABLE gacha_inventory (
    id        BIGINT PRIMARY KEY,
    user_id   BIGINT NOT NULL,
    chat_id   BIGINT NOT NULL,   -- ← items are chat-scoped in DB
    item_key  TEXT,
    rarity    TEXT,
    equipped  INT DEFAULT 0,
    slot      TEXT,              -- 'weapon', 'armor', 'artifact', or NULL (flair)
    ...
)
```

### GET /api/inventory (miniapp_views.py line 1864)

```python
cur.execute(
    f"SELECT id, item_key, ... FROM gacha_inventory WHERE user_id={ph} ORDER BY id DESC",
    (uid,),   # ← NO chat_id filter — shows items from ALL chats
)
```

### GET /api/user_data (miniapp_views.py line 156+)

```python
cur.execute(
    f"SELECT item_name, rarity, equipped FROM gacha_inventory "
    f"WHERE user_id={ph} AND chat_id={ph} LIMIT 20",
    (uid, chat_id),   # ← filtered by current chat
)
```

**The inconsistency**:
- `/api/inventory` returns items across ALL chats (global view) — no chat_id filter
- `/api/user_data` returns only items from the CURRENT chat (chat-scoped)
- `user_rpg_stats` (equipped slots reference) is stored per `(user_id, chat_id)` — so equipped state is per-chat
- But `/api/inventory` shows equipment from ALL chats, while equipping uses one specific chat's `user_rpg_stats`

**Result**: User might see items from Chat A while in Chat B's context, equipped state may look wrong.

### Fix needed

`/api/inventory` query should add `AND chat_id={ph}` with the `chat_id` from request params, 
or the endpoint needs to accept and validate a `chat_id` parameter.

---

## 6. Transfer System (`api/economy.py`)

```python
async def transfer_mora(from_uid, to_uid, chat_id, amount, cover_vat=True):
    # Progressive tax: 3% (≤1000), 7% (≤5000), 8% (>5000)
    # Max transfer: MORA_TRANSFER_MAX (default 5000 if config missing)
    
    # Atomic: all three ops in one transaction
    # 1. Deduct from_uid (with balance check): UPDATE users SET balance = balance - deduct WHERE balance >= deduct
    # 2. Credit to_uid
    # 3. Tax → chat_treasury
    
    if cursor.rowcount == 0:
        raise ValueError("Недостаточно Моры. Нужно X 🪙")
```

**⚠️ RISK**: `cursor.rowcount` — the compat layer must correctly expose the number of affected rows.
From `postgres.py`, the `_ExecuteContext` returns an object wrapping asyncpg execute result.
Must verify that `cursor.rowcount` (or `.rowcount` attribute) is correctly populated.

**⚠️ RISK**: `chat_treasury` and `treasury_log` tables must exist. If they don't, the INSERT fails and the entire transaction rolls back (including the deduction), causing a 500 that looks like "mora transfer failed" but the rollback means no money was lost.

---

## 7. Relevant DB Tables Quick Reference

| Table | Key | Purpose |
|---|---|---|
| `users` | `user_id PK` | Global: `balance`, `total_earned`, `full_name` |
| `user_mora` | `(user_id, chat_id)` | Per-chat: streak, VIP, xp_boost, theme |
| `user_stats` | `(user_id, chat_id)` | Per-chat: XP, level, rank, messages, warns |
| `gacha_inventory` | `id PK` | Chat-scoped items: `user_id`, `chat_id`, `rarity`, `equipped` |
| `user_rpg_stats` | `(user_id, chat_id)` | Per-chat RPG stats + equipped slot references |
| `wallet_ledger` | `id` | Transaction log for `/api/wallet/history` |
| `chat_treasury` | `chat_id PK` | Treasury balance (tax from transfers) |
| `treasury_log` | `id` | Audit log for treasury |
| `admin_groups` | `chat_id PK` | Chats isolated from economy (bot memory cache) |
| `test_chats` | `chat_id PK` | Test chats isolated from economy |
| `marriages_global` | `user_id PK` | Global marriage (cross-chat): `user_id`, `partner_id`, `married_at` |
| `pets_global` | `user_id PK` | Global pet reference |

---

## 8. Auth Flow (Mini App)

```python
def _validate_init_data(init_data: str) -> int | None:
    # HMAC-SHA256(key=HMAC-SHA256("WebAppData", BOT_TOKEN), msg=sorted_data_check_string)
    # Returns user_id (int) if valid, else None

def _require_auth(request, headers) -> tuple[int, None] | tuple[None, JsonResponse]:
    # Used by ~90% of miniapp views
    # Falls back to ?user_id=N if BOT_TOKEN not set (dev mode)
```

All protected views call `_require_auth` at the top. Some views do their OWN auth
(like `miniapp_user_data`, `miniapp_checkin`) with duplicate code.

---

## 9. Django ↔ Bot DB Async Bridge

Most economy views use this pattern:

```python
from asgiref.sync import async_to_sync as _a2s
from api.economy import transfer_mora as _api_tr

result = _a2s(_api_tr)(uid, target_id, chat_id, amount)
```

`async_to_sync` creates a new event loop thread for each call.
The asyncpg pool is created fresh for that loop on first call (see `get_pg_pool()`).
This is thread-safe but adds ~5-10ms overhead per request.

**IMPORTANT**: The Bot's asyncpg pool (on the bot's event loop) and Django's asyncpg pool 
(on Django's ASGI loop) are COMPLETELY SEPARATE. They share the same PostgreSQL server.
Both correctly commit to/read from the same data.

---

## 10. Known Outstanding Issues Summary

| # | Issue | File | Severity |
|---|---|---|---|
| 1 | `add_mora` silently no-ops in isolated chats but returns "success" to the caller | `database/db.py:3320` | HIGH — causes confusing bot behavior |
| 2 | `miniapp_inventory` lacks `chat_id` filter — shows cross-chat items | `miniapp_views.py:1892` | MEDIUM — inventory display bug |
| 3 | `user_rpg_stats` equip references are per-chat but inventory is shown globally | `miniapp_views.py:1930+` | MEDIUM — equipped items might show wrong state |
| 4 | `_admin_groups` in-memory cache is EMPTY in Django context | `database/db.py:1597` | LOW (Django bypasses isolation anyway) |
| 5 | `PREDVESTNIK_DATABASE_URL` not set → all miniapp views read empty SQLite | `miniapp_views.py:102` | CRITICAL if env var missing |
| 6 | `transfer_mora` max is 5000 (hardcoded fallback) — may be too low | `miniapp_views.py`, `api/economy.py` | LOW |
| 7 | `chat_treasury` / `treasury_log` tables may not exist → transfer fails with 500 | `api/economy.py:103` | MEDIUM |
| 8 | `get_mora` in `db.py` returns `Row` dict — callers access as `mora["balance"]` — OK with asyncpg Records | `database/db.py:3268` | OK (works) |
| 9 | Season endpoints (`/api/season/*`) added in commit `163f06fd` call `db.py` season functions that may use `?` vs asyncpg | `miniapp_views.py:5340+` | MEDIUM — will fail when active season exists |

---

## 11. File Map (Most Relevant)

```
IESA_ROOT/
└── IESA_ROOT/
    ├── miniapp_views.py      # 5500+ lines, ALL miniapp API handlers
    │                          # Two DB access patterns: psycopg2 (direct) + async_to_sync
    └── urls.py               # All /api/* routes → miniapp_views functions

PredvestnikBot/
├── database/
│   ├── db.py                 # 7000+ lines, bot DB layer (? placeholders, asyncpg compat)
│   └── postgres.py           # asyncpg pool + aiosqlite compat shim (?→$N converter)
├── api/
│   ├── economy.py            # transfer_mora, wallet_history, log_wallet_tx
│   ├── admin.py              # admin_add_mora, admin_add_xp, member_update
│   ├── checkin.py            # daily check-in rewards
│   ├── loans.py              # mora loans
│   ├── bonds.py              # bond investments
│   └── gacha.py              # gacha roll logic
├── handlers/
│   ├── owner.py              # cmd_emit_mora, cmd_setuser (bot commands)
│   ├── economy.py            # trading, market commands
│   └── gacha.py              # /inventory command, gacha rolls
└── config.py                 # MORA_TRANSFER_MIN/MAX, prices, constants
```

---

## 12. Suggested Questions for the AI Reviewer

1. **Inventory bug**: Should `/api/inventory` filter by `chat_id`? If items are intentionally cross-chat (global inventory), then `user_rpg_stats` equip slots should also be global. Currently they're per-chat — this is the root inconsistency.

2. **Mora no-op**: When `add_mora` is called for an isolated chat and silently skips, the bot command handler prints the OLD balance as if it's "-→ new_balance". Should the handler check if balance actually changed, or should `add_mora` raise an exception instead of returning silently?

3. **Transfer max**: `MORA_TRANSFER_MAX` defaults to 5000 if `config.py` import fails. Is 5000 the intended hard limit? Large transfers are impossible without a code change.

4. **Season pass DB functions** (`get_active_season`, `get_season_rewards` in `db.py` lines 6540+): These functions were written for SQLite (use `?` placeholders consistently with the compat layer, so they should work). But do these functions exist in the current `db.py`? The Django season views call them via `async_to_sync`.

5. **Wallet ledger for daily mora**: `check_daily_mora` in `db.py` updates streak/last_daily but does NOT write to `wallet_ledger`. Only explicit calls to `log_wallet_tx` create ledger entries. Daily message mora rewards are invisible in the wallet history. Is this intentional?
