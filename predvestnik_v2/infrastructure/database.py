# infrastructure/database.py
# Unified SQLite connection factory.
# Always enables WAL mode so the Bot and the Web panel can write concurrently.
import aiosqlite


async def create_connection(db_path: str) -> aiosqlite.Connection:
    """Open a WAL-mode SQLite connection with sensible performance defaults."""
    conn = await aiosqlite.connect(db_path, timeout=20.0)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.execute("PRAGMA temp_store=MEMORY")
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.execute("PRAGMA busy_timeout=5000")
    await conn.commit()
    return conn
