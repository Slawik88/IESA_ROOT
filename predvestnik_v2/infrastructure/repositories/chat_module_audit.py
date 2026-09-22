"""Canonical module mutations with append-only operator receipts."""
from __future__ import annotations

from core.chat_modules import CHAT_MODULES, CHAT_MODULE_KEYS, chat_module_default


def _default(module_key: str) -> int:
    return int(chat_module_default(module_key))


async def install_schema(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chat_module_audit (
            id BIGSERIAL PRIMARY KEY,
            scope TEXT NOT NULL CHECK (scope IN ('chat', 'global')),
            chat_id BIGINT,
            module_key TEXT NOT NULL,
            actor_id BIGINT NOT NULL,
            before_enabled INTEGER NOT NULL CHECK (before_enabled IN (0, 1)),
            after_enabled INTEGER NOT NULL CHECK (after_enabled IN (0, 1)),
            reason TEXT,
            source TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK ((scope = 'chat' AND chat_id IS NOT NULL) OR (scope = 'global' AND chat_id IS NULL))
        )
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION reject_chat_module_audit_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'chat_module_audit is append-only';
        END $$
    """)
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'trg_chat_module_audit_immutable'
                  AND tgrelid = 'chat_module_audit'::regclass
            ) THEN
                CREATE TRIGGER trg_chat_module_audit_immutable
                BEFORE UPDATE OR DELETE ON chat_module_audit
                FOR EACH ROW EXECUTE FUNCTION reject_chat_module_audit_mutation();
            END IF;
        END $$
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_module_audit_chat "
        "ON chat_module_audit(chat_id, created_at DESC) WHERE scope = 'chat'"
    )


def catalog() -> list[dict]:
    return [{"key": key, **spec}
            for key, spec in CHAT_MODULES.items()]


async def set_chat_module(db, *, chat_id: int, module_key: str, enabled: bool,
                          actor_id: int, source: str) -> dict:
    if module_key not in CHAT_MODULE_KEYS:
        raise ValueError("unknown chat module")
    value = int(bool(enabled))
    async with db.connection.transaction():
        await db.execute(
            "INSERT INTO chat_settings (chat_id) VALUES (?) ON CONFLICT (chat_id) DO NOTHING",
            (chat_id,),
        )
        async with db.execute(
            f"SELECT COALESCE({module_key}, ?) AS enabled FROM chat_settings "
            "WHERE chat_id = ? FOR UPDATE",
            (_default(module_key), chat_id),
        ) as cursor:
            row = await cursor.fetchone()
        before = int(row["enabled"])
        if before == value:
            return {"changed": False, "before": before, "after": value}
        await db.execute(
            f"UPDATE chat_settings SET {module_key} = ? WHERE chat_id = ?",
            (value, chat_id),
        )
        await db.execute(
            "INSERT INTO chat_module_audit "
            "(scope,chat_id,module_key,actor_id,before_enabled,after_enabled,source) "
            "VALUES ('chat',?,?,?,?,?,?)",
            (chat_id, module_key, actor_id, before, value, source),
        )
    return {"changed": True, "before": before, "after": value}


async def set_global_module(db, *, module_key: str, enabled: bool, actor_id: int,
                            reason: str | None, source: str) -> dict:
    if module_key not in CHAT_MODULE_KEYS:
        raise ValueError("unknown chat module")
    value = int(bool(enabled))
    clean_reason = (reason or "").strip() or None
    async with db.connection.transaction():
        await db.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))",
            (f"global-chat-module:{module_key}",),
        )
        await db.execute(
            "INSERT INTO global_module_toggles(module_key,enabled,disabled_reason,updated_at) "
            "VALUES (?,?,NULL,NOW()) ON CONFLICT(module_key) DO NOTHING",
            (module_key, _default(module_key)),
        )
        async with db.execute(
            "SELECT enabled, disabled_reason FROM global_module_toggles "
            "WHERE module_key = ? FOR UPDATE", (module_key,),
        ) as cursor:
            row = await cursor.fetchone()
        before = int(row["enabled"])
        old_reason = row["disabled_reason"]
        next_reason = None if value else clean_reason
        if before == value and old_reason == next_reason:
            return {"changed": False, "before": before, "after": value}
        await db.execute(
            "INSERT INTO global_module_toggles(module_key,enabled,disabled_reason,updated_at) "
            "VALUES (?,?,?,NOW()) ON CONFLICT(module_key) DO UPDATE SET "
            "enabled=excluded.enabled,disabled_reason=excluded.disabled_reason,updated_at=NOW()",
            (module_key, value, next_reason),
        )
        await db.execute(
            "INSERT INTO chat_module_audit "
            "(scope,chat_id,module_key,actor_id,before_enabled,after_enabled,reason,source) "
            "VALUES ('global',NULL,?,?,?,?,?,?)",
            (module_key, actor_id, before, value, next_reason, source),
        )
    return {"changed": True, "before": before, "after": value}


async def recent(db, *, scope: str, chat_id: int | None = None, limit: int = 20) -> list[dict]:
    if scope not in {"chat", "global"}:
        raise ValueError("unknown audit scope")
    where = "a.scope = ?"
    params: list = [scope]
    if scope == "chat":
        where += " AND a.chat_id = ?"
        params.append(chat_id)
    params.append(max(1, min(int(limit), 50)))
    async with db.execute(
        "SELECT a.id,a.scope,a.chat_id,a.module_key,a.actor_id,a.before_enabled," 
        "a.after_enabled,a.reason,a.source,a.created_at,u.user_tg_username AS actor_name "
        "FROM chat_module_audit a LEFT JOIN users u ON u.user_tg_id=a.actor_id "
        f"WHERE {where} ORDER BY a.id DESC LIMIT ?", tuple(params),
    ) as cursor:
        rows = [dict(row) for row in await cursor.fetchall()]
    for row in rows:
        row["created_at"] = str(row["created_at"])
        row["module"] = CHAT_MODULES.get(row["module_key"], {"name": row["module_key"], "icon": "🧩"})
    return rows
