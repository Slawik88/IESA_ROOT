# infrastructure/repositories/clans.py — кланы/гильдии (SQL-слой).
# Один клан на игрока (PK clan_members.user_id). Атомарные операции — через
# db.connection.transaction() + FOR UPDATE (как marriages/economy).
from core.constants import CLAN_CREATE_COST_MORA, CLAN_MAX_MEMBERS


async def ensure_tables(db) -> None:
    """Идемпотентно создать таблицы кланов (нужно веб-процессу до init_db бота —
    как ensure_table для тем/косметики). Тот же DDL, что в bot/core/database.py."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS clans (
            clan_id     SERIAL PRIMARY KEY,
            name        TEXT UNIQUE NOT NULL,
            tag         TEXT NOT NULL,
            leader_id   BIGINT NOT NULL,
            description TEXT DEFAULT '',
            emblem      TEXT DEFAULT '🛡',
            total_xp    BIGINT DEFAULT 0,
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS clan_members (
            user_id   BIGINT PRIMARY KEY,
            clan_id   INTEGER NOT NULL REFERENCES clans(clan_id) ON DELETE CASCADE,
            role      TEXT DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT NOW()
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_clan_members_clan ON clan_members(clan_id)")


async def get_user_clan(db, user_id: int) -> dict | None:
    """Клан игрока + его роль (или None)."""
    async with db.execute(
        "SELECT c.clan_id, c.name, c.tag, c.emblem, c.description, c.leader_id, "
        "c.total_xp, c.created_at, m.role "
        "FROM clan_members m JOIN clans c ON c.clan_id = m.clan_id "
        "WHERE m.user_id = ?",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_clan(db, clan_id: int) -> dict | None:
    async with db.execute(
        "SELECT clan_id, name, tag, emblem, description, leader_id, total_xp, created_at "
        "FROM clans WHERE clan_id = ?",
        (clan_id,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_members(db, clan_id: int) -> list[dict]:
    """Состав клана: лидер первым, затем по дате вступления."""
    async with db.execute(
        "SELECT m.user_id, m.role, m.joined_at, u.user_tg_username AS username "
        "FROM clan_members m LEFT JOIN users u ON u.user_tg_id = m.user_id "
        "WHERE m.clan_id = ? ORDER BY (m.role = 'leader') DESC, m.joined_at ASC",
        (clan_id,),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def list_top_clans(db, limit: int = 20) -> list[dict]:
    """Топ кланов по суммарному XP (затем по числу участников)."""
    async with db.execute(
        "SELECT c.clan_id, c.name, c.tag, c.emblem, c.total_xp, c.leader_id, "
        "(SELECT COUNT(*) FROM clan_members m WHERE m.clan_id = c.clan_id) AS member_count "
        "FROM clans c ORDER BY c.total_xp DESC, member_count DESC LIMIT ?",
        (limit,),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def create_clan(db, leader_id: int, name: str, tag: str,
                      desc: str, emblem: str) -> tuple[bool, str, int | None]:
    """Основать клан: списать 🪙, создать клан, добавить лидера. Атомарно."""
    cost = CLAN_CREATE_COST_MORA
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT clan_id FROM clan_members WHERE user_id = ?", (leader_id,)
            ) as c:
                if await c.fetchone():
                    return False, "Ты уже состоишь в клане.", None
            async with db.execute(
                "SELECT 1 FROM clans WHERE LOWER(name) = LOWER(?)", (name,)
            ) as c:
                if await c.fetchone():
                    return False, "Клан с таким названием уже есть.", None
            async with db.execute(
                "SELECT 1 FROM clans WHERE LOWER(tag) = LOWER(?)", (tag,)
            ) as c:
                if await c.fetchone():
                    return False, "Этот тег уже занят.", None
            async with db.execute(
                "SELECT COALESCE(user_balance_mora, 0) FROM users WHERE user_tg_id = ? FOR UPDATE",
                (leader_id,),
            ) as c:
                row = await c.fetchone()
            bal = float(row[0]) if row else 0.0
            if bal < cost:
                return False, f"Нужно {cost:,} 🪙 для основания клана.".replace(",", " "), None
            await db.execute(
                "UPDATE users SET user_balance_mora = COALESCE(user_balance_mora, 0) - ? "
                "WHERE user_tg_id = ?",
                (cost, leader_id),
            )
            async with db.execute(
                "INSERT INTO clans (name, tag, leader_id, description, emblem) "
                "VALUES (?, ?, ?, ?, ?) RETURNING clan_id",
                (name, tag, leader_id, desc, emblem),
            ) as c:
                cid = (await c.fetchone())[0]
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) VALUES (?, ?, 'leader')",
                (leader_id, cid),
            )
        return True, f"Клан «{name}» основан! 🎉", cid
    except Exception as e:
        return False, f"Ошибка: {e}", None


async def join_clan(db, user_id: int, clan_id: int) -> tuple[bool, str]:
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT clan_id FROM clan_members WHERE user_id = ?", (user_id,)
            ) as c:
                if await c.fetchone():
                    return False, "Ты уже в клане. Сначала выйди из текущего."
            async with db.execute(
                "SELECT name FROM clans WHERE clan_id = ? FOR UPDATE", (clan_id,)
            ) as c:
                cl = await c.fetchone()
            if not cl:
                return False, "Клан не найден."
            async with db.execute(
                "SELECT COUNT(*) FROM clan_members WHERE clan_id = ?", (clan_id,)
            ) as c:
                cnt = (await c.fetchone())[0]
            if cnt >= CLAN_MAX_MEMBERS:
                return False, "В клане нет свободных мест."
            await db.execute(
                "INSERT INTO clan_members (user_id, clan_id, role) VALUES (?, ?, 'member')",
                (user_id, clan_id),
            )
            return True, f"Ты вступил в клан «{cl[0]}»!"
    except Exception as e:
        return False, f"Ошибка: {e}"


async def leave_clan(db, user_id: int) -> tuple[bool, str]:
    """Выход. Лидер: передаёт лидерство старейшему участнику, иначе клан распускается."""
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT clan_id, role FROM clan_members WHERE user_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                m = await c.fetchone()
            if not m:
                return False, "Ты не состоишь в клане."
            cid, role = m[0], m[1]
            await db.execute("DELETE FROM clan_members WHERE user_id = ?", (user_id,))
            if role == "leader":
                async with db.execute(
                    "SELECT user_id FROM clan_members WHERE clan_id = ? "
                    "ORDER BY joined_at ASC LIMIT 1",
                    (cid,),
                ) as c:
                    nxt = await c.fetchone()
                if nxt:
                    await db.execute(
                        "UPDATE clan_members SET role = 'leader' WHERE user_id = ?", (nxt[0],)
                    )
                    await db.execute(
                        "UPDATE clans SET leader_id = ? WHERE clan_id = ?", (nxt[0], cid)
                    )
                    return True, "Ты покинул клан. Лидерство передано старейшему участнику."
                await db.execute("DELETE FROM clans WHERE clan_id = ?", (cid,))
                return True, "Ты покинул клан. Клан распущен (не осталось участников)."
            return True, "Ты покинул клан."
    except Exception as e:
        return False, f"Ошибка: {e}"


async def add_clan_xp(db, user_id: int, amount: int) -> None:
    """Начислить XP клану игрока (хук прогрессии; no-op если игрок без клана)."""
    if amount <= 0:
        return
    await db.execute(
        "UPDATE clans SET total_xp = total_xp + ? "
        "WHERE clan_id = (SELECT clan_id FROM clan_members WHERE user_id = ?)",
        (amount, user_id),
    )
    await db.commit()
