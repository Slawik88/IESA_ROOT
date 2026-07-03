"""
infrastructure/repositories/clans2.py — R3 Кланы 2.0: казна, здания, Бездна,
войны за узлы (GDD_REBUILD_PLAN.md). Только SQL; логика — services/clans2.py.
"""
import json


async def ensure_tables(db) -> None:
    # Казна клана: 💠 (стройка) и 🪙 (доход узлов → взносы войн)
    for stmt in (
        "ALTER TABLE clans ADD COLUMN IF NOT EXISTS treasury_shards FLOAT8 DEFAULT 0",
        "ALTER TABLE clans ADD COLUMN IF NOT EXISTS treasury_mora FLOAT8 DEFAULT 0",
    ):
        try:
            await db.execute(stmt)
        except Exception:
            pass
    await db.execute("""
        CREATE TABLE IF NOT EXISTS clan_buildings (
            clan_id  INTEGER NOT NULL,
            key      TEXT NOT NULL,
            level    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (clan_id, key)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS clan_abyss (
            clan_id     INTEGER NOT NULL,
            week_key    TEXT NOT NULL,
            floor       INTEGER NOT NULL DEFAULT 1,
            grid_json   TEXT NOT NULL,
            opened_json TEXT NOT NULL DEFAULT '[]',
            key_found   BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (clan_id, week_key)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS clan_abyss_log (
            id      SERIAL PRIMARY KEY,
            clan_id INTEGER NOT NULL,
            user_id BIGINT NOT NULL,
            text    TEXT NOT NULL,
            at      TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    # Еженедельный кап личного взноса в казну (§ABYSS_TREASURY_WEEKLY_CAP)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS clan_abyss_contrib (
            clan_id  INTEGER NOT NULL,
            user_id  BIGINT NOT NULL,
            week_key TEXT NOT NULL,
            shards   FLOAT8 NOT NULL DEFAULT 0,
            PRIMARY KEY (clan_id, user_id, week_key)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS war_nodes (
            id             SERIAL PRIMARY KEY,
            name           TEXT NOT NULL,
            buff_key       TEXT NOT NULL,
            owner_clan_id  INTEGER,
            wall_json      TEXT NOT NULL DEFAULT '[]',
            wall_hp_max    FLOAT8 NOT NULL DEFAULT 0,
            shield_until   TIMESTAMP,
            last_income_at TIMESTAMP
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS clan_wars2 (
            id               SERIAL PRIMARY KEY,
            node_id          INTEGER NOT NULL,
            attacker_clan_id INTEGER NOT NULL,
            defender_clan_id INTEGER,
            status           TEXT NOT NULL DEFAULT 'active',
            damage_total     FLOAT8 NOT NULL DEFAULT 0,
            started_at       TIMESTAMP NOT NULL DEFAULT NOW(),
            ends_at          TIMESTAMP NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS clan_war_attacks (
            id      SERIAL PRIMARY KEY,
            war_id  INTEGER NOT NULL,
            user_id BIGINT NOT NULL,
            damage  FLOAT8 NOT NULL DEFAULT 0,
            at      TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    # Роли 2.0: leader → owner, member → fighter (идемпотентно)
    try:
        await db.execute("UPDATE clan_members SET role = 'owner' WHERE role = 'leader'")
        await db.execute("UPDATE clan_members SET role = 'fighter' WHERE role = 'member'")
    except Exception:
        pass
    # Узлы-сиды (ровно 5, вставляются один раз)
    async with db.execute("SELECT COUNT(*) FROM war_nodes") as c:
        n = int((await c.fetchone())[0] or 0)
    if n == 0:
        for name, buff in (
            ("⛰ Рудник Бездны", "expedition_pct"),
            ("🌋 Огненный Разлом", "dark_mora_pct"),
            ("🏪 Торговый Тракт", "shop_discount_pct"),
            ("🗿 Древний Алтарь", "expedition_pct"),
            ("🌊 Туманная Гавань", "dark_mora_pct"),
        ):
            await db.execute(
                "INSERT INTO war_nodes (name, buff_key) VALUES (?, ?)", (name, buff))
    await db.commit()


async def migrate_clan_coins_to_shards(db, rate: tuple[int, int]) -> int:
    """R3-миграция: 10🎖 → 3💠 ЛИЧНО (в инвентарь). Идемпотентно: сконверченные
    монеты списываются; остаток <10 остаётся. Возвращает число игроков."""
    coins_per, shards_per = rate
    async with db.execute(
        "SELECT user_id, clan_coins FROM clan_members WHERE clan_coins >= ?",
        (coins_per,),
    ) as c:
        rows = [dict(r) for r in await c.fetchall()]
    for r in rows:
        packs = int(float(r["clan_coins"]) // coins_per)
        shards = packs * shards_per
        await db.execute(
            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, 'abyss_shard', ?) "
            "ON CONFLICT (user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
            (r["user_id"], shards, shards),
        )
        await db.execute(
            "UPDATE clan_members SET clan_coins = clan_coins - ? WHERE user_id = ?",
            (packs * coins_per, r["user_id"]),
        )
    if rows:
        await db.commit()
    return len(rows)


# ── Роли / участники ──────────────────────────────────────────────────────────

async def get_member(db, user_id: int) -> dict | None:
    async with db.execute(
        "SELECT cm.user_id, cm.clan_id, cm.role, c.name, c.tag, c.total_xp, "
        "COALESCE(c.treasury_shards,0) AS treasury_shards, "
        "COALESCE(c.treasury_mora,0) AS treasury_mora "
        "FROM clan_members cm JOIN clans c ON c.clan_id = cm.clan_id "
        "WHERE cm.user_id = ?", (user_id,),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def set_role(db, clan_id: int, user_id: int, role: str) -> None:
    await db.execute(
        "UPDATE clan_members SET role = ? WHERE clan_id = ? AND user_id = ?",
        (role, clan_id, user_id))
    await db.commit()


# ── Здания / казна ────────────────────────────────────────────────────────────

async def get_buildings(db, clan_id: int) -> dict[str, int]:
    async with db.execute(
        "SELECT key, level FROM clan_buildings WHERE clan_id = ?", (clan_id,)
    ) as c:
        return {r["key"]: int(r["level"]) for r in await c.fetchall()}


async def building_level(db, clan_id: int, key: str) -> int:
    async with db.execute(
        "SELECT level FROM clan_buildings WHERE clan_id = ? AND key = ?",
        (clan_id, key)) as c:
        row = await c.fetchone()
    return int(row[0]) if row else 0


async def upgrade_building(db, clan_id: int, key: str, cost: float) -> bool:
    """Атомарно: списать 💠 из казны (если хватает) и +1 уровень зданию."""
    async with db.execute(
        "UPDATE clans SET treasury_shards = treasury_shards - ? "
        "WHERE clan_id = ? AND treasury_shards >= ? RETURNING clan_id",
        (cost, clan_id, cost)) as c:
        if not await c.fetchone():
            return False
    await db.execute(
        "INSERT INTO clan_buildings (clan_id, key, level) VALUES (?, ?, 1) "
        "ON CONFLICT (clan_id, key) DO UPDATE SET level = clan_buildings.level + 1",
        (clan_id, key))
    await db.commit()
    return True


async def add_treasury(db, clan_id: int, shards: float = 0, mora: float = 0) -> None:
    await db.execute(
        "UPDATE clans SET treasury_shards = COALESCE(treasury_shards,0) + ?, "
        "treasury_mora = COALESCE(treasury_mora,0) + ? WHERE clan_id = ?",
        (shards, mora, clan_id))


# ── Бездна ────────────────────────────────────────────────────────────────────

async def get_abyss(db, clan_id: int, week_key: str) -> dict | None:
    async with db.execute(
        "SELECT * FROM clan_abyss WHERE clan_id = ? AND week_key = ?",
        (clan_id, week_key)) as c:
        row = await c.fetchone()
    if not row:
        return None
    d = dict(row)
    d["grid"] = json.loads(d["grid_json"])
    d["opened"] = json.loads(d["opened_json"])
    return d


async def create_abyss(db, clan_id: int, week_key: str, floor: int, grid: list) -> None:
    await db.execute(
        "INSERT INTO clan_abyss (clan_id, week_key, floor, grid_json) "
        "VALUES (?, ?, ?, ?) ON CONFLICT (clan_id, week_key) DO NOTHING",
        (clan_id, week_key, floor, json.dumps(grid)))
    await db.commit()


async def save_abyss(db, clan_id: int, week_key: str, opened: list,
                     key_found: bool | None = None) -> None:
    if key_found is None:
        await db.execute(
            "UPDATE clan_abyss SET opened_json = ? WHERE clan_id = ? AND week_key = ?",
            (json.dumps(opened), clan_id, week_key))
    else:
        await db.execute(
            "UPDATE clan_abyss SET opened_json = ?, key_found = ? "
            "WHERE clan_id = ? AND week_key = ?",
            (json.dumps(opened), key_found, clan_id, week_key))


async def replace_abyss_floor(db, clan_id: int, week_key: str, floor: int, grid: list) -> None:
    await db.execute(
        "UPDATE clan_abyss SET floor = ?, grid_json = ?, opened_json = '[]', "
        "key_found = FALSE WHERE clan_id = ? AND week_key = ?",
        (floor, json.dumps(grid), clan_id, week_key))
    await db.commit()


async def abyss_log(db, clan_id: int, user_id: int, text: str) -> None:
    await db.execute(
        "INSERT INTO clan_abyss_log (clan_id, user_id, text) VALUES (?, ?, ?)",
        (clan_id, user_id, text))


async def abyss_log_tail(db, clan_id: int, n: int = 10) -> list[dict]:
    async with db.execute(
        "SELECT l.text, l.at, u.user_tg_username AS username FROM clan_abyss_log l "
        "LEFT JOIN users u ON u.user_tg_id = l.user_id "
        "WHERE l.clan_id = ? ORDER BY l.id DESC LIMIT ?", (clan_id, n)) as c:
        return [dict(r) for r in await c.fetchall()]


async def contrib_this_week(db, clan_id: int, user_id: int, week_key: str) -> float:
    async with db.execute(
        "SELECT shards FROM clan_abyss_contrib WHERE clan_id = ? AND user_id = ? AND week_key = ?",
        (clan_id, user_id, week_key)) as c:
        row = await c.fetchone()
    return float(row[0]) if row else 0.0


async def add_contrib(db, clan_id: int, user_id: int, week_key: str, shards: float) -> None:
    await db.execute(
        "INSERT INTO clan_abyss_contrib (clan_id, user_id, week_key, shards) "
        "VALUES (?, ?, ?, ?) ON CONFLICT (clan_id, user_id, week_key) "
        "DO UPDATE SET shards = clan_abyss_contrib.shards + ?",
        (clan_id, user_id, week_key, shards, shards))


# ── Войны за узлы ─────────────────────────────────────────────────────────────

async def get_nodes(db) -> list[dict]:
    async with db.execute(
        "SELECT n.*, c.name AS owner_name, c.tag AS owner_tag, "
        "CAST(EXTRACT(EPOCH FROM (n.shield_until - NOW())) AS BIGINT) AS shield_left_sec "
        "FROM war_nodes n LEFT JOIN clans c ON c.clan_id = n.owner_clan_id ORDER BY n.id"
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_node(db, node_id: int) -> dict | None:
    async with db.execute("SELECT * FROM war_nodes WHERE id = ?", (node_id,)) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def get_active_war(db, node_id: int | None = None,
                         attacker_clan_id: int | None = None) -> dict | None:
    q = ("SELECT w.*, CAST(EXTRACT(EPOCH FROM (w.ends_at - NOW())) AS BIGINT) AS remaining_sec "
         "FROM clan_wars2 w WHERE w.status = 'active'")
    p: list = []
    if node_id is not None:
        q += " AND w.node_id = ?"; p.append(node_id)
    if attacker_clan_id is not None:
        q += " AND w.attacker_clan_id = ?"; p.append(attacker_clan_id)
    q += " ORDER BY w.id DESC LIMIT 1"
    async with db.execute(q, tuple(p)) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def create_war(db, node_id: int, attacker: int, defender: int | None, hours: int) -> int:
    async with db.execute(
        "INSERT INTO clan_wars2 (node_id, attacker_clan_id, defender_clan_id, ends_at) "
        "VALUES (?, ?, ?, NOW() + (? * INTERVAL '1 hour')) RETURNING id",
        (node_id, attacker, defender, hours)) as c:
        row = await c.fetchone()
    await db.commit()
    return int(row[0])


async def war_attacks_today(db, war_id: int, user_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM clan_war_attacks WHERE war_id = ? AND user_id = ? "
        "AND at >= DATE_TRUNC('day', NOW())", (war_id, user_id)) as c:
        return int((await c.fetchone())[0] or 0)


async def add_war_damage(db, war_id: int, user_id: int, damage: float) -> float:
    """Записать атаку и вернуть суммарный урон войны."""
    await db.execute(
        "INSERT INTO clan_war_attacks (war_id, user_id, damage) VALUES (?, ?, ?)",
        (war_id, user_id, damage))
    async with db.execute(
        "UPDATE clan_wars2 SET damage_total = damage_total + ? WHERE id = ? "
        "RETURNING damage_total", (damage, war_id)) as c:
        row = await c.fetchone()
    return float(row[0])


async def finish_war(db, war_id: int, status: str) -> None:
    await db.execute("UPDATE clan_wars2 SET status = ? WHERE id = ?", (status, war_id))


async def transfer_node(db, node_id: int, new_owner: int, wall_json: str,
                        wall_hp: float, shield_hours: int) -> None:
    await db.execute(
        "UPDATE war_nodes SET owner_clan_id = ?, wall_json = ?, wall_hp_max = ?, "
        "shield_until = NOW() + (? * INTERVAL '1 hour') WHERE id = ?",
        (new_owner, wall_json, wall_hp, shield_hours, node_id))


async def set_wall(db, node_id: int, wall_json: str, wall_hp: float) -> None:
    await db.execute(
        "UPDATE war_nodes SET wall_json = ?, wall_hp_max = ? WHERE id = ?",
        (wall_json, wall_hp, node_id))
    await db.commit()


async def expired_wars(db) -> list[dict]:
    async with db.execute(
        "SELECT * FROM clan_wars2 WHERE status = 'active' AND ends_at <= NOW()") as c:
        return [dict(r) for r in await c.fetchall()]


async def nodes_due_income(db) -> list[dict]:
    async with db.execute(
        "SELECT * FROM war_nodes WHERE owner_clan_id IS NOT NULL "
        "AND (last_income_at IS NULL OR last_income_at <= NOW() - INTERVAL '24 hours')"
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def mark_income(db, node_id: int) -> None:
    await db.execute(
        "UPDATE war_nodes SET last_income_at = NOW() WHERE id = ?", (node_id,))