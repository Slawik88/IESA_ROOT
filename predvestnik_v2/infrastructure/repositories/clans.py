# infrastructure/repositories/clans.py — кланы/гильдии (SQL-слой).
# Один клан на игрока (PK clan_members.user_id). Атомарные операции — через
# db.connection.transaction() + FOR UPDATE (как marriages/economy).
from core.constants import (
    CLAN_CREATE_COST_MORA, CLAN_MAX_MEMBERS,
    CLAN_XP_PER_LEVEL, CLAN_MAX_LEVEL, CLAN_BUILDINGS, CLAN_HQ_SLOTS_PER_LEVEL,
    CLAN_REQUEST_QTY_BASE, CLAN_REQUEST_QTY_PER_LEVEL,
    CLAN_REQUEST_ACTIVE_BASE, CLAN_REQUEST_ACTIVE_PER_3LVL,
    CLAN_REQUEST_COIN_PER_ITEM, CLAN_REQUEST_XP_PER_ITEM,
    CLAN_SHOP,
)

# ── БЛОК19 Ч.5: уровень клана и здания — чистая проекция от total_xp ─────────────
# Здания не хранят состояние: их уровень = уровень клана, эффекты считаются на лету.


def clan_level(total_xp) -> int:
    """Уровень клана из суммарного XP (линейно, с потолком CLAN_MAX_LEVEL)."""
    lvl = 1 + int(max(0, int(total_xp or 0)) // CLAN_XP_PER_LEVEL)
    return min(lvl, CLAN_MAX_LEVEL)


def clan_level_progress(total_xp) -> dict:
    """Прогресс к следующему уровню (для прогресс-бара в UI)."""
    txp = max(0, int(total_xp or 0))
    lvl = clan_level(txp)
    if lvl >= CLAN_MAX_LEVEL:
        return {"level": lvl, "xp_into": 0, "xp_needed": 0, "is_max": True}
    return {"level": lvl, "xp_into": txp - (lvl - 1) * CLAN_XP_PER_LEVEL,
            "xp_needed": CLAN_XP_PER_LEVEL, "is_max": False}


def effective_max_members(total_xp) -> int:
    """Вместимость клана с учётом здания Штаб (+слоты за уровень)."""
    return CLAN_MAX_MEMBERS + (clan_level(total_xp) - 1) * CLAN_HQ_SLOTS_PER_LEVEL


def board_qty_cap(level: int) -> int:
    """Потолок qty в одном запросе Доски (растёт с уровнем здания Доска)."""
    return CLAN_REQUEST_QTY_BASE + (level - 1) * CLAN_REQUEST_QTY_PER_LEVEL


def board_active_cap(level: int) -> int:
    """Сколько активных запросов может держать один участник (уровень Доски)."""
    return CLAN_REQUEST_ACTIVE_BASE + ((level - 1) // 3) * CLAN_REQUEST_ACTIVE_PER_3LVL


def treasury_mult(level: int) -> float:
    """Множитель клановых монет донорам (здание Казна)."""
    return 1.0 + (level - 1) * 0.1


def _building_effect(bid: str, level: int) -> str:
    """Человекочитаемый эффект здания на конкретном уровне (для current и next)."""
    if bid == "hq":
        cap = CLAN_MAX_MEMBERS + (level - 1) * CLAN_HQ_SLOTS_PER_LEVEL
        return f"Вместимость клана: {cap}"
    if bid == "board":
        return f"До {board_active_cap(level)} запросов/чел · до {board_qty_cap(level)} шт в запросе"
    return f"Монеты за помощь: ×{treasury_mult(level):.1f}"


def building_levels(total_xp) -> list[dict]:
    """Здания клана (все на уровне клана): текущий эффект + что даст след. уровень."""
    lvl = clan_level(total_xp)
    out = []
    for bid, emoji, name, desc in CLAN_BUILDINGS:
        item = {"id": bid, "emoji": emoji, "name": name, "desc": desc,
                "level": lvl, "effect": _building_effect(bid, lvl)}
        if lvl < CLAN_MAX_LEVEL:
            item["next_effect"] = _building_effect(bid, lvl + 1)
        out.append(item)
    return out


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
    # Ч.5: клановые монеты у участника + Доска Запросов (зеркало database.py._init_clans).
    await db.execute("ALTER TABLE clan_members ADD COLUMN IF NOT EXISTS clan_coins FLOAT8 DEFAULT 0")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS clan_requests (
            request_id SERIAL PRIMARY KEY,
            clan_id    INTEGER NOT NULL,
            author_id  BIGINT NOT NULL,
            item_id    TEXT NOT NULL,
            qty_need   INTEGER NOT NULL,
            qty_filled INTEGER DEFAULT 0,
            status     TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_clan_requests ON clan_requests(clan_id, status)")


async def get_user_clan(db, user_id: int) -> dict | None:
    """Клан игрока + его роль и клановые монеты (или None)."""
    async with db.execute(
        "SELECT c.clan_id, c.name, c.tag, c.emblem, c.description, c.leader_id, "
        "c.total_xp, c.created_at, m.role, COALESCE(m.clan_coins, 0) AS clan_coins "
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
        "SELECT m.user_id, m.role, m.joined_at, COALESCE(m.clan_coins, 0) AS clan_coins, "
        "u.user_tg_username AS username "
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
                "SELECT name, total_xp FROM clans WHERE clan_id = ? FOR UPDATE", (clan_id,)
            ) as c:
                cl = await c.fetchone()
            if not cl:
                return False, "Клан не найден."
            async with db.execute(
                "SELECT COUNT(*) FROM clan_members WHERE clan_id = ?", (clan_id,)
            ) as c:
                cnt = (await c.fetchone())[0]
            if cnt >= effective_max_members(cl[1]):
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


# ── БЛОК19 Ч.5: Доска Запросов (кооперация без общего склада) ────────────────────


async def list_requests(db, clan_id: int) -> list[dict]:
    """Открытые запросы клана (старые первыми) + ник автора."""
    async with db.execute(
        "SELECT r.request_id, r.author_id, r.item_id, r.qty_need, r.qty_filled, "
        "u.user_tg_username AS author_name "
        "FROM clan_requests r LEFT JOIN users u ON u.user_tg_id = r.author_id "
        "WHERE r.clan_id = ? AND r.status = 'open' ORDER BY r.created_at ASC",
        (clan_id,),
    ) as c:
        return [dict(x) for x in await c.fetchall()]


async def create_request(db, user_id: int, item_id: str, qty: int) -> tuple[bool, str]:
    """Создать запрос на Доске. Лимит активных запросов растёт с уровнем здания Доска."""
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT m.clan_id, c.total_xp FROM clan_members m "
                "JOIN clans c ON c.clan_id = m.clan_id WHERE m.user_id = ?",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return False, "Ты не в клане."
            cid, total_xp = row[0], row[1]
            cap = board_active_cap(clan_level(total_xp))
            async with db.execute(
                "SELECT COUNT(*) FROM clan_requests "
                "WHERE clan_id = ? AND author_id = ? AND status = 'open'",
                (cid, user_id),
            ) as cur:
                cnt = (await cur.fetchone())[0]
            if cnt >= cap:
                return False, f"Лимит активных запросов: {cap}. Закрой старый или прокачай Доску."
            await db.execute(
                "INSERT INTO clan_requests (clan_id, author_id, item_id, qty_need) "
                "VALUES (?, ?, ?, ?)",
                (cid, user_id, item_id, int(qty)),
            )
        return True, "Запрос опубликован на Доске клана."
    except Exception as e:
        return False, f"Ошибка: {e}"


async def fill_request(db, donor_id: int, request_id: int, qty: int) -> tuple[bool, str]:
    """Помочь по запросу: передать предмет автору лично (не в общий склад → анти-твинк).
    Атомарно: списать у донора → выдать автору → клан-монеты донору (× Казна) + XP клану."""
    if qty <= 0:
        return False, "Количество должно быть больше 0."
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT clan_id, author_id, item_id, qty_need, qty_filled, status "
                "FROM clan_requests WHERE request_id = ? FOR UPDATE",
                (request_id,),
            ) as c:
                r = await c.fetchone()
            if not r:
                return False, "Запрос не найден."
            cid, author_id, item_id = r[0], r[1], r[2]
            qty_need, qty_filled, status = int(r[3]), int(r[4]), r[5]
            if status != "open":
                return False, "Запрос уже закрыт."
            async with db.execute(
                "SELECT clan_id FROM clan_members WHERE user_id = ?", (donor_id,)
            ) as c:
                dm = await c.fetchone()
            if not dm or dm[0] != cid:
                return False, "Помогать можно только своему клану."
            if donor_id == author_id:
                return False, "Нельзя выполнять собственный запрос."
            remaining = qty_need - qty_filled
            if remaining <= 0:
                return False, "Запрос уже заполнен."
            # списать у донора под локом строки инвентаря; отдаём сколько реально можем
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? FOR UPDATE",
                (donor_id, item_id),
            ) as c:
                inv = await c.fetchone()
            have = int(inv[0]) if inv else 0
            give = min(int(qty), remaining, have)
            if give <= 0:
                return False, "У тебя нет этого предмета."
            await db.execute(
                "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ?",
                (give, donor_id, item_id),
            )
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0",
                (donor_id, item_id),
            )
            # выдать предмет автору запроса
            await db.execute(
                "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
                (author_id, item_id, give, give),
            )
            new_filled = qty_filled + give
            done = new_filled >= qty_need
            await db.execute(
                "UPDATE clan_requests SET qty_filled = ?, status = ? WHERE request_id = ?",
                (new_filled, "filled" if done else "open", request_id),
            )
            # награды донору: клан-монеты (× Казна) + XP клану
            async with db.execute("SELECT total_xp FROM clans WHERE clan_id = ?", (cid,)) as c:
                txp = (await c.fetchone())[0]
            mult = treasury_mult(clan_level(txp))
            coins = round(give * CLAN_REQUEST_COIN_PER_ITEM * mult, 2)
            xp = give * CLAN_REQUEST_XP_PER_ITEM
            await db.execute(
                "UPDATE clan_members SET clan_coins = COALESCE(clan_coins, 0) + ? WHERE user_id = ?",
                (coins, donor_id),
            )
            await db.execute(
                "UPDATE clans SET total_xp = total_xp + ? WHERE clan_id = ?", (xp, cid),
            )
        head = "✅ Запрос полностью закрыт!" if done else f"Передано {give} шт. Осталось {qty_need - new_filled}."
        return True, f"{head} +{coins:g} 🎖 · +{xp} XP клану."
    except Exception as e:
        return False, f"Ошибка: {e}"


