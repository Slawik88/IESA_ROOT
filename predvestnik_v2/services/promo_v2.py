"""Промокоды: создание в админке и активация игроком («бот промокод КОД»).

Таблицы старые (promocodes, promocode_redemptions) — дополнены колонками, данные не трогаются.
Награды нового формата лежат в promocodes.rewards_json списком:
    {"type": "mora", "amount": 1000}      {"type": "diamonds", "amount": 5}
    {"type": "essence", "amount": 50}     {"type": "skin", "id": "<skin_id>"}
    {"type": "vip", "days": 7}             {"type": "zarniki", "amount": 100}
Коды старого формата (rewards_json пуст) не активируются, пока их не пересохранят в админке.
Зарники в код кладёт только создатель (платная валюта, core/economy_v3: источник promocode_zarniki).
"""
from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from core.economy_contract import CURRENCY_SPECS
from core.skins_v3_catalog import SEASONS, SETS, SKINS
from infrastructure.repositories import skins_v3 as skins_v3_repo
from infrastructure.repositories import vip_v2 as vip_v2_repo
from services import skins_v3 as skins_v3_service
from infrastructure.repositories.economy_ledger import apply_balance_change

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,31}$")
MAX_REWARDS = 10
LIMITS = {"mora": 1_000_000_000, "diamonds": 1_000_000, "essence": 100_000, "zarniki": 100_000, "vip": 365}

