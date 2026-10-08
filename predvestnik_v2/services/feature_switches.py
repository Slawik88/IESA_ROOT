"""Выключатели функций бота и сайта — глобально или в одном чате.

Строка в bot_feature_switches = функция ВЫКЛЮЧЕНА (chat_id 0 — везде). Нет строки — включена.
Чат не может включить то, что выключено везде. Проверка идёт до выполнения:
команда в чате не запускается, запрос к сайту отклоняется до обработчика (503).

Ключи:
    all                  весь бот в чатах
    section:<раздел>     раздел «бот помощь» (games, social, moderation…)
    group:<набор>        набор команд (group:warps — все варп-команды)
    cmd:<команда>        одна команда («cmd:перевод»)
    notice:achievements  объявления о новых уровнях достижений
    site                 весь сайт (мини-приложение)
    site:<область>       часть сайта (site:rhythm, site:skins…) — только глобально
"""
from __future__ import annotations

import time

GLOBAL = 0
TTL = 15.0   # сек; запись из админки сбрасывает кэш сразу (бот и сайт — один процесс)

SITE_AREAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "rhythm": ("🥁 Ритм", ("/rhythm-v2",)),
    "minesweeper": ("💣 Сапёр", ("/minesweeper-v2", "/minesweeper")),
    "mafia": ("🕵️ Мафия: статистика", ("/mafia-v1",)),
    "skins": ("✨ Образы и внешний вид", ("/skins-v3", "/appearance", "/cosmetics")),
    "store": ("💳 Покупки: Зарники и VIP", ("/payments", "/vip")),
    "pets": ("🐾 Питомцы", ("/pets-v1",)),
    "quests": ("📜 Квесты", ("/quests-v1",)),
    "achievements": ("🏆 Достижения", ("/achievements-v1",)),
    "chests": ("🎁 Сундуки", ("/chests-v1",)),
    "exchange": ("📈 Биржа монет", ("/player-exchange/v1",)),
    "family": ("💞 Семья", ("/marriage",)),
    "top": ("🏅 Топы", ("/leaderboards",)),
    "profiles": ("👤 Профили и регалии", ("/public-profile-v3", "/marks-v1")),
}
# Всегда открыто, даже при выключенном сайте: админка, вход, правовые документы, служебное.
SITE_ALWAYS_OPEN = ("/bot-admin", "/auth", "/legal", "/api/health", "/api/ready", "/static", "/manifest.json")
NOTICES = {"achievements": "🏆 Объявления о новых уровнях достижений"}
GROUPS = {"warps": "🤗 Все варп-команды (обнять, погладить…)"}

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS bot_feature_switches (
        chat_id    BIGINT NOT NULL,
        feature    TEXT   NOT NULL,
        reason     TEXT   NOT NULL DEFAULT '',
        updated_by BIGINT,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (chat_id, feature)
    )""",
)

_cache: dict[tuple[int, str], str] = {}
_loaded_at = -1e9


async def ensure_schema(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)


def invalidate() -> None:
    global _loaded_at
    _loaded_at = -1e9


async def _load(db) -> None:
    global _cache, _loaded_at
    async with db.execute("SELECT to_regclass('bot_feature_switches') IS NOT NULL") as cur:
        exists = (await cur.fetchone())[0]
    if exists:
        async with db.execute("SELECT chat_id, feature, reason FROM bot_feature_switches") as cur:
            _cache = {(int(r[0]), str(r[1])): str(r[2] or "") for r in await cur.fetchall()}
    else:
        _cache = {}
    _loaded_at = time.monotonic()


async def _switches(db=None) -> dict[tuple[int, str], str]:
    """Кэш выключателей; без db соединение берётся из пула только для обновления кэша."""
    if time.monotonic() - _loaded_at > TTL:
        if db is not None:
            await _load(db)
        else:
            from infrastructure.database import create_pool, get_pool
            from infrastructure.pg_adapter import PGAdapter
            await create_pool()
            async with get_pool().acquire() as conn:
                await _load(PGAdapter(conn))
    return _cache


async def disabled(db, features: list[str], chat_id: int | None) -> tuple[str, str] | None:
    """Первая выключенная функция из списка: (ключ, причина) или None, если всё включено."""
    switches = await _switches(db)
    scopes = (GLOBAL,) if not chat_id else (GLOBAL, int(chat_id))
    for feature in features:
        for scope in scopes:
            if (scope, feature) in switches:
                return feature, switches[(scope, feature)]
    return None


def command_features(name: str, section: str, group: str) -> list[str]:
    out = ["all"]
    if section:
        out.append(f"section:{section}")
    if group:
        out.append(f"group:{group}")
    out.append(f"cmd:{name}")
    return out


def site_area(path: str, root: str = "") -> str | None | bool:
    """Область сайта для пути: имя области, None — без области, False — всегда открыто."""
    if root and path.startswith(root):
        path = path[len(root):] or "/"
    if any(path == p or path.startswith(p + "/") or path.startswith(p + "?") for p in SITE_ALWAYS_OPEN):
        return False
    for key, (_, prefixes) in SITE_AREAS.items():
        if any(path == p or path.startswith(p + "/") for p in prefixes):
            return key
    return None


async def set_switch(db, chat_id: int, feature: str, enabled: bool, *, actor_id: int, reason: str = "") -> None:
    if enabled:
        await db.execute("DELETE FROM bot_feature_switches WHERE chat_id = ? AND feature = ?", (chat_id, feature))
    else:
        await db.execute(
            "INSERT INTO bot_feature_switches (chat_id, feature, reason, updated_by) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (chat_id, feature) DO UPDATE SET reason = EXCLUDED.reason, "
            "updated_by = EXCLUDED.updated_by, updated_at = NOW()",
            (chat_id, feature, reason[:200], actor_id))
    invalidate()


def catalog() -> list[dict]:
    """Все выключатели для админки: группы с вложенными функциями."""
    from bot.chat import registry
    from bot.chat.help import SECTIONS
    by_section: dict[str, list] = {k: [] for k in SECTIONS}
    other = []
    for c in sorted(registry.commands(), key=lambda c: c.name):
        if c.always_on or c.group:
            continue
        item = {"key": f"cmd:{c.name}", "title": f"бот {c.name}", "hint": c.summary}
        (by_section[c.section] if c.section in by_section else other).append(item)
    chat = [{"key": "all", "title": "🤖 Весь бот в чатах", "hint": "Бот молчит на все команды"}]
    for key, title in SECTIONS.items():
        chat.append({"key": f"section:{key}", "title": title, "hint": "Весь раздел", "items": by_section[key]})
    chat.append({"key": "group:warps", "title": GROUPS["warps"], "hint": "122 команды разом"})
    if other:
        chat.append({"key": "", "title": "Прочие команды", "items": other})
    for key, title in NOTICES.items():
        chat.append({"key": f"notice:{key}", "title": title, "hint": "Уровни считаются, но в чат не пишутся"})
    site = [{"key": "site", "title": "🌐 Весь сайт", "hint": "Мини-приложение отвечает «временно закрыто»"}]
    site += [{"key": f"site:{k}", "title": t, "hint": ", ".join(p)} for k, (t, p) in SITE_AREAS.items()]
    return [{"scope": "chat", "title": "Чат-бот", "items": chat}, {"scope": "site", "title": "Сайт", "items": site}]


async def state(db, chat_id: int) -> dict:
    """Что выключено: везде и (если задан чат) в этом чате."""
    async with db.execute(
        "SELECT chat_id, feature, reason, updated_at FROM bot_feature_switches WHERE chat_id IN (?, ?)",
        (GLOBAL, int(chat_id or GLOBAL))) as cur:
        rows = await cur.fetchall()
    out: dict[str, dict] = {"global": {}, "chat": {}}
    for r in rows:
        scope = "global" if int(r[0]) == GLOBAL else "chat"
        out[scope][str(r[1])] = {"reason": r[2] or "", "at": r[3].isoformat() if r[3] else None}
    return out
