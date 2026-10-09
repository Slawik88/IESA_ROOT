"""Промокоды: создание в админке и активация игроком («бот промокод КОД»).

Таблицы старые (promocodes, promocode_redemptions) — дополнены колонками, данные не трогаются.
Награды нового формата лежат в promocodes.rewards_json списком:
    {"type": "mora", "amount": 1000}      {"type": "diamonds", "amount": 5}
    {"type": "essence", "amount": 50}     {"type": "skin", "id": "<skin_id>"}
    {"type": "vip", "days": 7}
Коды старого формата (rewards_json пуст) не активируются, пока их не пересохранят в админке.
Зарники промокодом не выдаются: положительные Зарники — только из оплаты (core/economy_v3).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from core.economy_contract import CURRENCY_SPECS
from core.skins_v3_catalog import SKINS
from infrastructure.repositories import skins_v3 as skins_v3_repo
from infrastructure.repositories import vip_v2 as vip_v2_repo
from infrastructure.repositories.economy_ledger import apply_balance_change

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,31}$")
MAX_REWARDS = 10
LIMITS = {"mora": 1_000_000_000, "diamonds": 1_000_000, "essence": 100_000, "vip": 365}

STATEMENTS = (
    "ALTER TABLE promocodes ADD COLUMN IF NOT EXISTS rewards_json JSONB",
    "ALTER TABLE promocodes ADD COLUMN IF NOT EXISTS note TEXT DEFAULT ''",
    "ALTER TABLE promocodes ADD COLUMN IF NOT EXISTS updated_by BIGINT",
    "ALTER TABLE promocodes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
    "ALTER TABLE promocode_redemptions ADD COLUMN IF NOT EXISTS rewards_json JSONB",
)


class PromoError(ValueError):
    """Понятная игроку или админу причина отказа."""


async def ensure_schema(db) -> None:
    async with db.execute("SELECT to_regclass('promocodes') IS NOT NULL AND "
                          "to_regclass('promocode_redemptions') IS NOT NULL") as cur:
        if not (await cur.fetchone())[0]:
            return   # таблицы создаёт init_db; без них промокодов просто нет
    for sql in STATEMENTS:
        await db.execute(sql)


# ── Награды ──────────────────────────────────────────────────────────────────

def _number(value, *, integer: bool, limit: int, what: str) -> int | Decimal:
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise PromoError(f"{what}: нужно число.")
    if not n.is_finite() or n <= 0:
        raise PromoError(f"{what}: нужно число больше нуля.")
    if n > limit:
        raise PromoError(f"{what}: не больше {limit:,}.".replace(",", " "))
    if integer:
        if n != n.to_integral_value():
            raise PromoError(f"{what}: только целое число.")
        return int(n)
    if n != n.quantize(Decimal("0.01")):
        raise PromoError(f"{what}: не больше двух знаков после запятой.")
    return n


def skin_choices() -> list[dict]:
    """Образы, которые можно положить в промокод (личные образы — только из консоли, по одному владельцу)."""
    return [{"id": sid, "name": s.get("name", sid), "tier": s.get("tier", ""), "blurb": s.get("blurb", ""),
             "pal": list(s.get("pal") or ()), "bg": (s.get("tokens") or {}).get("--v3-bg", "#0e0f14"),
             "wash": (s.get("tokens") or {}).get("--v3-wash", ""), "frame": (s.get("kinds") or {}).get("frame", "ring"),
             "season": bool(s.get("season")), "set": s.get("set")}
            for sid, s in SKINS.items() if not s.get("exclusive")]   # поля превью: админка рисует карточку образа цветами его палитры


def normalize_rewards(raw) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise PromoError("Добавьте хотя бы одну награду.")
    if len(raw) > MAX_REWARDS:
        raise PromoError(f"Не больше {MAX_REWARDS} наград в одном промокоде.")
    out: list[dict] = []
    for item in raw:
        kind = str((item or {}).get("type", "")).strip()
        if kind in ("mora", "diamonds", "essence"):
            label = CURRENCY_SPECS[kind].label if kind in CURRENCY_SPECS else "Эссенция"
            amount = _number(item.get("amount"), integer=kind != "diamonds", limit=LIMITS[kind], what=label)
            out.append({"type": kind, "amount": str(amount) if kind == "diamonds" else amount})
        elif kind == "vip":
            out.append({"type": "vip", "days": _number(item.get("days"), integer=True, limit=LIMITS["vip"],
                                                       what="VIP, дней")})
        elif kind == "skin":
            sid = str(item.get("id", "")).strip()
            skin = SKINS.get(sid)
            if not skin:
                raise PromoError("Такого образа нет.")
            if skin.get("exclusive"):
                raise PromoError("Личные образы промокодом не выдаются.")
            out.append({"type": "skin", "id": sid})
        elif kind == "zarniki":
            raise PromoError("Зарники промокодом не выдаются: они приходят только из оплаты.")
        else:
            raise PromoError(f"Неизвестная награда: {kind or '—'}.")
    kinds = [r["type"] for r in out if r["type"] != "skin"]
    if len(kinds) != len(set(kinds)):
        raise PromoError("Одна и та же награда указана дважды — сложите в одну строку.")
    skins = [r["id"] for r in out if r["type"] == "skin"]
    if len(skins) != len(set(skins)):
        raise PromoError("Один и тот же образ указан дважды.")
    return out


def _fmt(n) -> str:
    d = Decimal(str(n))
    s = f"{d:,.2f}" if d != d.to_integral_value() else f"{int(d):,}"
    return s.replace(",", " ")


def describe(reward: dict) -> str:
    kind = reward["type"]
    if kind in ("mora", "diamonds"):
        spec = CURRENCY_SPECS[kind]
        return f"{spec.icon} {_fmt(reward['amount'])} {spec.label.lower()}"
    if kind == "essence":
        return f"🔮 {_fmt(reward['amount'])} эссенции"
    if kind == "vip":
        return f"👑 VIP на {reward['days']} дн."
    if kind == "skin":
        return f"✨ образ «{SKINS.get(reward['id'], {}).get('name', reward['id'])}»"
    return kind


async def _grant(db, user_id: int, code: str, index: int, reward: dict) -> str:
    key = f"promocode:{code}:{user_id}:{index}"
    kind = reward["type"]
    if kind in ("mora", "diamonds"):
        await apply_balance_change(
            db, user_id, {kind: Decimal(str(reward["amount"]))}, reason_code="promocode",
            idempotency_key=key, source_type="promocode", reference_type="promocode", reference_id=code)
        return describe(reward)
    if kind == "essence":
        await skins_v3_repo.essence_apply(db, user_id, int(reward["amount"]), reason="promocode",
                                          reference=code, idempotency_key=key)
        return describe(reward)
    if kind == "vip":
        await vip_v2_repo.lock_user(db, user_id)
        await vip_v2_repo.extend_subscription(db, user_id=user_id, days=int(reward["days"]))
        return describe(reward)
    if kind == "skin":
        if await skins_v3_repo.grant(db, user_id, reward["id"]):
            return describe(reward)
        return describe(reward) + " — уже был"
    raise PromoError(f"Неизвестная награда: {kind}.")


# ── Активация ────────────────────────────────────────────────────────────────

def normalize_code(code: str) -> str:
    return str(code or "").strip().upper()


def _ids(raw) -> list[int]:
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return [int(x) for x in data]
    except (TypeError, ValueError):
        return []


def _when(raw) -> datetime | None:
    if not raw:
        return None
    try:
        d = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


@dataclass
class Redemption:
    code: str
    granted: list[str]


async def redeem(db, *, user_id: int, code: str, chat_id: int | None) -> Redemption:
    """Активировать промокод: все проверки и все награды — одной транзакцией."""
    code = normalize_code(code)
    if not code:
        raise PromoError("Напишите код: бот промокод КОД")
    async with db.connection.transaction():
        async with db.execute(
            "SELECT code, is_active, valid_from, valid_until, max_activations, activations_count, "
            "allowed_chats_json, allowed_users_json, rewards_json FROM promocodes WHERE upper(code) = ? FOR UPDATE",
            (code,)) as cur:
            row = await cur.fetchone()
        if not row or not row[1]:
            raise PromoError("Такого промокода нет или он выключен.")
        code = str(row[0])
        now = datetime.now(timezone.utc)
        start, end = _when(row[2]), _when(row[3])
        if start and now < start:
            raise PromoError("Этот промокод ещё не начал действовать.")
        if end and now > end:
            raise PromoError("Срок действия промокода закончился.")
        if row[4] and int(row[5] or 0) >= int(row[4]):
            raise PromoError("У промокода закончились активации.")
        chats = _ids(row[6])
        if chats and chat_id not in chats:
            raise PromoError("Этот промокод работает только в определённых чатах.")
        users = _ids(row[7])
        if users and user_id not in users:
            raise PromoError("Этот промокод не для вас.")
        rewards = row[8]
        if isinstance(rewards, str):
            rewards = json.loads(rewards)
        if not rewards:
            raise PromoError("Промокод старого формата: попросите администратора пересохранить его.")
        await db.execute("INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,))
        async with db.execute(
            "INSERT INTO promocode_redemptions (code, user_id, chat_id) VALUES (?, ?, ?) "
            "ON CONFLICT (code, user_id) DO NOTHING RETURNING 1", (code, user_id, chat_id)) as cur:
            if not await cur.fetchone():
                raise PromoError("Вы уже активировали этот промокод.")
        await db.execute("UPDATE promocodes SET activations_count = COALESCE(activations_count, 0) + 1 "
                         "WHERE code = ?", (code,))
        granted = [await _grant(db, user_id, code, i, r) for i, r in enumerate(rewards)]
        await db.execute("UPDATE promocode_redemptions SET rewards_json = ?::jsonb WHERE code = ? AND user_id = ?",
                         (json.dumps(granted, ensure_ascii=False), code, user_id))
    return Redemption(code, granted)


# ── Админка ──────────────────────────────────────────────────────────────────

def _iso(value) -> str | None:
    if value in (None, ""):
        return None
    d = _when(value)
    if d is None:
        raise PromoError("Дата: формат ГГГГ-ММ-ДДTЧЧ:ММ.")
    return d.astimezone(timezone.utc).isoformat(timespec="minutes")


def _row(r) -> dict:
    rewards = r[8]
    if isinstance(rewards, str):
        rewards = json.loads(rewards)
    return {
        "code": r[0], "is_active": bool(r[1]), "valid_from": r[2] or None, "valid_until": r[3] or None,
        "max_activations": int(r[4] or 0), "activations": int(r[5] or 0),
        "allowed_chats": _ids(r[6]), "allowed_users": _ids(r[7]),
        "rewards": rewards or [], "rewards_text": [describe(x) for x in rewards or []],
        "legacy": not rewards, "note": r[9] or r[10] or "",
        "created_at": r[11].isoformat() if r[11] else None,
    }


_COLUMNS = ("code, is_active, valid_from, valid_until, max_activations, activations_count, allowed_chats_json, "
            "allowed_users_json, rewards_json, note, description, created_at")


async def list_codes(db, *, query: str = "", limit: int = 200) -> list[dict]:
    like = f"%{query.strip().upper()}%"
    async with db.execute(f"SELECT {_COLUMNS} FROM promocodes WHERE upper(code) LIKE ? "
                          "ORDER BY created_at DESC NULLS LAST, code LIMIT ?", (like, limit)) as cur:
        return [_row(r) for r in await cur.fetchall()]


async def get_code(db, code: str) -> dict | None:
    async with db.execute(f"SELECT {_COLUMNS} FROM promocodes WHERE upper(code) = ?", (normalize_code(code),)) as cur:
        r = await cur.fetchone()
    if not r:
        return None
    out = _row(r)
    titles: dict[int, str] = {}
    if out["allowed_chats"]:
        async with db.execute("SELECT chat_id, chat_title FROM chat_settings WHERE chat_id = ANY(?::bigint[])",
                              (out["allowed_chats"],)) as cur:
            titles = {int(x[0]): x[1] for x in await cur.fetchall() if x[1]}
    out["chats"] = [{"id": c, "title": titles.get(c, str(c))} for c in out["allowed_chats"]]
    async with db.execute(
        "SELECT r.user_id, u.user_tg_username, r.chat_id, c.chat_title, r.redeemed_at, r.rewards_json "
        "FROM promocode_redemptions r LEFT JOIN users u ON u.user_tg_id = r.user_id "
        "LEFT JOIN chat_settings c ON c.chat_id = r.chat_id WHERE r.code = ? "
        "ORDER BY r.redeemed_at DESC LIMIT 300", (out["code"],)) as cur:
        out["redemptions"] = [
            {"user_id": int(x[0]), "username": x[1], "chat_id": x[2], "chat_title": x[3],
             "at": x[4].isoformat() if x[4] else None,
             "granted": json.loads(x[5]) if isinstance(x[5], str) else (x[5] or [])}
            for x in await cur.fetchall()]
    return out


async def save_code(db, data: dict, *, actor_id: int, create: bool) -> dict:
    code = normalize_code(data.get("code"))
    if not CODE_RE.match(code):
        raise PromoError("Код: 3–32 символа, латиница, цифры, «-» и «_».")
    rewards = normalize_rewards(data.get("rewards"))
    try:
        max_act = int(data.get("max_activations") or 0)
    except (TypeError, ValueError):
        raise PromoError("Лимит активаций: целое число (0 — без лимита).")
    if max_act < 0:
        raise PromoError("Лимит активаций не может быть отрицательным.")
    start, end = _iso(data.get("valid_from")), _iso(data.get("valid_until"))
    if start and end and end <= start:
        raise PromoError("Конец действия должен быть позже начала.")
    try:
        chats = sorted({int(x) for x in data.get("allowed_chats") or []})
        users = sorted({int(x) for x in data.get("allowed_users") or []})
    except (TypeError, ValueError):
        raise PromoError("ID чатов и игроков — только числа.")
    note = str(data.get("note") or "")[:300]
    values = (bool(data.get("is_active", True)), start, end, max_act, json.dumps(chats) if chats else "",
              json.dumps(users) if users else "", json.dumps(rewards, ensure_ascii=False), note, actor_id)
    if create:
        async with db.execute("SELECT 1 FROM promocodes WHERE upper(code) = ?", (code,)) as cur:
            if await cur.fetchone():
                raise PromoError("Такой код уже есть.")
        async with db.execute(
            "INSERT INTO promocodes (code, is_active, valid_from, valid_until, max_activations, allowed_chats_json, "
            "allowed_users_json, rewards_json, note, created_by, updated_by, updated_at, description) "
            "VALUES (?, ?::int, ?, ?, ?, ?, ?, ?::jsonb, ?, ?, ?, NOW(), '') ON CONFLICT DO NOTHING RETURNING 1",
            (code, *values[:-1], actor_id, actor_id)) as cur:
            if not await cur.fetchone():
                raise PromoError("Такой код уже есть.")
    else:
        async with db.execute(
            "UPDATE promocodes SET is_active = ?::int, valid_from = ?, valid_until = ?, max_activations = ?, "
            "allowed_chats_json = ?, allowed_users_json = ?, rewards_json = ?::jsonb, note = ?, updated_by = ?, "
            "updated_at = NOW() WHERE upper(code) = ? RETURNING 1", (*values, code)) as cur:
            if not await cur.fetchone():
                raise PromoError("Промокод не найден.")
    return await get_code(db, code)


async def set_active(db, code: str, active: bool, *, actor_id: int) -> dict:
    async with db.execute("UPDATE promocodes SET is_active = ?::int, updated_by = ?, updated_at = NOW() "
                          "WHERE upper(code) = ? RETURNING 1", (active, actor_id, normalize_code(code))) as cur:
        if not await cur.fetchone():
            raise PromoError("Промокод не найден.")
    return await get_code(db, code)