async def cancel_request(db, user_id: int, request_id: int) -> tuple[bool, str]:
    """Снять запрос с Доски (автор или лидер клана)."""
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT author_id, clan_id, status FROM clan_requests WHERE request_id = ? FOR UPDATE",
                (request_id,),
            ) as c:
                r = await c.fetchone()
            if not r:
                return False, "Запрос не найден."
            author_id, cid, status = r[0], r[1], r[2]
            if status != "open":
                return False, "Запрос уже закрыт."
            if user_id != author_id:
                async with db.execute(
                    "SELECT role FROM clan_members WHERE user_id = ? AND clan_id = ?",
                    (user_id, cid),
                ) as c:
                    rr = await c.fetchone()
                if not rr or rr[0] != "leader":
                    return False, "Снять запрос может только автор или лидер."
            await db.execute(
                "UPDATE clan_requests SET status = 'cancelled' WHERE request_id = ?",
                (request_id,),
            )
        return True, "Запрос снят с Доски."
    except Exception as e:
        return False, f"Ошибка: {e}"


async def clan_shop_buy(db, user_id: int, shop_id: str) -> tuple[bool, str]:
    """Купить в Клан-лавке за clan_coins. Атомарно: лок участника → списать монеты → выдать
    эффект. Non-P2W: только Clan XP (прогресс клана) или мягкие расходники."""
    item = next((s for s in CLAN_SHOP if s["id"] == shop_id), None)
    if not item:
        return False, "Товар не найден."
    cost = float(item["cost"])
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT clan_id, COALESCE(clan_coins, 0) FROM clan_members WHERE user_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            if not row:
                return False, "Ты не состоишь в клане."
            clan_id = row[0]
            coins = float(row[1])
            if coins + 1e-9 < cost:
                return False, f"Недостаточно клан-монет: нужно {cost:g} 🎖, у тебя {coins:g} 🎖."
            await db.execute(
                "UPDATE clan_members SET clan_coins = COALESCE(clan_coins, 0) - ? WHERE user_id = ?",
                (cost, user_id),
            )
            if item["kind"] == "clan_xp":
                await db.execute(
                    "UPDATE clans SET total_xp = total_xp + ? WHERE clan_id = ?",
                    (int(item["amount"]), clan_id),
                )
                msg = f"🏛 +{int(item['amount'])} Clan XP клану! (−{cost:g} 🎖)"
            elif item["kind"] == "item":
                iid = item["item"]
                qty = int(item["qty"])
                await db.execute(
                    "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
                    "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
                    (user_id, iid, qty, qty),
                )
                msg = f"{item['emoji']} Куплено: {item['name']} (−{cost:g} 🎖)"
            else:
                return False, "Неизвестный тип товара."
        return True, msg
    except Exception as e:
        return False, f"Ошибка: {e}"