STATEMENTS = (
    "ALTER TABLE promocodes ADD COLUMN IF NOT EXISTS rewards_json JSONB",
    "ALTER TABLE promocodes ADD COLUMN IF NOT EXISTS note TEXT DEFAULT ''",
    "ALTER TABLE promocodes ADD COLUMN IF NOT EXISTS updated_by BIGINT",
    "ALTER TABLE promocodes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
    "ALTER TABLE promocode_redemptions ADD COLUMN IF NOT EXISTS rewards_json JSONB",
    "ALTER TABLE promocodes ADD COLUMN IF NOT EXISTS show_in_app BOOLEAN NOT NULL DEFAULT FALSE",   # «Доступно сейчас» в Mini App (services/promo_player)
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


TIER_ORDER = ("D", "C", "B", "A", "S", "SS", "SSS")
_PREVIEW_TOKENS = ("--v3-bg", "--v3-ink", "--v3-dim", "--v3-acc", "--v3-wash", "--acc-rgb")


def _skin_row(sid: str, s: dict) -> dict:
    """Поля для карточки образа в админке: цвета самого образа, название набора и сезона, из чего он состоит."""
    tokens = s.get("tokens") or {}
    group = SETS.get(s.get("set") or "")
    season = SEASONS.get(s.get("season") or "")
    return {"id": sid, "name": s.get("name", sid), "tier": s.get("tier", ""), "blurb": s.get("blurb", ""),
            "pal": list(s.get("pal") or ()), "bg": tokens.get("--v3-bg", "#0e0f14"), "wash": tokens.get("--v3-wash", ""),
            "tokens": {k: tokens[k] for k in _PREVIEW_TOKENS if k in tokens},
            "kinds": dict(s.get("kinds") or {}), "items": dict(s.get("items") or {}),
            "frame": (s.get("kinds") or {}).get("frame", "ring"), "season": bool(s.get("season")),
            "season_name": season["name"] if season else "", "set": s.get("set"),
            "set_name": group["name"] if group else "", "exclusive": bool(s.get("exclusive"))}


def _skin_sort(item: dict) -> tuple:
    tier = item["tier"]
    return (TIER_ORDER.index(tier) if tier in TIER_ORDER else len(TIER_ORDER), item["name"])


def skin_choices() -> list[dict]:
    """Образы, которые можно положить в промокод: все, кроме личных, по возрастанию редкости."""
    return sorted((_skin_row(sid, s) for sid, s in SKINS.items() if not s.get("exclusive")), key=_skin_sort)


def private_skins() -> list[dict]:
    """Личные образы (один владелец на образ), без данных о владельцах."""
    return sorted((_skin_row(sid, s) for sid, s in SKINS.items() if s.get("exclusive")), key=_skin_sort)


async def private_skins_state(db) -> list[dict]:
    """Личные образы с текущим владельцем: занятый образ в промокод не кладётся, пока его не отозвали."""
    await skins_v3_repo.ensure_tables(db)
    out = private_skins()
    for item in out:
        item["holders"] = [{"user_id": h["user_id"], "name": f"@{h['username']}" if h["username"] else f"id{h['user_id']}"}
                           for h in await skins_v3_repo.holders(db, item["id"])]
    return out


def normalize_rewards(raw) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise PromoError("Добавьте хотя бы одну награду.")
    if len(raw) > MAX_REWARDS:
        raise PromoError(f"Не больше {MAX_REWARDS} наград в одном промокоде.")
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            raise PromoError("Награда: неверный формат.")
        kind = str(item.get("type", "")).strip()
        if kind in ("mora", "diamonds", "essence", "zarniki"):
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
            out.append({"type": "skin", "id": sid})
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
    if kind == "zarniki":
        return f"✨ {_fmt(reward['amount'])} зарников"
    if kind == "vip":
        return f"👑 VIP на {reward['days']} дн."
    if kind == "skin":
        skin = SKINS.get(reward["id"], {})
        return f"{'🌟 личный образ' if skin.get('exclusive') else '✨ образ'} «{skin.get('name', reward['id'])}»"
    return kind


async def _grant(db, user_id: int, code: str, index: int, reward: dict) -> str:
    key = f"promocode:{code}:{user_id}:{index}"
    kind = reward["type"]
    if kind in ("mora", "diamonds"):
        await apply_balance_change(
            db, user_id, {kind: Decimal(str(reward["amount"]))}, reason_code="promocode",
            idempotency_key=key, source_type="promocode", reference_type="promocode", reference_id=code)
        return describe(reward)
    if kind == "zarniki":
        await apply_balance_change(
            db, user_id, {"zarniki": Decimal(str(reward["amount"]))}, reason_code="promocode_zarniki",
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
        if SKINS.get(reward["id"], {}).get("exclusive"):
            return await _grant_private(db, user_id, code, reward)
        if await skins_v3_repo.grant(db, user_id, reward["id"]):
            return describe(reward)
        return describe(reward) + " — уже был"
    raise PromoError(f"Неизвестная награда: {kind}.")


async def _grant_private(db, user_id: int, code: str, reward: dict) -> str:
    """Личный образ: у него один владелец, поэтому выдаём через правило единственного владельца."""
    await skins_v3_repo.ensure_tables(db)
    if any(h["user_id"] == user_id for h in await skins_v3_repo.holders(db, reward["id"])):
        return describe(reward) + " — уже был"
    try:
        await skins_v3_service.grant_exclusive(db, user_id, reward["id"], f"промокод {code}")
    except skins_v3_service.SkinConflict:
        # Имя владельца игроку не показываем.
        raise PromoError(f"Личный образ «{SKINS[reward['id']]['name']}» уже достался другому игроку.")
    return describe(reward)


# ── Активация ────────────────────────────────────────────────────────────────

def normalize_code(code: str) -> str:
    return str(code or "").strip().upper()


def _ids(raw) -> list[int]:
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return [i for i in (int(x) for x in data) if abs(i) < 2 ** 63]   # больше BIGINT в базу не передать
    except (TypeError, ValueError):
        return []


MAX_ACTIVATIONS = 100_000_000


def like_pattern(q: str) -> str:
    """Поисковая строка для LIKE: «_» и «%» в запросе ищутся как обычные символы."""
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


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
        "show_in_app": bool(r[12]),
    }


_COLUMNS = ("code, is_active, valid_from, valid_until, max_activations, activations_count, allowed_chats_json, "
            "allowed_users_json, rewards_json, note, description, created_at, COALESCE(show_in_app, FALSE)")


async def list_codes(db, *, query: str = "", limit: int = 200) -> list[dict]:
    like = like_pattern(query.strip().upper())
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
    out["stats"] = await _stats(db, out)
    out["warnings"] = cost_warnings(out["rewards"], out["max_activations"], out["allowed_users"], out["valid_until"])
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


@dataclass
class Parsed:
    code: str
    rewards: list
    max_act: int
    start: str | None
    end: str | None
    chats: list
    users: list
    note: str


def _parse(data: dict, *, need_code: bool = True) -> Parsed:
    """Проверка полей промокода из формы: одна и для сохранения, и для предпросмотра."""
    code = normalize_code(data.get("code"))
    if need_code and not CODE_RE.match(code):
        raise PromoError("Код: 3–32 символа, латиница, цифры, «-» и «_».")
    rewards = normalize_rewards(data.get("rewards"))
    try:
        max_act = int(data.get("max_activations") or 0)
    except (TypeError, ValueError):
        raise PromoError("Лимит активаций: целое число (0 — без лимита).")
    if max_act < 0:
        raise PromoError("Лимит активаций не может быть отрицательным.")
    if max_act > MAX_ACTIVATIONS:
        raise PromoError(f"Лимит активаций: не больше {MAX_ACTIVATIONS:,}.".replace(",", " "))
    start, end = _iso(data.get("valid_from")), _iso(data.get("valid_until"))
    if start and end and end <= start:
        raise PromoError("Конец действия должен быть позже начала.")
    try:
        chats = sorted({int(x) for x in data.get("allowed_chats") or [] if not isinstance(x, (bool, float))})
        users = sorted({int(x) for x in data.get("allowed_users") or [] if not isinstance(x, (bool, float))})
    except (TypeError, ValueError):
        raise PromoError("ID чатов и игроков — только числа.")
    if any(abs(i) >= 2 ** 63 for i in chats + users):
        raise PromoError("ID чата или игрока слишком большой.")
    return Parsed(code, rewards, max_act, start, end, chats, users, str(data.get("note") or "")[:300])


async def require_zarniki_rights(db, rewards: list[dict], actor_id: int) -> None:
    """Зарники — платная валюта: класть их в промокод может только создатель."""
    if not any(r["type"] == "zarniki" for r in rewards):
        return
    from bot.chat.global_ranks import CREATOR, get_bot_rank
    if await get_bot_rank(db, actor_id) < CREATOR:
        raise PromoError("Зарники в промокод кладёт только создатель.")


async def save_code(db, data: dict, *, actor_id: int, create: bool) -> dict:
    parsed = _parse(data)
    await require_zarniki_rights(db, parsed.rewards, actor_id)
    code, rewards, max_act, start, end, chats, users, note = (
        parsed.code, parsed.rewards, parsed.max_act, parsed.start, parsed.end, parsed.chats, parsed.users, parsed.note)
    await _check_private(db, rewards, max_act, users, code=None if create else code)
    values = (bool(data.get("is_active", True)), start, end, max_act, json.dumps(chats) if chats else "",
              json.dumps(users) if users else "", json.dumps(rewards, ensure_ascii=False), note, bool(data.get("show_in_app")), actor_id)
    if create:
        async with db.execute("SELECT 1 FROM promocodes WHERE upper(code) = ?", (code,)) as cur:
            if await cur.fetchone():
                raise PromoError("Такой код уже есть.")
        async with db.execute(
            "INSERT INTO promocodes (code, is_active, valid_from, valid_until, max_activations, allowed_chats_json, "
            "allowed_users_json, rewards_json, note, show_in_app, created_by, updated_by, updated_at, description) "
            "VALUES (?, ?::int, ?, ?, ?, ?, ?, ?::jsonb, ?, ?, ?, ?, NOW(), '') ON CONFLICT DO NOTHING RETURNING 1",
            (code, *values[:-1], actor_id, actor_id)) as cur:
            if not await cur.fetchone():
                raise PromoError("Такой код уже есть.")
    else:
        async with db.execute(
            "UPDATE promocodes SET is_active = ?::int, valid_from = ?, valid_until = ?, max_activations = ?, "
            "allowed_chats_json = ?, allowed_users_json = ?, rewards_json = ?::jsonb, note = ?, show_in_app = ?, updated_by = ?, "
            "updated_at = NOW() WHERE upper(code) = ? RETURNING 1", (*values, code)) as cur:
            if not await cur.fetchone():
                raise PromoError("Промокод не найден.")
    return await get_code(db, code)


async def _check_private(db, rewards: list[dict], max_act: int, users: list[int], *, code: str | None) -> None:
    """Личный образ достаётся одному игроку: промокод с ним — одноразовый или именной, и образ ещё свободен."""
    private = [r["id"] for r in rewards if r["type"] == "skin" and SKINS.get(r["id"], {}).get("exclusive")]
    if not private:
        return
    if max_act != 1 and len(users) != 1:
        raise PromoError("Личный образ — на одного владельца: поставьте лимит активаций 1 или выберите одного игрока.")
    if code:   # правка уже использованного промокода не должна упираться в его же получателя
        async with db.execute("SELECT COALESCE(activations_count, 0) FROM promocodes WHERE upper(code) = ?", (code,)) as cur:
            row = await cur.fetchone()
        if row and int(row[0]) > 0:
            return
    await skins_v3_repo.ensure_tables(db)
    for sid in private:
        have = await skins_v3_repo.holders(db, sid)
        if have:
            who = f"@{have[0]['username']}" if have[0]["username"] else f"id{have[0]['user_id']}"
            raise PromoError(f"Личный образ «{SKINS[sid]['name']}» уже у {who}. Сначала отзовите его у игрока.")


async def set_active(db, code: str, active: bool, *, actor_id: int) -> dict:
    async with db.execute("UPDATE promocodes SET is_active = ?::int, updated_by = ?, updated_at = NOW() "
                          "WHERE upper(code) = ? RETURNING 1", (active, actor_id, normalize_code(code))) as cur:
        if not await cur.fetchone():
            raise PromoError("Промокод не найден.")
    return await get_code(db, code)


# ── Статистика, предпросмотр, пачки ──────────────────────────────────────────

async def _stats(db, code: dict) -> dict:
    """Сводка по активациям: сколько, где, когда, сколько осталось и сколько всего выдано (оценка по текущим наградам)."""
    async with db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT chat_id), COUNT(*) FILTER (WHERE chat_id IS NULL), MIN(redeemed_at), MAX(redeemed_at) "
        "FROM promocode_redemptions WHERE code = ?", (code["code"],)) as cur:
        total, chats, private, first, last = await cur.fetchone()
    async with db.execute(
        "SELECT (redeemed_at AT TIME ZONE 'UTC')::date AS d, COUNT(*) FROM promocode_redemptions "
        "WHERE code = ? AND redeemed_at > NOW() - INTERVAL '14 days' GROUP BY d", (code["code"],)) as cur:
        by_day = {r[0].isoformat(): int(r[1]) for r in await cur.fetchall()}
    today = datetime.now(timezone.utc).date()
    series = []
    for back in range(13, -1, -1):
        day = (today - timedelta(days=back)).isoformat()
        series.append({"day": day, "n": by_day.get(day, 0)})
    total = int(total or 0)
    limit = int(code["max_activations"] or 0)
    spent: dict[str, str] = {}
    for reward in code["rewards"]:
        key = {"mora": "mora", "diamonds": "diamonds", "essence": "essence", "zarniki": "zarniki", "vip": "vip_days"}.get(reward["type"])
        if key:
            value = Decimal(str(reward.get("amount", reward.get("days", 0)))) * total
            spent[key] = str(value)
    return {"activations": total, "limit": limit or None, "left": max(0, limit - total) if limit else None,
            "chats": int(chats or 0), "private": int(private or 0),
            "first_at": first.isoformat() if first else None, "last_at": last.isoformat() if last else None,
            "per_day": series, "spent": spent}


