"""
infrastructure/repositories/twin_signals.py — сигналы для твинк-детекта (dev-console only).

Хранит НЕ сырые IP/отпечатки устройств, а солёные HMAC-хэши (FastAPI.auth.hash_signal) —
само значение никогда не попадает в БД. Пишется из FastAPI/deps.py (require_tg_user_base)
на авторизованных запросах, с троттлингом в памяти процесса.

НЕ используется для банов/ограничений — только для вкладки «Твинки» в dev-консоли
(services/twin_detection.py). Мультиаккаунтинг сам по себе не запрещён (BASE_PROMPT) —
это диагностика для разработчика, не автомодерация.
"""


async def ensure_table(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS user_login_signals (
            user_id     BIGINT NOT NULL,
            kind        TEXT NOT NULL,
            value_hash  TEXT NOT NULL,
            first_seen  TIMESTAMP NOT NULL DEFAULT NOW(),
            last_seen   TIMESTAMP NOT NULL DEFAULT NOW(),
            hits        INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (user_id, kind, value_hash)
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_login_signals_lookup "
        "ON user_login_signals(kind, value_hash)"
    )
    await db.commit()


async def record(db, user_id: int, kind: str, value_hash: str) -> None:
    if not value_hash:
        return
    await db.execute("""
        INSERT INTO user_login_signals (user_id, kind, value_hash)
        VALUES (?, ?, ?)
        ON CONFLICT (user_id, kind, value_hash)
        DO UPDATE SET last_seen = NOW(), hits = user_login_signals.hits + 1
    """, (user_id, kind, value_hash))
    await db.commit()


async def shared_signal_pairs(db, kind: str) -> list[tuple]:
    """Самосоединение по совпавшему хэшу: (user_a, user_b, value_hash, hits_a, hits_b),
    только a<b, без дублей."""
    async with db.execute("""
        SELECT a.user_id, b.user_id, a.value_hash, a.hits, b.hits
        FROM user_login_signals a
        JOIN user_login_signals b
          ON a.value_hash = b.value_hash AND a.kind = b.kind AND a.user_id < b.user_id
        WHERE a.kind = ?
    """, (kind,)) as c:
        return await c.fetchall()
