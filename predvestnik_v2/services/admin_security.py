"""Защита админки: подтверждение самых опасных действий, лимиты частоты, журнал входов, завершение сессий, тревоги владельцу.

Владелец (создатель бота) от лимитов освобождён, но его необычные пачки действий тоже видны другим владельцам.
Журнал входов (адрес и устройство) пишется только для сотрудников и виден только создателю.
"""
from __future__ import annotations

import asyncio
import html
import time
from collections import defaultdict, deque
from decimal import Decimal, InvalidOperation

from loguru import logger

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS bot_admin_logins (
        id         BIGSERIAL PRIMARY KEY,
        user_id    BIGINT NOT NULL,
        ip         TEXT   NOT NULL DEFAULT '',
        ua         TEXT   NOT NULL DEFAULT '',
        via        TEXT   NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_bot_admin_logins_user ON bot_admin_logins (user_id, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_bot_admin_logins_time ON bot_admin_logins (created_at DESC)",
    # user_id = 0 — «все сотрудники»: сессии, начатые раньше revoked_at, перестают работать
    """CREATE TABLE IF NOT EXISTS bot_admin_session_revocations (
        user_id    BIGINT PRIMARY KEY,
        revoked_at TIMESTAMPTZ NOT NULL
    )""",
)

# ── Подтверждение опасных действий ──
CONFIRM_ACTIONS = ("global_ban", "rank", "skin_revoke")
BALANCE_CONFIRM = {"mora": Decimal(100_000), "diamonds": Decimal(100), "essence": Decimal(500), "zarniki": Decimal(100)}

# ── Лимиты частоты (на одного сотрудника, в памяти процесса) ──
SENSITIVE_ACTIONS = frozenset({"balance", "vip", "rank", "global_ban", "global_unban", "mark_grant", "mark_revoke", "block",
                               "unblock", "message", "dm", "skin_grant", "skin_revoke", "leave", "revoke_sessions", "promo_create", "promo_update", "promo_bulk", "broadcast"})
LIMITS = {"moderation": (60, 300), "sensitive": (60, 3600)}   # сколько действий за сколько секунд
_hits: dict[tuple[int, str], deque] = defaultdict(deque)

# ── Тревоги владельцу ──
BURST_ACTIONS = ("balance", "vip", "rank", "mark_grant", "mark_revoke", "global_ban", "block", "message", "leave",
                 "promo_create", "promo_update", "promo_bulk", "broadcast", "sessions_revoke")
BURST_COUNT, OWNER_BURST_COUNT, BURST_MINUTES, BURST_PAUSE = 10, 30, 10, 1800
_last_burst: dict[int, float] = {}
_tasks: set[asyncio.Task] = set()
_bot_getter = None

_ready = False


async def ensure_schema(db) -> None:
    global _ready
    for sql in STATEMENTS:
        await db.execute(sql)
    _ready = True


async def _ensure(db) -> None:
    if not _ready:
        await ensure_schema(db)


def use_bot(getter) -> None:
    """Откуда брать клиент Bot API для тревог (общий с действиями админки)."""
    global _bot_getter
    _bot_getter = getter


def is_owner(user_id: int, rank: int) -> bool:
    from bot.chat.access import is_developer
    from bot.chat.global_ranks import CREATOR
    return rank >= CREATOR or is_developer(user_id)


# ── Подтверждение ────────────────────────────────────────────────────────────

def needs_confirm(action: str, data: dict) -> bool:
    if action in CONFIRM_ACTIONS:
        return True
    if action == "balance":
        limit = BALANCE_CONFIRM.get(str(data.get("currency") or ""))
        try:
            amount = Decimal(str(data.get("amount")))
        except (InvalidOperation, ValueError):
            return False
        return bool(limit is not None and amount.is_finite() and abs(amount) >= limit)
    return False


def confirmed(user_id: int, username: str | None, data: dict) -> bool:
    """Подтверждение — ID игрока или его @ник, набранные вручную."""
    given = str(data.get("confirm") or "").strip().lstrip("@").lower()
    return bool(given) and given in {str(user_id), (username or "").lower()} - {""}


def rules() -> dict:
    """Что подтверждается вводом ID: отдаётся в карточку игрока, чтобы окно знало, когда спрашивать."""
    return {"actions": list(CONFIRM_ACTIONS), "balance": {k: int(v) for k, v in BALANCE_CONFIRM.items()}}


# ── Лимиты ───────────────────────────────────────────────────────────────────

def rate_wait(actor_id: int, rank: int, kind: str, weight: int = 1, *, now: float | None = None) -> int:
    """0 — действие разрешено и засчитано; иначе сколько секунд подождать. Владелец не ограничивается."""
    if is_owner(actor_id, rank):
        return 0
    limit, window = LIMITS[kind]
    now = time.monotonic() if now is None else now
    queue = _hits[(actor_id, kind)]
    while queue and queue[0][0] <= now - window:
        queue.popleft()
    weight = max(1, int(weight))
    if sum(w for _, w in queue) + weight > limit:
        return max(1, int(queue[0][0] + window - now) + 1) if queue else window
    queue.append((now, weight))
    return 0


def rate_limit(user: dict, action: str, weight: int = 1) -> None:
    from fastapi import HTTPException
    kind = "sensitive" if action in SENSITIVE_ACTIONS else "moderation"
    wait = rate_wait(user["id"], user["rank"], kind, weight if kind == "sensitive" else 1)
    if wait:
        minutes = (wait + 59) // 60
        raise HTTPException(429, f"Слишком много действий подряд. Подождите примерно {minutes} мин. и повторите.")


def reset_limits() -> None:   # для тестов
    _hits.clear()
    _last_burst.clear()


# ── Журнал входов ────────────────────────────────────────────────────────────

def device_label(ua: str, via: str = "") -> str:
    u = (ua or "").lower()
    system = next((name for key, name in (("iphone", "iPhone"), ("ipad", "iPad"), ("android", "Android"), ("windows", "Windows"),
                                          ("mac os", "Mac"), ("linux", "Linux")) if key in u), "устройство")
    app = "Telegram" if via == "telegram" or "telegram" in u else next(
        (name for key, name in (("edg/", "Edge"), ("firefox", "Firefox"), ("chrome", "Chrome"), ("safari", "Safari")) if key in u), "браузер")
    return f"{system} · {app}"


async def record_login(db, user_id: int, ip: str, ua: str, via: str) -> dict:
    """Записать вход. new_device — раньше с этого устройства (по User-Agent) этот человек не заходил, хотя входы уже были."""
    await _ensure(db)
    ip, ua = (ip or "")[:64], (ua or "")[:300]
    async with db.execute(
        "SELECT 1 FROM bot_admin_logins WHERE user_id = ? AND ip = ? AND ua = ? AND created_at > NOW() - INTERVAL '30 minutes' LIMIT 1",
        (user_id, ip, ua)) as cur:
        if await cur.fetchone():
            return {"logged": False, "new_device": False}
    async with db.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE ua = ?) FROM bot_admin_logins WHERE user_id = ?", (ua, user_id)) as cur:
        total, same = await cur.fetchone()
    await db.execute("INSERT INTO bot_admin_logins (user_id, ip, ua, via) VALUES (?, ?, ?, ?)", (user_id, ip, ua, via))
    return {"logged": True, "new_device": int(total) > 0 and int(same) == 0}