# Порог «дорогого» промокода: на одну активацию и в сумме по лимиту.
_COST_LIMITS = {"mora": (100_000, 1_000_000), "diamonds": (50, 500), "essence": (200, 2_000), "zarniki": (100, 1_000), "vip": (30, 365)}
_COST_NAMES = {"mora": "мора", "diamonds": "алмазов", "essence": "эссенции", "zarniki": "зарников", "vip": "дн. VIP"}


def cost_warnings(rewards: list, max_act: int, users: list | tuple, valid_until) -> list[str]:
    """Что стоит перепроверить до сохранения: большая сумма, редкий образ, нет лимита и срока. Только подсказки, сохранять не мешают."""
    out: list[str] = []
    crowd = len(users) if users else (max_act or 0)
    for reward in rewards:
        kind = reward["type"]
        if kind in _COST_LIMITS:
            one = Decimal(str(reward.get("amount", reward.get("days", 0))))
            per, total = _COST_LIMITS[kind]
            if one >= per:
                out.append(f"Крупная награда на одного игрока: {_fmt(one)} {_COST_NAMES[kind]}.")
            elif crowd and one * crowd >= total:
                out.append(f"Крупная сумма за весь лимит: {_fmt(one * crowd)} {_COST_NAMES[kind]} на {crowd} активаций.")
        elif kind == "skin":
            skin = SKINS.get(reward["id"], {})
            if skin.get("exclusive"):
                out.append(f"Личный образ «{skin.get('name', reward['id'])}» достанется одному игроку насовсем.")
            elif skin.get("tier") in ("SS", "SSS"):
                out.append(f"Редкий образ «{skin.get('name', reward['id'])}» ({skin['tier']}).")
    if any(r["type"] == "zarniki" for r in rewards):
        out.append("Зарники — платная валюта: игрок сможет потратить их на косметику и обменять на мору. Выданное не отозвать.")
    if not max_act and not users:
        tail = " и без срока" if not valid_until else ""
        out.append(f"Нет лимита активаций{tail}: награду получит каждый, кто узнает код.")
    return out


