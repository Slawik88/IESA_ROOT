"""Append-only чеки изменений «скалярных» настроек чата (всё вне модулей).

Модульные тумблеры пишутся в chat_module_audit; пороги рангов, пороги чистки,
NSFW/глобальный топ, часовой пояс и привязка админ-чата раньше менялись без
следа. Журнал отвечает на вопрос «кто, что и когда поменял» сразу на обеих
поверхностях: бот («📜 Изменения») и панель модератора.

Схема устанавливается из chat_module_audit.install_schema — той же точки,
которую уже вызывают init_db бота и lifespan FastAPI.
"""
from __future__ import annotations

from core.chat_settings_defaults import chat_setting_label


async def install_schema(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chat_settings_audit (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            setting_key TEXT NOT NULL,
            before_value TEXT,
            after_value TEXT,
            actor_id BIGINT NOT NULL,
            source TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION reject_chat_settings_audit_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'chat_settings_audit is append-only';
        END $$
    """)
    await db.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'trg_chat_settings_audit_immutable'
                  AND tgrelid = 'chat_settings_audit'::regclass
            ) THEN
                CREATE TRIGGER trg_chat_settings_audit_immutable
                BEFORE UPDATE OR DELETE ON chat_settings_audit
                FOR EACH ROW EXECUTE FUNCTION reject_chat_settings_audit_mutation();
            END IF;
        END $$
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_settings_audit_chat "
        "ON chat_settings_audit(chat_id, id DESC)"
    )


async def record(db, *, chat_id: int, setting_key: str, before, after,
                 actor_id: int, source: str) -> bool:
    """Записать изменение; False — значение не изменилось, чека нет."""
    before_s = None if before is None else str(before)
    after_s = None if after is None else str(after)
    if before_s == after_s:
        return False
    await db.execute(
        "INSERT INTO chat_settings_audit "
        "(chat_id,setting_key,before_value,after_value,actor_id,source) "
        "VALUES (?,?,?,?,?,?)",
        (chat_id, setting_key, before_s, after_s, actor_id, source),
    )
    return True


async def recent(db, *, chat_id: int, limit: int = 20) -> list[dict]:
    async with db.execute(
        "SELECT a.id,a.chat_id,a.setting_key,a.before_value,a.after_value,"
        "a.actor_id,a.source,a.created_at,u.user_tg_username AS actor_name "
        "FROM chat_settings_audit a LEFT JOIN users u ON u.user_tg_id=a.actor_id "
        "WHERE a.chat_id = ? ORDER BY a.id DESC LIMIT ?",
        (chat_id, max(1, min(int(limit), 50))),
    ) as cursor:
        rows = [dict(row) for row in await cursor.fetchall()]
    for row in rows:
        row["created_at"] = str(row["created_at"])
        row["label"] = chat_setting_label(str(row["setting_key"]))
    return rows