async def logins(db, days: int = 30, user_id: int | None = None, limit: int = 100) -> list[dict]:
    await _ensure(db)
    days = max(1, min(int(days or 30), 365))
    where, params = "l.created_at > NOW() - make_interval(days => ?)", [days]
    if user_id:
        where += " AND l.user_id = ?"
        params.append(user_id)
    async with db.execute(
        f"SELECT l.user_id, u.user_tg_username, l.ip, l.ua, l.via, l.created_at FROM bot_admin_logins l "
        f"LEFT JOIN users u ON u.user_tg_id = l.user_id WHERE {where} ORDER BY l.id DESC LIMIT ?", (*params, max(1, min(limit, 300)))) as cur:
        return [{"user": {"id": int(r[0]), "username": r[1]}, "ip": r[2], "device": device_label(r[3], r[4]), "via": r[4],
                 "at": r[5].isoformat() if r[5] else None} for r in await cur.fetchall()]


# ── Завершение сессий ────────────────────────────────────────────────────────

async def revoke(db, user_id: int) -> None:
    """Сессии админки этого сотрудника (0 — всех) перестанут работать: нужно открыть админку заново."""
    await _ensure(db)
    await db.execute("INSERT INTO bot_admin_session_revocations (user_id, revoked_at) VALUES (?, NOW()) "
                     "ON CONFLICT (user_id) DO UPDATE SET revoked_at = NOW()", (user_id,))