async def preview(db, data: dict) -> dict:
    """Как промокод увидит игрок и что стоит перепроверить. Ничего не сохраняет; код можно не указывать."""
    parsed = _parse(data, need_code=False)
    await _check_private(db, parsed.rewards, parsed.max_act, parsed.users, code=parsed.code or None)
    lines = [describe(r) for r in parsed.rewards]
    where = []
    if parsed.chats:
        where.append(f"работает только в выбранных чатах ({len(parsed.chats)})")
    if parsed.users:
        where.append(f"доступен только выбранным игрокам ({len(parsed.users)})")
    if parsed.start:
        where.append("ещё не начал действовать")
    return {
        "code": parsed.code or "КОД",
        "player_text": lines,
        "who_can": "; ".join(where) or "работает у любого игрока в любом чате и в личке с ботом",
        "warnings": cost_warnings(parsed.rewards, parsed.max_act, parsed.users, parsed.end),
    }


MAX_BULK = 200
_BULK_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # без похожих O/0, I/1


async def bulk_create(db, data: dict, *, actor_id: int) -> dict:
    """Пачка одноразовых кодов с одинаковой наградой. Всё или ничего: ошибка на любом шаге не оставляет часть кодов."""
    try:
        count = int(data.get("count") or 0)
    except (TypeError, ValueError):
        raise PromoError("Сколько кодов: целое число.")
    if not 1 <= count <= MAX_BULK:
        raise PromoError(f"Сколько кодов: от 1 до {MAX_BULK}.")
    prefix = normalize_code(data.get("prefix"))
    if prefix and not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,15}", prefix):
        raise PromoError("Начало кода: до 16 символов, латиница, цифры, «-» и «_».")
    if data.get("allowed_users"):
        raise PromoError("Пачка одноразовых не привязывается к игрокам: для одного игрока создайте обычный именной код.")
    parsed = _parse({**data, "code": prefix + "AAAA" if len(prefix) < 3 else prefix, "max_activations": 1})
    await require_zarniki_rights(db, parsed.rewards, actor_id)
    if any(r["type"] == "skin" and SKINS.get(r["id"], {}).get("exclusive") for r in parsed.rewards):
        raise PromoError("Личный образ нельзя раздавать пачкой: он достаётся одному игроку. Создайте обычный код на один раз.")
    note = parsed.note or f"Пачка из {count} одноразовых кодов"
    codes: list[str] = []
    async with db.connection.transaction():
        while len(codes) < count:
            code = prefix + ("-" if prefix else "") + "".join(secrets.choice(_BULK_ALPHABET) for _ in range(8))
            async with db.execute(
                "INSERT INTO promocodes (code, is_active, valid_from, valid_until, max_activations, allowed_chats_json, "
                "allowed_users_json, rewards_json, note, created_by, updated_by, updated_at, description) "
                "VALUES (?, 1, ?, ?, 1, ?, '', ?::jsonb, ?, ?, ?, NOW(), '') ON CONFLICT DO NOTHING RETURNING 1",
                (code, parsed.start, parsed.end, json.dumps(parsed.chats) if parsed.chats else "",
                 json.dumps(parsed.rewards, ensure_ascii=False), note, actor_id, actor_id)) as cur:
                if await cur.fetchone():
                    codes.append(code)
    return {"codes": codes, "rewards_text": [describe(r) for r in parsed.rewards], "note": note}
