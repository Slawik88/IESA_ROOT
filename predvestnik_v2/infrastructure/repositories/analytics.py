"""infrastructure/repositories/analytics.py — посещаемость мини-аппа (БЛОК 35)."""
from datetime import datetime, timezone, timedelta


async def ensure_table(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS site_analytics (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            tab        TEXT NOT NULL,
            session_id TEXT NOT NULL,
            visited_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_sa_visited_at ON site_analytics(visited_at)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_sa_tab ON site_analytics(tab, visited_at)"
    )
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

    async with db.execute(
        "SELECT tab, COUNT(*) AS views, COUNT(DISTINCT user_id) AS users "
        "FROM site_analytics WHERE visited_at >= ? "
        "GROUP BY tab ORDER BY views DESC LIMIT 10",
        (day30,),
    ) as c:
        top_tabs = [
            {"tab": r[0], "views": r[1], "users": r[2]} for r in await c.fetchall()
        ]

    return {"dau": dau, "wau": wau, "mau": mau, "daily": daily, "top_tabs": top_tabs}