async def revoked_before(db, user_id: int) -> float | None:
    await _ensure(db)
    async with db.execute("SELECT MAX(revoked_at) FROM bot_admin_session_revocations WHERE user_id IN (?, 0)", (user_id,)) as cur:
        row = await cur.fetchone()
    return row[0].timestamp() if row and row[0] else None


# ── Тревоги владельцу ────────────────────────────────────────────────────────

async def owners(db) -> list[int]:
    from bot.config import config
    ids = {int(config.developer_id)} if config.developer_id else set()
    async with db.execute("SELECT user_tg_id FROM users WHERE COALESCE(bot_rank, 0) >= 6") as cur:
        ids |= {int(r[0]) for r in await cur.fetchall()}
    return sorted(ids)


def _spawn(coro) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def drain() -> None:   # для тестов: дождаться отправленных тревог
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


async def _send(recipients: list[int], text: str) -> None:
    if not _bot_getter:
        return
    bot = _bot_getter()
    for uid in recipients:
        try:
            await asyncio.wait_for(bot.send_message(uid, text, parse_mode="HTML", disable_web_page_preview=True), 8)
        except Exception as exc:   # владелец не открывал личку с ботом или сеть недоступна
            logger.debug(f"admin alert to {uid} failed: {exc}")


async def alert(db, text: str, *, skip: int | None = None, title: str = "Админка: необычное действие") -> None:
    """Написать владельцам в личку (кроме skip). Получатели собираются сразу, отправка идёт в фоне."""
    recipients = [o for o in await owners(db) if o != skip]
    if recipients:
        _spawn(_send(recipients, f"🔔 <b>{title}</b>\n" + text))


async def _name(db, uid: int | None) -> str:
    if not uid:
        return "?"
    async with db.execute("SELECT user_tg_username FROM users WHERE user_tg_id = ?", (uid,)) as cur:
        row = await cur.fetchone()
    return html.escape(f"@{row[0]}" if row and row[0] else f"id{uid}")


async def after_action(db, user: dict, action: str, target_id: int | None = None, *, details: dict | None = None) -> None:
    """Вызывается после успешного опасного действия: одиночные тревоги (роль, бан во всех чатах, крупная сумма) и «пачка за 10 минут».
    Никогда не мешает самому действию."""
    try:
        actor, details = user["id"], details or {}
        owner = is_owner(actor, user["rank"])
        who, target = await _name(db, actor), await _name(db, target_id)
        if not owner:
            if action == "rank":
                await alert(db, f"{who} изменил роль {target}: {html.escape(str(details.get('from', '')))} → {html.escape(str(details.get('to', '')))}.", skip=actor)
            elif action == "global_ban":
                await alert(db, f"{who} забанил {target} во всех чатах.", skip=actor)
            elif action == "balance":
                limit = BALANCE_CONFIRM.get(str(details.get("code") or ""))
                try:
                    big = limit is not None and abs(Decimal(str(details.get("amount")))) >= limit
                except (InvalidOperation, ValueError):
                    big = False
                if big:
                    await alert(db, f"{who} изменил баланс {target}: {html.escape(str(details.get('currency', '')))} {html.escape(str(details.get('amount', '')))}.", skip=actor)
        if action not in BURST_ACTIONS:
            return
        async with db.execute(
            "SELECT COUNT(*) FROM bot_admin_actions WHERE actor_id = ? AND action = ANY(?::text[]) "
            "AND created_at > NOW() - make_interval(mins => ?)", (actor, list(BURST_ACTIONS), BURST_MINUTES)) as cur:
            count = int((await cur.fetchone())[0])
        threshold = OWNER_BURST_COUNT if owner else BURST_COUNT
        now = time.monotonic()
        if count >= threshold and now - _last_burst.get(actor, -BURST_PAUSE) >= BURST_PAUSE:
            _last_burst[actor] = now
            await alert(db, f"{who} сделал {count} важных действий за {BURST_MINUTES} минут (выдача, роли, баны, промокоды, рассылки). Проверьте раздел «Журнал».",
                        skip=None if owner else actor)
    except Exception as exc:
        logger.warning(f"admin_security.after_action skipped: {exc}")
