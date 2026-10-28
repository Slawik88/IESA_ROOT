"""infrastructure/repositories/analytics.py — посещаемость мини-аппа (БЛОК 35)."""
from datetime import datetime, timezone, timedelta


async def ensure_table(db) -> None:
    """Каждый DDL изолирован и логируется: молчаливый `except: pass` уже приводил
    к тому, что упавший ALTER (лок на живой таблице при деплое) тихо ронял всю
    цепочку и колонка duration_sec не появлялась на проде."""
    from loguru import logger

    async def _try(label: str, sql: str) -> None:
        try:
            await db.execute(sql)
        except Exception as e:
            logger.warning(f"[analytics.ensure] {label}: {e}")

    await _try("create table", """
        CREATE TABLE IF NOT EXISTS site_analytics (
            id         SERIAL PRIMARY KEY,
            user_id    BIGINT NOT NULL,
            tab        TEXT NOT NULL,
            session_id TEXT NOT NULL,
            visited_at TIMESTAMP NOT NULL DEFAULT NOW(),
            duration_sec INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Время удержания на вкладке — копится хартбитом с фронта (раз в 15с, только
    # пока вкладка реально видима) поверх той же строки визита. ADD COLUMN идёт
    # ПЕРВЫМ из ALTER'ов — до тяжёлой BIGINT-миграции.
    await _try("add duration_sec",
        "ALTER TABLE site_analytics ADD COLUMN IF NOT EXISTS duration_sec INTEGER NOT NULL DEFAULT 0")
    # Migration: INTEGER → BIGINT — новые Telegram ID (5+ млрд) не влезали в int32.
    # Гоняем ТОЛЬКО если колонка реально int4: same-type ALTER в PG всё равно
    # переписывает таблицу под ACCESS EXCLUSIVE — это и был источник лока на старте.
    try:
        async with db.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'site_analytics' AND column_name = 'user_id'"
        ) as c:
            row = await c.fetchone()
        if row and str(row[0]).lower() in ("integer", "int4"):
            await db.execute("ALTER TABLE site_analytics ALTER COLUMN user_id TYPE BIGINT")
    except Exception as e:
        logger.warning(f"[analytics.ensure] user_id→BIGINT: {e}")
    await _try("idx visited_at",
        "CREATE INDEX IF NOT EXISTS idx_sa_visited_at ON site_analytics(visited_at)")
    await _try("idx tab",
        "CREATE INDEX IF NOT EXISTS idx_sa_tab ON site_analytics(tab, visited_at)")
    await db.commit()


async def record_visit(db, user_id: int, tab: str, session_id: str) -> None:
    try:
        await db.execute(
            "INSERT INTO site_analytics (user_id, tab, session_id) VALUES (?, ?, ?)",
            (user_id, tab, session_id),
        )
        await db.commit()
    except Exception:
        pass  # некритично; PGAdapter уже залогировал ошибку


HEARTBEAT_MAX_DELTA = 120  # секунд в одном хартбите: защита от накрученных/испорченных тиков с клиента


async def add_tab_durations(db, rows: list[tuple[int, str, str, int]]) -> None:
    """Пачка хартбитов (user_id, tab, session_id, секунды) одним запросом: каждая сумма — к последней строке своего визита."""
    if not rows:
        return
    users, tabs, sessions, deltas = (list(column) for column in zip(*rows))
    await db.execute(
        "UPDATE site_analytics s SET duration_sec = s.duration_sec + latest.delta "
        "FROM (SELECT DISTINCT ON (b.user_id, b.tab, b.session_id) a.id, b.delta "
        "      FROM unnest(?::bigint[], ?::text[], ?::text[], ?::int[]) AS b(user_id, tab, session_id, delta) "
        "      JOIN site_analytics a ON a.user_id = b.user_id AND a.tab = b.tab AND a.session_id = b.session_id "
        "      ORDER BY b.user_id, b.tab, b.session_id, a.visited_at DESC) latest "
        "WHERE s.id = latest.id",
        (users, tabs, sessions, deltas),
    )


async def get_dashboard(db) -> dict:
    try:
        return await _get_dashboard_inner(db)
    except Exception:
        return {"dau": 0, "wau": 0, "mau": 0, "daily": [], "top_tabs": [], "error": "таблица ещё не создана"}


async def _get_dashboard_inner(db) -> dict:
    now = datetime.now(timezone.utc)

    def _since(days: int) -> str:
        return (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    day1, day7, day30 = _since(1), _since(7), _since(30)

    async def _dau(since: str) -> int:
        async with db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM site_analytics WHERE visited_at >= ?",
            (since,),
        ) as c:
            row = await c.fetchone()
        return int(row[0]) if row else 0

    dau = await _dau(day1)
    wau = await _dau(day7)
    mau = await _dau(day30)

    async with db.execute(
        "SELECT DATE(visited_at) AS d, COUNT(DISTINCT session_id) AS sess, "
        "COUNT(DISTINCT user_id) AS users "
        "FROM site_analytics WHERE visited_at >= ? GROUP BY d ORDER BY d",
        (day30,),
    ) as c:
        daily = [
            {"date": str(r[0]) if r[0] else "", "sessions": r[1], "users": r[2]}
            for r in await c.fetchall()
        ]

    # top-level pages (tab без '/')
    async with db.execute(
        "SELECT tab, COUNT(*) AS views, COUNT(DISTINCT user_id) AS users, "
        "AVG(duration_sec) AS avg_dwell "
        "FROM site_analytics WHERE visited_at >= ? AND tab NOT LIKE '%/%' "
        "GROUP BY tab ORDER BY views DESC LIMIT 15",
        (day30,),
    ) as c:
        top_tabs = [
            {"tab": r[0], "views": r[1], "users": r[2], "avg_dwell_sec": round(float(r[3] or 0), 1)}
            for r in await c.fetchall()
        ]

    # под-вкладки (tab содержит '/'), за 7 дней чтобы видеть актуальное
    async with db.execute(
        "SELECT tab, COUNT(*) AS views, COUNT(DISTINCT user_id) AS users, "
        "AVG(duration_sec) AS avg_dwell "
        "FROM site_analytics WHERE visited_at >= ? AND tab LIKE '%/%' "
        "GROUP BY tab ORDER BY views DESC LIMIT 30",
        (day7,),
    ) as c:
        top_subtabs = [
            {"tab": r[0], "views": r[1], "users": r[2], "avg_dwell_sec": round(float(r[3] or 0), 1)}
            for r in await c.fetchall()
        ]

    return {
        "dau": dau, "wau": wau, "mau": mau,
        "daily": daily, "top_tabs": top_tabs, "top_subtabs": top_subtabs,
    }
